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
import urllib.request
import urllib.error
from datetime import datetime, timezone

import azure.functions as func
import azure.durable_functions as df
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

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
BLOB_CONTAINER_NAME = os.environ.get("AZURE_BLOB_CONTAINER_NAME", "raw-documents")
DEFAULT_MAX_PAGES = int(os.environ.get("CRAWLER_MAX_PAGES", "0"))  # 0 = 무제한
CRAWL_DETAIL_WORKERS = int(os.environ.get("CRAWL_DETAIL_WORKERS", "5"))
CRAWL_RETRY_COUNT = int(os.environ.get("CRAWLER_RETRY_COUNT", "2"))
UPLOAD_RETRY_COUNT = int(os.environ.get("UPLOAD_RETRY_COUNT", "2"))
RETRY_SLEEP_SECONDS = float(os.environ.get("RETRY_SLEEP_SECONDS", "1.0"))
PREPROCESS_FUNCTION_URI = os.environ.get("PREPROCESS_FUNCTION_URI", "")
PREPROCESS_TIMEOUT_SECONDS = int(os.environ.get("PREPROCESS_TIMEOUT_SECONDS", "3600"))
PREPROCESS_RETRY_COUNT = int(os.environ.get("PREPROCESS_RETRY_COUNT", "3"))  # 총 시도 횟수 (1=재시도 안 함)
PREPROCESS_RETRY_BACKOFF_SECONDS = float(os.environ.get("PREPROCESS_RETRY_BACKOFF_SECONDS", "10.0"))
# crawl Function 은 Consumption plan 의 230s gateway timeout 한계가 있어,
# preprocess 완료까지 동기 대기하면 504 GatewayTimeout 으로 응답이 잘림.
# 따라서 preprocess HTTP 호출을 짧은 wait 후 "dispatched" 로 종료하고,
# preprocess Function 은 자기 플랜에서 백그라운드로 계속 실행됨.
PREPROCESS_DISPATCH_WAIT_SECONDS = int(os.environ.get("PREPROCESS_DISPATCH_WAIT_SECONDS", "30"))

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

    # 크롤 완료 후 preprocess Function 호출 (각 소스 병렬, 재시도 포함)
    preprocess_results = _invoke_preprocess(targets, date_folder, triggered_by)

    # preprocess 단일 소스라도 실패하면 전체 응답 status 도 partial 로 표시
    preprocess_failed = [
        src for src, r in preprocess_results.items()
        if isinstance(r, dict) and r.get("status") not in ("success", "dispatched")
    ] if isinstance(preprocess_results, dict) else []
    overall_status = "success" if not preprocess_failed else "partial_preprocess_failed"

    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 2)
    result = {
        "status": overall_status,
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
        "preprocess": preprocess_results,
        "preprocess_failed_sources": preprocess_failed,
        "elapsed_seconds": elapsed,
        "timestamp": start.isoformat(),
    }
    logging.info(f"Crawl complete: status={overall_status} preprocess_failed={preprocess_failed}")
    # preprocess 가 모두 성공했을 때만 200, 부분 실패시 207 (Multi-Status) 로 호출자가 인지하도록 함
    http_status = 200 if not preprocess_failed else 207
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        status_code=http_status, mimetype="application/json",
    )


