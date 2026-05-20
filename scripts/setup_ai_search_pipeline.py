"""
AI Search 법률 데이터 인덱싱 파이프라인 설정 스크립트

4개 법률 소스별 인덱스/스킬셋/데이터소스/인덱서 생성:
  1. prec-court-index      — 판례 (대법원·고등법원·지방법원)
  2. const-court-index     — 헌재결정례
  3. legis-interp-index    — 법제처 해석례
  4. admin-appeal-index    — 행정심판 재결례

파이프라인 흐름:
  Blob Storage (processed-documents/{source}/) — JSONL bundles
    → JSON Lines 파싱 (parsingMode: jsonLines) — preprocess 가 생성한 processed-documents/*.jsonl
    → 필드 매핑 (크롤러 한국어 키 → 인덱스 영문 필드)
    → Azure OpenAI Embedding Skill (요지 텍스트 벡터 생성)
    → AI Search Index (저장)

  ※ Preprocess 파이프라인(`scripts/preprocess_integration.py` or Logic App)·
      raw-documents/{source}/{date}/*.json → processed-documents/{source}/{date}/docs-part-NNN.jsonl
  ※ 각 소스별 별도 Datasource(prefix 필터) + Indexer + Skillset + Index
  ※ HighWaterMark 변경 감지 → 신규/변경 데이터만 처리

실행 방법:
  VNet 내부 머신 또는 VPN 접속 후 실행 (AI Search가 Private Endpoint 전용)

  # 전체 4개 파이프라인 생성 (기본)
  uv run python scripts/setup_ai_search_pipeline.py

  # 특정 소스만 생성
  uv run python scripts/setup_ai_search_pipeline.py --source prec

  # 생성 후 즉시 실행
  uv run python scripts/setup_ai_search_pipeline.py --run

  # 스케줄 변경
  uv run python scripts/setup_ai_search_pipeline.py --schedule PT12H
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from urllib.parse import urlparse

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "2024-11-01-preview"

# ── 환경 변수 ──────────────────────────────────────────────────
SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT") or os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT", "")
SEARCH_ADMIN_KEY = os.environ.get("AZURE_SEARCH_ADMIN_KEY", "")
STORAGE_RESOURCE_ID = os.environ.get("AZURE_STORAGE_RESOURCE_ID", "")
# Indexer 는 preprocess 가 JSONL 로 묶은 processed-documents 를 읽어야 하므로 전용 환경변수 사용.
# (BLOB_CONTAINER_NAME=raw-documents 는 crawler/uploader 용. 세팅 충돌 방지)
STORAGE_CONTAINER = os.environ.get("AZURE_SEARCH_INDEXING_CONTAINER", "processed-documents")
OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
EMBEDDING_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# ── 인증 ──────────────────────────────────────────────────────
# VM의 Managed Identity 대신 노트북 사용자(`az login`)를 우선 —
# DefaultAzureCredential 기본 순서에서 IMDS가 먼저 잡히면 RBAC 없는 MI로 403 발생
from azure.identity import DefaultAzureCredential  # noqa: E402  (re-import for clarity)
_credential = (
    DefaultAzureCredential(
        exclude_managed_identity_credential=True,
        exclude_workload_identity_credential=True,
    )
    if not SEARCH_ADMIN_KEY
    else None
)


def _normalize_search_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return endpoint
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint.rstrip("/")


def _search_host(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    return parsed.hostname or ""


def _assert_dns_resolvable(endpoint: str, attempts: int = 3, wait_sec: int = 2) -> None:
    host = _search_host(endpoint)
    if not host:
        raise RuntimeError(f"Invalid AZURE_SEARCH_SERVICE_ENDPOINT: {endpoint}")

    last_exc: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            socket.getaddrinfo(host, 443)
            return
        except OSError as exc:
            last_exc = exc
            if i < attempts:
                time.sleep(wait_sec)

    raise RuntimeError(
        "Failed to resolve Azure AI Search host. "
        f"host={host}, endpoint={endpoint}. "
        "Check DNS/network egress in the current environment, and verify that the deployed "
        "service name and endpoint are correct."
    ) from last_exc


def _request(method: str, url: str, **kwargs) -> requests.Response:
    tries = kwargs.pop("tries", 3)
    retry_wait = kwargs.pop("retry_wait", 2)

    last_exc: Exception | None = None
    for i in range(1, tries + 1):
        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            if i < tries:
                time.sleep(retry_wait)

    raise RuntimeError(
        "Connection to Azure AI Search failed after retries. "
        f"url={url}. "
        "If the error includes NameResolutionError, DNS could not resolve the Search endpoint."
    ) from last_exc


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if SEARCH_ADMIN_KEY:
        headers["api-key"] = SEARCH_ADMIN_KEY
    else:
        token = _credential.get_token("https://search.azure.com/.default")
        headers["Authorization"] = f"Bearer {token.token}"
    return headers


def api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{SEARCH_ENDPOINT}{path}?api-version={API_VERSION}"
    resp = _request(method, url, headers=_headers(), json=body, timeout=120)
    if resp.status_code not in (200, 201, 202, 204):
        print(f"  ERROR {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    return resp.json() if resp.content else {}


def delete_safe(path: str) -> None:
    url = f"{SEARCH_ENDPOINT}{path}?api-version={API_VERSION}"
    resp = _request("DELETE", url, headers=_headers(), timeout=120)
    if resp.status_code in (200, 202, 204):
        print(f"  - 기존 {path} 삭제")


# ══════════════════════════════════════════════════════════════════
# 4개 소스별 파이프라인 설정
# ══════════════════════════════════════════════════════════════════

def _vector_field(name: str = "summaryEmbedding", dims: int = 3072) -> dict:
    return {
        "name": name,
        "type": "Collection(Edm.Single)",
        "searchable": True,
        "retrievable": False,
        "dimensions": dims,
        "vectorSearchProfile": "vector-profile",
    }


def _vector_search() -> dict:
    return {
        "profiles": [{"name": "vector-profile", "algorithm": "hnsw-algo"}],
        "algorithms": [{
            "name": "hnsw-algo",
            "kind": "hnsw",
            "hnswParameters": {"metric": "cosine", "m": 4, "efConstruction": 400, "efSearch": 500},
        }],
    }


def _semantic(config_name: str, title: str, content_fields: list[str], keyword_fields: list[str]) -> dict:
    return {
        "configurations": [{
            "name": config_name,
            "prioritizedFields": {
                "titleField": {"fieldName": title},
                "prioritizedContentFields": [{"fieldName": f} for f in content_fields],
                "prioritizedKeywordsFields": [{"fieldName": f} for f in keyword_fields],
            },
        }],
    }


# ── 공통 필드 헬퍼 ────────────────────────────────────────────

def _key(name: str = "id") -> dict:
    return {"name": name, "type": "Edm.String", "key": True, "filterable": True, "analyzer": "keyword"}


def _str_searchable(name: str, **kw) -> dict:
    d = {"name": name, "type": "Edm.String", "searchable": True}
    d.update(kw)
    return d


def _str_filter(name: str, **kw) -> dict:
    d = {"name": name, "type": "Edm.String", "filterable": True}
    d.update(kw)
    return d


def _date(name: str) -> dict:
    return {"name": name, "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True}


def _collection_str(name: str) -> dict:
    return {
        "name": name,
        "type": "Collection(Edm.String)",
        "searchable": True,
        "filterable": True,
    }


def _text(name: str) -> dict:
    """한국어 형태소 분석기 적용 텍스트 필드"""
    return {"name": name, "type": "Edm.String", "searchable": True, "analyzer": "ko.microsoft"}


def _text_long(name: str) -> dict:
    """장문 용 텍스트 필드 — custom analyzer 'ko_safe'.
    fullText 처럼 매우 긴 본문을 색인할 때 사용.
    32K byte 단일 토큰 한도 회피를 위해 filterable/sortable/facetable 을 모두 비활성."""
    return {
        "name": name, "type": "Edm.String",
        "searchable": True, "analyzer": "ko_safe",
        "filterable": False, "sortable": False, "facetable": False,
    }


# ══════════════════════════════════════════════════════════════════
# 1. 판례 (prec) → prec-court-index
# ══════════════════════════════════════════════════════════════════

PREC_CONFIG = {
    "index_name": "prec-court-index",
    "datasource_name": "prec-blob-datasource",
    "skillset_name": "prec-rag-skillset",
    "indexer_name": "prec-blob-indexer",
    "blob_prefix": "prec/",
    "semantic_config_name": "prec-semantic",
    "semantic_title": "caseName",
    "semantic_content": ["holdings", "summary"],
    "semantic_keywords": ["keywords", "relatedLaws"],
    # 임베딩 대상: 크롤러 JSON 원본 필드명
    "embedding_source_field": "/document/판결요지",
    "fields": [
        _key(),
        # 필터용 메타데이터
        _str_searchable("courtName", filterable=True, facetable=True),
        _str_searchable("caseNumber", filterable=True, sortable=True),
        _date("judgmentDate"),
        _str_searchable("courtLevel", filterable=True, facetable=True),
        _str_searchable("caseType", filterable=True, facetable=True),
        _str_searchable("status", filterable=True, facetable=True),
        _text("relatedLaws"),
        _collection_str("keywords"),
        _str_filter("sourceUrl"),
        _date("registrationDate"),
        # 키워드 검색용 본문
        _text("caseName"),
        _text("holdings"),
        _text("summary"),
        _text_long("fullText"),
        # 벡터
        _vector_field(),
    ],
    # 크롤러 JSON 키 → 인덱스 필드 매핑
    "field_mappings": [
        {"sourceFieldName": "seq", "targetFieldName": "id"},
        {"sourceFieldName": "법원명", "targetFieldName": "courtName"},
        {"sourceFieldName": "사건번호", "targetFieldName": "caseNumber"},
        {"sourceFieldName": "선고일자", "targetFieldName": "judgmentDate"},
        {"sourceFieldName": "사건명", "targetFieldName": "caseName"},
        {"sourceFieldName": "판시사항", "targetFieldName": "holdings"},
        {"sourceFieldName": "판결요지", "targetFieldName": "summary"},
        {"sourceFieldName": "전문", "targetFieldName": "fullText"},
        {"sourceFieldName": "url", "targetFieldName": "sourceUrl"},
        {"sourceFieldName": "참조조문", "targetFieldName": "relatedLaws"},
    ],
}

# ══════════════════════════════════════════════════════════════════
# 2. 헌재결정례 (detc) → const-court-index
# ══════════════════════════════════════════════════════════════════

CONST_CONFIG = {
    "index_name": "const-court-index",
    "datasource_name": "const-blob-datasource",
    "skillset_name": "const-rag-skillset",
    "indexer_name": "const-blob-indexer",
    "blob_prefix": "detc/",
    "semantic_config_name": "const-semantic",
    "semantic_title": "caseName",
    "semantic_content": ["holdings", "summary"],
    "semantic_keywords": ["keywords", "relatedLaws"],
    "embedding_source_field": "/document/결정요지",
    "fields": [
        _key(),
        _str_searchable("caseNumber", filterable=True, sortable=True),
        _date("decisionDate"),
        _str_searchable("decisionType", filterable=True, facetable=True),
        _text("relatedLaws"),
        _collection_str("keywords"),
        _str_filter("sourceUrl"),
        _str_filter("fiscalYear", sortable=True),
        _date("registrationDate"),
        _text("caseName"),
        _text("holdings"),
        _text("summary"),
        _text_long("fullText"),
        _vector_field(),
    ],
    "field_mappings": [
        {"sourceFieldName": "seq", "targetFieldName": "id"},
        {"sourceFieldName": "사건번호", "targetFieldName": "caseNumber"},
        {"sourceFieldName": "결정일자", "targetFieldName": "decisionDate"},
        {"sourceFieldName": "사건명", "targetFieldName": "caseName"},
        {"sourceFieldName": "판시사항", "targetFieldName": "holdings"},
        {"sourceFieldName": "결정요지", "targetFieldName": "summary"},
        {"sourceFieldName": "전문", "targetFieldName": "fullText"},
        {"sourceFieldName": "url", "targetFieldName": "sourceUrl"},
        {"sourceFieldName": "참조조문", "targetFieldName": "relatedLaws"},
    ],
}

# ══════════════════════════════════════════════════════════════════
# 3. 법제처 해석례 (expc) → legis-interp-index
# ══════════════════════════════════════════════════════════════════

INTERP_CONFIG = {
    "index_name": "legis-interp-index",
    "datasource_name": "interp-blob-datasource",
    "skillset_name": "interp-rag-skillset",
    "indexer_name": "interp-blob-indexer",
    "blob_prefix": "expc/",
    "semantic_config_name": "interp-semantic",
    "semantic_title": "title",
    "semantic_content": ["querySummary", "reply"],
    "semantic_keywords": ["keywords", "relatedLaws"],
    "embedding_source_field": "/document/회답",
    "fields": [
        _key(),
        _str_searchable("docNumber", filterable=True, sortable=True),
        _date("replyDate"),
        _str_searchable("interpType", filterable=True, facetable=True),
        _collection_str("relatedLaws"),
        _collection_str("keywords"),
        _str_filter("sourceUrl"),
        _date("registrationDate"),
        _text("title"),
        _text("querySummary"),
        _text("reply"),
        _text_long("reason"),
        _vector_field(),
    ],
    "field_mappings": [
        {"sourceFieldName": "seq", "targetFieldName": "id"},
        {"sourceFieldName": "문서번호", "targetFieldName": "docNumber"},
        {"sourceFieldName": "회시일자", "targetFieldName": "replyDate"},
        {"sourceFieldName": "제목", "targetFieldName": "title"},
        {"sourceFieldName": "질의요지", "targetFieldName": "querySummary"},
        {"sourceFieldName": "회답", "targetFieldName": "reply"},
        {"sourceFieldName": "이유", "targetFieldName": "reason"},
        {"sourceFieldName": "url", "targetFieldName": "sourceUrl"},
    ],
}

# ══════════════════════════════════════════════════════════════════
# 4. 행정심판 재결례 (admrul) → admin-appeal-index
# ══════════════════════════════════════════════════════════════════

ADMIN_CONFIG = {
    "index_name": "admin-appeal-index",
    "datasource_name": "admin-blob-datasource",
    "skillset_name": "admin-rag-skillset",
    "indexer_name": "admin-blob-indexer",
    "blob_prefix": "admrul/",
    "semantic_config_name": "admin-semantic",
    "semantic_title": "caseName",
    "semantic_content": ["order", "reasonSummary"],
    "semantic_keywords": ["keywords", "relatedLaws"],
    "embedding_source_field": "/document/재결요지",
    "fields": [
        _key(),
        _str_searchable("caseNumber", filterable=True, sortable=True),
        _date("decisionDate"),
        _str_searchable("decisionType", filterable=True, facetable=True),
        _collection_str("relatedLaws"),
        _collection_str("keywords"),
        _str_filter("sourceUrl"),
        _str_searchable("committee", filterable=True, facetable=True),
        _date("registrationDate"),
        _text("caseName"),
        _text("order"),
        _text("reasonSummary"),
        _text_long("fullText"),
        _vector_field(),
    ],
    "field_mappings": [
        {"sourceFieldName": "seq", "targetFieldName": "id"},
        {"sourceFieldName": "사건번호", "targetFieldName": "caseNumber"},
        {"sourceFieldName": "재결일자", "targetFieldName": "decisionDate"},
        {"sourceFieldName": "재결결과", "targetFieldName": "decisionType"},
        {"sourceFieldName": "재결기관", "targetFieldName": "committee"},
        {"sourceFieldName": "사건명", "targetFieldName": "caseName"},
        {"sourceFieldName": "주문", "targetFieldName": "order"},
        {"sourceFieldName": "재결요지", "targetFieldName": "reasonSummary"},
        {"sourceFieldName": "이유", "targetFieldName": "fullText"},
        {"sourceFieldName": "url", "targetFieldName": "sourceUrl"},
    ],
}

ALL_CONFIGS = {
    "prec": PREC_CONFIG,
    "detc": CONST_CONFIG,
    "expc": INTERP_CONFIG,
    "admrul": ADMIN_CONFIG,
}


# ══════════════════════════════════════════════════════════════════
# 리소스 생성 함수
# ══════════════════════════════════════════════════════════════════

def create_index(cfg: dict) -> None:
    name = cfg["index_name"]
    print(f"[Index] {name}")
    delete_safe(f"/indexes/{name}")
    api("PUT", f"/indexes/{name}", {
        "name": name,
        "fields": cfg["fields"],
        "vectorSearch": _vector_search(),
        "semantic": _semantic(
            cfg["semantic_config_name"],
            cfg["semantic_title"],
            cfg["semantic_content"],
            cfg["semantic_keywords"],
        ),
        # ko_safe custom analyzer:
        #   원문 그대로 저장 → 색인 시 한자/가나 제거 + 긴 런 분할 → 한국어 형태소
        #   ko.microsoft 의 32K byte 단일 토큰 한계 회피
        "analyzers": [
            {
                "@odata.type": "#Microsoft.Azure.Search.CustomAnalyzer",
                "name": "ko_safe",
                "tokenizer": "microsoft_korean_tok",
                "charFilters": ["strip_cjk", "split_long_runs"],
                "tokenFilters": ["lowercase"],
            },
        ],
        "charFilters": [
            {
                "@odata.type": "#Microsoft.Azure.Search.PatternReplaceCharFilter",
                "name": "strip_cjk",
                "pattern": "[\\u3400-\\u4DBF\\u4E00-\\u9FFF\\uF900-\\uFAFF\\u3040-\\u309F\\u30A0-\\u30FF]+",
                "replacement": " ",
            },
            {
                "@odata.type": "#Microsoft.Azure.Search.PatternReplaceCharFilter",
                "name": "split_long_runs",
                "pattern": "(\\S{200})(?=\\S)",
                "replacement": "$1 ",
            },
        ],
        "tokenizers": [
            {
                "@odata.type": "#Microsoft.Azure.Search.MicrosoftLanguageTokenizer",
                "name": "microsoft_korean_tok",
                "language": "korean",
                "isSearchTokenizer": False,
                "maxTokenLength": 200,
            },
        ],
    })
    print(f"  ✓ Index '{name}' 생성 완료")


def create_skillset(cfg: dict) -> None:
    name = cfg["skillset_name"]
    print(f"[Skillset] {name}")
    delete_safe(f"/skillsets/{name}")
    api("PUT", f"/skillsets/{name}", {
        "name": name,
        "description": f"{cfg['index_name']} 임베딩 파이프라인",
        "skills": [
            # 1) 임베딩 입력이 8000 토큰을 초과하면 AzureOpenAIEmbeddingSkill 가 실패하므로
            #    먼저 SplitSkill 로 분할 (페이지 단위, ~12000 chars ≈ 7K-8K tokens 한국어 기준)
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "split-skill",
                "description": "임베딩 입력 길이 제한 회피 (8K token)",
                "context": "/document",
                "textSplitMode": "pages",
                "maximumPageLength": 5000,
                "defaultLanguageCode": "ko",
                "inputs": [
                    {"name": "text", "source": cfg["embedding_source_field"]},
                ],
                "outputs": [
                    {"name": "textItems", "targetName": "embedSourcePages"},
                ],
            },
            # 2) 첫 페이지만 임베딩 (요약/회답 필드는 본질적으로 짧음 — 초과는 예외 케이스)
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "description": "text-embedding-3-large 벡터 생성",
                "context": "/document",
                "resourceUri": OPENAI_ENDPOINT,
                "deploymentId": EMBEDDING_DEPLOYMENT,
                "modelName": "text-embedding-3-large",
                "dimensions": 3072,
                "inputs": [
                    {"name": "text", "source": "/document/embedSourcePages/0"},
                ],
                "outputs": [
                    {"name": "embedding", "targetName": "summaryEmbedding"},
                ],
            },
        ],
    })
    print(f"  ✓ Skillset '{name}' 생성 완료 (임베딩: {cfg['embedding_source_field']})")


def create_datasource(cfg: dict) -> None:
    name = cfg["datasource_name"]
    print(f"[DataSource] {name}")
    delete_safe(f"/datasources/{name}")
    api("PUT", f"/datasources/{name}", {
        "name": name,
        "type": "azureblob",
        "credentials": {
            "connectionString": f"ResourceId={STORAGE_RESOURCE_ID}",
        },
        "container": {
            "name": STORAGE_CONTAINER,
            "query": cfg["blob_prefix"],
        },
        "dataChangeDetectionPolicy": {
            "@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy",
            "highWaterMarkColumnName": "metadata_storage_last_modified",
        },
    })
    print(f"  ✓ DataSource '{name}' 생성 완료 ({STORAGE_CONTAINER}/{cfg['blob_prefix']})")


def create_indexer(cfg: dict, schedule: str, start_time: str) -> None:
    name = cfg["indexer_name"]
    print(f"[Indexer] {name}")

    indexer = {
        "name": name,
        "dataSourceName": cfg["datasource_name"],
        "skillsetName": cfg["skillset_name"],
        "targetIndexName": cfg["index_name"],
        "parameters": {
            "batchSize": 200,
            "maxFailedItems": 5000,
            "maxFailedItemsPerBatch": 1000,
            "configuration": {
                "dataToExtract": "contentAndMetadata",
                # processed-documents 의 JSONL 을 읽으므로 jsonLines 사용
                "parsingMode": "jsonLines",
            },
        },
        "fieldMappings": cfg["field_mappings"],
        "outputFieldMappings": [
            {"sourceFieldName": "/document/summaryEmbedding", "targetFieldName": "summaryEmbedding"},
        ],
    }
    # Incremental enrichment cache (옵션): SETUP_ENABLE_CACHE=1 인 경우만 활성화
    if os.environ.get("SETUP_ENABLE_CACHE") == "1":
        indexer["cache"] = {
            "storageConnectionString": f"ResourceId={STORAGE_RESOURCE_ID};",
            "enableReprocessing": True,
        }

    if schedule.lower() != "none":
        indexer["schedule"] = {
            "interval": schedule,
            "startTime": start_time,
        }

    delete_safe(f"/indexers/{name}")
    api("PUT", f"/indexers/{name}", indexer)

    schedule_msg = f"매 {schedule} 실행" if schedule.lower() != "none" else "수동 실행"
    print(f"  ✓ Indexer '{name}' 생성 완료 ({schedule_msg})")


def run_indexer(name: str) -> None:
    api("POST", f"/indexers/{name}/run")
    print(f"  → Indexer '{name}' 실행 요청")


def poll_indexer(name: str, timeout_sec: int = 1800) -> None:
    start = time.time()
    while True:
        status = api("GET", f"/indexers/{name}/status")
        last = status.get("lastResult") or {}
        state = last.get("status", "unknown")
        processed = last.get("itemsProcessed", 0)
        failed = last.get("itemsFailed", 0)
        print(f"    상태: {state} (처리 {processed}건, 실패 {failed}건)")
        if state in ("success", "transientFailure", "persistentFailure"):
            break
        if (time.time() - start) > timeout_sec:
            print("    타임아웃 — 모니터링 종료")
            break
        time.sleep(15)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="법률 데이터 4개 인덱싱 파이프라인 설정")
    parser.add_argument("--source", choices=["prec", "detc", "expc", "admrul", "all"],
                        default="all", help="생성할 소스 (기본: all)")
    parser.add_argument("--run", action="store_true", help="생성 후 즉시 실행")
    parser.add_argument("--schedule", default="PT24H",
                        help="Indexer 스케줄 (ISO 8601, 예: PT24H, PT12H). 'none'이면 수동 전용")
    parser.add_argument("--start-time", default="2026-01-01T06:00:00Z",
                        help="스케줄 시작 시간 (UTC)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global SEARCH_ENDPOINT

    if not SEARCH_ENDPOINT:
        print("ERROR: AZURE_SEARCH_SERVICE_ENDPOINT (or AZURE_SEARCH_ENDPOINT) 환경변수 필요")
        sys.exit(1)
    if not OPENAI_ENDPOINT:
        print("ERROR: AZURE_OPENAI_ENDPOINT 환경변수 필요")
        sys.exit(1)
    if not STORAGE_RESOURCE_ID:
        print("ERROR: AZURE_STORAGE_RESOURCE_ID 환경변수 필요")
        sys.exit(1)

    SEARCH_ENDPOINT = _normalize_search_endpoint(SEARCH_ENDPOINT)
    _assert_dns_resolvable(SEARCH_ENDPOINT)

    targets = list(ALL_CONFIGS.keys()) if args.source == "all" else [args.source]

    print("=" * 60)
    print("AI Search 법률 인덱싱 파이프라인 설정")
    print("=" * 60)
    print(f"  Search    : {SEARCH_ENDPOINT}")
    print(f"  Container : {STORAGE_CONTAINER}")
    print(f"  스케줄    : {args.schedule} (start: {args.start_time})")
    print(f"  대상      : {', '.join(targets)}")
    print()

    # Shared Private Link 승인 여부 확인 안내
    print("[사전 확인] AI Search Shared Private Link 승인 필요:")
    print("  az search shared-private-link-resource list \\")
    print("      --service-name <search-name> --resource-group <rg>")
    print("  → status가 'Approved'인지 확인\n")

    for source_key in targets:
        cfg = ALL_CONFIGS[source_key]
        print(f"\n{'─' * 60}")
        print(f"  [{source_key}] {cfg['index_name']}")
        print(f"{'─' * 60}")

        # Indexer reset 먼저 (cache/change tracking이 있으면 skillset/datasource 변경 불가)
        indexer_name = cfg["indexer_name"]
        reset_url = f"{SEARCH_ENDPOINT}/indexers/{indexer_name}/reset?api-version={API_VERSION}"
        reset_resp = _request("POST", reset_url, headers=_headers(), json={}, timeout=120)
        if reset_resp.status_code == 204:
            print(f"  - Indexer '{indexer_name}' reset 완료")
        elif reset_resp.status_code == 404:
            pass  # indexer가 없으면 skip
        else:
            print(f"  - Indexer reset skip: {reset_resp.status_code}")

        create_index(cfg)
        create_skillset(cfg)
        create_datasource(cfg)
        create_indexer(cfg, schedule=args.schedule, start_time=args.start_time)

        if args.run:
            run_indexer(cfg["indexer_name"])
            poll_indexer(cfg["indexer_name"])

    print(f"\n{'=' * 60}")
    print("✓ 파이프라인 설정 완료!")
    if args.schedule.lower() != "none":
        print(f"  Indexer가 매 {args.schedule} 간격으로 자동 실행됩니다.")
        print(f"  신규/변경 데이터가 없으면 자동으로 skip합니다.")
    print()
    print("  인덱스 목록:")
    for cfg in ALL_CONFIGS.values():
        if cfg["index_name"] in [ALL_CONFIGS[t]["index_name"] for t in targets]:
            print(f"    - {cfg['index_name']} (semantic: {cfg['semantic_config_name']})")
    print()
    print("  수동 실행:")
    print("    uv run python scripts/setup_ai_search_pipeline.py --source prec --run")
    print("    uv run python scripts/setup_ai_search_pipeline.py --run")


if __name__ == "__main__":
    main()
