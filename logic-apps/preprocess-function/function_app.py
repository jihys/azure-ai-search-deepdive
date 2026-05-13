"""
Azure Function App - JSON → JSONL Integration (Preprocess)

Logic Apps `crawl-preprocess-workflow` 가 crawl 성공 후 호출합니다.

HTTP 트리거 (POST /api/preprocess):
  Body (JSON):
    source       : "prec" | "detc" | "expc" | "admrul" | "all"  (default "all")
    crawl_date   : YYYY-MM-DD (default 오늘 UTC)
    workers      : 병렬 다운로드 워커 수 (default 16)
    triggered_by : 호출 출처 표기

처리 흐름:
  raw-documents/{source}/{date}/*.json
    → date 필드 정규화 (빈/파싱 불가는 키 제거)
    → ~80 MiB JSONL 파트로 묶기 (AI Search S1 blob limit 128 MiB)
  → processed-documents/{source}/{date}/docs-part-NNN.jsonl

Storage 접근: Managed Identity (VNet Integration → Storage Private Endpoint)
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import azure.functions as func
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

app = func.FunctionApp()

STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
RAW_CONTAINER = os.environ.get("AZURE_BLOB_CONTAINER_RAW", "raw-documents")
PROCESSED_CONTAINER = os.environ.get("AZURE_BLOB_CONTAINER_PROCESSED", "processed-documents")
TARGET_PART_BYTES = int(os.environ.get("TARGET_PART_BYTES", 80 * 1024 * 1024))  # 80 MiB
DEFAULT_WORKERS = int(os.environ.get("PREPROCESS_WORKERS", "16"))

SOURCES = ("prec", "detc", "expc", "admrul")

# AI Search 인덱스가 DateTimeOffset 으로 매핑하는 한국어 날짜 필드
DATE_FIELDS = {
    "prec":   ("선고일자", "등록일자"),
    "detc":   ("결정일자", "등록일자"),
    "expc":   ("회시일자", "등록일자"),
    "admrul": ("재결일자", "등록일자"),
}


def _make_blob_client():
    if not STORAGE_ACCOUNT_NAME:
        logging.error("AZURE_STORAGE_ACCOUNT_NAME 미설정")
        return None
    try:
        return BlobServiceClient(
            account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=ManagedIdentityCredential(),
        )
    except Exception as e:
        logging.error(f"BlobServiceClient 생성 실패: {e}")
        return None


def _parse_iso(value):
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    try:
        if v.endswith("Z"):
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
    return None


def _clean_document(doc: dict, source: str) -> dict:
    out = dict(doc)
    for f in DATE_FIELDS.get(source, ()):
        if f in out:
            normalized = _parse_iso(out.get(f))
            if normalized is None:
                out.pop(f, None)
            else:
                out[f] = normalized
    if "seq" in out and not isinstance(out["seq"], str):
        out["seq"] = str(out["seq"])
    return out


def _process_source(svc: BlobServiceClient, source: str, date: str, workers: int) -> dict:
    raw = svc.get_container_client(RAW_CONTAINER)
    proc = svc.get_container_client(PROCESSED_CONTAINER)
    prefix = f"{source}/{date}/"
    logging.info(f"[{source}] listing {prefix}")

    blobs = [b for b in raw.list_blobs(name_starts_with=prefix) if b.name.endswith(".json")]
    total = len(blobs)
    logging.info(f"[{source}] {total} JSON files")
    if total == 0:
        return {"files": 0, "parts": 0, "errors": 0, "uploaded": []}

    serialized = []
    errors = [0]

    def _one(blob_name: str):
        try:
            data = json.loads(raw.get_blob_client(blob_name).download_blob().readall())
            data = _clean_document(data, source)
            return (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
        except Exception as e:
            logging.error(f"  ERR {blob_name}: {e}")
            errors[0] += 1
            return None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_one, b.name): b.name for b in blobs}
        for i, fut in enumerate(as_completed(futures), 1):
            line = fut.result()
            if line is not None:
                serialized.append(line)
            if i % 1000 == 0 or i == total:
                logging.info(f"  [{source}] {i}/{total} processed, {time.time()-t0:.1f}s")

    # 동일 날짜의 기존 파트 삭제 (멱등성 보장)
    for b in proc.list_blobs(name_starts_with=prefix):
        proc.delete_blob(b.name)
        logging.info(f"  removed existing {b.name}")

    # 80 MiB 단위로 분할
    parts = []
    current = []
    cur_size = 0
    for line in serialized:
        if current and cur_size + len(line) > TARGET_PART_BYTES:
            parts.append(current)
            current = []
            cur_size = 0
        current.append(line)
        cur_size += len(line)
    if current:
        parts.append(current)

    uploaded = []
    for i, part in enumerate(parts):
        target = f"{source}/{date}/docs-part-{i:03d}.jsonl"
        body = b"".join(part)
        proc.upload_blob(name=target, data=body, overwrite=True)
        uploaded.append({"path": target, "bytes": len(body), "docs": len(part)})
        logging.info(f"  uploaded {target} ({len(body)/1024/1024:.1f} MiB, {len(part)} docs)")

    return {"files": total, "parts": len(parts), "errors": errors[0], "uploaded": uploaded}


@app.function_name(name="preprocess")
@app.route(route="preprocess", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def preprocess_trigger(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Preprocess function triggered")
    start = datetime.now(timezone.utc)

    try:
        body = req.get_json()
    except (ValueError, AttributeError):
        body = {}

    source = req.params.get("source") or body.get("source", "all")
    crawl_date = req.params.get("crawl_date") or body.get("crawl_date") or start.strftime("%Y-%m-%d")
    triggered_by = req.params.get("triggered_by") or body.get("triggered_by", "manual")
    try:
        workers = int(req.params.get("workers") or body.get("workers", DEFAULT_WORKERS))
    except (TypeError, ValueError):
        workers = DEFAULT_WORKERS

    if source not in list(SOURCES) + ["all"]:
        return func.HttpResponse(
            json.dumps({"error": f"Unknown source '{source}'. Use: prec, detc, expc, admrul, all"}),
            status_code=400, mimetype="application/json",
        )

    targets = list(SOURCES) if source == "all" else [source]

    svc = _make_blob_client()
    if svc is None:
        return func.HttpResponse(
            json.dumps({"error": "Blob client unavailable"}),
            status_code=500, mimetype="application/json",
        )

    logging.info(f"Preprocess start sources={targets} date={crawl_date} workers={workers} triggered_by={triggered_by}")

    summary = {}
    files_total = 0
    parts_total = 0
    errors_total = 0

    for src in targets:
        try:
            r = _process_source(svc, src, crawl_date, workers)
            summary[src] = r
            files_total += r["files"]
            parts_total += r["parts"]
            errors_total += r["errors"]
        except Exception as e:
            logging.error(f"[{src}] preprocess failed: {e}", exc_info=True)
            summary[src] = {"error": str(e)}
            errors_total += 1

    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 2)
    status = "success" if errors_total == 0 else "partial"
    result = {
        "status": status,
        "triggered_by": triggered_by,
        "crawl_date": crawl_date,
        "sources": summary,
        "total_files": files_total,
        "total_parts": parts_total,
        "total_errors": errors_total,
        "elapsed_seconds": elapsed,
        "timestamp": start.isoformat(),
    }
    logging.info(f"Preprocess complete: files={files_total} parts={parts_total} errors={errors_total} elapsed={elapsed}s")
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        status_code=200, mimetype="application/json",
    )
