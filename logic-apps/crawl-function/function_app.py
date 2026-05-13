"""
Azure Function App - 법령 크롤러 (law.go.kr 웹 스크래핑)
Azure Functions Python v2 프로그래밍 모델

HTTP 트리거: Logic Apps / 수동 POST 호출
  Body (JSON):
    source         : "prec" | "detc" | "expc" | "admrul" | "all"  (기본: "all")
    max_pages      : 크롤링 페이지 수 (기본: 0 = 무제한, 페이지당 100건)
    detail_workers : 상세 크롤링 병렬 스레드 수 (기본: 5)
    triggered_by   : 호출 출처 (기본: "manual")

처리 흐름:
  1. Blob Storage에서 기존 seq ID 조회 (중복 크롤링 방지)
  2. law.go.kr 웹 스크래핑 (판례·헌재·법제처·행정심판, 4소스 병렬)
  3. 상세 페이지 병렬 수집 (detail_workers 스레드)
  4. Blob Storage raw-documents/{source}/{date}/{seq}.json 저장
  5. 결과 JSON 반환

Storage 접근:
  - Managed Identity 기반 (VNet Integration → Storage Private Endpoint)
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone

import azure.functions as func
from azure.core.exceptions import ResourceExistsError
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from precedent_crawler import (
    LawPrecedentCrawler,
    HunjaeCrawler,
    ExpCrawler,
    AdmRulCrawler,
)

app = func.FunctionApp()

STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
BLOB_CONTAINER_NAME = os.environ.get("AZURE_BLOB_CONTAINER_NAME", "raw-documents")
DEFAULT_MAX_PAGES = int(os.environ.get("CRAWLER_MAX_PAGES", "0"))  # 0 = 무제한
CRAWL_DETAIL_WORKERS = int(os.environ.get("CRAWL_DETAIL_WORKERS", "5"))
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
def crawl(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Crawl function triggered")
    start = datetime.now(timezone.utc)

    try:
        body = req.get_json()
    except (ValueError, AttributeError):
        body = {}

    source = req.params.get("source") or body.get("source", "all")
    triggered_by = req.params.get("triggered_by") or body.get("triggered_by", "manual")

    raw_max_pages = req.params.get("max_pages") or body.get("max_pages", DEFAULT_MAX_PAGES)
    try:
        max_pages = int(raw_max_pages)
    except (TypeError, ValueError):
        max_pages = DEFAULT_MAX_PAGES

    targets = list(_CRAWLERS.keys()) if source == "all" else [source]
    if source not in list(_CRAWLERS.keys()) + ["all"]:
        return func.HttpResponse(
            json.dumps({"error": f"Unknown source '{source}'. Use: prec, detc, expc, admrul, all"}),
            status_code=400, mimetype="application/json",
        )

    max_pages_val = max_pages if max_pages > 0 else None
    raw_detail_workers = req.params.get("detail_workers") or body.get("detail_workers", CRAWL_DETAIL_WORKERS)
    try:
        detail_workers = int(raw_detail_workers)
    except (TypeError, ValueError):
        detail_workers = CRAWL_DETAIL_WORKERS

    logging.info(
        f"Crawl start: source={source}, max_pages={max_pages_val}, "
        f"detail_workers={detail_workers}, triggered_by={triggered_by}"
    )

    date_folder = start.strftime("%Y-%m-%d")
    total_saved = []
    total_skipped_existing = 0
    total_upload_failed = 0
    total_pre_existing = 0
    retried_sources = {}
    counts = {}
    crawl_logs = {}

    blob_client = _make_blob_client()

    # 모든 소스를 병렬 처리 (소스별 1스레드)
    with ThreadPoolExecutor(max_workers=len(targets)) as executor:
        future_map = {
            executor.submit(
                _process_source, target, blob_client,
                date_folder, max_pages_val, detail_workers,
            ): target
            for target in targets
        }
        for future in as_completed(future_map):
            target = future_map[future]
            try:
                res = future.result()
                total_saved.extend(res["saved"])
                total_skipped_existing += res["skipped_existing"]
                total_upload_failed += res["upload_failed"]
                total_pre_existing += res["pre_existing"]
                retried_sources[target] = max(res["crawl_attempts"] - 1, 0)
                counts[target] = res["doc_count"]
                crawl_logs[target] = res.get("crawl_log_path")
            except Exception as e:
                logging.error(f"[{target}] 처리 실패: {e}")
                counts[target] = 0
                crawl_logs[target] = None

    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 2)
    result = {
        "status": "success",
        "triggered_by": triggered_by,
        "date_folder": date_folder,
        "counts": counts,
        "total_docs": sum(counts.values()),
        "total_files": len(total_saved),
        "total_pre_existing": total_pre_existing,
        "total_skipped_existing": total_skipped_existing,
        "total_upload_failed": total_upload_failed,
        "retried_sources": retried_sources,
        "crawl_logs": crawl_logs,
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


def _get_existing_seqs(blob_client: BlobServiceClient | None, source: str) -> set[str]:
    """Blob Storage에서 이미 크롤링된 seq ID 목록 (모든 날짜 폴더 통합)"""
    if not blob_client:
        return set()
    try:
        container = blob_client.get_container_client(BLOB_CONTAINER_NAME)
        seqs = set()
        for blob in container.list_blobs(name_starts_with=f"{source}/"):
            filename = blob.name.rsplit("/", 1)[-1]
            if filename.startswith(f"{source}_") and filename.endswith(".json"):
                seqs.add(filename[len(f"{source}_"):-5])
        logging.info(f"[{source}] 기존 blob {len(seqs)}건 발견 → 크롤링 제외")
        return seqs
    except Exception as e:
        logging.warning(f"[{source}] 기존 blob 조회 실패: {e}")
        return set()


def _process_source(
    target: str,
    blob_client: BlobServiceClient | None,
    date_folder: str,
    max_pages: int | None,
    detail_workers: int,
) -> dict:
    """단일 소스 처리: 기존 blob 조회 → 건별 크롤링+즉시 업로드 (스트리밍)"""
    CrawlerClass, _ = _CRAWLERS[target]
    crawler = CrawlerClass()

    existing_seqs = _get_existing_seqs(blob_client, target)

    # Blob 컨테이너·설정 준비 (건별 업로드용)
    container = None
    settings = ContentSettings(content_type="application/json", content_encoding="utf-8")
    if blob_client:
        container = blob_client.get_container_client(BLOB_CONTAINER_NAME)

    saved = []
    upload_failed = 0
    doc_count = 0
    skipped_existing = 0
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    crawl_log_path = None

    state_lock = Lock()
    log_lock = Lock()
    log_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".jsonl", delete=False)

    def _write_log(entry: dict) -> None:
        with log_lock:
            log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _on_doc(doc: dict) -> None:
        """상세 페이지 1건 크롤링 완료 시 즉시 Blob 업로드"""
        nonlocal upload_failed, doc_count, skipped_existing
        with state_lock:
            doc_count += 1

        if not container:
            return

        seq = doc.get("seq", doc.get("id", "unknown"))
        blob_name = f"{target}/{date_folder}/{target}_{seq}.json"

        last_error = None
        for attempt in range(1, UPLOAD_RETRY_COUNT + 2):
            try:
                container.upload_blob(
                    name=blob_name,
                    data=json.dumps(doc, ensure_ascii=False).encode("utf-8"),
                    overwrite=False,
                    content_settings=settings,
                )
                with state_lock:
                    saved.append(blob_name)
                _write_log({"seq": str(seq), "blob": blob_name, "status": "uploaded"})
                last_error = None
                break
            except ResourceExistsError:
                with state_lock:
                    skipped_existing += 1
                _write_log({"seq": str(seq), "blob": blob_name, "status": "skipped_existing"})
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt <= UPLOAD_RETRY_COUNT:
                    time.sleep(RETRY_SLEEP_SECONDS)

        if last_error is not None:
            with state_lock:
                upload_failed += 1
            _write_log(
                {
                    "seq": str(seq),
                    "blob": blob_name,
                    "status": "failed",
                    "error": str(last_error),
                }
            )
            logging.error(f"Blob 업로드 실패 ({blob_name}): {last_error}")

    # 크롤링 실행 — 건별 콜백으로 즉시 업로드
    crawl_attempts = 1
    try:
        crawler.crawl_all(
            query="*", max_pages=max_pages,
            skip_seqs=existing_seqs, max_workers=detail_workers,
            on_doc=_on_doc,
        )
    except Exception as e:
        logging.error(f"[{target}] 크롤링 실패: {e}")

    if container:
        log_file.close()
        crawl_log_path = f"_logs/{date_folder}/{target}/{run_id}.jsonl"
        try:
            with open(log_file.name, "rb") as f:
                container.upload_blob(
                    name=crawl_log_path,
                    data=f,
                    overwrite=False,
                    content_settings=ContentSettings(content_type="application/json"),
                )
        except Exception as e:
            logging.warning(f"[{target}] crawl log 업로드 실패: {e}")
            crawl_log_path = None
        finally:
            try:
                os.unlink(log_file.name)
            except OSError:
                pass
    else:
        log_file.close()
        try:
            os.unlink(log_file.name)
        except OSError:
            pass

    logging.info(
        f"[{target}] {doc_count}건 수집, {len(saved)}건 저장, "
        f"기존blob {len(existing_seqs)}건 제외, "
        f"업로드중복 {skipped_existing}건, 업로드실패 {upload_failed}건"
    )

    return {
        "saved": saved,
        "skipped_existing": skipped_existing,
        "upload_failed": upload_failed,
        "crawl_attempts": crawl_attempts,
        "doc_count": doc_count,
        "pre_existing": len(existing_seqs),
        "crawl_log_path": crawl_log_path,
    }



