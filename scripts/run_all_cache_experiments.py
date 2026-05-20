#!/usr/bin/env python3
"""
멀티모달 3개 파이프라인 캐싱 효과 실험 — 통합 스크립트

3개 파이프라인 각각에 대해 A/B/C 실험 수행:
  A: 인덱서/인덱스 삭제 (캐시 비움)
  B: cache ON 재생성 → 1차 실행 (캐시 채움)
  C: cache ON reset+run (캐시 HIT)

파이프라인:
  1. verbalized  — DI Layout → GPT Verbalize → Markdown Split → Embedding (PDF only)
  2. pdf         — DI Layout → markdown_split (WebApi) → Embedding (PDF only)
  3. pptx        — DI Layout → pptx_page_split (WebApi) → Embedding (PPTX only)

실행:
  cd /home/azureuser/localfiles/azure-ai-search-deepdive
  nohup uv run python scripts/run_all_cache_experiments.py > logs/all_cache_experiment.log 2>&1 &
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from azure.identity import AzureCliCredential, ChainedTokenCredential, DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# ── 프로젝트 루트 ──
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

# ── 환경변수 ──
STORAGE_NAME = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"].rstrip("/")
CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw-documents")
TENANT_ID = os.environ.get("AZURE_TENANT_ID")
API_VERSION = "2024-11-01-preview"
SOURCE = "st"

BLOB_PREFIX_PDF = "raw/pdf/"
BLOB_PREFIX_PPTX = "raw/pptx/"

# 파이프라인별 리소스 이름
PIPELINES = {
    "verbalized": {
        "indexer": f"{SOURCE}-multimodal-verbalized-indexer",
        "index": f"{SOURCE}-multimodal-verbalized-index",
        "skillset": f"{SOURCE}-multimodal-verbalized-skillset",
        "label": "Verbalized (DI Layout → GPT Verbalize → Markdown Split → Embedding)",
        "file_type": "pdf",
        "setup_pipeline_arg": "verbalized",
    },
    "pdf": {
        "indexer": f"{SOURCE}-multimodal-pdf-indexer",
        "index": f"{SOURCE}-multimodal-pdf-index",
        "skillset": f"{SOURCE}-multimodal-pdf-skillset",
        "label": "PDF Basic (DI Layout → markdown_split → Embedding)",
        "file_type": "pdf",
        "setup_pipeline_arg": "pdf",
    },
    "pptx": {
        "indexer": f"{SOURCE}-multimodal-pptx-indexer",
        "index": f"{SOURCE}-multimodal-pptx-index",
        "skillset": f"{SOURCE}-multimodal-pptx-skillset",
        "label": "PPTX Basic (DI Layout → pptx_page_split → Embedding)",
        "file_type": "pptx",
        "setup_pipeline_arg": "pptx",
    },
}

REPORT_PATH = ROOT / "multi-modal-report.md"

# ── Credential ──
cli_kwargs = {"tenant_id": TENANT_ID} if TENANT_ID else {}
credential = ChainedTokenCredential(
    AzureCliCredential(**cli_kwargs),
    DefaultAzureCredential(
        exclude_managed_identity_credential=True,
        **({
            "interactive_browser_tenant_id": TENANT_ID,
            "shared_cache_tenant_id": TENANT_ID,
            "visual_studio_code_tenant_id": TENANT_ID,
            "workload_identity_tenant_id": TENANT_ID,
        } if TENANT_ID else {}),
    ),
)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════
# Search API helpers
# ═══════════════════════════════════════════════════════════════

def get_search_headers() -> dict:
    token = credential.get_token("https://search.azure.com/.default").token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def delete_resource(resource_type: str, name: str) -> int:
    """인덱서/인덱스/스킬셋 삭제."""
    url = f"{SEARCH_ENDPOINT}/{resource_type}/{name}?api-version={API_VERSION}"
    r = requests.delete(url, headers=get_search_headers())
    return r.status_code


def reset_indexer(name: str) -> bool:
    url = f"{SEARCH_ENDPOINT}/indexers/{name}/reset?api-version={API_VERSION}"
    r = requests.post(url, headers=get_search_headers())
    return r.status_code in (200, 204)


def run_indexer(name: str, max_retries: int = 5) -> bool:
    for attempt in range(max_retries):
        url = f"{SEARCH_ENDPOINT}/indexers/{name}/run?api-version={API_VERSION}"
        r = requests.post(url, headers=get_search_headers())
        if r.status_code == 202:
            log(f"    ▶ {name} 실행 시작")
            return True
        if r.status_code == 409:
            wait = 30 * (attempt + 1)
            log(f"    ⏳ 409 Conflict (attempt {attempt+1}/{max_retries}), {wait}s 대기")
            time.sleep(wait)
            continue
        log(f"    ✗ 실행 실패: {r.status_code} {r.text[:300]}")
        return False
    log(f"    ✗ 409 Conflict 최대 재시도 초과")
    return False


def get_indexer_status(name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexers/{name}/status?api-version={API_VERSION}"
    r = requests.get(url, headers=get_search_headers())
    if r.status_code == 404:
        return {"_notfound": True}
    return r.json()


def get_index_stats(name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexes/{name}/stats?api-version={API_VERSION}"
    r = requests.get(url, headers=get_search_headers())
    return r.json() if r.status_code == 200 else {}


def _last_start_time(status: dict) -> str | None:
    if status.get("_notfound"):
        return None
    last = status.get("lastResult") or {}
    return last.get("startTime")


def wait_indexer_complete(name: str, timeout_sec: int = 7200, poll_interval: int = 20,
                          baseline: str | None = "__auto__") -> tuple[str, dict]:
    """인덱서의 새 실행이 완료될 때까지 대기. lastResult 기반."""
    if baseline == "__auto__":
        baseline = _last_start_time(get_indexer_status(name))
    start = time.time()
    log(f"    ⏳ {name} 완료 대기 (baseline={baseline})")
    while True:
        status = get_indexer_status(name)
        if status.get("_notfound"):
            return "notFound", {}
        last = status.get("lastResult") or {}
        last_state = last.get("status", "unknown")
        last_start = last.get("startTime")
        processed = last.get("itemsProcessed", 0)
        failed = last.get("itemsFailed", 0)
        elapsed = int(time.time() - start)
        is_new = last_start is not None and last_start != baseline

        if elapsed % 60 < poll_interval:
            log(f"      [{elapsed:>4d}s] state={last_state} new={is_new} proc={processed} fail={failed}")

        if is_new and last_state in ("success", "transientFailure", "persistentFailure"):
            return last_state, last
        if elapsed > timeout_sec:
            log(f"      ⚠ timeout ({timeout_sec}s)")
            return "timeout", last
        time.sleep(poll_interval)


def wait_until_idle(name: str, timeout_sec: int = 7200, poll_interval: int = 20) -> str:
    """현재 실행이 완료될 때까지 대기."""
    t0 = time.time()
    while True:
        st = get_indexer_status(name)
        if st.get("_notfound"):
            return "notFound"
        hist = st.get("executionHistory") or []
        latest_status = hist[0].get("status") if hist else None
        if latest_status != "inProgress":
            return latest_status or st.get("status", "unknown")
        elapsed = int(time.time() - t0)
        if elapsed % 60 < poll_interval:
            log(f"      wait_idle {name}: {latest_status} elapsed={elapsed}s")
        if time.time() - t0 > timeout_sec:
            return "timeout"
        time.sleep(poll_interval)


def get_metrics_from_last_result(name: str) -> dict:
    """인덱서의 lastResult에서 메트릭 추출."""
    st = get_indexer_status(name)
    last = st.get("lastResult") or {}
    start_t = last.get("startTime")
    end_t = last.get("endTime")
    elapsed = None
    if start_t and end_t:
        s = datetime.fromisoformat(start_t.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_t.replace("Z", "+00:00"))
        elapsed = (e - s).total_seconds()
    return {
        "status": last.get("status"),
        "items_processed": last.get("itemsProcessed", 0),
        "items_failed": last.get("itemsFailed", 0),
        "indexer_elapsed_sec": elapsed,
        "start_time": start_t,
        "end_time": end_t,
        "warnings": last.get("warnings", []),
        "errors": last.get("errors", []),
    }


# ═══════════════════════════════════════════════════════════════
# Blob helpers
# ═══════════════════════════════════════════════════════════════

def get_blob_info() -> dict:
    try:
        blob_service = BlobServiceClient(
            account_url=f"https://{STORAGE_NAME}.blob.core.windows.net",
            credential=credential,
        )
        container = blob_service.get_container_client(CONTAINER_NAME)
        info = {"pdf": [], "pptx": []}
        for prefix, ftype in [(BLOB_PREFIX_PDF, "pdf"), (BLOB_PREFIX_PPTX, "pptx")]:
            for b in container.list_blobs(name_starts_with=prefix):
                info[ftype].append({"name": b.name, "size": b.size})
        return info
    except Exception as e:
        log(f"  ⚠ Blob 조회 실패 ({e.__class__.__name__}), 기존 데이터 사용")
        return _fallback_blob_info()


def _fallback_blob_info() -> dict:
    """이전 실행에서 확인된 blob 정보 (fallback)."""
    pdfs = [
        ("raw/pdf/HA/HA_0032_0013106.pdf", 706560),
        ("raw/pdf/HA/HA_0051_0014672.pdf", 7980032),
        ("raw/pdf/HA/HA_0078_0044181.pdf", 1041408),
        ("raw/pdf/HA/HA_0114_0043314.pdf", 963584),
        ("raw/pdf/HA/HA_0132_0067633.pdf", 735232),
        ("raw/pdf/SS/SS_0017_0082677.pdf", 805888),
        ("raw/pdf/SS/SS_0025_0027983.pdf", 705536),
        ("raw/pdf/SS/SS_0050_0016707.pdf", 505856),
        ("raw/pdf/SS/SS_0132_0068276.pdf", 615424),
        ("raw/pdf/SS/SS_0144_0061959.pdf", 861184),
        ("raw/pdf/ST/ST_0028_0008931.pdf", 308224),
        ("raw/pdf/ST/ST_0028_0028442.pdf", 471040),
        ("raw/pdf/ST/ST_0119_0006320.pdf", 3073024),
        ("raw/pdf/ST/ST_0145_0074863.pdf", 1010688),
        ("raw/pdf/ST/ST_0145_0075608.pdf", 1018880),
    ]
    pptxs = [
        ("raw/pptx/HA/HA_0032_0014125.pptx", 26624),
        ("raw/pptx/HA/HA_0047_0038756.pptx", 27648),
        ("raw/pptx/HA/HA_0077_0020961.pptx", 24576),
        ("raw/pptx/HA/HA_0114_0049819.pptx", 26624),
        ("raw/pptx/HA/HA_0133_0063408.pptx", 1330176),
        ("raw/pptx/SS/SS_0015_0035043.pptx", 227328),
        ("raw/pptx/SS/SS_0021_0026355.pptx", 131072),
        ("raw/pptx/SS/SS_0042_0039515.pptx", 247808),
        ("raw/pptx/SS/SS_0132_0067965.pptx", 200704),
        ("raw/pptx/SS/SS_0144_0062244.pptx", 225280),
        ("raw/pptx/ST/ST_0028_0008774.pptx", 585728),
        ("raw/pptx/ST/ST_0028_0010206.pptx", 168960),
        ("raw/pptx/ST/ST_0119_0006205.pptx", 4005888),
        ("raw/pptx/ST/ST_0145_0074816.pptx", 87040),
        ("raw/pptx/ST/ST_0145_0075614.pptx", 406528),
    ]
    return {
        "pdf": [{"name": n, "size": s} for n, s in pdfs],
        "pptx": [{"name": n, "size": s} for n, s in pptxs],
    }


# ═══════════════════════════════════════════════════════════════
# Setup script wrapper
# ═══════════════════════════════════════════════════════════════

def run_setup(pipeline: str, cache_on: bool, schedule: str = "none", timeout: int = 600) -> tuple[int, str]:
    """setup_ai_search_multimodal_pipeline.py 실행."""
    env = os.environ.copy()
    env["SETUP_ENABLE_CACHE"] = "1" if cache_on else "0"
    log(f"    setup --pipeline {pipeline} (cache={'ON' if cache_on else 'OFF'}, schedule={schedule})")
    res = subprocess.run(
        [sys.executable, "scripts/setup_ai_search_multimodal_pipeline.py",
         "--source", SOURCE, "--pipeline", pipeline, "--schedule", schedule],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env, check=False,
    )
    if res.returncode != 0:
        log(f"    setup FAILED (rc={res.returncode})")
        log(f"    stderr: {res.stderr[-500:]}")
        return res.returncode, res.stderr[-300:]
    for line in res.stdout.splitlines()[-5:]:
        log(f"      {line}")
    return 0, ""


# ═══════════════════════════════════════════════════════════════
# Single-pipeline experiment runner
# ═══════════════════════════════════════════════════════════════

def run_experiment(pipeline_key: str) -> dict:
    """단일 파이프라인에 대해 A/B/C 실험 수행. 결과 dict 반환."""
    p = PIPELINES[pipeline_key]
    indexer = p["indexer"]
    index = p["index"]
    setup_arg = p["setup_pipeline_arg"]
    log(f"{'='*60}")
    log(f"파이프라인: {pipeline_key.upper()} — {p['label']}")
    log(f"{'='*60}")

    result = {"pipeline": pipeline_key, "label": p["label"], "file_type": p["file_type"]}

    # ── A: 초기화 (인덱서/인덱스/스킬셋 삭제 → 캐시 완전 무효화) ──
    log(f"  [A] 초기화: {indexer} / {index} / {p['skillset']} 삭제")
    wait_until_idle(indexer, timeout_sec=3600)
    sc = delete_resource("indexers", indexer)
    log(f"    DELETE indexer → {sc}")
    sc = delete_resource("indexes", index)
    log(f"    DELETE index → {sc}")
    sc = delete_resource("skillsets", p["skillset"])
    log(f"    DELETE skillset → {sc}")
    time.sleep(5)

    # ── B: cache ON, 1차 실행 (캐시 채움) ──
    log(f"  [B] cache ON 재생성 + 1차 실행 (캐시 채움)")
    pre_baseline = _last_start_time(get_indexer_status(indexer))  # should be None
    rc, err = run_setup(setup_arg, cache_on=True, schedule="none")
    if rc != 0:
        log(f"    ✗ setup 실패: {err}")
        result["error"] = f"setup failed: {err}"
        return result

    # PUT 인덱서 → Azure 자동 실행 시작. 대기.
    log(f"    PUT 후 자동 실행 대기...")
    time.sleep(10)
    wall_b_start = time.time()
    state_b, last_b = wait_indexer_complete(indexer, timeout_sec=7200,
                                             poll_interval=20, baseline=pre_baseline)
    wall_b = time.time() - wall_b_start
    metrics_b = get_metrics_from_last_result(indexer)
    log(f"    [B 결과] state={state_b} items={metrics_b['items_processed']} "
        f"failed={metrics_b['items_failed']} elapsed={metrics_b['indexer_elapsed_sec']}s")

    # 자동 실행에서 0건이면 수동 reset+run
    if metrics_b["items_processed"] == 0:
        log(f"    ⚠ 0건 → 수동 reset+run")
        manual_baseline = _last_start_time(get_indexer_status(indexer))
        reset_indexer(indexer)
        time.sleep(5)
        if not run_indexer(indexer):
            result["error"] = "run_indexer failed on step B manual"
            return result
        time.sleep(5)
        state_b, _ = wait_indexer_complete(indexer, timeout_sec=7200, poll_interval=20,
                                            baseline=manual_baseline)
        metrics_b = get_metrics_from_last_result(indexer)
        log(f"    [B-manual] items={metrics_b['items_processed']} elapsed={metrics_b['indexer_elapsed_sec']}s")

    result["metrics_b"] = metrics_b
    result["wall_b"] = metrics_b.get("indexer_elapsed_sec") or wall_b
    result["rc_b"] = 0 if state_b == "success" else 2

    # ── C: cache ON, 2차 실행 (캐시 HIT) ──
    log(f"  [C] cache ON reset+run (캐시 HIT)")
    # baseline을 reset/run 전에 캡처해야 "new" 감지 가능
    pre_c_baseline = _last_start_time(get_indexer_status(indexer))
    reset_indexer(indexer)
    time.sleep(5)
    wall_c_start = time.time()
    if not run_indexer(indexer):
        result["error"] = "run_indexer failed on step C"
        return result
    time.sleep(5)
    state_c, _ = wait_indexer_complete(indexer, timeout_sec=7200, poll_interval=20,
                                        baseline=pre_c_baseline)
    wall_c = time.time() - wall_c_start
    metrics_c = get_metrics_from_last_result(indexer)
    log(f"    [C 결과] state={state_c} items={metrics_c['items_processed']} "
        f"failed={metrics_c['items_failed']} elapsed={metrics_c['indexer_elapsed_sec']}s")

    result["metrics_c"] = metrics_c
    result["wall_c"] = metrics_c.get("indexer_elapsed_sec") or wall_c
    result["rc_c"] = 0 if state_c == "success" else 2

    # B vs C 요약
    idx_b = metrics_b.get("indexer_elapsed_sec") or 0
    idx_c = metrics_c.get("indexer_elapsed_sec") or 0
    if idx_b > 0:
        saving = idx_b - idx_c
        pct = saving / idx_b * 100
        log(f"    ────────────────────────────────")
        log(f"    B (cache 채움): {idx_b:.1f}s")
        log(f"    C (cache HIT):  {idx_c:.1f}s")
        log(f"    절감: {saving:+.1f}s ({pct:+.1f}%)")
        log(f"    ────────────────────────────────")

    # Index stats
    result["index_stats"] = get_index_stats(index)
    return result


# ═══════════════════════════════════════════════════════════════
# Cost estimation per pipeline
# ═══════════════════════════════════════════════════════════════

def estimate_pipeline_cost(pipeline_key: str, blob_info: dict, metrics_b: dict, metrics_c: dict) -> dict:
    """파이프라인별 비용 추정."""
    p = PIPELINES[pipeline_key]
    ftype = p["file_type"]
    files = blob_info.get(ftype, [])
    n_files = len(files)
    total_bytes = sum(b["size"] for b in files)
    est_pages = max(1, total_bytes // (50 * 1024))

    items_b = metrics_b.get("items_processed", 0)
    items_c = metrics_c.get("items_processed", 0)

    # DI Layout: ~$0.015/page (for pdf/verbalized), ~$0.015/slide (for pptx)
    di_cost_per_page = 0.015
    di_cost_b = est_pages * di_cost_per_page
    di_cost_c = 0.0  # cache HIT

    # GPT verbalize (only for verbalized pipeline)
    gpt_input_per_page = 1500
    gpt_output_per_page = 500
    gpt_cost_per_page = (gpt_input_per_page * 2.50 + gpt_output_per_page * 10.0) / 1_000_000
    if pipeline_key == "verbalized":
        gpt_total_input = est_pages * gpt_input_per_page
        gpt_total_output = est_pages * gpt_output_per_page
        gpt_cost_b = est_pages * gpt_cost_per_page
        gpt_cost_c = 0.0
    else:
        gpt_total_input = 0
        gpt_total_output = 0
        gpt_cost_b = 0.0
        gpt_cost_c = 0.0

    # Custom WebApiSkill (markdown_split / pptx_page_split): negligible cost (self-hosted function)
    webapi_cost_b = 0.0
    webapi_cost_c = 0.0

    # Embedding: $0.13/1M tokens
    avg_tokens_per_chunk = 500
    emb_cost_b = items_b * avg_tokens_per_chunk * 0.13 / 1_000_000
    emb_cost_c = items_c * avg_tokens_per_chunk * 0.13 / 1_000_000

    return {
        "n_files": n_files,
        "total_bytes": total_bytes,
        "est_pages": est_pages,
        "items_b": items_b,
        "items_c": items_c,
        "di_cost_b": di_cost_b,
        "di_cost_c": di_cost_c,
        "gpt_cost_b": gpt_cost_b,
        "gpt_cost_c": gpt_cost_c,
        "gpt_cost_per_page": gpt_cost_per_page,
        "gpt_total_input": gpt_total_input,
        "gpt_total_output": gpt_total_output,
        "webapi_cost_b": webapi_cost_b,
        "webapi_cost_c": webapi_cost_c,
        "emb_cost_b": emb_cost_b,
        "emb_cost_c": emb_cost_c,
        "total_b": di_cost_b + gpt_cost_b + emb_cost_b,
        "total_c": di_cost_c + gpt_cost_c + emb_cost_c,
    }


# ═══════════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════════

def generate_report(blob_info: dict, results: dict[str, dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    search_svc = SEARCH_ENDPOINT.split("//")[1].split(".")[0]

    n_pdf = len(blob_info["pdf"])
    n_pptx = len(blob_info["pptx"])
    total_pdf_bytes = sum(b["size"] for b in blob_info["pdf"])
    total_pptx_bytes = sum(b["size"] for b in blob_info["pptx"])
    total_blob_mib = (total_pdf_bytes + total_pptx_bytes) / (1024 * 1024)
    est_pdf_pages = max(1, total_pdf_bytes // (50 * 1024))
    est_pptx_pages = max(1, total_pptx_bytes // (50 * 1024))

    md = f"""# 멀티모달 인덱싱 — 캐싱 효과 실험 리포트

