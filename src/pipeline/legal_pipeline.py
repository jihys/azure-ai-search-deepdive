"""
법률 데이터 4개 소스별 AI Search 인덱싱 파이프라인 설정.

4개 인덱스:
  - prec-court-index      (판례)
  - const-court-index     (헌재결정례)
  - legis-interp-index    (법제처 해석례)
  - admin-appeal-index    (행정심판 재결례)

파이프라인 흐름:
  Blob Storage (processed-documents/{source}/) — JSONL
    → JSON Lines 파싱
    → 필드 매핑 (한국어 → 영문)
    → SplitSkill + AzureOpenAI EmbeddingSkill
    → AI Search Index
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from src.pipeline.indexer_ops import SearchAdminClient, reset_indexer, run_indexer, poll_indexer

load_dotenv()


# ── 환경변수 (모듈 로드 시 읽기) ─────────────────────────────

def _env(key: str, *alt_keys: str, default: str = "") -> str:
    for k in (key, *alt_keys):
        val = os.environ.get(k, "")
        if val:
            return val
    return default


# ── 필드 헬퍼 ────────────────────────────────────────────────

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
    return {"name": name, "type": "Collection(Edm.String)", "searchable": True, "filterable": True}

def _text(name: str) -> dict:
    return {"name": name, "type": "Edm.String", "searchable": True, "analyzer": "ko.microsoft"}

def _text_long(name: str) -> dict:
    return {
        "name": name, "type": "Edm.String",
        "searchable": True, "analyzer": "ko_safe",
        "filterable": False, "sortable": False, "facetable": False,
    }

def _vector_field(name: str = "summaryEmbedding", dims: int = 3072) -> dict:
    return {
        "name": name, "type": "Collection(Edm.Single)",
        "searchable": True, "retrievable": False,
        "dimensions": dims, "vectorSearchProfile": "vector-profile",
    }

def _vector_search() -> dict:
    return {
        "profiles": [{"name": "vector-profile", "algorithm": "hnsw-algo"}],
        "algorithms": [{
            "name": "hnsw-algo", "kind": "hnsw",
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


# ══════════════════════════════════════════════════════════════
# 4개 소스별 설정
# ══════════════════════════════════════════════════════════════

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
    "embedding_source_field": "/document/판결요지",
    "fields": [
        _key(),
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
        _text("caseName"),
        _text("holdings"),
        _text("summary"),
        _text_long("fullText"),
        _vector_field(),
    ],
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


# ══════════════════════════════════════════════════════════════
# 리소스 생성 함수
# ══════════════════════════════════════════════════════════════

def _create_index(client: SearchAdminClient, cfg: dict) -> None:
    name = cfg["index_name"]
    print(f"[Index] {name}")
    client.delete_if_exists(f"/indexes/{name}")
    client.request("PUT", f"/indexes/{name}", {
        "name": name,
        "fields": cfg["fields"],
        "vectorSearch": _vector_search(),
        "semantic": _semantic(
            cfg["semantic_config_name"], cfg["semantic_title"],
            cfg["semantic_content"], cfg["semantic_keywords"],
        ),
        "analyzers": [{
            "@odata.type": "#Microsoft.Azure.Search.CustomAnalyzer",
            "name": "ko_safe",
            "tokenizer": "microsoft_korean_tok",
            "charFilters": ["strip_cjk", "split_long_runs"],
            "tokenFilters": ["lowercase"],
        }],
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
        "tokenizers": [{
            "@odata.type": "#Microsoft.Azure.Search.MicrosoftLanguageTokenizer",
            "name": "microsoft_korean_tok",
            "language": "korean",
            "isSearchTokenizer": False,
            "maxTokenLength": 200,
        }],
    })
    print(f"  ✓ Index '{name}' 생성 완료")


def _create_skillset(client: SearchAdminClient, cfg: dict) -> None:
    name = cfg["skillset_name"]
    openai_endpoint = _env("AZURE_OPENAI_ENDPOINT")
    embedding_deployment = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", default="text-embedding-3-large")

    print(f"[Skillset] {name}")
    client.delete_if_exists(f"/skillsets/{name}")
    client.request("PUT", f"/skillsets/{name}", {
        "name": name,
        "description": f"{cfg['index_name']} 임베딩 파이프라인",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "split-skill",
                "description": "임베딩 입력 길이 제한 회피 (8K token)",
                "context": "/document",
                "textSplitMode": "pages",
                "maximumPageLength": 5000,
                "defaultLanguageCode": "ko",
                "inputs": [{"name": "text", "source": cfg["embedding_source_field"]}],
                "outputs": [{"name": "textItems", "targetName": "embedSourcePages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "description": "text-embedding-3-large 벡터 생성",
                "context": "/document",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": 3072,
                "inputs": [{"name": "text", "source": "/document/embedSourcePages/0"}],
                "outputs": [{"name": "embedding", "targetName": "summaryEmbedding"}],
            },
        ],
    })
    print(f"  ✓ Skillset '{name}' 생성 완료")


def _create_datasource(client: SearchAdminClient, cfg: dict) -> None:
    name = cfg["datasource_name"]
    storage_resource_id = _env("AZURE_STORAGE_RESOURCE_ID")
    container = _env("AZURE_SEARCH_INDEXING_CONTAINER", default="processed-documents")

    print(f"[DataSource] {name}")
    client.delete_if_exists(f"/datasources/{name}")
    client.request("PUT", f"/datasources/{name}", {
        "name": name,
        "type": "azureblob",
        "credentials": {"connectionString": f"ResourceId={storage_resource_id}"},
        "container": {"name": container, "query": cfg["blob_prefix"]},
        "dataChangeDetectionPolicy": {
            "@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy",
            "highWaterMarkColumnName": "metadata_storage_last_modified",
        },
    })
    print(f"  ✓ DataSource '{name}' 생성 완료")


def _create_indexer(
    client: SearchAdminClient,
    cfg: dict,
    schedule: str = "PT24H",
    start_time: str = "2026-01-01T06:00:00Z",
    enable_cache: bool = False,
) -> None:
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
            "configuration": {"dataToExtract": "contentAndMetadata", "parsingMode": "jsonLines"},
        },
        "fieldMappings": cfg["field_mappings"],
        "outputFieldMappings": [
            {"sourceFieldName": "/document/summaryEmbedding", "targetFieldName": "summaryEmbedding"},
        ],
    }

    if enable_cache:
        storage_resource_id = _env("AZURE_STORAGE_RESOURCE_ID")
        indexer["cache"] = {
            "storageConnectionString": f"ResourceId={storage_resource_id};",
            "enableReprocessing": True,
        }

    if schedule.lower() != "none":
        indexer["schedule"] = {"interval": schedule, "startTime": start_time}

    client.delete_if_exists(f"/indexers/{name}")
    client.request("PUT", f"/indexers/{name}", indexer)
    print(f"  ✓ Indexer '{name}' 생성 완료")


# ══════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════

def setup_legal_pipeline(
    source: str = "all",
    run: bool = False,
    schedule: str = "PT24H",
    start_time: str = "2026-01-01T06:00:00Z",
    enable_cache: bool = False,
    client: SearchAdminClient | None = None,
) -> None:
    """법률 인덱싱 파이프라인 생성 (및 선택적 실행).

    Args:
        source: 'prec', 'detc', 'expc', 'admrul', 또는 'all'
        run: True이면 생성 후 즉시 인덱서 실행 + 완료 대기
        schedule: 인덱서 스케줄 (ISO 8601). 'none'이면 수동
        start_time: 스케줄 시작 시간 (UTC)
        enable_cache: True이면 incremental enrichment cache 활성화
        client: SearchAdminClient 인스턴스 (None이면 환경변수로 생성)
    """
    if client is None:
        client = SearchAdminClient()

    client.assert_dns_resolvable()

    targets = list(ALL_CONFIGS.keys()) if source == "all" else [source]

    print("=" * 60)
    print("AI Search 법률 인덱싱 파이프라인 설정")
    print(f"  대상: {', '.join(targets)}")
    print(f"  스케줄: {schedule}")
    print("=" * 60)

    for source_key in targets:
        cfg = ALL_CONFIGS[source_key]
        print(f"\n{'─' * 60}")
        print(f"  [{source_key}] {cfg['index_name']}")
        print(f"{'─' * 60}")

        reset_indexer(client, cfg["indexer_name"])
        _create_index(client, cfg)
        _create_skillset(client, cfg)
        _create_datasource(client, cfg)
        _create_indexer(client, cfg, schedule=schedule, start_time=start_time, enable_cache=enable_cache)

        if run:
            run_indexer(client, cfg["indexer_name"])
            poll_indexer(client, cfg["indexer_name"])

    print(f"\n{'=' * 60}")
    print("✓ 파이프라인 설정 완료!")
