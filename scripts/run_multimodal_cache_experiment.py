#!/usr/bin/env python3
"""
멀티모달 인덱서 캐싱 효과 실험 — 백그라운드 실행 스크립트

노트북 05의 §7 캐싱 비교 실험을 독립 스크립트로 실행:
  A: 인덱스/인덱서 초기화 + 캐시 비우기
  B: cache ON reindex (1차 — 캐시 채움)
  C: cache ON reindex (2차 — 캐시 HIT)

결과를 multi-modal-report.md 로 저장합니다.

실행:
  cd /home/azureuser/localfiles/azure-ai-search-deepdive
  nohup uv run python scripts/run_multimodal_cache_experiment.py > logs/mm_cache_experiment.log 2>&1 &
"""
from __future__ import annotations

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
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
RG_NAME = os.environ["AZURE_RESOURCE_GROUP"]
CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw-documents")
TENANT_ID = os.environ.get("AZURE_TENANT_ID")

API_VERSION = "2024-11-01-preview"
SOURCE = "st"

# 인덱서/인덱스 이름
PDF_INDEXER = f"{SOURCE}-multimodal-pdf-indexer"
PPTX_INDEXER = f"{SOURCE}-multimodal-pptx-indexer"
VERBALIZED_INDEXER = f"{SOURCE}-multimodal-verbalized-indexer"
PDF_INDEX = f"{SOURCE}-multimodal-pdf-index"
PPTX_INDEX = f"{SOURCE}-multimodal-pptx-index"
VERBALIZED_INDEX = f"{SOURCE}-multimodal-verbalized-index"
ALL_INDEXERS = [PDF_INDEXER, PPTX_INDEXER, VERBALIZED_INDEXER]

BLOB_PREFIX_PDF = "raw/pdf/"
BLOB_PREFIX_PPTX = "raw/pptx/"

EXP_INDEXER = VERBALIZED_INDEXER
EXP_INDEX = VERBALIZED_INDEX

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


def run_indexer(name: str, max_retries: int = 5) -> bool:
    """인덱서 실행. 409 (다른 인덱서 실행 중) 시 대기 후 재시도."""
    for attempt in range(max_retries):
        url = f"{SEARCH_ENDPOINT}/indexers/{name}/run?api-version={API_VERSION}"
        r = requests.post(url, headers=get_search_headers())
        if r.status_code == 202:
            log(f"  ▶ {name} 실행 시작")
            return True
        if r.status_code == 409:
            wait = 30 * (attempt + 1)
            log(f"  ⏳ {name} 409 Conflict (attempt {attempt+1}/{max_retries}), {wait}s 대기 후 재시도")
            time.sleep(wait)
            continue
        log(f"  ✗ {name} 실행 실패: {r.status_code} {r.text[:300]}")
        return False
    log(f"  ✗ {name} 실행 실패: 409 Conflict 최대 재시도 초과")
    return False