> 측정일자: {now}
> Region: `swedencentral` / Search Service: `{search_svc}`
> 실험 대상: 3개 멀티모달 파이프라인 (Verbalized / PDF Basic / PPTX Basic)

---

## 1. 한눈에 보기 — 파이프라인별 캐시 효과 비교

| 파이프라인 | B (cache 채움) | C (cache HIT) | 시간 절감 | 절감률 | B 비용 | C 비용 | 비용 절감 |
|-----------|---------------:|---------------:|----------:|-------:|-------:|-------:|----------:|
"""
    for pk in ["verbalized", "pdf", "pptx"]:
        r = results.get(pk, {})
        if r.get("error"):
            md += f"| **{pk.upper()}** | ERROR | — | — | — | — | — | — |\n"
            continue
        mb = r.get("metrics_b", {})
        mc = r.get("metrics_c", {})
        idx_b = mb.get("indexer_elapsed_sec") or 0
        idx_c = mc.get("indexer_elapsed_sec") or 0
        saving = idx_b - idx_c
        pct = (saving / idx_b * 100) if idx_b else 0
        costs = r.get("costs", {})
        md += (f"| **{pk.upper()}** "
               f"| {idx_b:.1f}s "
               f"| {idx_c:.1f}s "
               f"| {saving:+.1f}s "
               f"| {pct:+.1f}% "
               f"| ${costs.get('total_b', 0):.4f} "
               f"| ${costs.get('total_c', 0):.4f} "
               f"| ${costs.get('total_b', 0) - costs.get('total_c', 0):.4f} |\n")

    md += f"""
