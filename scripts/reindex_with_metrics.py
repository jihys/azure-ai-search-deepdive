"""
인덱싱 옵션 B 검증: baseline 측정 → 인덱스 재생성 → 메트릭 수집
- 총 시간 / 임베딩 토큰 / 인덱스 문서 수 / blob 데이터 크기 / AI Search 스토리지
"""
import os, sys, time, subprocess, json, requests
from datetime import datetime
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

load_dotenv()
EP = os.environ.get("AZURE_SEARCH_ENDPOINT") or os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
KEY = os.environ["AZURE_SEARCH_ADMIN_KEY"]
HD = {"api-key": KEY, "Content-Type": "application/json"}
STG = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
PROC_CONTAINER = "processed-documents"

SOURCES = [
    ("prec",   "prec-blob-indexer",   "prec-court-index"),
    ("detc",   "const-blob-indexer",  "const-court-index"),
    ("expc",   "interp-blob-indexer", "legis-interp-index"),
    ("admrul", "admin-blob-indexer",  "admin-appeal-index"),
]

def search_stats():
    r = requests.get(f"{EP}/servicestats?api-version=2024-07-01", headers=HD).json()
    return r

def index_stats(name):
    r = requests.get(f"{EP}/indexes/{name}/stats?api-version=2024-07-01", headers=HD).json()
    return r

def blob_size(prefix):
    cred = DefaultAzureCredential()
    cc = BlobServiceClient(account_url=f"https://{STG}.blob.core.windows.net", credential=cred).get_container_client(PROC_CONTAINER)
    total_b, files = 0, 0
    for b in cc.list_blobs(name_starts_with=prefix):
        total_b += b.size; files += 1
    return total_b, files

print(f"\n{'='*70}\n[1] BASELINE (인덱싱 전)\n{'='*70}")
svc_before = search_stats()
print(f"AI Search storage (전체): {svc_before['counters']['storageSize']['usage']/1024/1024:.1f} MiB / quota {svc_before['counters']['storageSize']['quota']/1024/1024:.1f} MiB")
print(f"vector index size       : {svc_before['counters']['vectorIndexSize']['usage']/1024/1024:.1f} MiB")
print(f"document count (전체)   : {svc_before['counters']['documentCount']['usage']:,}")

baseline_per_index = {}
print("\n[Per-index baseline]")
for src, idxer, idx in SOURCES:
    s = index_stats(idx)
    baseline_per_index[idx] = s
    print(f"  {idx:<25} docs={s.get('documentCount',0):>7,}  storage={s.get('storageSize',0)/1024/1024:>7.1f} MiB  vector={s.get('vectorIndexSize',0)/1024/1024:>7.1f} MiB")

print("\n[Blob 데이터 (입력)]")
blob_totals = {}
for src, idxer, idx in SOURCES:
    b, f = blob_size(f"{src}/")
    blob_totals[src] = (b, f)
    print(f"  {src:<8} files={f:>4}  size={b/1024/1024:>7.1f} MiB")

# ─── 인덱싱 실행 ───
print(f"\n{'='*70}\n[2] 인덱싱 실행 (옵션 B: cache 활성화 + 인덱스 재생성)\n{'='*70}")
overall_start = time.time()
per_source_time = {}
for src, idxer, idx in SOURCES:
    print(f"\n--- {src} ---")
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "scripts/setup_ai_search_pipeline.py", "--source", src, "--run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
    )
    elapsed = time.time() - t0
    per_source_time[src] = elapsed
    # 마지막 50줄만 보여줌
    lines = r.stdout.splitlines()
    for ln in lines[-30:]:
        print(ln)
    print(f"  → {src} 종료 코드={r.returncode} 소요={elapsed:.1f}s")

overall_elapsed = time.time() - overall_start
print(f"\n총 소요 시간: {overall_elapsed:.1f}s ({overall_elapsed/60:.1f} min)")

# ─── 사후 측정 ───
print(f"\n{'='*70}\n[3] 사후 측정\n{'='*70}")
time.sleep(5)
svc_after = search_stats()
print(f"AI Search storage (전체): {svc_after['counters']['storageSize']['usage']/1024/1024:.1f} MiB (Δ {(svc_after['counters']['storageSize']['usage']-svc_before['counters']['storageSize']['usage'])/1024/1024:+.1f} MiB)")
print(f"vector index size       : {svc_after['counters']['vectorIndexSize']['usage']/1024/1024:.1f} MiB (Δ {(svc_after['counters']['vectorIndexSize']['usage']-svc_before['counters']['vectorIndexSize']['usage'])/1024/1024:+.1f} MiB)")
print(f"document count (전체)   : {svc_after['counters']['documentCount']['usage']:,}")

print("\n[Per-index 결과]")
print(f"{'index':<22} {'docs':>8} {'storage':>12} {'vector':>10} {'time':>8}")
total_processed = 0; total_failed = 0; total_size = 0; total_vec = 0
for src, idxer, idx in SOURCES:
    s = index_stats(idx)
    storage_mb = s.get('storageSize',0)/1024/1024
    vec_mb = s.get('vectorIndexSize',0)/1024/1024
    docs = s.get('documentCount',0)
    total_size += s.get('storageSize',0); total_vec += s.get('vectorIndexSize',0)
    print(f"{idx:<22} {docs:>8,} {storage_mb:>9.1f} MiB {vec_mb:>7.1f} MiB {per_source_time[src]:>6.1f}s")
    # indexer last result
    st = requests.get(f"{EP}/indexers/{idxer}/status?api-version=2024-07-01", headers=HD).json()
    last = st.get('lastResult') or {}
    total_processed += last.get('itemsProcessed',0)
    total_failed += last.get('itemsFailed',0)
    print(f"  └ indexer status={last.get('status')} processed={last.get('itemsProcessed')} failed={last.get('itemsFailed')} duration={last.get('endTime','')[:19]}")

# ─── 비용 추정 ───
print(f"\n{'='*70}\n[4] 비용 추정 (text-embedding-3-large = $0.13 / 1M token)\n{'='*70}")
# 평균 임베딩 입력 토큰: 요약 필드 ~500 token (보수적)
EST_TOK_PER_DOC = 500
est_tokens = total_processed * EST_TOK_PER_DOC
est_cost = est_tokens / 1_000_000 * 0.13
print(f"임베딩 처리 문서: {total_processed:,}")
print(f"예상 토큰     : ~{est_tokens:,} (가정: {EST_TOK_PER_DOC} token/doc)")
print(f"예상 비용     : ~${est_cost:.2f}")
print(f"실패 문서     : {total_failed}")

# ─── 요약 ───
print(f"\n{'='*70}\n[SUMMARY]\n{'='*70}")
print(f"  총 인덱싱 시간  : {overall_elapsed:.1f}s ({overall_elapsed/60:.1f} min)")
print(f"  인덱싱 문서     : {total_processed:,} (실패 {total_failed})")
print(f"  Blob 입력 크기   : {sum(b for b,_ in blob_totals.values())/1024/1024:.1f} MiB ({sum(f for _,f in blob_totals.values())} files)")
print(f"  AI Search 사용량: {total_size/1024/1024:.1f} MiB (벡터 {total_vec/1024/1024:.1f} MiB)")
print(f"  예상 임베딩 비용: ~${est_cost:.2f}")
