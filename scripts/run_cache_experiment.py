#!/usr/bin/env python3
"""
캐싱 실험 백그라운드 스크립트 — 03-indexing.ipynb 시나리오 A~D 자동 실행 + 결과 리포트 생성.

출력:
  notebooks/REPORT_CACHE.md   — blob/JSONL/인덱스 문서 수 비교 + 시나리오별 소요시간
  stdout                       — 진행 로그

실행:
  cd /home/azureuser/localfiles/azure-ai-search-deepdive
  nohup python scripts/run_cache_experiment.py > logs/cache_exp.log 2>&1 &
"""
import json, os, sys, subprocess, time, traceback
from datetime import datetime, timezone

# ── 경로 세팅 ──
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from src.search.legal_indexes import PREC_INDEX, CONST_INDEX, INTERP_INDEX, ADMIN_INDEX

# ── 설정 ──
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
STORAGE_NAME = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
RAW_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw-documents")
PROCESSED_CONTAINER = "processed-documents"
ORCH_URL = os.environ.get("AZURE_FUNCTION_CRAWL_ORCH_URL", "")
API_VERSION = "2024-07-01"
EXP_SOURCE = "detc"

INDEX_META = {
    PREC_INDEX:   {"name": "판례",              "source": "prec",   "blob_prefix": "prec/"},
    CONST_INDEX:  {"name": "헌법재판소 결정례", "source": "detc",   "blob_prefix": "detc/"},
    INTERP_INDEX: {"name": "법제처 해석례",     "source": "expc",   "blob_prefix": "expc/"},
    ADMIN_INDEX:  {"name": "행정심판 재결례",   "source": "admrul", "blob_prefix": "admrul/"},
}

EXP_INDEXER = {"prec": "prec-blob-indexer", "detc": "const-blob-indexer",
               "expc": "interp-blob-indexer", "admrul": "admin-blob-indexer"}[EXP_SOURCE]

credential = DefaultAzureCredential(
    exclude_managed_identity_credential=True,
    exclude_workload_identity_credential=True,
)


def _hdr():
    tok = credential.get_token("https://search.azure.com/.default").token
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ── Blob 클라이언트 ──
# Storage 접근이 느려질 수 있으므로 비활성화 (Private Endpoint + 대량 blob)
raw_client = None
proc_client = None


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
#  데이터 집계 함수
# ═══════════════════════════════════════════════════════════════════
def count_blobs(container_client, prefix: str, suffix: str = ".json") -> int:
    if container_client is None:
        return -1
    try:
        return sum(1 for b in container_client.list_blobs(name_starts_with=prefix) if b.name.endswith(suffix))
    except Exception:
        return -1


def count_all_blobs() -> dict:
    """raw-documents 소스별 .json 파일 수"""
    result = {}
    for idx_name, meta in INDEX_META.items():
        result[idx_name] = count_blobs(raw_client, meta["blob_prefix"])
    return result


def count_all_jsonl() -> dict:
    """processed-documents 소스별 .jsonl 파일 수"""
    result = {}
    for idx_name, meta in INDEX_META.items():
        result[idx_name] = count_blobs(proc_client, meta["blob_prefix"], suffix=".jsonl")
    return result


def count_all_index_docs() -> dict:
    """AI Search 인덱스별 문서 수"""
    result = {}
    for idx_name in INDEX_META:
        try:
            url = f"{SEARCH_ENDPOINT}/indexes('{idx_name}')/docs/$count?api-version={API_VERSION}"
            r = requests.get(url, headers=_hdr(), timeout=30)
            result[idx_name] = int(r.text.strip()) if r.status_code == 200 else 0
        except Exception:
            result[idx_name] = 0
    return result