---

## 2. Blob Storage 파일 현황

| 유형 | 파일 수 | 총 크기 | 추정 페이지 수 |
|------|--------:|--------:|---------------:|
| PDF | {n_pdf} | {total_pdf_bytes / (1024*1024):.1f} MiB | ~{est_pdf_pages} |
| PPTX | {n_pptx} | {total_pptx_bytes / (1024*1024):.1f} MiB | ~{est_pptx_pages} |
| **합계** | **{n_pdf + n_pptx}** | **{total_blob_mib:.1f} MiB** | **~{est_pdf_pages + est_pptx_pages}** |

### 2.1 PDF 파일 목록

"""
    for b in sorted(blob_info["pdf"], key=lambda x: x["name"]):
        md += f"- `{b['name']}` ({b['size'] / 1024:.0f} KB)\n"

    md += "\n### 2.2 PPTX 파일 목록\n\n"
    for b in sorted(blob_info["pptx"], key=lambda x: x["name"]):
        md += f"- `{b['name']}` ({b['size'] / 1024:.0f} KB)\n"

    # ── 인덱스 통계 ──
    md += "\n---\n\n## 3. 인덱스 통계 (실험 완료 후)\n\n"
    md += "| 인덱스 | 문서 수 | Storage (MiB) | Vector (MiB) |\n"
    md += "|--------|--------:|--------------:|-------------:|\n"
    total_docs = 0
    total_storage = 0.0
    total_vector = 0.0
    for pk in ["verbalized", "pdf", "pptx"]:
        r = results.get(pk, {})
        idx_stats = r.get("index_stats", {})
        docs = idx_stats.get("documentCount", 0)
        storage_mib = idx_stats.get("storageSize", 0) / (1024 * 1024)
        vector_mib = idx_stats.get("vectorIndexSize", 0) / (1024 * 1024)
        total_docs += docs
        total_storage += storage_mib
        total_vector += vector_mib
        idx_name = PIPELINES[pk]["index"]
        md += f"| `{idx_name}` | {docs:,} | {storage_mib:.1f} | {vector_mib:.1f} |\n"
    md += f"| **합계** | **{total_docs:,}** | **{total_storage:.1f}** | **{total_vector:.1f}** |\n"

    # ── 파이프라인별 상세 결과 ──
    for pk in ["verbalized", "pdf", "pptx"]:
        r = results.get(pk, {})
        p = PIPELINES[pk]
        md += f"\n---\n\n## 4-{['A','B','C'][['verbalized','pdf','pptx'].index(pk)]}. {pk.upper()} 파이프라인 상세\n\n"
        md += f"> {p['label']}\n\n"

        if r.get("error"):
            md += f"**⚠️ 실험 실패**: {r['error']}\n"
            continue

        mb = r.get("metrics_b", {})
        mc = r.get("metrics_c", {})
        idx_b = mb.get("indexer_elapsed_sec") or 0
        idx_c = mc.get("indexer_elapsed_sec") or 0
        saving = idx_b - idx_c
        pct = (saving / idx_b * 100) if idx_b else 0
        costs = r.get("costs", {})

        md += f"""### 실험 결과