def _invoke_preprocess(targets: list[str], date_folder: str, triggered_by: str) -> dict:
    """크롤 완료 후 preprocess Function을 소스별로 병렬 호출 (Logic App 타임아웃과 무관)"""
    if not PREPROCESS_FUNCTION_URI:
        logging.warning("PREPROCESS_FUNCTION_URI 미설정 — preprocess 호출 건너뜀")
        return {"status": "skipped", "reason": "PREPROCESS_FUNCTION_URI not set"}

    logging.info(f"Preprocess 호출 시작: sources={targets} date={date_folder}")

    def _call(src: str) -> dict:
        body = json.dumps({
            "source": src,
            "crawl_date": date_folder,
            "triggered_by": f"crawl-function-after:{triggered_by}",
        }).encode("utf-8")

        last_error: dict | None = None
        for attempt in range(1, PREPROCESS_RETRY_COUNT + 1):
            req = urllib.request.Request(
                PREPROCESS_FUNCTION_URI,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            t0 = time.time()
            try:
                # 짧은 timeout 으로 preprocess 호출만 dispatch — 응답 본문은 기다리지 않음.
                # preprocess Function 은 자기 플랜의 functionTimeout 까지 백그라운드로 실행됨.
                with urllib.request.urlopen(req, timeout=PREPROCESS_DISPATCH_WAIT_SECONDS) as resp:
                    payload = resp.read().decode("utf-8", errors="replace")
                    try:
                        parsed = json.loads(payload)
                    except json.JSONDecodeError:
                        parsed = {"raw": payload[:500]}
                    return {
                        "source": src,
                        "status": "success",
                        "http_status": resp.status,
                        "attempts": attempt,
                        "elapsed_seconds": round(time.time() - t0, 2),
                        "response": parsed,
                    }
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")[:500]
                last_error = {
                    "source": src,
                    "status": "http_error",
                    "http_status": e.code,
                    "attempts": attempt,
                    "elapsed_seconds": round(time.time() - t0, 2),
                    "error": err_body,
                }
                # 4xx (응답이 명시적 client error) 는 재시도해도 의미 없음 → 즉시 종료
                if 400 <= e.code < 500:
                    logging.error(f"[preprocess:{src}] HTTP {e.code} (4xx, no retry): {err_body[:200]}")
                    return last_error
                logging.warning(f"[preprocess:{src}] HTTP {e.code} attempt {attempt}/{PREPROCESS_RETRY_COUNT}: {err_body[:200]}")
            except (TimeoutError, urllib.error.URLError) as e:
                # TimeoutError / URLError(socket timeout) = 응답 대기 시간 초과.
                # preprocess Function 은 이미 받았고 백그라운드 실행 중 → "dispatched" 로 처리.
                elapsed = time.time() - t0
                # 정말 connect 자체가 실패한 경우와 구분하기 위해, dispatch wait 의 80% 이상 흘렀으면 dispatched 로 간주.
                if elapsed >= PREPROCESS_DISPATCH_WAIT_SECONDS * 0.8:
                    logging.info(
                        f"[preprocess:{src}] dispatched (no wait for response): elapsed={elapsed:.1f}s "
                        f"(preprocess Function 은 백그라운드로 계속 실행됨)"
                    )
                    return {
                        "source": src,
                        "status": "dispatched",
                        "attempts": attempt,
                        "elapsed_seconds": round(elapsed, 2),
                        "note": "fire-and-forget: preprocess running in background; check processed-documents/{src}/{date}/ later",
                    }
                # 빠른 실패는 진짜 네트워크 에러 → 재시도
                last_error = {
                    "source": src,
                    "status": "error",
                    "attempts": attempt,
                    "elapsed_seconds": round(elapsed, 2),
                    "error": f"{type(e).__name__}: {e}",
                }
                logging.warning(f"[preprocess:{src}] {type(e).__name__} attempt {attempt}/{PREPROCESS_RETRY_COUNT}: {e}")
            except Exception as e:
                last_error = {
                    "source": src,
                    "status": "error",
                    "attempts": attempt,
                    "elapsed_seconds": round(time.time() - t0, 2),
                    "error": str(e),
                }
                logging.warning(f"[preprocess:{src}] error attempt {attempt}/{PREPROCESS_RETRY_COUNT}: {e}")

            if attempt < PREPROCESS_RETRY_COUNT:
                # exponential backoff: 10s, 20s, 40s ...
                sleep_s = PREPROCESS_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logging.info(f"[preprocess:{src}] retry in {sleep_s:.0f}s ...")
                time.sleep(sleep_s)

        logging.error(f"[preprocess:{src}] 모든 재시도 실패 ({PREPROCESS_RETRY_COUNT}회): {last_error}")
        return last_error or {"source": src, "status": "error", "error": "unknown"}

    results = {}
    with ThreadPoolExecutor(max_workers=max(len(targets), 1)) as ex:
        futures = {ex.submit(_call, src): src for src in targets}
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                results[src] = fut.result()
            except Exception as e:
                results[src] = {"source": src, "status": "error", "error": str(e)}
            logging.info(f"[preprocess:{src}] {results[src].get('status')} elapsed={results[src].get('elapsed_seconds')}s")

    return results


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
    """Blob Storage에서 이미 크롤링된 seq ID 목록 (모든 날짜 폴더 통합).

    IMPORTANT: list_blobs 가 실패하면 절대 빈 set 을 반환하지 말고 예외를 그대로 raise 한다.
    빈 set 을 반환하면 후속 크롤이 "기존 blob 없음" 으로 판단하여 cross-date 중복을
    생성한다 (과거 admrul:92 / expc:282 중복의 근본 원인). 호출자가 retry/abort 를 결정해야 한다.
    """
    if not blob_client:
        # 의도적으로 blob_client 가 없는 경우만 빈 set 허용 (로컬 dry-run 등)
        return set()
    container = blob_client.get_container_client(BLOB_CONTAINER_NAME)
    seqs = set()
    for blob in container.list_blobs(name_starts_with=f"{source}/"):
        filename = blob.name.rsplit("/", 1)[-1]
        if filename.startswith(f"{source}_") and filename.endswith(".json"):
            seqs.add(filename[len(f"{source}_"):-5])
    logging.info(f"[{source}] 기존 blob {len(seqs)}건 발견 → 크롤링 제외")
    return seqs


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
        seq_key = str(seq)
        # cross-date 중복 방어: 이미 다른 날짜에 있다면 skip (existing_seqs 는 함수 시작 시 캡처)
        if seq_key in existing_seqs:
            with state_lock:
                skipped_existing += 1
            _write_log({"seq": seq_key, "status": "skipped_cross_date_existing"})
            return
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


# =============================================================================
# Helpers for Method B (Consumption + Durable + Activity 분할)
#   - 목록 수집 활동 (activity_list_seqs)와 상세 배치 활동 (activity_crawl_detail_batch)
#     으로 분리하여 각 Activity가 Consumption Plan 10분 한도 내에서 끝나도록 함.
# =============================================================================

# Consumption Plan에서 단일 Activity 실행 시간 한도(약 10분)를 고려한 배치 크기.
# 50건 × (HTTP detail ~0.3s + delay) × 5 workers ≈ 30s/배치 (충분히 여유).
DETAIL_BATCH_SIZE = int(os.environ.get("CRAWLER_DETAIL_BATCH_SIZE", "50"))

# 목록(list) Activity 한 개당 처리할 페이지 수.
# 한 페이지 ~100 items, fetch ~2-3s/page → 30 pages ≈ 1-2분
LIST_PAGE_CHUNK = int(os.environ.get("CRAWLER_LIST_PAGE_CHUNK", "30"))
# 한 소스에서 list activity 의 최대 wave 수 (하한: 1)
# 0 또는 음수면 max_pages 제한이 있을 때만 사용 (max_pages=0 이면 무제한)
LIST_MAX_WAVES = int(os.environ.get("CRAWLER_LIST_MAX_WAVES", "20"))


def _list_seqs_to_fetch(source: str, start_page: int = 1, page_count: int | None = None) -> dict:
    """
    목록만 순회하여 (기존 blob 제외, 목록 중복 제거 후) 가져올 seq 리스트를 반환.
    상세 페이지는 가져오지 않음.

    페이지 범위가 주어지면 (start_page ~ start_page+page_count-1) 만 순회.
    메소드 당 10분 제한 내 끝내기 위한 chunking.
    """
    if source not in _CRAWLERS:
        raise ValueError(f"unknown source {source}")
    CrawlerClass, _ = _CRAWLERS[source]
    crawler = CrawlerClass()

    blob_client = _make_blob_client()
    existing = _get_existing_seqs(blob_client, source)

    seqs: list[str] = []
    seen: set[str] = set()
    skipped_existing_listing = 0
    skipped_dup = 0
    items_seen = 0

    for item in crawler.iter_list(query="*", start_page=start_page, max_pages=page_count):
        items_seen += 1
        seq = item[crawler.SEQ_FIELD]
        if seq in existing:
            skipped_existing_listing += 1
            continue
        if seq in seen:
            skipped_dup += 1
            continue
        seen.add(seq)
        seqs.append(str(seq))

    return {
        "source": source,
        "start_page": start_page,
        "page_count": page_count,
        "items_seen": items_seen,
        "seqs": seqs,
        "pre_existing": len(existing),
        "skipped_existing_listing": skipped_existing_listing,
        "skipped_duplicate": skipped_dup,
    }


def _fetch_and_upload_batch(
    source: str,
    seqs: list[str],
    date_folder: str,
    detail_workers: int,
) -> dict:
    """
    seq 배치를 받아 상세 페이지 수집 + Blob 업로드까지 수행.
    Activity 단위로 호출되며 Consumption 10분 한도 내에서 끝나는 크기여야 함.
    """
    if source not in _CRAWLERS:
        return {"source": source, "status": "error", "error": f"unknown source {source}", "seqs_in": len(seqs)}

    CrawlerClass, _ = _CRAWLERS[source]
    crawler = CrawlerClass()
    blob_client = _make_blob_client()
    container = blob_client.get_container_client(BLOB_CONTAINER_NAME) if blob_client else None
    settings = ContentSettings(content_type="application/json", content_encoding="utf-8")

    # 업로드 직전 cross-date 중복 방어선:
    # list activity 와 detail activity 사이에 시간 간격이 있고 (다른 orchestrator 인스턴스가
    # 동시 실행 중이거나 retry 가 발생할 수 있으므로) 업로드 시점에 다시 한 번 모든 날짜
    # 폴더에서 동일 seq 가 존재하는지 확인한다. 이미 존재하면 다른 date_folder 라 하더라도
    # skip 하여 cross-date 중복을 막는다.
    existing_at_upload = _get_existing_seqs(blob_client, source)

    saved: list[str] = []
    skipped_existing = 0
    upload_failed = 0
    fetch_failed = 0
    state_lock = Lock()
    log_entries: list[dict] = []
    log_lock = Lock()

    def _upload_doc(doc: dict) -> None:
        nonlocal upload_failed, skipped_existing
        if not container:
            return
        seq = doc.get("seq", doc.get("id", "unknown"))
        seq_key = str(seq)
        # cross-date 중복 방어: 이미 다른 날짜 폴더에 있으면 skip
        if seq_key in existing_at_upload:
            with state_lock:
                skipped_existing += 1
            with log_lock:
                log_entries.append({"seq": seq_key, "status": "skipped_cross_date_existing"})
            return
        blob_name = f"{source}/{date_folder}/{source}_{seq}.json"
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
                with log_lock:
                    log_entries.append({"seq": str(seq), "blob": blob_name, "status": "uploaded"})
                last_error = None
                break
            except ResourceExistsError:
                with state_lock:
                    skipped_existing += 1
                with log_lock:
                    log_entries.append({"seq": str(seq), "blob": blob_name, "status": "skipped_existing"})
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt <= UPLOAD_RETRY_COUNT:
                    time.sleep(RETRY_SLEEP_SECONDS)
        if last_error is not None:
            with state_lock:
                upload_failed += 1
            with log_lock:
                log_entries.append({"seq": str(seq), "blob": blob_name, "status": "failed", "error": str(last_error)})
            logging.error(f"Blob 업로드 실패 ({blob_name}): {last_error}")

    def _fetch_one(seq: str) -> None:
        nonlocal fetch_failed
        doc = crawler.get_detail(seq)
        if doc:
            _upload_doc(doc)
        else:
            with state_lock:
                fetch_failed += 1
            with log_lock:
                log_entries.append({"seq": str(seq), "status": "fetch_failed"})

    workers = max(1, int(detail_workers))
    if workers <= 1:
        for s in seqs:
            _fetch_one(s)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_fetch_one, s) for s in seqs]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logging.warning(f"[{source}] batch fetch 예외: {e}")

    # 배치별 로그를 blob에 저장(소량) → orchestrator가 collect할 필요 없음
    log_blob = None
    if container and log_entries:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        log_blob = f"_logs/{date_folder}/{source}/batch-{run_id}.jsonl"
        try:
            container.upload_blob(
                name=log_blob,
                data=("\n".join(json.dumps(e, ensure_ascii=False) for e in log_entries)).encode("utf-8"),
                overwrite=False,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except Exception as e:
            logging.warning(f"[{source}] batch log 업로드 실패: {e}")
            log_blob = None

    return {
        "source": source,
        "status": "success",
        "seqs_in": len(seqs),
        "saved": len(saved),
        "skipped_existing": skipped_existing,
        "upload_failed": upload_failed,
        "fetch_failed": fetch_failed,
        "log_blob": log_blob,
    }


# =============================================================================
# Durable Functions: HTTP Starter → Orchestrator → Activities (fan-out / fan-in)
#
# 사용:
#   POST /api/orchestrators/crawl_preprocess
#     Body: { "source": "all"|"prec"|..., "max_pages": 0, "detail_workers": 5,
#             "triggered_by": "...", "skip_preprocess": false }
#   응답: 202 Accepted + statusQueryGetUri
#   상태 폴링: GET <statusQueryGetUri>
#
# 흐름 (Method B — Consumption Plan 호환):
#   1) Top orchestrator: 소스별 sub-orchestrator 병렬 호출 (fan-out)
#   2) Sub-orchestrator (소스 1개):
#        a) activity_list_seqs : 목록만 수집 (가져올 seq 리스트)
#        b) seq를 N개씩 배치 분할 → activity_crawl_detail_batch 병렬 fan-out
#           (각 배치는 Consumption 10분 한도 내에서 종료)
#        c) 결과 합산 → activity_preprocess_source 호출
#   3) Top orchestrator: 모든 source 합산 → 최종 요약 반환
# =============================================================================


@app.route(route="orchestrators/crawl_preprocess", methods=["POST", "GET"])
@app.durable_client_input(client_name="client")
async def http_start_crawl_preprocess(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    try:
        body = req.get_json()
    except (ValueError, AttributeError):
        body = {}
    payload = {
        "source": req.params.get("source") or body.get("source", "all"),
        "max_pages": int(req.params.get("max_pages") or body.get("max_pages", DEFAULT_MAX_PAGES)),
        "detail_workers": int(req.params.get("detail_workers") or body.get("detail_workers", CRAWL_DETAIL_WORKERS)),
        "triggered_by": req.params.get("triggered_by") or body.get("triggered_by", "manual"),
        "skip_preprocess": bool(body.get("skip_preprocess", False)),
        "crawl_date": req.params.get("crawl_date") or body.get("crawl_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    instance_id = await client.start_new("crawl_preprocess_orchestrator", None, payload)
    logging.info(f"Started orchestration {instance_id} payload={payload}")
    return client.create_check_status_response(req, instance_id)


@app.orchestration_trigger(context_name="context")
def crawl_preprocess_orchestrator(context: df.DurableOrchestrationContext):
    """
    Method B (flat orchestrator):
      1) 모든 source 에 대해 activity_list_seqs 병렬 실행
      2) 모든 source × 모든 batch 에 대해 activity_crawl_detail_batch 병렬 실행
      3) 모든 source 에 대해 activity_preprocess_source 병렬 실행

    각 activity 는 Consumption 10분 한도 내에서 끝나도록 분할.
    sub-orchestrator 를 사용하지 않아 Python v2 DFApp 호환 이슈를 회피.
    """
    payload = context.get_input() or {}
    source = payload.get("source", "all")
    crawl_date = payload.get("crawl_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    targets = list(_CRAWLERS.keys()) if source == "all" else [source]
    max_pages = payload.get("max_pages", DEFAULT_MAX_PAGES)
    detail_workers = payload.get("detail_workers", CRAWL_DETAIL_WORKERS)
    skip_preprocess = bool(payload.get("skip_preprocess", False))
    triggered_by = payload.get("triggered_by", "manual")
    max_pages_val = max_pages if max_pages and max_pages > 0 else None

    if not context.is_replaying:
        logging.info(f"[orch:{context.instance_id}] start sources={targets} date={crawl_date}")

    # ─── Step 1: List (parallel page-range chunks across sources) ───
    # max_pages = 0 → 무제한 (LIST_MAX_WAVES * LIST_PAGE_CHUNK 만큼 wave 으로 fan-out)
    # max_pages > 0 → ceil(max_pages / LIST_PAGE_CHUNK) 만큼 fan-out
    chunk = LIST_PAGE_CHUNK
    if max_pages_val and max_pages_val > 0:
        waves_per_source = max(1, (max_pages_val + chunk - 1) // chunk)
    else:
        waves_per_source = max(1, LIST_MAX_WAVES)

    list_tasks = []
    list_owners = []  # (source_index, wave_index)
    for i, s in enumerate(targets):
        for w in range(waves_per_source):
            start_page = 1 + w * chunk
            # 마지막 wave 는 max_pages 에 맞춰 잘라냄
            if max_pages_val and max_pages_val > 0:
                remaining = max_pages_val - w * chunk
                if remaining <= 0:
                    break
                this_count = min(chunk, remaining)
            else:
                this_count = chunk
            list_tasks.append(context.call_activity("activity_list_seqs", {
                "source": s,
                "start_page": start_page,
                "page_count": this_count,
            }))
            list_owners.append((i, w))

    list_chunk_results = (yield context.task_all(list_tasks)) if list_tasks else []

    # source 별 결과 병합 (chunk 결과 합치기 + 중복 제거)
    list_results = []
    for i, s in enumerate(targets):
        merged_seqs: list[str] = []
        seen = set()
        pre_existing = 0
        skipped_listing = 0
        skipped_dup = 0
        items_seen = 0
        had_error = False
        chunk_ok = 0
        for k, owner in enumerate(list_owners):
            if owner[0] != i:
                continue
            cr = list_chunk_results[k] or {}
            if cr.get("status") == "error":
                had_error = True
                continue
            chunk_ok += 1
            pre_existing = max(pre_existing, cr.get("pre_existing", 0))
            skipped_listing += cr.get("skipped_existing_listing", 0)
            skipped_dup += cr.get("skipped_duplicate", 0)
            items_seen += cr.get("items_seen", 0)
            for seq in cr.get("seqs", []):
                if seq in seen:
                    continue
                seen.add(seq)
                merged_seqs.append(seq)
        list_results.append({
            "source": s,
            "seqs": merged_seqs,
            "pre_existing": pre_existing,
            "skipped_existing_listing": skipped_listing,
            "skipped_duplicate": skipped_dup,
            "items_seen": items_seen,
            "list_chunks": chunk_ok,
            "status": "error" if had_error and chunk_ok == 0 else "success",
        })

    # ─── Step 2: Detail batches (parallel across all sources × batches) ───
    batch_size = DETAIL_BATCH_SIZE
    detail_tasks = []
    detail_owners = []  # 각 task 가 어느 source 에 속하는지 (index)
    for i, s in enumerate(targets):
        lr = list_results[i]
        if isinstance(lr, dict) and lr.get("status") == "error":
            continue
        seqs = (lr or {}).get("seqs", [])
        for j in range(0, len(seqs), batch_size):
            batch = seqs[j:j + batch_size]
            detail_tasks.append(context.call_activity("activity_crawl_detail_batch", {
                "source": s,
                "seqs": batch,
                "crawl_date": crawl_date,
                "detail_workers": detail_workers,
            }))
            detail_owners.append(i)

    detail_results = (yield context.task_all(detail_tasks)) if detail_tasks else []

    # ─── 집계 (per-source) ───
    per_source = {}
    for i, s in enumerate(targets):
        lr = list_results[i] or {}
        per_source[s] = {
            "saved": 0, "upload_failed": 0, "fetch_failed": 0, "skipped_existing": 0,
            "batches": 0, "batch_logs": [],
            "pre_existing": lr.get("pre_existing", 0),
            "skipped_existing_listing": lr.get("skipped_existing_listing", 0),
            "skipped_duplicate": lr.get("skipped_duplicate", 0),
            "list_status": lr.get("status", "unknown"),
        }

    for k, br in enumerate(detail_results):
        s = targets[detail_owners[k]]
        b = br or {}
        per_source[s]["saved"] += b.get("saved", 0)
        per_source[s]["upload_failed"] += b.get("upload_failed", 0)
        per_source[s]["fetch_failed"] += b.get("fetch_failed", 0)
        per_source[s]["skipped_existing"] += b.get("skipped_existing", 0)
        per_source[s]["batches"] += 1
        if b.get("log_blob"):
            per_source[s]["batch_logs"].append(b.get("log_blob"))

    crawl_summary = {
        s: {
            "source": s,
            "status": "success" if per_source[s]["list_status"] != "error" else "error",
            "doc_count": per_source[s]["saved"] + per_source[s]["skipped_existing"],
            "saved_files": per_source[s]["saved"],
            "skipped_existing": per_source[s]["skipped_existing"],
            "upload_failed": per_source[s]["upload_failed"],
            "fetch_failed": per_source[s]["fetch_failed"],
            "pre_existing": per_source[s]["pre_existing"],
            "skipped_existing_listing": per_source[s]["skipped_existing_listing"],
            "skipped_duplicate": per_source[s]["skipped_duplicate"],
            "total_batches": per_source[s]["batches"],
            "batch_size": batch_size,
            "batch_logs": per_source[s]["batch_logs"],
        }
        for s in targets
    }

    if not context.is_replaying:
        logging.info(f"[orch:{context.instance_id}] crawl done: {crawl_summary}")

    # ─── Step 3: Preprocess (parallel across sources) ───
    # 항상 모든 날짜를 재처리("all")해 raw-documents 전체와 processed-documents 가 일치하도록 보장.
    # (특정 날짜 단일 처리는 cross-date 중복/누락을 야기하므로 사용하지 않음)
    preprocess_summary = None
    if not skip_preprocess:
        pre_tasks = [
            context.call_activity("activity_preprocess_source", {
                "source": s,
                "crawl_date": "all",
                "triggered_by": f"durable:{triggered_by}",
            })
            for s in targets
        ]
        pre_results = yield context.task_all(pre_tasks)
        preprocess_summary = {targets[i]: pre_results[i] for i in range(len(targets))}

    return {
        "status": "completed",
        "crawl_date": crawl_date,
        "triggered_by": triggered_by,
        "crawl": crawl_summary,
        "preprocess": preprocess_summary,
    }


@app.activity_trigger(input_name="payload")
def activity_list_seqs(payload: dict) -> dict:
    """단일 소스 목록 페이지 순회 → 가져올 seq 리스트 (상세 미수집)

    payload:
      source       : 소스 아이디
      start_page   : 시작 페이지 (default 1)
      page_count   : 수집할 페이지 수 (None 모두, 이 경우 10분 타임아웃 주의)
    """
    source = payload["source"]
    start_page = int(payload.get("start_page", 1))
    page_count = payload.get("page_count")
    if page_count is not None:
        page_count = int(page_count)
    t0 = time.time()
    try:
        res = _list_seqs_to_fetch(source, start_page=start_page, page_count=page_count)
        res["elapsed_seconds"] = round(time.time() - t0, 2)
        return res
    except Exception as e:
        logging.error(f"[activity_list_seqs:{source}:p{start_page}+{page_count}] failed: {e}", exc_info=True)
        return {
            "source": source,
            "start_page": start_page,
            "page_count": page_count,
            "status": "error",
            "error": str(e),
            "elapsed_seconds": round(time.time() - t0, 2),
        }


@app.activity_trigger(input_name="payload")
def activity_crawl_detail_batch(payload: dict) -> dict:
    """단일 소스의 seq 배치 → 상세 수집 + Blob 업로드 (Consumption 10분 한도 내 종료)"""
    source = payload["source"]
    seqs = payload.get("seqs", [])
    crawl_date = payload["crawl_date"]
    detail_workers = payload.get("detail_workers", CRAWL_DETAIL_WORKERS)
    t0 = time.time()
    try:
        res = _fetch_and_upload_batch(source, seqs, crawl_date, detail_workers)
        res["elapsed_seconds"] = round(time.time() - t0, 2)
        return res
    except Exception as e:
        logging.error(f"[activity_crawl_detail_batch:{source}] failed: {e}", exc_info=True)
        return {
            "source": source,
            "status": "error",
            "error": str(e),
            "seqs_in": len(seqs),
            "saved": 0,
            "upload_failed": 0,
            "fetch_failed": len(seqs),
            "elapsed_seconds": round(time.time() - t0, 2),
        }


@app.activity_trigger(input_name="payload")
def activity_preprocess_source(payload: dict) -> dict:
    """단일 소스 preprocess Function HTTP 호출 Activity"""
    source = payload["source"]
    crawl_date = payload["crawl_date"]
    triggered_by = payload.get("triggered_by", "durable")
    if not PREPROCESS_FUNCTION_URI:
        return {"source": source, "status": "skipped", "reason": "PREPROCESS_FUNCTION_URI not set"}

    body = json.dumps({
        "source": source,
        "crawl_date": crawl_date,
        "triggered_by": triggered_by,
    }).encode("utf-8")
    req = urllib.request.Request(
        PREPROCESS_FUNCTION_URI,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=PREPROCESS_TIMEOUT_SECONDS) as resp:
            payload_text = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(payload_text)
            except json.JSONDecodeError:
                parsed = {"raw": payload_text[:500]}
            return {
                "source": source,
                "status": "success",
                "http_status": resp.status,
                "elapsed_seconds": round(time.time() - t0, 2),
                "response": parsed,
            }
    except urllib.error.HTTPError as e:
        return {
            "source": source,
            "status": "http_error",
            "http_status": e.code,
            "elapsed_seconds": round(time.time() - t0, 2),
            "error": e.read().decode("utf-8", errors="replace")[:500],
        }
    except Exception as e:
        return {
            "source": source,
            "status": "error",
            "elapsed_seconds": round(time.time() - t0, 2),
            "error": str(e),
        }