def get_indexer_status(indexer_name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexers('{indexer_name}')/status?api-version={API_VERSION}"
    r = requests.get(url, headers=_hdr(), timeout=30)
    r.raise_for_status()
    return r.json()


def get_index_stats(index_name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexes/{index_name}/stats?api-version={API_VERSION}"
    r = requests.get(url, headers=_hdr(), timeout=30)
    return r.json() if r.status_code == 200 else {}


def get_service_stats() -> dict:
    url = f"{SEARCH_ENDPOINT}/servicestats?api-version={API_VERSION}"
    r = requests.get(url, headers=_hdr(), timeout=30)
    return r.json() if r.status_code == 200 else {}


def blob_size_mib(container_client, prefix: str) -> float:
    if container_client is None:
        return 0.0
    try:
        total = sum(b.size for b in container_client.list_blobs(name_starts_with=prefix))
        return total / 1024 / 1024
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════
#  실험 실행 함수
# ═══════════════════════════════════════════════════════════════════
def run_setup(source: str, cache_on: bool, run: bool = False) -> tuple:
    """setup_ai_search_pipeline.py 호출. schedule=none 으로 자동 시작 방지."""
    env = os.environ.copy()
    env["SETUP_ENABLE_CACHE"] = "1" if cache_on else "0"
    cmd = [sys.executable, "scripts/setup_ai_search_pipeline.py",
           "--source", source, "--schedule", "none"]
    if run:
        cmd.append("--run")
    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    elapsed = time.time() - t0
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        log(f"  ⚠️ setup rc={result.returncode}, 출력 (마지막 500자):")
        log(f"  {output[-500:]}")
    return result.returncode, elapsed, output


def run_indexer_only(indexer_name: str, poll_interval: int = 10) -> dict:
    """POST /run + 완료 폴링. 409 (이미 실행 중) 도 gracefully 처리."""
    try:
        prev_last = get_indexer_status(indexer_name).get("lastResult") or {}
        prev_start = prev_last.get("startTime")
    except Exception:
        prev_start = None

    run_url = f"{SEARCH_ENDPOINT}/indexers/{indexer_name}/run?api-version={API_VERSION}"
    r = requests.post(run_url, headers=_hdr(), timeout=60)
    if r.status_code == 409:
        log(f"  indexer 이미 실행 중 (409) — 기존 실행 폴링")
        # 인덱서가 생성 시 자동 시작된 경우, prev_start와 cur_start가 같으므로
        # prev_start를 None으로 리셋하여 현재 실행을 "new"로 인식하게 함
        prev_start = None
    elif r.status_code not in (202, 204):
        log(f"  ⚠️ indexer run 실패: {r.status_code} {r.text[:300]}")
        return {"status": f"run_error_{r.status_code}", "items_processed": 0,
                "items_failed": 0, "elapsed_sec": 0}

    t0 = time.time()
    time.sleep(5)
    last = {}
    while True:
        try:
            data = get_indexer_status(indexer_name)
        except Exception as e:
            log(f"  ⚠️ status 조회 실패 (재시도): {e}")
            time.sleep(poll_interval)
            continue
        last = data.get("lastResult", {}) or {}
        st = last.get("status")
        cur_start = last.get("startTime")
        items = last.get("itemsProcessed")
        failed = last.get("itemsFailed")
        elapsed = int(time.time() - t0)
        is_new = cur_start and cur_start != prev_start
        log(f"  [{elapsed:>4d}s] status={st}  items={items}  failed={failed}  {'(new)' if is_new else '(prev)'}")
        if is_new and st in ("success", "transientFailure", "persistentFailure", "error"):
            break
        # 안전장치: inProgress 가 아닌 터미널 상태면 (prev 포함) 종료
        if st in ("success", "transientFailure", "persistentFailure", "error") and not (st == last.get("status") and items is None):
            log(f"  ⚠️ 터미널 상태 감지 (prev_start 불일치) — 종료")
            break
        time.sleep(poll_interval)
    return {
        "status": st, "items_processed": items, "items_failed": failed,
        "elapsed_sec": round(time.time() - t0, 2),
        "start_time": last.get("startTime"), "end_time": last.get("endTime"),
    }


def run_crawl_orch(source: str, max_pages: int = 2) -> dict:
    """Durable Functions orchestrator 호출 + 폴링."""
    if not ORCH_URL:
        log("  ORCH_URL 미설정 — B.5 스킵")
        return {"status": "skipped", "added": 0, "elapsed": 0}
    params = {"source": source, "max_pages": str(max_pages), "triggered_by": "cache-exp-bg"}
    t0 = time.time()
    sr = requests.post(ORCH_URL, params=params, timeout=120)
    log(f"  orchestrator POST status={sr.status_code}")
    if sr.status_code >= 400:
        log(f"  ❌ orchestrator POST 실패: {sr.status_code} {sr.text[:500]}")
        return {"status": "error", "output": sr.text[:500], "elapsed": round(time.time() - t0, 1)}
    try:
        sj = sr.json()
    except Exception:
        log(f"  ❌ orchestrator 응답 JSON 파싱 실패: {sr.text[:500]}")
        return {"status": "error", "output": sr.text[:500], "elapsed": round(time.time() - t0, 1)}
    status_uri = sj.get("statusQueryGetUri")
    log(f"  orchestrator started: instance={sj.get('id')}")
    last_rt = None
    output = None
    while True:
        elapsed = time.time() - t0
        s = requests.get(status_uri, timeout=30).json()
        rt = s.get("runtimeStatus")
        if rt != last_rt:
            log(f"  [{int(elapsed):>4d}s] runtimeStatus={rt}")
            last_rt = rt
        if rt in ("Completed", "Failed", "Terminated"):
            output = s.get("output")
            break
        if elapsed > 1800:
            break
        time.sleep(15)
    return {"status": last_rt, "output": output, "elapsed": round(time.time() - t0, 1)}


# ═══════════════════════════════════════════════════════════════════
#  메인 실행
# ═══════════════════════════════════════════════════════════════════
def main():
    experiment_start = datetime.now()
    log(f"=== 캐싱 실험 시작 (source={EXP_SOURCE}, indexer={EXP_INDEXER}) ===")

    # ── BEFORE 스냅샷 ──
    log("스냅샷: Blob/JSONL/인덱스 수 집계 (before) ...")
    blob_before = count_all_blobs()
    jsonl_before = count_all_jsonl()
    docs_before = count_all_index_docs()
    _bb_sum = sum(v for v in blob_before.values() if v >= 0)
    _jb_sum = sum(v for v in jsonl_before.values() if v >= 0)
    _db_sum = sum(docs_before.values())
    log(f"  Blob 합계: {_bb_sum:,}  JSONL 합계: {_jb_sum:,}  인덱스 합계: {_db_sum:,}")
    if any(v < 0 for v in blob_before.values()):
        log("  ⚠️ Storage 접근 불가 (publicNetworkAccess=Disabled?) — Blob/JSONL 수치는 -1로 표시")

    results = {}

    # ── A: 파이프라인 초기화 (캐시 OFF, 생성만) ──
    log("=" * 70)
    log(f"A. 파이프라인 초기화 (SETUP_ENABLE_CACHE=0, --run 없음) (source={EXP_SOURCE})")
    rc_a, elapsed_a, log_a = run_setup(EXP_SOURCE, cache_on=False, run=False)
    log(f"  rc={rc_a}  소요={elapsed_a:.1f}s")
    results["A"] = {"label": "파이프라인 초기화 (캐시 OFF, 생성만)", "elapsed": elapsed_a, "rc": rc_a}

    # ── B: 캐시 ON 파이프라인 생성 + REST API 로 인덱서 실행/폴링 ──
    log("=" * 70)
    log(f"B. 캐시 ON 전체 재인덱싱 (캐시 채움) (source={EXP_SOURCE})")
    rc_b, setup_elapsed_b, log_b = run_setup(EXP_SOURCE, cache_on=True, run=False)
    log(f"  B setup rc={rc_b}  소요={setup_elapsed_b:.1f}s")
    if rc_b != 0:
        log("  ⚠️ B setup 실패 — indexer 실행 건너뜀")
        elapsed_b = setup_elapsed_b
        results["B"] = {"label": "캐시 ON 전체 재인덱싱 (1차, 캐시 채움)", "elapsed": elapsed_b, "rc": rc_b}
    else:
        log(f"  B indexer 실행 시작 (REST API) ...")
        result_b = run_indexer_only(EXP_INDEXER)
        elapsed_b = setup_elapsed_b + result_b["elapsed_sec"]
        log(f"  B 완료: status={result_b['status']}  items={result_b['items_processed']}  "
            f"failed={result_b['items_failed']}  소요={elapsed_b:.1f}s ({int(elapsed_b//60)}m{int(elapsed_b%60)}s)")
        results["B"] = {"label": "캐시 ON 전체 재인덱싱 (1차, 캐시 채움)", "elapsed": elapsed_b,
                        "rc": rc_b, "status": result_b["status"],
                        "items": result_b["items_processed"], "failed": result_b["items_failed"]}

    # ── B.5: 크롤링으로 신규 데이터 추가 (실패해도 계속 진행) ──
    log("=" * 70)
    log("B.5 크롤링으로 신규 데이터 추가")
    added_n = 0
    try:
        blob_before_crawl = count_blobs(raw_client, f"{INDEX_META[CONST_INDEX]['blob_prefix']}")
        crawl_result = run_crawl_orch(EXP_SOURCE, max_pages=2)
        blob_after_crawl = count_blobs(raw_client, f"{INDEX_META[CONST_INDEX]['blob_prefix']}")
        if blob_before_crawl >= 0 and blob_after_crawl >= 0:
            added_n = blob_after_crawl - blob_before_crawl
        else:
            added_n = 0
            log("  ⚠️ Blob 카운팅 불가 — 추가 건수 미확인")
        log(f"  B.5 결과: status={crawl_result['status']}  추가={added_n}건  소요={crawl_result['elapsed']:.1f}s")
        results["B.5"] = {"label": f"크롤링 신규 데이터 추가 ({added_n}건)", "elapsed": crawl_result["elapsed"],
                          "status": crawl_result["status"], "added": added_n}
    except Exception as e:
        log(f"  ⚠️ B.5 크롤링 실패 (무시하고 계속): {e}")
        results["B.5"] = {"label": "크롤링 실패 (스킵)", "elapsed": 0, "status": "error", "added": 0}

    # ── C: Incremental Update (reset 없이 run) ──
    log("=" * 70)
    log(f"C. Incremental Update (reset 없이 run) (indexer={EXP_INDEXER})")
    result_c = run_indexer_only(EXP_INDEXER)
    elapsed_c = result_c["elapsed_sec"]
    log(f"  status={result_c['status']}  items={result_c['items_processed']}  failed={result_c['items_failed']}  소요={elapsed_c:.1f}s")
    results["C"] = {"label": f"Incremental Update (신규 {added_n}건)", "elapsed": elapsed_c,
                    "status": result_c["status"], "items": result_c["items_processed"],
                    "failed": result_c["items_failed"]}

    # ── D: 캐시 ON Reindex (2차 — 캐시 재사용 검증) ──
    log("=" * 70)
    log(f"D. 캐시 ON Reindex 2차 (캐시 재사용 검증) (source={EXP_SOURCE})")
    rc_d, setup_elapsed_d, log_d = run_setup(EXP_SOURCE, cache_on=True, run=False)
    log(f"  D setup rc={rc_d}  소요={setup_elapsed_d:.1f}s")
    if rc_d != 0:
        log("  ⚠️ D setup 실패 — indexer 실행 건너뜀")
        elapsed_d = setup_elapsed_d
        results["D"] = {"label": "캐시 ON 전체 재인덱싱 (2차, 캐시 재사용)", "elapsed": elapsed_d, "rc": rc_d}
    else:
        log(f"  D indexer 실행 시작 (REST API) ...")
        result_d = run_indexer_only(EXP_INDEXER)
        elapsed_d = setup_elapsed_d + result_d["elapsed_sec"]
        log(f"  D 완료: status={result_d['status']}  items={result_d['items_processed']}  "
            f"failed={result_d['items_failed']}  소요={elapsed_d:.1f}s ({int(elapsed_d//60)}m{int(elapsed_d%60)}s)")
        results["D"] = {"label": "캐시 ON 전체 재인덱싱 (2차, 캐시 재사용)", "elapsed": elapsed_d,
                        "rc": rc_d, "status": result_d["status"],
                        "items": result_d["items_processed"], "failed": result_d["items_failed"]}

    # ── AFTER 스냅샷 ──
    log("=" * 70)
    log("스냅샷: Blob/JSONL/인덱스 수 집계 (after) ...")
    blob_after = count_all_blobs()
    jsonl_after = count_all_jsonl()
    docs_after = count_all_index_docs()
    _ba_sum = sum(v for v in blob_after.values() if v >= 0)
    _ja_sum = sum(v for v in jsonl_after.values() if v >= 0)
    _da_sum = sum(docs_after.values())
    log(f"  Blob 합계: {_ba_sum:,}  JSONL 합계: {_ja_sum:,}  인덱스 합계: {_da_sum:,}")

    experiment_end = datetime.now()
    total_elapsed = (experiment_end - experiment_start).total_seconds()

    # ═══════════════════════════════════════════════════════════════
    #  REPORT_CACHE.md 생성
    # ═══════════════════════════════════════════════════════════════
    exp_name = next((m["name"] for m in INDEX_META.values() if m["source"] == EXP_SOURCE), EXP_SOURCE)

    md = []
    md.append("# Indexer Caching 효과 비교 리포트 (Reindex vs Incremental Update)")
    md.append("")
    md.append(f"> 측정일자: {experiment_start.strftime('%Y-%m-%d')} / Search: `{SEARCH_ENDPOINT}`")
    md.append(f"> 실험 소스: `{EXP_SOURCE}` ({exp_name}) / indexer: `{EXP_INDEXER}`")
    md.append(f"> Storage: `{STORAGE_NAME}` / 총 소요: {total_elapsed:.0f}s ({int(total_elapsed//60)}분 {int(total_elapsed%60)}초)")
    md.append("")
    md.append("---")
    md.append("")

    # ── 한눈에 보기 ──
    ea = results["A"]["elapsed"]
    eb = results["B"]["elapsed"]
    ec = results["C"]["elapsed"]
    ed = results["D"]["elapsed"]
    diff_bd = eb - ed
    pct_bd = diff_bd / eb * 100 if eb > 0 else 0
    speedup_cb = eb / ec if ec > 0 else float("inf")

    md.append("## 1. 한눈에 보기")
    md.append("")
    md.append("| 항목 | 값 |")
    md.append("|------|---:|")
    md.append(f"| A. 파이프라인 초기화 (캐시 OFF) | {ea:.1f}s |")
    md.append(f"| B. 캐시 ON Reindex 1차 (baseline) | {eb:.1f}s ({int(eb//60)}분 {int(eb%60)}초) |")
    md.append(f"| B.5 크롤링 신규 추가 | +{added_n}건 |")
    md.append(f"| C. Incremental Update | {ec:.1f}s |")
    md.append(f"| D. 캐시 ON Reindex 2차 (재사용) | {ed:.1f}s ({int(ed//60)}분 {int(ed%60)}초) |")
    md.append(f"| **C / B 가속비** | **x{speedup_cb:.1f}** |")
    md.append(f"| **B→D 캐시 재사용 절감** | **{diff_bd:+.1f}s ({pct_bd:+.1f}%)** |")
    md.append("")
    md.append("---")
    md.append("")

    # ── 데이터 현황 비교 ──
    md.append("## 1. 데이터 현황 (Before → After)")
    md.append("")
    md.append("| 인덱스 | 한국어명 | Blob JSON (before→after) | JSONL (before→after) | 인덱스 문서 (before→after) |")
    md.append("|--------|----------|--------------------------|----------------------|---------------------------|")
    t_blob_b, t_blob_a = 0, 0
    t_jsonl_b, t_jsonl_a = 0, 0
    t_docs_b, t_docs_a = 0, 0
    for idx_name, meta in INDEX_META.items():
        bb = blob_before.get(idx_name, 0)
        ba = blob_after.get(idx_name, 0)
        jb = jsonl_before.get(idx_name, 0)
        ja = jsonl_after.get(idx_name, 0)
        db = docs_before.get(idx_name, 0)
        da = docs_after.get(idx_name, 0)
        t_blob_b += max(bb, 0); t_blob_a += max(ba, 0)
        t_jsonl_b += max(jb, 0); t_jsonl_a += max(ja, 0)
        t_docs_b += db; t_docs_a += da
        if bb >= 0 and ba >= 0:
            blob_delta = f" (+{ba-bb})" if ba > bb else ""
            blob_col = f"{bb:,}→{ba:,}{blob_delta}"
        else:
            blob_col = "N/A"
        if jb >= 0 and ja >= 0:
            jsonl_delta = f" (+{ja-jb})" if ja > jb else ""
            jsonl_col = f"{jb:,}→{ja:,}{jsonl_delta}"
        else:
            jsonl_col = "N/A"
        docs_delta = f" (+{da-db})" if da > db else ""
        md.append(f"| {idx_name} | {meta['name']} | {blob_col} | {jsonl_col} | {db:,}→{da:,}{docs_delta} |")
    md.append(f"| **합계** | | **{t_blob_b:,}→{t_blob_a:,}** | **{t_jsonl_b:,}→{t_jsonl_a:,}** | **{t_docs_b:,}→{t_docs_a:,}** |")
    md.append("")

    # ── 인덱스별 스토리지/벡터 상세 ──
    md.append("### 인덱스별 스토리지")
    md.append("")
    md.append("| Index | docs | storage (MiB) | vector (MiB) | storage/doc (KB) | Blob 입력 (MiB) |")
    md.append("|-------|-----:|--------------:|-------------:|-----------------:|----------------:|")
    total_stor = total_vec = total_blob_mib = 0.0
    total_doc_count = 0
    for idx_name, meta in INDEX_META.items():
        ist = get_index_stats(idx_name)
        docs = ist.get("documentCount", 0)
        stor = ist.get("storageSize", 0) / 1024 / 1024
        vec = ist.get("vectorIndexSize", 0) / 1024 / 1024
        per_doc = (stor * 1024 / docs) if docs > 0 else 0
        b_mib = blob_size_mib(proc_client, f"{meta['blob_prefix']}")
        total_doc_count += docs; total_stor += stor; total_vec += vec; total_blob_mib += b_mib
        marker = " ⬅️" if meta["source"] == EXP_SOURCE else ""
        md.append(f"| `{idx_name}`{marker} | {docs:,} | {stor:.1f} | {vec:.1f} | {per_doc:.1f} | {b_mib:.1f} |")
    md.append(f"| **합계** | **{total_doc_count:,}** | **{total_stor:.1f}** | **{total_vec:.1f}** | — | **{total_blob_mib:.1f}** |")
    md.append("")

    # ── 서비스 전체 볼륨 ──
    svc = get_service_stats()
    svc_c = svc.get("counters", {})
    if svc_c:
        md.append("### AI Search 서비스 전체 사용량")
        md.append("")
        md.append("| 항목 | 사용량 | Quota | 사용률 |")
        md.append("|------|------:|------:|------:|")
        for key, label in [("storageSize", "Storage"), ("vectorIndexSize", "Vector")]:
            u = svc_c.get(key, {}).get("usage", 0) / 1024 / 1024
            q = svc_c.get(key, {}).get("quota", 1) / 1024 / 1024
            md.append(f"| {label} | {u:.1f} MiB | {q:.0f} MiB | {u/q*100:.2f}% |")
        doc_u = svc_c.get("documentCount", {}).get("usage", 0)
        idx_u = svc_c.get("indexesCount", {}).get("usage", 0)
        idx_q = svc_c.get("indexesCount", {}).get("quota", 1)
        md.append(f"| Documents | {doc_u:,} | — | — |")
        md.append(f"| Indexes | {idx_u} | {idx_q} | {idx_u/idx_q*100:.0f}% |")
        md.append("")

    md.append("---")
    md.append("")

    # ── 시나리오 결과 ──
    md.append("## 2. 캐싱 시나리오 결과")
    md.append("")
    md.append("| 시나리오 | 종류 | 소요(초) | 소요(분:초) | 비고 |")
    md.append("|----------|------|---------|------------|------|")
    for key in ["A", "B", "B.5", "C", "D"]:
        r = results.get(key, {})
        e = r.get("elapsed", 0)
        m, s = divmod(int(e), 60)
        kind = "Crawl" if key == "B.5" else ("Update" if key == "C" else "Reindex")
        note = ""
        if "rc" in r:
            note = f"rc={r['rc']}"
        elif "status" in r:
            note = f"status={r['status']}"
            if "items" in r:
                note += f", items={r['items']}, failed={r['failed']}"
            if "added" in r:
                note += f", 추가={r['added']}건"
        md.append(f"| {key}. {r.get('label', '')} | {kind} | {e:.1f} | {m}:{s:02d} | {note} |")
    md.append("")

    # ── 비교 분석 ──
    md.append("## 3. 비교 분석")
    md.append("")
    md.append(f"- **A (Setup only)**: {ea:.1f}s — 파이프라인 생성만 (indexer 실행 없음)")
    md.append(f"- **B (cache 채움 baseline)**: {eb:.1f}s — 캐시 ON 1차 Reindex")
    if ec > 0:
        md.append(f"- **C (incremental)**: {ec:.1f}s — vs B: x{eb/ec:.1f} 빠름")
    else:
        md.append(f"- **C (incremental)**: {ec:.1f}s")
    diff_bd = eb - ed
    pct_bd = diff_bd / eb * 100 if eb > 0 else 0
    md.append(f"- **D (cache 재사용 2차)**: {ed:.1f}s — vs B: {diff_bd:+.1f}s ({pct_bd:+.1f}%)")
    md.append("")

    md.append("### 해석")
    md.append("")
    md.append("- A 는 `setup_ai_search_pipeline.py` (--run 없음) → 파이프라인 생성만")
    md.append("- B, D 는 `setup_ai_search_pipeline.py --run` → indexer reset + 전체 재인덱싱")
    md.append("- C 는 reset 없이 `POST /indexers/{name}/run` → change tracking 기반 증분")
    md.append("- D 에서 enrichment cache HIT 시 임베딩 재호출을 건너뛰어 B 대비 시간 절감")
    md.append("")
    md.append("### 캐시 동작 정리")
    md.append("")
    md.append("| 동작 | Change Tracking | Enrichment Cache | 임베딩 비용 |")
    md.append("|------|:-:|:-:|---:|")
    md.append("| Incremental run (C) | ✅ 변경분만 | ✅ 기존 결과 재사용 | 변경분만 |")
    md.append("| Reindex + cache warm (D) | ❌ 전체 재처리 | ✅ 기존 결과 재사용 | **$0** (cache HIT) |")
    md.append("| Reindex + cache cold (B 1차) | ❌ 전체 재처리 | ❌ 캐시 비어있음 | **전액** |")
    md.append("")

    report_path = os.path.join(ROOT, "notebooks", "REPORT_CACHE.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    log(f"✅ REPORT_CACHE.md 저장: {report_path}")

    # ── JSON 결과 저장 (노트북에서 재로드용) ──
    json_data = {
        "experiment_start": experiment_start.isoformat(),
        "experiment_end": experiment_end.isoformat(),
        "total_elapsed_sec": total_elapsed,
        "source": EXP_SOURCE,
        "indexer": EXP_INDEXER,
        "blob_before": blob_before,
        "blob_after": blob_after,
        "jsonl_before": jsonl_before,
        "jsonl_after": jsonl_after,
        "docs_before": docs_before,
        "docs_after": docs_after,
        "scenarios": results,
    }
    json_path = os.path.join(ROOT, "notebooks", "cache_experiment_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
    log(f"✅ JSON 결과 저장: {json_path}")

    # ── 최종 요약 ──
    log("")
    log("=" * 70)
    log("실험 완료 요약")
    log("=" * 70)
    log(f"  Blob   : {t_blob_b:,} → {t_blob_a:,}")
    log(f"  JSONL  : {t_jsonl_b:,} → {t_jsonl_a:,}")
    log(f"  인덱스 : {t_docs_b:,} → {t_docs_a:,}")
    log(f"  A={ea:.0f}s  B={eb:.0f}s  C={ec:.0f}s  D={ed:.0f}s")
    log(f"  총 소요: {total_elapsed:.0f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ 실험 실패: {e}")
        traceback.print_exc()
        sys.exit(1)