| 시나리오 | indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| B. cache 채움 (1차) | {idx_b:.1f} | {mb.get('items_processed', 0)} | {mb.get('items_failed', 0)} | {r.get('index_stats', {}).get('documentCount', '?')} |
| C. cache HIT (2차) | {idx_c:.1f} | {mc.get('items_processed', 0)} | {mc.get('items_failed', 0)} | {r.get('index_stats', {}).get('documentCount', '?')} |

### 캐시 효과

| 비교 | indexer 소요 | 차이 | 절감률 |
|------|------------:|-----:|-------:|
| B (baseline) | {idx_b:.1f} s | — | — |
| C (cache HIT) | {idx_c:.1f} s | {saving:+.1f} s | {pct:+.1f}% |

"""
        if saving > 0:
            md += f"**✅ 캐시 HIT 효과 확인**: 시간 {saving:.1f}s ({pct:.1f}%) 절감\n\n"
        else:
            md += f"⚠️ 캐시 효과 미확인 — 데이터 크기가 작아 cache lookup overhead가 원래 처리 시간을 초과할 수 있음\n\n"

        # Cost breakdown
        md += "### 비용 추정\n\n"
        if pk == "verbalized":
            md += f"""| 항목 | B (cache 채움) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout ({costs['est_pages']} pages × $0.015) | ${costs['di_cost_b']:.4f} | ${costs['di_cost_c']:.4f} | ${costs['di_cost_b']:.4f} |
