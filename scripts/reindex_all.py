"""
전체 4개 소스 인덱싱 파이프라인 재실행 + 결과 리포트 생성

노트북 03-indexing.ipynb 의 핵심 흐름을 단일 스크립트로 통합:
  1. 환경 설정 + Blob 현황 집계
  2. setup_ai_search_pipeline.py --source {src} --run  (4개 순차 실행)
  3. 인덱서 상태 폴링 + 문서 수 검증
  4. Knowledge Agent + Knowledge Sources 재등록
  5. report.md 생성
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ── 환경 변수 ──────────────────────────────────────────────────
SEARCH_ENDPOINT = (
    os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
    or os.environ.get("AZURE_SEARCH_ENDPOINT", "")
).rstrip("/")
OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
STORAGE_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
RAW_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "raw-documents")
PROCESSED_CONTAINER = os.environ.get("AZURE_SEARCH_INDEXING_CONTAINER", "processed-documents")

API_VERSION = "2024-07-01"
KS_API_VERSION = "2025-08-01-preview"

credential = DefaultAzureCredential(
    exclude_managed_identity_credential=True,
    exclude_workload_identity_credential=True,
)

SOURCES = [
    {"key": "prec",   "label": "판례",          "index": "prec-court-index",   "indexer": "prec-blob-indexer",   "blob_prefix": "prec/"},
    {"key": "detc",   "label": "헌법재판소 결정례", "index": "const-court-index",  "indexer": "const-blob-indexer",  "blob_prefix": "detc/"},
    {"key": "expc",   "label": "법제처 해석례",    "index": "legis-interp-index", "indexer": "interp-blob-indexer", "blob_prefix": "expc/"},
    {"key": "admrul", "label": "행정심판 재결례",   "index": "admin-appeal-index", "indexer": "admin-blob-indexer",  "blob_prefix": "admrul/"},
]


def _headers():
    tok = credential.get_token("https://search.azure.com/.default").token
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════
# 1. Blob 현황 집계
# ══════════════════════════════════════════════════════════════════
def count_blobs() -> dict[str, int]:
    log("Blob 파일 수 집계 중 (raw-documents/*.json)...")
    blob_svc = BlobServiceClient(
        account_url=f"https://{STORAGE_NAME}.blob.core.windows.net",
        credential=credential,
    )
    counts = {}
    for src in SOURCES:
        try:
            container = blob_svc.get_container_client(RAW_CONTAINER)
            n = sum(1 for b in container.list_blobs(name_starts_with=src["blob_prefix"])
                    if b.name.endswith(".json"))
            counts[src["key"]] = n
        except Exception:
            counts[src["key"]] = -1
    for src in SOURCES:
        log(f"  {src['label']:<20} ({RAW_CONTAINER}/{src['blob_prefix']}): {counts[src['key']]:,}개")
    return counts


# ══════════════════════════════════════════════════════════════════
# 2. 파이프라인 재실행 (setup_ai_search_pipeline.py)
# ══════════════════════════════════════════════════════════════════
def run_pipeline(source_key: str, label: str) -> dict:
    log(f"{'='*60}")
    log(f"[{label}] 파이프라인 재생성 + 인덱서 실행 (source={source_key})")
    log(f"{'='*60}")

    start = time.time()
    script = os.path.join(os.path.dirname(__file__), "setup_ai_search_pipeline.py")
    result = subprocess.run(
        [sys.executable, script, "--source", source_key, "--run"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    elapsed = time.time() - start

    # 마지막 50줄만 출력
    lines = result.stdout.splitlines()
    tail = "\n".join(lines[-50:]) if len(lines) > 50 else result.stdout
    print(tail, flush=True)
    if result.stderr:
        err_lines = result.stderr.splitlines()[-10:]
        print("\n".join(err_lines), flush=True)

    log(f"[{label}] 완료: rc={result.returncode}, 소요={elapsed:.1f}s ({int(elapsed//60)}분 {int(elapsed%60)}초)")

    return {
        "source": source_key,
        "label": label,
        "returncode": result.returncode,
        "elapsed_sec": round(elapsed, 1),
    }


# ══════════════════════════════════════════════════════════════════
# 3. 인덱서 상태 + 인덱스 문서 수 조회
# ══════════════════════════════════════════════════════════════════
def get_indexer_status(indexer_name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/indexers('{indexer_name}')/status?api-version={API_VERSION}"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code >= 400:
        return {"status": "error", "items_processed": 0, "items_failed": 0, "elapsed_sec": None}
    data = r.json()
    last = data.get("lastResult") or {}
    start_t = last.get("startTime")
    end_t = last.get("endTime")
    elapsed = None
    if start_t and end_t:
        s = datetime.fromisoformat(start_t.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_t.replace("Z", "+00:00"))
        elapsed = round((e - s).total_seconds(), 1)
    return {
        "status": last.get("status", "unknown"),
        "items_processed": last.get("itemsProcessed") or last.get("itemCount") or 0,
        "items_failed": last.get("itemsFailed") or last.get("failedItemCount") or 0,
        "elapsed_sec": elapsed,
        "start_time": start_t,
        "end_time": end_t,
    }


def get_index_doc_count(index_name: str) -> int:
    url = f"{SEARCH_ENDPOINT}/indexes('{index_name}')/docs/$count?api-version={API_VERSION}"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code == 200:
        try:
            return int(r.text.strip())
        except ValueError:
            return 0
    return 0


def poll_all_indexers(timeout_sec: int = 1200):
    """모든 인덱서가 완료될 때까지 폴링"""
    log("모든 인덱서 완료 대기 중...")
    start = time.time()
    while True:
        all_done = True
        for src in SOURCES:
            st = get_indexer_status(src["indexer"])
            status = st["status"]
            if status not in ("success", "transientFailure", "persistentFailure", "error"):
                all_done = False
        if all_done:
            log("모든 인덱서 완료!")
            break
        elapsed = time.time() - start
        if elapsed > timeout_sec:
            log(f"⚠️ 타임아웃 ({timeout_sec}s) — 일부 인덱서가 아직 실행 중일 수 있습니다.")
            break
        time.sleep(15)


# ══════════════════════════════════════════════════════════════════
# 4. Knowledge Agent + Sources 재등록
# ══════════════════════════════════════════════════════════════════
def register_knowledge_agent():
    log("Knowledge Sources + Agent 재등록 중...")
    PLANNER_DEPLOY = "gpt-4o"
    AGENT_NAME = "legal-knowledge-agent"

    INDEX_TO_SRC = {
        "prec-court-index":   ("ks-prec",   "한국 법원 판례",
            "caseName,caseNumber,courtName,courtLevel,judgmentDate,relatedLaws,keywords,holdings,summary"),
        "const-court-index":  ("ks-const",  "헌법재판소 결정례",
            "caseName,caseNumber,decisionDate,decisionType,relatedLaws,keywords,holdings,summary"),
        "legis-interp-index": ("ks-interp", "법제처 법령해석례",
            "title,docNumber,replyDate,interpType,relatedLaws,keywords,querySummary,reply"),
        "admin-appeal-index": ("ks-admin",  "행정심판 재결례",
            "caseName,caseNumber,decisionDate,decisionType,committee,relatedLaws,keywords,order,reasonSummary"),
    }

    hdr = _headers()

    for idx_name, (src_name, desc, fields) in INDEX_TO_SRC.items():
        body = {
            "name": src_name, "kind": "searchIndex", "description": desc,
            "searchIndexParameters": {"searchIndexName": idx_name, "sourceDataSelect": fields},
        }
        url = f"{SEARCH_ENDPOINT}/knowledgesources('{src_name}')?api-version={KS_API_VERSION}"
        r = requests.put(url, headers=hdr, json=body, timeout=30)
        log(f"  KS '{src_name}' <- {idx_name}: {r.status_code}")

    agent_body = {
        "name": AGENT_NAME,
        "description": "Korean legal corpus: 판례 / 헌재 / 법제처 / 행심",
        "models": [{"kind": "azureOpenAI", "azureOpenAIParameters": {
            "resourceUri": OPENAI_ENDPOINT.rstrip("/"),
            "deploymentId": PLANNER_DEPLOY, "modelName": PLANNER_DEPLOY,
        }}],
        "knowledgeSources": [
            {"name": s, "alwaysQuerySource": True, "includeReferences": True,
             "includeReferenceSourceData": True, "maxSubQueries": 4, "rerankerThreshold": 1.5}
            for _, (s, _, _) in INDEX_TO_SRC.items()
        ],
        "outputConfiguration": {"modality": "answerSynthesis", "includeActivity": True, "attemptFastPath": False},
        "requestLimits": {"maxRuntimeInSeconds": 60, "maxOutputSize": 16000},
        "retrievalInstructions": (
            "사용자 질문에 한국 법령·판례 자료가 필요하면 4개 소스에서 hybrid+semantic 검색을 수행한다. "
            "이전 대화 메시지에 사건번호(예: 2019도1234)나 법령명이 언급되어 있으면 그 키워드로 sub-query 를 추가 계획하라."
        ),
    }
    url = f"{SEARCH_ENDPOINT}/agents('{AGENT_NAME}')?api-version={KS_API_VERSION}"
    r = requests.put(url, headers=hdr, json=agent_body, timeout=30)
    log(f"  Agent '{AGENT_NAME}': {r.status_code}")
    if r.status_code < 400:
        log("  ✅ Knowledge Agent 등록 완료")
    else:
        log(f"  ❌ Agent 등록 실패: {r.text[:300]}")


# ══════════════════════════════════════════════════════════════════
# 5. 리포트 생성
# ══════════════════════════════════════════════════════════════════
def generate_report(blob_counts: dict, pipeline_results: list[dict]) -> str:
    log("report.md 생성 중...")

    lines = []
    lines.append("# 인덱싱 파이프라인 전체 재실행 리포트")
    lines.append("")
    lines.append(f"- **생성 시각**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Search Endpoint**: `{SEARCH_ENDPOINT}`")
    lines.append(f"- **Storage Account**: `{STORAGE_NAME}`")
    lines.append(f"- **인덱싱 컨테이너**: `{PROCESSED_CONTAINER}`")
    lines.append("")

    # 파이프라인 실행 결과
    lines.append("## 1. 파이프라인 실행 결과")
    lines.append("")
    lines.append("| 소스 | 한국어명 | 종료코드 | 소요시간(초) | 결과 |")
    lines.append("|------|----------|----------|-------------|------|")
    total_elapsed = 0
    for pr in pipeline_results:
        status_icon = "✅" if pr["returncode"] == 0 else "❌"
        lines.append(f"| {pr['source']} | {pr['label']} | {pr['returncode']} | {pr['elapsed_sec']} | {status_icon} |")
        total_elapsed += pr["elapsed_sec"]
    lines.append(f"| **합계** | | | **{round(total_elapsed, 1)}** | |")
    lines.append("")

    # 인덱서 상태
    lines.append("## 2. 인덱서 최종 상태")
    lines.append("")
    lines.append("| 인덱서 | 상태 | 처리건수 | 실패건수 | 소요시간(초) | 시작시간 | 종료시간 |")
    lines.append("|--------|------|---------|---------|-------------|---------|---------|")
    for src in SOURCES:
        st = get_indexer_status(src["indexer"])
        status_icon = "✅" if st["status"] == "success" else ("⚠️" if st["status"] == "transientFailure" else "❌")
        lines.append(
            f"| {src['indexer']} | {status_icon} {st['status']} | {st['items_processed']:,} | {st['items_failed']:,} "
            f"| {st['elapsed_sec'] or '-'} | {(st.get('start_time') or '-')[:19]} | {(st.get('end_time') or '-')[:19]} |"
        )
    lines.append("")

    # 인덱스 문서 수
    lines.append("## 3. 인덱스 문서 수 vs Blob 파일 수")
    lines.append("")
    lines.append("| 인덱스 | 한국어명 | Blob 파일수 | 인덱스 문서수 | 차이 | 판정 |")
    lines.append("|--------|----------|------------|-------------|------|------|")
    total_blob = 0
    total_docs = 0
    for src in SOURCES:
        blob_n = blob_counts.get(src["key"], 0)
        doc_n = get_index_doc_count(src["index"])
        diff = doc_n - blob_n
        total_blob += max(blob_n, 0)
        total_docs += doc_n
        if blob_n < 0:
            verdict = "⚠️ Blob 집계 실패"
        elif diff == 0:
            verdict = "✅ 일치"
        elif diff > 0:
            verdict = "ℹ️ 문서 > 파일"
        else:
            verdict = "⚠️ 누락 가능"
        lines.append(f"| {src['index']} | {src['label']} | {blob_n:,} | {doc_n:,} | {diff:+,} | {verdict} |")
    lines.append(f"| **합계** | | **{total_blob:,}** | **{total_docs:,}** | **{total_docs - total_blob:+,}** | |")
    lines.append("")

    # Knowledge Agent
    lines.append("## 4. Knowledge Agent 등록 상태")
    lines.append("")
    try:
        hdr = _headers()
        r = requests.get(f"{SEARCH_ENDPOINT}/agents('legal-knowledge-agent')?api-version={KS_API_VERSION}",
                         headers=hdr, timeout=30)
        if r.status_code == 200:
            agent = r.json()
            ks_list = [ks["name"] for ks in agent.get("knowledgeSources", [])]
            lines.append(f"- **Agent**: `{agent['name']}` ✅")
            lines.append(f"- **Knowledge Sources**: {', '.join(f'`{k}`' for k in ks_list)}")
        else:
            lines.append(f"- Agent 조회 실패: HTTP {r.status_code}")
    except Exception as e:
        lines.append(f"- Agent 조회 오류: {e}")
    lines.append("")

    # 요약
    lines.append("## 5. 요약")
    lines.append("")
    all_ok = all(pr["returncode"] == 0 for pr in pipeline_results)
    if all_ok:
        lines.append("✅ **모든 파이프라인이 정상 완료되었습니다.**")
    else:
        failed = [pr["source"] for pr in pipeline_results if pr["returncode"] != 0]
        lines.append(f"⚠️ **실패한 파이프라인**: {', '.join(failed)}")
    lines.append(f"- 총 소요 시간: **{round(total_elapsed, 1)}초** ({int(total_elapsed//60)}분 {int(total_elapsed%60)}초)")
    lines.append(f"- 인덱스 총 문서 수: **{total_docs:,}건**")
    lines.append("")

    report_path = os.path.join(os.path.dirname(__file__), "..", "report.md")
    report_content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    log(f"report.md 저장 완료: {os.path.abspath(report_path)}")
    return report_path


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
def main():
    log("=" * 60)
    log("전체 인덱싱 파이프라인 재실행 시작")
    log("=" * 60)

    total_start = time.time()

    # 1. Blob 현황
    blob_counts = count_blobs()

    # 2. 4개 소스 파이프라인 순차 실행
    pipeline_results = []
    for src in SOURCES:
        pr = run_pipeline(src["key"], src["label"])
        pipeline_results.append(pr)

    # 3. 모든 인덱서 완료 대기
    poll_all_indexers(timeout_sec=3600)

    # 4. Knowledge Agent 재등록
    register_knowledge_agent()

    # 5. 리포트 생성
    report_path = generate_report(blob_counts, pipeline_results)

    total_elapsed = time.time() - total_start
    log(f"전체 완료! 총 소요: {total_elapsed:.1f}s ({int(total_elapsed//60)}분 {int(total_elapsed%60)}초)")
    log(f"리포트: {report_path}")


if __name__ == "__main__":
    main()
