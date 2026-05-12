"""
Azure Function App - 법령 크롤러 (law.go.kr 웹 스크래핑)
Azure Functions Python v2 프로그래밍 모델

HTTP 트리거: Logic Apps / 수동 POST 호출
  Body (JSON):
    source       : "prec" | "detc" | "expc" | "admrul" | "all"  (기본: "all")
    max_pages    : 크롤링 페이지 수 (기본: 1, 페이지당 최대 100건)
    triggered_by : 호출 출처 (기본: "manual")

처리 흐름:
  law.go.kr 웹 스크래핑 (판례·헌재·법제처·행정심판)
  → Blob Storage raw-documents/{date}/{source}/{seq}.json 저장
  → 결과 JSON 반환

Storage 접근:
  - Managed Identity 기반 (VNet Integration → Storage Private Endpoint)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import azure.functions as func
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from precedent_crawler import (
    LawPrecedentCrawler,
    HunjaeCrawler,
    ExpCrawler,
    AdmRulCrawler,
)

app = func.FunctionApp()

STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
BLOB_CONTAINER_NAME = os.environ.get("AZURE_BLOB_CONTAINER_NAME", "raw-documents")
DEFAULT_MAX_PAGES = int(os.environ.get("CRAWLER_MAX_PAGES", "1"))
CRAWL_RETRY_COUNT = int(os.environ.get("CRAWLER_RETRY_COUNT", "2"))
UPLOAD_RETRY_COUNT = int(os.environ.get("UPLOAD_RETRY_COUNT", "2"))
RETRY_SLEEP_SECONDS = float(os.environ.get("RETRY_SLEEP_SECONDS", "1.0"))

_CRAWLERS = {
    "prec":   (LawPrecedentCrawler, "precSeq"),
    "detc":   (HunjaeCrawler,       "detcSeq"),
    "expc":   (ExpCrawler,          "expcSeq"),
    "admrul": (AdmRulCrawler,       "deccSeq"),
}


@app.function_name(name="crawl")
@app.route(route="crawl", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def crawl_trigger(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Crawl function triggered")
    start = datetime.now(timezone.utc)

    try:
        body = req.get_json()
    except (ValueError, AttributeError):
        body = {}

    source = body.get("source", "all")
    max_pages = int(body.get("max_pages", DEFAULT_MAX_PAGES))
    triggered_by = body.get("triggered_by", "manual")

    targets = list(_CRAWLERS.keys()) if source == "all" else [source]
    if source not in list(_CRAWLERS.keys()) + ["all"]:
        return func.HttpResponse(
            json.dumps({"error": f"Unknown source '{source}'. Use: prec, detc, expc, admrul, all"}),
            status_code=400, mimetype="application/json",
        )

    logging.info(f"Crawl start: source={source}, max_pages={max_pages}, triggered_by={triggered_by}")

    date_folder = start.strftime("%Y-%m-%d")
    total_saved = []
    total_skipped_existing = 0
    total_upload_failed = 0
    retried_sources = {}
    counts = {}

    blob_client = _make_blob_client()

    for target in targets:
        CrawlerClass, _ = _CRAWLERS[target]
        crawler = CrawlerClass()
        docs, crawl_attempts = _crawl_with_retry(
            crawler=crawler,
            source=target,
            max_pages=max_pages,
            retry_count=CRAWL_RETRY_COUNT,
            sleep_seconds=RETRY_SLEEP_SECONDS,
        )

        saved, skipped_existing, upload_failed = _upload_docs(
            blob_client=blob_client,
            docs=docs,
            source=target,
            date_folder=date_folder,
            retry_count=UPLOAD_RETRY_COUNT,
            sleep_seconds=RETRY_SLEEP_SECONDS,
        )
        total_saved.extend(saved)
        total_skipped_existing += skipped_existing
        total_upload_failed += upload_failed
        retried_sources[target] = max(crawl_attempts - 1, 0)
        counts[target] = len(docs)
        logging.info(
            f"[{target}] {len(docs)}건 수집, {len(saved)}건 저장, "
            f"기존ID 스킵 {skipped_existing}건, 업로드 실패 {upload_failed}건"
        )

    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 2)
    result = {
        "status": "success",
        "triggered_by": triggered_by,
        "date_folder": date_folder,
        "counts": counts,
        "total_docs": sum(counts.values()),
        "total_files": len(total_saved),
        "total_skipped_existing": total_skipped_existing,
        "total_upload_failed": total_upload_failed,
        "retried_sources": retried_sources,
        "elapsed_seconds": elapsed,
        "timestamp": start.isoformat(),
    }
    logging.info(f"Crawl complete: {result}")
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        status_code=200, mimetype="application/json",
    )


def _make_blob_client() -> BlobServiceClient | None:
    if not STORAGE_ACCOUNT_NAME:
        logging.warning("AZURE_STORAGE_ACCOUNT_NAME not set — Blob 저장 건너뜀")
        return None
    try:
        credential = ManagedIdentityCredential()
        return BlobServiceClient(
            account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=credential,
        )
    except Exception as e:
        logging.error(f"BlobServiceClient 생성 실패: {e}")
        return None


def _upload_docs(
    blob_client: BlobServiceClient | None,
    docs: list[dict],
    source: str,
    date_folder: str,
    retry_count: int,
    sleep_seconds: float,
) -> tuple[list[str], int, int]:
    """Upload docs with retry and skip documents that already exist in blob."""
    if not blob_client or not docs:
        return [], 0, 0

    container = blob_client.get_container_client(BLOB_CONTAINER_NAME)
    # source-first 경로: {source}/{date}/ → AI Search Datasource prefix 필터 지원
    prefix = f"{source}/{date_folder}/"
    existing = {b.name for b in container.list_blobs(name_starts_with=prefix)}

    saved = []
    skipped_existing = 0
    upload_failed = 0
    settings = ContentSettings(content_type="application/json", content_encoding="utf-8")

    for doc in docs:
        seq = doc.get("seq", doc.get("id", "unknown"))
        blob_name = f"{source}/{date_folder}/{source}_{seq}.json"
        if blob_name in existing:
            skipped_existing += 1
            continue

        last_error = None
        for attempt in range(1, retry_count + 2):
            try:
                container.upload_blob(
                    name=blob_name,
                    data=json.dumps(doc, ensure_ascii=False).encode("utf-8"),
                    overwrite=False,
                    content_settings=settings,
                )
                saved.append(blob_name)
                existing.add(blob_name)
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt <= retry_count:
                    logging.warning(
                        f"Blob 업로드 재시도 {attempt}/{retry_count} ({blob_name}): {e}"
                    )
                    time.sleep(sleep_seconds)

        if last_error is not None:
            upload_failed += 1
            logging.error(f"Blob 업로드 최종 실패 ({blob_name}): {last_error}")

    return saved, skipped_existing, upload_failed


def _crawl_with_retry(
    crawler,
    source: str,
    max_pages: int,
    retry_count: int,
    sleep_seconds: float,
) -> tuple[list[dict], int]:
    """Run crawler with source-level retry. Returns docs and attempts used."""
    last_error = None
    docs: list[dict] = []

    for attempt in range(1, retry_count + 2):
        docs = []
        try:
            for doc in crawler.crawl_all(query="*", max_pages=max_pages):
                docs.append(doc)
            return docs, attempt
        except Exception as e:
            last_error = e
            if attempt <= retry_count:
                logging.warning(
                    f"[{source}] 크롤링 재시도 {attempt}/{retry_count}: {e}"
                )
                time.sleep(sleep_seconds)

    logging.error(f"[{source}] 크롤링 최종 실패: {last_error}")
    return docs, retry_count + 1