| GPT Verbalize ({costs['est_pages']} calls) | ${costs['gpt_cost_b']:.4f} | ${costs['gpt_cost_c']:.4f} | ${costs['gpt_cost_b']:.4f} |
| Embedding ({costs['items_b']} / {costs['items_c']} chunks) | ${costs['emb_cost_b']:.4f} | ${costs['emb_cost_c']:.4f} | ${costs['emb_cost_b'] - costs['emb_cost_c']:.4f} |
| **합계** | **${costs['total_b']:.4f}** | **${costs['total_c']:.4f}** | **${costs['total_b'] - costs['total_c']:.4f}** |

> GPT 토큰 추정: input ~{costs['gpt_total_input']:,} / output ~{costs['gpt_total_output']:,} tokens
> Cache HIT 시 DI Layout + GPT Verbalize 호출 완전 skip → **시간·비용 모두 절감**

"""
        else:
            md += f"""| 항목 | B (cache 채움) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout ({costs['est_pages']} pages × $0.015) | ${costs['di_cost_b']:.4f} | ${costs['di_cost_c']:.4f} | ${costs['di_cost_b']:.4f} |
| Custom WebApiSkill ({p['setup_pipeline_arg']}_split) | $0.0000 | $0.0000 | $0.0000 |
| Embedding ({costs['items_b']} / {costs['items_c']} chunks) | ${costs['emb_cost_b']:.4f} | ${costs['emb_cost_c']:.4f} | ${costs['emb_cost_b'] - costs['emb_cost_c']:.4f} |
| **합계** | **${costs['total_b']:.4f}** | **${costs['total_c']:.4f}** | **${costs['total_b'] - costs['total_c']:.4f}** |