def get_indexer_status(name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexers/{name}/status?api-version={API_VERSION}"
    r = requests.get(url, headers=get_search_headers())
    if r.status_code == 404:
        return {"status": "notFound"}
    return r.json()


def reset_indexer(name: str) -> bool:
    url = f"{SEARCH_ENDPOINT}/indexers/{name}/reset?api-version={API_VERSION}"
    r = requests.post(url, headers=get_search_headers())
    return r.status_code in (200, 204)


def get_index_stats(name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexes/{name}/stats?api-version={API_VERSION}"
    r = requests.get(url, headers=get_search_headers())
    return r.json() if r.status_code == 200 else {}


def _last_start_time(status: dict) -> str | None:
    last = status.get("lastResult") or {}
    return last.get("startTime")


def wait_until_idle(name: str, timeout_sec: int = 7200, poll_interval: int = 30) -> str:
    """인덱서의 현재 실행이 완료될 때까지 대기. 404면 즉시 리턴.
    scheduled 인덱서는 top-level status가 항상 'running'이므로
    executionHistory[0].status 기반으로 판단한다."""
    t0 = time.time()
    while True:
        st = get_indexer_status(name)
        top = st.get("status", "unknown")
        if top == "notFound":
            return "notFound"
        hist = st.get("executionHistory") or []
        latest_status = hist[0].get("status") if hist else None
        # inProgress가 아니면 idle
        if latest_status != "inProgress":
            return latest_status or top
        elapsed = int(time.time() - t0)
        if elapsed % 60 < poll_interval:
            log(f"    wait_idle {name}: top={top} hist0={latest_status} elapsed={elapsed}s")
        if time.time() - t0 > timeout_sec:
            log(f"  ⚠ wait_until_idle timeout (top={top})")
            return "timeout"
        time.sleep(poll_interval)


def wait_all_indexers_idle(timeout_sec: int = 7200) -> None:
    """모든 멀티모달 인덱서가 idle 상태가 될 때까지 대기."""
    for name in ALL_INDEXERS:
        st = wait_until_idle(name, timeout_sec=timeout_sec)
        log(f"  {name}: {st}")


def wait_indexer_complete(name: str, timeout_sec: int = 7200, poll_interval: int = 20,
                          baseline: str | None = "__auto__"):
    """인덱서의 새 실행이 시작되어 완료될 때까지 대기.
    lastResult 기반으로 판단 (executionHistory는 완료 후에만 채워지므로)."""
    if baseline == "__auto__":
        baseline = _last_start_time(get_indexer_status(name))
    start = time.time()
    log(f"  ⏳ {name} 완료 대기 (baseline={baseline})")
    while True:
        status = get_indexer_status(name)
        last = status.get("lastResult") or {}
        last_state = last.get("status", "unknown")
        last_start = last.get("startTime")
        processed = last.get("itemsProcessed", 0)
        failed = last.get("itemsFailed", 0)
        elapsed = int(time.time() - start)
        is_new = last_start is not None and last_start != baseline

        if elapsed % 60 < poll_interval:
            log(f"    [{elapsed:>4d}s] last={last_state} new={is_new} proc={processed} fail={failed}")

        if is_new and last_state in ("success", "transientFailure", "persistentFailure"):
            return last_state, last
        if elapsed > timeout_sec:
            log(f"    ⚠ timeout ({timeout_sec}s)")
            return "timeout", last
        time.sleep(poll_interval)


def get_indexer_metrics(name: str) -> dict:
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
    """Blob Storage의 멀티모달 파일 현황 조회."""
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


# ═══════════════════════════════════════════════════════════════
# Setup script wrapper — verbalized only
# ═══════════════════════════════════════════════════════════════

def run_setup_only(cache_on: bool, schedule: str = "none", timeout: int = 600) -> tuple[int, str]:
    """Setup 스크립트 실행 (인덱서 PUT만, run은 별도)."""
    env = os.environ.copy()
    env["SETUP_ENABLE_CACHE"] = "1" if cache_on else "0"
    log(f"  setup (cache={'ON' if cache_on else 'OFF'}, pipeline=verbalized, schedule={schedule})")
    res = subprocess.run(
        [sys.executable, "scripts/setup_ai_search_multimodal_pipeline.py",
         "--source", SOURCE, "--pipeline", "verbalized", "--schedule", schedule],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env, check=False,
    )
    if res.returncode != 0:
        log(f"  setup FAILED (rc={res.returncode})")
        log(f"  stdout: {res.stdout[-500:]}")
        log(f"  stderr: {res.stderr[-500:]}")
        return res.returncode, res.stderr[-300:]
    for line in res.stdout.splitlines()[-5:]:
        log(f"    {line}")
    return 0, ""


def run_and_wait(name: str, timeout: int = 7200) -> tuple[int, float, str]:
    """인덱서 reset → run → 완료 대기. wall clock 반환."""
    t0 = time.time()
    # reset → 전 문서 재처리 강제
    log(f"  reset {name}")
    reset_indexer(name)
    time.sleep(5)
    # run (409 재시도 포함)
    if not run_indexer(name):
        return 1, time.time() - t0, "run_indexer failed"
    time.sleep(5)
    state, last = wait_indexer_complete(name, timeout_sec=timeout, poll_interval=20)
    elapsed = time.time() - t0
    summary = f"state={state} processed={last.get('itemsProcessed', 0)} failed={last.get('itemsFailed', 0)}"
    return (0 if state == "success" else 2), elapsed, summary


# ═══════════════════════════════════════════════════════════════
# Cost estimation
# ═══════════════════════════════════════════════════════════════

def estimate_costs(blob_info: dict, metrics_b: dict, metrics_c: dict) -> dict:
    """GPT/DI/Embedding 비용 추정."""
    n_pdf = len(blob_info.get("pdf", []))
    total_pdf_bytes = sum(b["size"] for b in blob_info.get("pdf", []))
    est_pages = max(1, total_pdf_bytes // (50 * 1024))

    items_b = metrics_b.get("items_processed", 0)
    items_c = metrics_c.get("items_processed", 0)

    # DI Layout: ~$0.015/page
    di_cost_per_page = 0.015
    di_cost_b = est_pages * di_cost_per_page
    di_cost_c = 0.0  # cache HIT

    # GPT verbalize: GPT-4o — $2.50/1M input, $10/1M output
    gpt_input_tokens_per_page = 1500
    gpt_output_tokens_per_page = 500
    gpt_cost_per_page = (gpt_input_tokens_per_page * 2.50 + gpt_output_tokens_per_page * 10.0) / 1_000_000
    gpt_total_input_tokens = est_pages * gpt_input_tokens_per_page
    gpt_total_output_tokens = est_pages * gpt_output_tokens_per_page
    gpt_cost_b = est_pages * gpt_cost_per_page
    gpt_cost_c = 0.0  # cache HIT

    # Embedding: $0.13/1M tokens
    avg_tokens_per_chunk = 500
    emb_cost_per_1m = 0.13
    emb_cost_b = items_b * avg_tokens_per_chunk * emb_cost_per_1m / 1_000_000
    emb_cost_c = items_c * avg_tokens_per_chunk * emb_cost_per_1m / 1_000_000

    return {
        "n_pdf": n_pdf,
        "n_pptx": len(blob_info.get("pptx", [])),
        "total_pdf_bytes": total_pdf_bytes,
        "est_pages": est_pages,
        "chunks_b": items_b,
        "chunks_c": items_c,
        "di_cost_b": di_cost_b,
        "di_cost_c": di_cost_c,
        "gpt_cost_b": gpt_cost_b,
        "gpt_cost_c": gpt_cost_c,
        "gpt_cost_per_page": gpt_cost_per_page,
        "gpt_total_input_tokens": gpt_total_input_tokens,
        "gpt_total_output_tokens": gpt_total_output_tokens,
        "emb_cost_b": emb_cost_b,
        "emb_cost_c": emb_cost_c,
        "total_b": di_cost_b + gpt_cost_b + emb_cost_b,
        "total_c": di_cost_c + gpt_cost_c + emb_cost_c,
    }


# ═══════════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════════

def generate_report(
    blob_info: dict,
    metrics_b: dict,
    metrics_c: dict,
    wall_b: float,
    wall_c: float,
    rc_b: int,
    rc_c: int,
    index_stats: dict,
    costs: dict,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    idx_b = metrics_b.get("indexer_elapsed_sec") or 0
    idx_c = metrics_c.get("indexer_elapsed_sec") or 0
    saving_sec = idx_b - idx_c
    saving_pct = (saving_sec / idx_b * 100) if idx_b else 0

    # Index stats
    idx_rows = []
    total_docs = 0
    total_storage = 0
    total_vector = 0
    for name in [PDF_INDEX, PPTX_INDEX, VERBALIZED_INDEX]:
        st = index_stats.get(name, {})
        docs = st.get("documentCount", 0)
        storage_mib = st.get("storageSize", 0) / (1024 * 1024)
        vector_mib = st.get("vectorIndexSize", 0) / (1024 * 1024)
        total_docs += docs
        total_storage += storage_mib
        total_vector += vector_mib
        idx_rows.append(f"| `{name}` | {docs:,} | {storage_mib:.1f} | {vector_mib:.1f} |")

    n_pdf = costs["n_pdf"]
    n_pptx = costs["n_pptx"]
    total_blob_bytes = sum(b["size"] for b in blob_info.get("pdf", [])) + sum(b["size"] for b in blob_info.get("pptx", []))
    total_blob_mib = total_blob_bytes / (1024 * 1024)

    md = f"""# 멀티모달 인덱싱 — 캐싱 효과 실험 리포트

> 측정일자: {now}
> Region: `swedencentral` / Search Service: `{SEARCH_ENDPOINT.split("//")[1].split(".")[0]}`
> 실험 대상 인덱서: `{EXP_INDEXER}` (Verbalized pipeline: DI Layout → GPT Verbalize → Markdown Split → Embedding)
> 실험 대상 인덱스: `{EXP_INDEX}`

---

## 1. 한눈에 보기

| 항목 | 값 |
|------|---:|
| **Blob PDF 파일 수** | **{n_pdf}** |
| **Blob PPTX 파일 수** | **{n_pptx}** |
| **Blob 총 크기** | **{total_blob_mib:.1f} MiB** |
| **추정 총 페이지 수** | **~{costs["est_pages"]}** |
| **B (cache 채움) indexer 소요** | **{idx_b:.1f} s** ({idx_b/60:.1f} min) |
| **C (cache HIT) indexer 소요** | **{idx_c:.1f} s** ({idx_c/60:.1f} min) |
| **캐시 HIT 시간 절감** | **{saving_sec:+.1f} s ({saving_pct:+.1f}%)** |
| **B 인덱싱 청크 수** | **{metrics_b.get("items_processed", 0):,}** |
| **C 인덱싱 청크 수** | **{metrics_c.get("items_processed", 0):,}** |
| **B 실패 건수** | **{metrics_b.get("items_failed", 0)}** |
| **C 실패 건수** | **{metrics_c.get("items_failed", 0)}** |
| **B 예상 API 비용** | **${costs["total_b"]:.4f}** |
| **C 예상 API 비용 (cache HIT)** | **${costs["total_c"]:.4f}** |
| **비용 절감** | **${costs["total_b"] - costs["total_c"]:.4f}** |

---

## 2. 실험 시나리오 결과

### 2.1 시나리오 설명

| | 시나리오 | cache 설정 | 동작 |
|---|---|---|---|
| **A** | 초기화 | — | verbalized 인덱서/인덱스 삭제 → 재생성 (cache OFF) → 캐시 완전 비움 |
| **B** | cache ON (1차) | `SETUP_ENABLE_CACHE=1` | reset + run → DI/GPT 전부 호출, 캐시 채움 |
| **C** | cache ON (2차) | `SETUP_ENABLE_CACHE=1` | reset + run → 캐시 HIT → DI/GPT skip |

### 2.2 측정 결과

| 시나리오 | wall clock (s) | indexer 소요 (s) | 처리 청크 | 실패 | rc |
|----------|---------------:|-----------------:|----------:|-----:|---:|
| A. 초기화 | — | — | — | — | — |
| B. cache 채움 | {wall_b:.1f} | {idx_b:.1f} | {metrics_b.get("items_processed", 0)} | {metrics_b.get("items_failed", 0)} | {rc_b} |
| C. cache HIT | {wall_c:.1f} | {idx_c:.1f} | {metrics_c.get("items_processed", 0)} | {metrics_c.get("items_failed", 0)} | {rc_c} |

### 2.3 캐시 효과 분석

| 비교 | indexer 소요 | 차이 | 절감률 |
|------|------------:|-----:|-------:|
| B (baseline, cache 채움) | {idx_b:.1f} s | — | — |
| C (cache HIT) | {idx_c:.1f} s | {saving_sec:+.1f} s | {saving_pct:+.1f}% |

{"**✅ 캐시 HIT 효과 확인**: DI Layout + GPT Verbalize 호출이 Storage 캐시 조회로 대체되어 큰 폭 단축." if saving_sec > 0 else "⚠️ 캐시 효과 미확인 — 데이터나 설정 점검 필요."}

---

## 3. Blob Storage 파일 현황

| 유형 | 파일 수 | 총 크기 |
|------|--------:|--------:|
| PDF | {n_pdf} | {sum(b["size"] for b in blob_info.get("pdf", [])) / (1024*1024):.1f} MiB |
| PPTX | {n_pptx} | {sum(b["size"] for b in blob_info.get("pptx", [])) / (1024*1024):.1f} MiB |
| **합계** | **{n_pdf + n_pptx}** | **{total_blob_mib:.1f} MiB** |

### 3.1 파일 목록

"""
    md += "**PDF 파일:**\n\n"
    for b in blob_info.get("pdf", []):
        md += f"- `{b['name']}` ({b['size'] / 1024:.0f} KB)\n"
    md += "\n"
    if blob_info.get("pptx"):
        md += "**PPTX 파일:**\n\n"
        for b in blob_info.get("pptx", []):
            md += f"- `{b['name']}` ({b['size'] / 1024:.0f} KB)\n"
        md += "\n"

    md += f"""---

## 4. 인덱스 통계

| 인덱스 | 문서 수 | Storage (MiB) | Vector (MiB) |
|--------|--------:|--------------:|-------------:|
{chr(10).join(idx_rows)}
| **합계** | **{total_docs:,}** | **{total_storage:.1f}** | **{total_vector:.1f}** |

---

## 5. 비용 추정

### 5.1 Verbalized 파이프라인 스킬별 단가

| 스킬 | 단가 | 비고 |
|------|------|------|
| `DocumentIntelligenceLayoutSkill` | ~$0.015 / 페이지 | DI Layout API (문서에서 마크다운 추출) |
| `ChatCompletionSkill` (GPT-4o verbalize) | ~${costs["gpt_cost_per_page"]:.5f} / 호출 | 이미지/도표 설명 생성 (input ~1.5K + output ~0.5K tokens) |
| `AzureOpenAIEmbeddingSkill` (text-embedding-3-large) | $0.13 / 1M tokens | 청크별 벡터 생성 |

### 5.2 GPT 토큰 사용량 추정

| 항목 | B (cache 채움) | C (cache HIT) |
|------|---------------:|---------------:|
| GPT input tokens | ~{costs["gpt_total_input_tokens"]:,} | 0 (cache) |
| GPT output tokens | ~{costs["gpt_total_output_tokens"]:,} | 0 (cache) |
| Embedding tokens | ~{costs["chunks_b"] * 500:,} | ~{costs["chunks_c"] * 500:,} |

### 5.3 시나리오별 비용 비교

| 항목 | B (cache 채움) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout ({costs["est_pages"]} pages) | ${costs["di_cost_b"]:.4f} | ${costs["di_cost_c"]:.4f} | ${costs["di_cost_b"] - costs["di_cost_c"]:.4f} |
| GPT Verbalize ({costs["est_pages"]} calls) | ${costs["gpt_cost_b"]:.4f} | ${costs["gpt_cost_c"]:.4f} | ${costs["gpt_cost_b"] - costs["gpt_cost_c"]:.4f} |
| Embedding ({costs["chunks_b"]} / {costs["chunks_c"]} chunks) | ${costs["emb_cost_b"]:.4f} | ${costs["emb_cost_c"]:.4f} | ${costs["emb_cost_b"] - costs["emb_cost_c"]:.4f} |
| **합계** | **${costs["total_b"]:.4f}** | **${costs["total_c"]:.4f}** | **${costs["total_b"] - costs["total_c"]:.4f}** |

> Cache HIT 시 DI Layout과 GPT Verbalize 호출이 완전히 skip → **시간·비용 모두 절감**.
> Embedding은 cache 유무와 관계없이 재호출됨 (indexProjection 재구성 시).

### 5.4 대규모 추정 (100 PDF 기준)

| 항목 | 100 PDF (~{costs["est_pages"] * 100 // max(n_pdf, 1)} pages) |
|------|---:|
| 1회 인덱싱 비용 | ~${costs["total_b"] * 100 / max(n_pdf, 1):.2f} |
| cache HIT 재인덱싱 | ~${costs["total_c"] * 100 / max(n_pdf, 1):.2f} |
| **절감** | **~${(costs["total_b"] - costs["total_c"]) * 100 / max(n_pdf, 1):.2f}** |

---

## 6. 캐싱 메커니즘 해석

### 6.1 왜 멀티모달에서 캐시가 효과적인가?

| 스킬 | 1건 처리 시간 | cache HIT (Storage lookup) | 효과 |
|------|-------------:|---------------------------:|------|
| `DocumentIntelligenceLayoutSkill` | **2–10 s / page** | ~30–150 ms | **✅ 시간·비용 모두 이득** |
| `ChatCompletionSkill` (GPT verbalize) | **3–8 s / call** | ~30–150 ms | **✅ 시간·비용 모두 이득** |
| `AzureOpenAIEmbeddingSkill` | ~5 ms / doc | ~30–150 ms | ❌ cache overhead > 원래 비용 |

→ DI Layout + GPT Verbalize가 전체 처리 시간의 **90% 이상**을 차지하므로,
  이 두 스킬의 cache HIT만으로 전체 파이프라인 시간을 **대폭 단축**.

### 6.2 텍스트 전용 파이프라인과 비교 (노트북 03 §6)

| 파이프라인 | dominant skill | cache 효과 |
|-----------|---------------|-----------|
| 텍스트 (notebook 03) | `EmbeddingSkill` (5ms/doc, batch) | ❌ 오히려 손해 (lookup > embedding) |
| **멀티모달 (notebook 05)** | **DI Layout + GPT** (수 초/doc) | **✅ 큰 폭 절감** |

---

## 7. Indexer 실행 상세 로그

### B (cache 채움)

| 항목 | 값 |
|------|------|
| 시작 | `{metrics_b.get("start_time", "N/A")}` |
| 종료 | `{metrics_b.get("end_time", "N/A")}` |
| 상태 | `{metrics_b.get("status", "N/A")}` |
| 처리 | {metrics_b.get("items_processed", 0)} 청크 |
| 실패 | {metrics_b.get("items_failed", 0)} 건 |

### C (cache HIT)

| 항목 | 값 |
|------|------|
| 시작 | `{metrics_c.get("start_time", "N/A")}` |
| 종료 | `{metrics_c.get("end_time", "N/A")}` |
| 상태 | `{metrics_c.get("status", "N/A")}` |
| 처리 | {metrics_c.get("items_processed", 0)} 청크 |
| 실패 | {metrics_c.get("items_failed", 0)} 건 |
"""

    for label, m in [("B", metrics_b), ("C", metrics_c)]:
        if m.get("warnings"):
            md += f"\n### {label} — Warnings\n\n"
            for w in m["warnings"][:10]:
                md += f"- {w.get('message', '')[:200]}\n"
        if m.get("errors"):
            md += f"\n### {label} — Errors\n\n"
            for e in m["errors"][:10]:
                md += f"- {e.get('message', '')[:200]}\n"

    md += f"""
---

## 8. 실험 조건

| 항목 | 값 |
|------|------|
| Search Endpoint | `{SEARCH_ENDPOINT}` |
| Storage Account | `{STORAGE_NAME}` |
| Container | `{CONTAINER_NAME}` |
| PDF Blob Prefix | `{BLOB_PREFIX_PDF}` |
| PPTX Blob Prefix | `{BLOB_PREFIX_PPTX}` |
| Embedding Model | text-embedding-3-large (dim 3072) |
| Pipeline | Verbalized (DI Layout → GPT-4o Verbalize → Markdown Split → Embedding) |
"""
    return md


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    log("=" * 70)
    log("멀티모달 캐싱 효과 실험 시작")
    log("=" * 70)

    # ── 1. Blob 현황 조회 (업로드는 seed 스크립트로 이미 완료) ──
    log("[1/5] Blob 현황 조회")
    blob_info = get_blob_info()
    n_pdf = len(blob_info["pdf"])
    n_pptx = len(blob_info["pptx"])
    total_bytes = sum(b["size"] for b in blob_info["pdf"]) + sum(b["size"] for b in blob_info["pptx"])
    log(f"  PDF: {n_pdf}개, PPTX: {n_pptx}개, 총 {total_bytes / (1024*1024):.1f} MiB")
    for b in blob_info["pdf"]:
        log(f"    {b['name']} ({b['size'] / 1024:.0f} KB)")
    for b in blob_info["pptx"]:
        log(f"    {b['name']} ({b['size'] / 1024:.0f} KB)")

    if n_pdf == 0:
        log("  ⚠️ PDF 파일 없음! seed 스크립트를 먼저 실행하세요.")
        return

    # ── 2. 시나리오 A: 초기화 (인덱서·인덱스 삭제 → 캐시 완전 비움) ──
    log("[2/6] 시나리오 A: verbalized 인덱서/인덱스 삭제")

    # 2a) verbalized 인덱서 삭제 (실행 중이면 대기 후 삭제)
    wait_until_idle(EXP_INDEXER, timeout_sec=7200)
    headers = get_search_headers()
    r = requests.delete(
        f"{SEARCH_ENDPOINT}/indexers/{EXP_INDEXER}?api-version={API_VERSION}",
        headers=headers,
    )
    log(f"  DELETE indexer {EXP_INDEXER} → {r.status_code}")

    # 2b) verbalized 인덱스 삭제
    r = requests.delete(
        f"{SEARCH_ENDPOINT}/indexes/{EXP_INDEX}?api-version={API_VERSION}",
        headers=headers,
    )
    log(f"  DELETE index {EXP_INDEX} → {r.status_code}")
    log("[A 완료] 초기화 완료 — 인덱서/인덱스/캐시 삭제됨")

    # ── 3. 시나리오 B: cache ON, 1차 (캐시 채움) ──
    log("[3/6] 시나리오 B: cache ON 인덱서 생성 + 1차 실행 (캐시 채움)")

    # 3a) baseline 캡처 (인덱서 삭제 후이므로 None)
    pre_setup_baseline = _last_start_time(get_indexer_status(EXP_INDEXER))
    log(f"  baseline (setup 전): {pre_setup_baseline}")

    # 3b) setup — cache ON, schedule none
    rc, err = run_setup_only(cache_on=True, schedule="none")
    if rc != 0:
        log(f"  ✗ setup 실패, 중단: {err}")
        return

    # 3c) PUT으로 인덱서 생성됨 → Azure가 자동 실행 시작
    # baseline을 setup 이전 값(None)으로 넘겨서 자동 실행을 "new"로 감지
    log("  PUT 후 자동 실행 완료 대기...")
    time.sleep(10)  # 자동 실행 시작까지 잠시 대기
    state_b, last_b = wait_indexer_complete(EXP_INDEXER, timeout_sec=7200,
                                             poll_interval=20, baseline=pre_setup_baseline)
    wall_b_auto = last_b.get("endTime", "")
    metrics_b = get_indexer_metrics(EXP_INDEXER)
    log(f"  [B-auto 결과] state={state_b} items={metrics_b['items_processed']} "
        f"failed={metrics_b['items_failed']} elapsed={metrics_b['indexer_elapsed_sec']}s")

    # 자동 실행으로 0건이면 수동 reset+run 시도
    if metrics_b["items_processed"] == 0:
        log("  ⚠ 자동 실행에서 0건 → 수동 reset+run 시도")
        rc_b, wall_b, _ = run_and_wait(EXP_INDEXER, timeout=7200)
        metrics_b = get_indexer_metrics(EXP_INDEXER)
        log(f"  [B-manual 결과] rc={rc_b} wall={wall_b:.1f}s items={metrics_b['items_processed']} "
            f"failed={metrics_b['items_failed']} elapsed={metrics_b['indexer_elapsed_sec']}s")
    else:
        wall_b = metrics_b["indexer_elapsed_sec"] or 0
        rc_b = 0 if state_b == "success" else 2

    log(f"  [B 최종] items={metrics_b['items_processed']} elapsed={metrics_b['indexer_elapsed_sec']}s")

    # ── 4. 시나리오 C: cache ON, 2차 (캐시 HIT) ──
    log("[4/6] 시나리오 C: cache ON reset+run (2차 — 캐시 HIT)")
    rc_c, wall_c, _ = run_and_wait(EXP_INDEXER, timeout=7200)
    metrics_c = get_indexer_metrics(EXP_INDEXER)
    log(f"  [C 결과] rc={rc_c} wall={wall_c:.1f}s indexer={metrics_c['indexer_elapsed_sec']}s "
        f"items={metrics_c['items_processed']} failed={metrics_c['items_failed']}")

    # B vs C 요약
    idx_b = metrics_b.get("indexer_elapsed_sec") or 0
    idx_c = metrics_c.get("indexer_elapsed_sec") or 0
    if idx_b:
        saving = idx_b - idx_c
        pct = saving / idx_b * 100
        log(f"\n  {'='*50}")
        log(f"  B (cache 채움): {idx_b:.1f}s ({idx_b/60:.1f}min)")
        log(f"  C (cache HIT):  {idx_c:.1f}s ({idx_c/60:.1f}min)")
        log(f"  절감: {saving:+.1f}s ({pct:+.1f}%)")
        log(f"  {'='*50}")

    # ── 5. 리포트 생성 ──
    log("[5/6] 리포트 생성")

    index_stats = {}
    for name in [PDF_INDEX, PPTX_INDEX, VERBALIZED_INDEX]:
        index_stats[name] = get_index_stats(name)

    costs = estimate_costs(blob_info, metrics_b, metrics_c)

    report = generate_report(
        blob_info=blob_info,
        metrics_b=metrics_b,
        metrics_c=metrics_c,
        wall_b=wall_b,
        wall_c=wall_c,
        rc_b=rc_b,
        rc_c=rc_c,
        index_stats=index_stats,
        costs=costs,
    )

    REPORT_PATH.write_text(report, encoding="utf-8")
    log(f"  ✅ 리포트 저장: {REPORT_PATH}")
    log("\n실험 완료!")


if __name__ == "__main__":
    main()