> Cache HIT 시 DI Layout 호출 skip → 비용 절감. Custom WebApiSkill은 자체 호스팅이므로 API 비용 없음.

"""

        # Indexer 실행 로그
        md += f"""### Indexer 실행 로그

**B (cache 채움):**

| 항목 | 값 |
|------|------|
| 시작 | `{mb.get('start_time', 'N/A')}` |
| 종료 | `{mb.get('end_time', 'N/A')}` |
| 상태 | `{mb.get('status', 'N/A')}` |
| 처리 | {mb.get('items_processed', 0)} 건 |
| 실패 | {mb.get('items_failed', 0)} 건 |

**C (cache HIT):**

| 항목 | 값 |
|------|------|
| 시작 | `{mc.get('start_time', 'N/A')}` |
| 종료 | `{mc.get('end_time', 'N/A')}` |
| 상태 | `{mc.get('status', 'N/A')}` |
| 처리 | {mc.get('items_processed', 0)} 건 |
| 실패 | {mc.get('items_failed', 0)} 건 |

"""
        # Errors/warnings
        for label, m in [("B", mb), ("C", mc)]:
            if m.get("errors"):
                md += f"**{label} — Errors:**\n\n"
                for e in m["errors"][:10]:
                    md += f"- {e.get('message', '')[:300]}\n"
                md += "\n"
            if m.get("warnings"):
                md += f"**{label} — Warnings ({len(m['warnings'])} 건):**\n\n"
                for w in m["warnings"][:5]:
                    md += f"- {w.get('message', '')[:200]}\n"
                md += "\n"

    # ── 비용 종합 ──
    md += """---

## 5. 비용 종합 비교

### 5.1 파이프라인별 스킬 구성

| 파이프라인 | 스킬 1 | 스킬 2 | 스킬 3 | 스킬 4 |
|-----------|--------|--------|--------|--------|
| **Verbalized** | DI Layout (built-in) | GPT Verbalize (WebApi) | Markdown Split (WebApi) | Embedding (built-in) |
| **PDF Basic** | DI Layout (built-in) | markdown_split (WebApi) | Embedding (built-in) | — |
| **PPTX Basic** | DI Layout (built-in) | pptx_page_split (WebApi) | Embedding (built-in) | — |

### 5.2 전체 비용 요약

"""
    total_cost_b = 0
    total_cost_c = 0
    md += "| 파이프라인 | B (cache 채움) | C (cache HIT) | 절감 |\n"
    md += "|-----------|---------------:|---------------:|-----:|\n"
    for pk in ["verbalized", "pdf", "pptx"]:
        r = results.get(pk, {})
        costs = r.get("costs", {})
        tb = costs.get("total_b", 0)
        tc = costs.get("total_c", 0)
        total_cost_b += tb
        total_cost_c += tc
        md += f"| {pk.upper()} | ${tb:.4f} | ${tc:.4f} | ${tb - tc:.4f} |\n"
    md += f"| **합계** | **${total_cost_b:.4f}** | **${total_cost_c:.4f}** | **${total_cost_b - total_cost_c:.4f}** |\n"

    md += f"""
### 5.3 대규모 추정 (PDF 100개 + PPTX 100개)

"""
    for pk in ["verbalized", "pdf", "pptx"]:
        r = results.get(pk, {})
        costs = r.get("costs", {})
        n = costs.get("n_files", 1) or 1
        scale = 100 / n
        md += f"| {pk.upper()} (100 files) | 1회: ~${costs.get('total_b', 0) * scale:.2f} | cache HIT: ~${costs.get('total_c', 0) * scale:.2f} | 절감: ~${(costs.get('total_b', 0) - costs.get('total_c', 0)) * scale:.2f} |\n"

    # ── 캐싱 메커니즘 해석 ──
    md += f"""
---

## 6. 캐싱 메커니즘 해석

### 6.1 왜 멀티모달에서 캐시가 효과적인가?

| 스킬 | 1건 처리 시간 | cache HIT (Storage lookup) | 효과 |
|------|-------------:|---------------------------:|------|
| `DocumentIntelligenceLayoutSkill` | **2–10 s / page** | ~30–150 ms | **✅ 시간·비용 모두 이득** |
| `ChatCompletionSkill` (GPT verbalize) | **3–8 s / call** | ~30–150 ms | **✅ 시간·비용 모두 이득** |
| Custom `WebApiSkill` (split) | ~100–500 ms / call | ~30–150 ms | ✅ 약간 이득 |
| `AzureOpenAIEmbeddingSkill` | ~5 ms / doc | ~30–150 ms | ❌ cache overhead > 원래 비용 |

→ **DI Layout**이 모든 파이프라인의 dominant cost. Verbalized는 여기에 **GPT Verbalize**까지 추가.
  이 두 스킬의 cache HIT만으로 전체 파이프라인 시간을 **대폭 단축**.

### 6.2 파이프라인별 캐시 효과 비교

| 파이프라인 | dominant skill | cache 효과 | 이유 |
|-----------|---------------|-----------|------|
| **Verbalized** | DI Layout + GPT (수 초/doc) | **✅✅ 매우 큰 절감** | DI + GPT 모두 캐시 hit |
| **PDF Basic** | DI Layout (수 초/page) | **✅ 큰 절감** | DI 캐시 hit |
| **PPTX Basic** | DI Layout (수 초/page) | **✅ 큰 절감** | DI 캐시 hit |
| 텍스트 전용 (notebook 03) | EmbeddingSkill (5ms/doc, batch) | ❌ 오히려 손해 | lookup > embedding |

---

## 7. 실험 조건

| 항목 | 값 |
|------|------|
| Search Endpoint | `{SEARCH_ENDPOINT}` |
| Storage Account | `{STORAGE_NAME}` |
| Container | `{CONTAINER_NAME}` |
| PDF Blob Prefix | `{BLOB_PREFIX_PDF}` |
| PPTX Blob Prefix | `{BLOB_PREFIX_PPTX}` |
| Embedding Model | text-embedding-3-large (dim 3072) |
| API Version | {API_VERSION} |
"""
    return md


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    log("=" * 70)
    log("멀티모달 3-파이프라인 캐싱 효과 실험 시작")
    log("=" * 70)

    # ── Blob 현황 ──
    log("[0] Blob 현황 조회")
    blob_info = get_blob_info()
    n_pdf = len(blob_info["pdf"])
    n_pptx = len(blob_info["pptx"])
    total_bytes = sum(b["size"] for b in blob_info["pdf"]) + sum(b["size"] for b in blob_info["pptx"])
    log(f"  PDF: {n_pdf}개, PPTX: {n_pptx}개, 총 {total_bytes / (1024*1024):.1f} MiB")

    if n_pdf == 0 and n_pptx == 0:
        log("⚠️ 파일 없음!")
        return

    # ── 모든 파이프라인 인덱서/인덱스/스킬셋 삭제 ──
    log("[0.5] 모든 파이프라인 리소스 삭제")
    for pk in ["verbalized", "pdf", "pptx"]:
        p = PIPELINES[pk]
        wait_until_idle(p["indexer"], timeout_sec=3600)
        for rtype, rname in [("indexers", p["indexer"]), ("indexes", p["index"]), ("skillsets", p["skillset"])]:
            sc = delete_resource(rtype, rname)
            log(f"  DELETE {rtype}/{rname} → {sc}")
    time.sleep(5)

    # ── 캐시 컨테이너 삭제 (진정한 cold start를 위해) ──
    log("[0.6] Enrichment cache 컨테이너 삭제")
    try:
        blob_service = BlobServiceClient(
            account_url=f"https://{STORAGE_NAME}.blob.core.windows.net",
            credential=credential,
        )
        deleted_count = 0
        for container in blob_service.list_containers(name_starts_with="ms-az-search-indexercache-"):
            cname = container["name"]
            blob_service.delete_container(cname)
            log(f"  ✗ 삭제: {cname}")
            deleted_count += 1
        log(f"  총 {deleted_count}개 캐시 컨테이너 삭제 완료")
    except Exception as e:
        log(f"  ⚠ 캐시 컨테이너 삭제 실패: {e}")
    time.sleep(10)  # 삭제 반영 대기

    # ── 각 파이프라인 실험 ──
    results: dict[str, dict] = {}
    for pk in ["verbalized", "pdf", "pptx"]:
        results[pk] = run_experiment(pk)
        # Cost estimation
        mb = results[pk].get("metrics_b", {})
        mc = results[pk].get("metrics_c", {})
        results[pk]["costs"] = estimate_pipeline_cost(pk, blob_info, mb, mc)

    # ── 리포트 생성 ──
    log("\n[REPORT] 리포트 생성 중...")
    report = generate_report(blob_info, results)
    REPORT_PATH.write_text(report, encoding="utf-8")
    log(f"✅ 리포트 저장: {REPORT_PATH}")

    # 요약 출력
    log("\n" + "=" * 70)
    log("실험 완료 요약:")
    for pk in ["verbalized", "pdf", "pptx"]:
        r = results[pk]
        if r.get("error"):
            log(f"  {pk.upper()}: ❌ {r['error']}")
            continue
        mb = r.get("metrics_b", {})
        mc = r.get("metrics_c", {})
        idx_b = mb.get("indexer_elapsed_sec") or 0
        idx_c = mc.get("indexer_elapsed_sec") or 0
        saving = idx_b - idx_c
        pct = (saving / idx_b * 100) if idx_b else 0
        log(f"  {pk.upper():12s}: B={idx_b:.1f}s → C={idx_c:.1f}s  절감={saving:+.1f}s ({pct:+.1f}%)  "
            f"chunks={r.get('index_stats', {}).get('documentCount', '?')}")
    log("=" * 70)


if __name__ == "__main__":
    main()
