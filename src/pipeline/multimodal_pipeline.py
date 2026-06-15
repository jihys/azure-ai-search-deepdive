"""
멀티모달(PDF/PPTX) AI Search 인덱싱 파이프라인 설정.

3개 파이프라인:
  - PDF basic     : DI Layout → Custom markdown_split → Embedding
  - PPTX basic    : DI Layout → Custom pptx_page_split → Embedding
  - Verbalized    : DI Layout → GPT-5.4 Verbalize → Custom markdown_split → Embedding
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from src.pipeline.indexer_ops import SearchAdminClient, run_indexer, poll_indexer

load_dotenv()


def _env(key: str, *alt_keys: str, default: str = "") -> str:
    for k in (key, *alt_keys):
        val = os.environ.get(k, "")
        if val:
            return val
    return default


# ── Index ────────────────────────────────────────────────────

def _create_index(client: SearchAdminClient, index_name: str, dimensions: int = 3072) -> None:
    print(f"  [index] {index_name}")
    client.delete_if_exists(f"/indexes/{index_name}")
    client.request("PUT", f"/indexes/{index_name}", {
        "name": index_name,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True, "analyzer": "keyword"},
            {"name": "parent_id", "type": "Edm.String", "filterable": True},
            {"name": "source_file_name", "type": "Edm.String", "searchable": True, "filterable": True},
            {"name": "source_blob_path", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "content_type", "type": "Edm.String", "filterable": True, "facetable": True},
            {"name": "file_type", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
            {"name": "source_category", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
            {"name": "content", "type": "Edm.String", "searchable": True, "analyzer": "ko.lucene"},
            {
                "name": "content_vector", "type": "Collection(Edm.Single)",
                "searchable": True, "retrievable": False,
                "dimensions": dimensions, "vectorSearchProfile": "mm-vector-profile",
            },
            {"name": "metadata_storage_last_modified", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True},
        ],
        "vectorSearch": {
            "profiles": [{"name": "mm-vector-profile", "algorithm": "mm-hnsw"}],
            "algorithms": [{"name": "mm-hnsw", "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}],
        },
        "semantic": {
            "configurations": [{
                "name": "mm-semantic-config",
                "prioritizedFields": {
                    "titleField": {"fieldName": "source_file_name"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                },
            }],
        },
    })
    print(f"    ✓ created")


# ── Skillsets ────────────────────────────────────────────────

def _create_basic_skillset(
    client: SearchAdminClient,
    skillset_name: str,
    index_name: str,
    file_type: str,
    openai_endpoint: str,
    embedding_deployment: str,
    dimensions: int,
    skills_function_url: str,
    skills_function_key: str,
    ai_services_subdomain: str = "",
) -> None:
    print(f"  [skillset] {skillset_name}  (file_type={file_type})")

    split_route = "markdown_split" if file_type == "pdf" else "pptx_page_split"

    skillset_payload = {
        "name": skillset_name,
        "description": f"Multimodal {file_type.upper()}: DI Layout + Custom {split_route} + Embedding",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                "name": "di-layout-skill",
                "context": "/document",
                "outputMode": "oneToMany",
                "inputs": [{"name": "file_data", "source": "/document/file_data"}],
                "outputs": [{"name": "markdown_document", "targetName": "layout_markdown"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
                "name": f"{file_type}-split-skill",
                "context": "/document",
                "uri": f"{skills_function_url}/api/{split_route}",
                "httpMethod": "POST",
                "timeout": "PT60S",
                "batchSize": 10,
                "degreeOfParallelism": 10,
                "httpHeaders": {"x-functions-key": skills_function_key},
                "inputs": [{"name": "text", "source": "/document/layout_markdown"}],
                "outputs": [{"name": "chunks", "targetName": "markdown_chunks"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "context": "/document/markdown_chunks/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [{"name": "text", "source": "/document/markdown_chunks/*"}],
                "outputs": [{"name": "embedding", "targetName": "chunk_vector"}],
            },
        ],
        "indexProjections": _index_projections(index_name),
    }

    if ai_services_subdomain:
        skillset_payload["cognitiveServices"] = {
            "@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity",
            "subdomainUrl": ai_services_subdomain.rstrip("/") + "/",
            "identity": None,
        }

    client.request("PUT", f"/skillsets/{skillset_name}?skipIndexerResetRequirementForCache=true", skillset_payload)
    print(f"    ✓ upserted")


def _create_verbalized_skillset(
    client: SearchAdminClient,
    skillset_name: str,
    index_name: str,
    openai_endpoint: str,
    embedding_deployment: str,
    dimensions: int,
    skills_function_url: str,
    skills_function_key: str,
    ai_services_subdomain: str = "",
) -> None:
    print(f"  [skillset] {skillset_name}")

    skillset_payload = {
        "name": skillset_name,
        "description": "Multimodal PDF: DI Layout + GPT-5.4 Verbalization + Markdown Split + Embedding",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                "name": "di-layout-skill",
                "context": "/document",
                "outputMode": "oneToMany",
                "inputs": [{"name": "file_data", "source": "/document/file_data"}],
                "outputs": [{"name": "markdown_document", "targetName": "layout_markdown"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
                "name": "verbalize-skill",
                "context": "/document",
                "uri": f"{skills_function_url}/api/verbalize",
                "httpMethod": "POST",
                "timeout": "PT230S",
                "batchSize": 1,
                "degreeOfParallelism": 10,
                "httpHeaders": {"x-functions-key": skills_function_key},
                "inputs": [
                    {"name": "markdown_text", "source": "/document/layout_markdown"},
                    {"name": "file_data", "source": "/document/file_data"},
                ],
                "outputs": [{"name": "verbalized_text", "targetName": "verbalized_markdown"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
                "name": "markdown-split-skill",
                "context": "/document",
                "uri": f"{skills_function_url}/api/markdown_split",
                "httpMethod": "POST",
                "timeout": "PT60S",
                "batchSize": 10,
                "degreeOfParallelism": 10,
                "httpHeaders": {"x-functions-key": skills_function_key},
                "inputs": [{"name": "text", "source": "/document/verbalized_markdown"}],
                "outputs": [{"name": "chunks", "targetName": "markdown_chunks"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "context": "/document/markdown_chunks/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [{"name": "text", "source": "/document/markdown_chunks/*"}],
                "outputs": [{"name": "embedding", "targetName": "chunk_vector"}],
            },
        ],
        "indexProjections": _index_projections(index_name),
    }

    if ai_services_subdomain:
        skillset_payload["cognitiveServices"] = {
            "@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity",
            "subdomainUrl": ai_services_subdomain.rstrip("/") + "/",
            "identity": None,
        }

    client.request("PUT", f"/skillsets/{skillset_name}?skipIndexerResetRequirementForCache=true", skillset_payload)
    print(f"    ✓ upserted")


def _index_projections(index_name: str) -> dict:
    return {
        "selectors": [{
            "targetIndexName": index_name,
            "parentKeyFieldName": "parent_id",
            "sourceContext": "/document/markdown_chunks/*",
            "mappings": [
                {"name": "content", "source": "/document/markdown_chunks/*"},
                {"name": "content_vector", "source": "/document/markdown_chunks/*/chunk_vector"},
                {"name": "source_file_name", "source": "/document/metadata_storage_name"},
                {"name": "source_blob_path", "source": "/document/metadata_storage_path"},
                {"name": "metadata_storage_last_modified", "source": "/document/metadata_storage_last_modified"},
                {"name": "file_type", "source": "/document/file_type"},
                {"name": "source_category", "source": "/document/source_category"},
            ],
        }],
        "parameters": {"projectionMode": "skipIndexingParentDocuments"},
    }


# ── Datasource ───────────────────────────────────────────────

def _create_datasource(
    client: SearchAdminClient,
    datasource_name: str,
    container_name: str,
    prefix: str,
    storage_resource_id: str,
) -> None:
    print(f"  [datasource] {datasource_name}")
    client.delete_if_exists(f"/datasources/{datasource_name}")
    client.request("PUT", f"/datasources/{datasource_name}", {
        "name": datasource_name,
        "type": "azureblob",
        "credentials": {"connectionString": f"ResourceId={storage_resource_id}"},
        "container": {"name": container_name, "query": prefix},
        "dataChangeDetectionPolicy": {
            "@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy",
            "highWaterMarkColumnName": "metadata_storage_last_modified",
        },
    })
    print(f"    ✓ created ({container_name}/{prefix})")


# ── Indexer ──────────────────────────────────────────────────

def _create_indexer(
    client: SearchAdminClient,
    indexer_name: str,
    datasource_name: str,
    index_name: str,
    skillset_name: str,
    schedule: str,
    start_time: str,
    indexed_extensions: str | None = None,
    enable_cache: bool = False,
) -> None:
    print(f"  [indexer] {indexer_name}")

    config: dict = {
        "dataToExtract": "contentAndMetadata",
        "parsingMode": "default",
        "allowSkillsetToReadFileData": True,
    }
    if indexed_extensions:
        config["indexedFileNameExtensions"] = indexed_extensions

    indexer_payload: dict = {
        "name": indexer_name,
        "dataSourceName": datasource_name,
        "targetIndexName": index_name,
        "skillsetName": skillset_name,
        "parameters": {
            "batchSize": 10,
            "maxFailedItems": 20,
            "maxFailedItemsPerBatch": 10,
            "configuration": config,
        },
        "fieldMappings": [
            {"sourceFieldName": "metadata_storage_path", "targetFieldName": "source_blob_path"},
            {"sourceFieldName": "metadata_storage_name", "targetFieldName": "source_file_name"},
        ],
    }

    if enable_cache:
        storage_resource_id = _env("AZURE_STORAGE_RESOURCE_ID")
        if storage_resource_id:
            indexer_payload["cache"] = {
                "storageConnectionString": f"ResourceId={storage_resource_id};",
                "enableReprocessing": True,
            }

    if schedule.lower() != "none":
        indexer_payload["schedule"] = {"interval": schedule, "startTime": start_time}

    client.request("PUT", f"/indexers/{indexer_name}", indexer_payload)
    print(f"    ✓ upserted")


# ══════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════

def setup_multimodal_pipeline(
    source: str = "st",
    pipeline: str = "all",
    run: bool = False,
    schedule: str = "PT24H",
    start_time: str = "2026-01-01T07:00:00Z",
    dimensions: int = 3072,
    container: str | None = None,
    prefix: str | None = None,
    enable_cache: bool = False,
    client: SearchAdminClient | None = None,
) -> None:
    """멀티모달 인덱싱 파이프라인 생성 (및 선택적 실행).

    Args:
        source: Blob prefix 세그먼트 (기본: 'st')
        pipeline: 'all', 'pdf', 'pptx', 'verbalized', 'basic', 'both'
        run: True이면 생성 후 인덱서 즉시 실행 + 폴링
        schedule: 인덱서 스케줄 (ISO 8601). 'none'이면 수동
        start_time: 스케줄 시작 시간 (UTC)
        dimensions: 임베딩 벡터 차원
        container: Blob 컨테이너 (None이면 환경변수)
        prefix: Blob prefix (None이면 'raw/')
        enable_cache: incremental enrichment cache 활성화
        client: SearchAdminClient 인스턴스 (None이면 환경변수로 생성)
    """
    if client is None:
        client = SearchAdminClient()

    # 환경변수 로드
    openai_endpoint = _env("AZURE_OPENAI_ENDPOINT")
    embedding_deployment = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", default="text-embedding-3-large")
    storage_resource_id = _env("AZURE_STORAGE_RESOURCE_ID")
    skills_function_url = _env("SKILLS_FUNCTION_URL")
    skills_function_key = _env("SKILLS_FUNCTION_KEY")
    ai_services_subdomain = _env("AZURE_AI_SERVICES_ENDPOINT")
    container = container or _env("AZURE_STORAGE_CONTAINER_NAME", default="raw-documents")
    prefix = prefix if prefix is not None else "raw/"

    want_pdf = pipeline in ("all", "both", "basic", "pdf")
    want_pptx = pipeline in ("all", "both", "basic", "pptx")
    want_verbalized = pipeline in ("all", "verbalized")

    # 리소스 이름
    pdf_index = f"{source}-multimodal-pdf-index"
    pdf_skillset = f"{source}-multimodal-pdf-skillset"
    pdf_indexer = f"{source}-multimodal-pdf-indexer"
    pptx_index = f"{source}-multimodal-pptx-index"
    pptx_skillset = f"{source}-multimodal-pptx-skillset"
    pptx_indexer = f"{source}-multimodal-pptx-indexer"
    verbalized_index = f"{source}-multimodal-verbalized-index"
    verbalized_skillset = f"{source}-multimodal-verbalized-skillset"
    verbalized_indexer = f"{source}-multimodal-verbalized-indexer"
    datasource_name = f"{source}-raw-datasource"

    print("=" * 60)
    print("AI Search 멀티모달 파이프라인 설정")
    print(f"  pipeline: {pipeline}  (pdf={want_pdf}, pptx={want_pptx}, verbalized={want_verbalized})")
    print(f"  container: {container}/{prefix}")
    print(f"  schedule: {schedule}")
    print("=" * 60)

    # 사전 정리
    print("\n[0] Cleanup dependent indexers")
    for idxr in (pdf_indexer, pptx_indexer, verbalized_indexer):
        client.delete_if_exists(f"/indexers/{idxr}")

    # 공유 데이터소스
    print("\n[1] Data Source")
    _create_datasource(client, datasource_name, container, prefix, storage_resource_id)

    if want_pdf:
        print(f"\n[2A] Pipeline PDF")
        _create_index(client, pdf_index, dimensions)
        _create_basic_skillset(
            client, pdf_skillset, pdf_index, "pdf",
            openai_endpoint, embedding_deployment, dimensions,
            skills_function_url, skills_function_key, ai_services_subdomain,
        )
        _create_indexer(
            client, pdf_indexer, datasource_name, pdf_index, pdf_skillset,
            schedule, start_time, indexed_extensions=".pdf", enable_cache=enable_cache,
        )
        if run:
            run_indexer(client, pdf_indexer)
            poll_indexer(client, pdf_indexer, timeout_sec=1200)

    if want_pptx:
        print(f"\n[2B] Pipeline PPTX")
        _create_index(client, pptx_index, dimensions)
        _create_basic_skillset(
            client, pptx_skillset, pptx_index, "pptx",
            openai_endpoint, embedding_deployment, dimensions,
            skills_function_url, skills_function_key, ai_services_subdomain,
        )
        _create_indexer(
            client, pptx_indexer, datasource_name, pptx_index, pptx_skillset,
            schedule, start_time, indexed_extensions=".pptx", enable_cache=enable_cache,
        )
        if run:
            run_indexer(client, pptx_indexer)
            poll_indexer(client, pptx_indexer, timeout_sec=1200)

    if want_verbalized:
        print(f"\n[2C] Pipeline Verbalized")
        _create_index(client, verbalized_index, dimensions)
        _create_verbalized_skillset(
            client, verbalized_skillset, verbalized_index,
            openai_endpoint, embedding_deployment, dimensions,
            skills_function_url, skills_function_key, ai_services_subdomain,
        )
        verb_start = start_time.replace("T07:00:", "T07:30:") if "T07:00:" in start_time else start_time
        _create_indexer(
            client, verbalized_indexer, datasource_name, verbalized_index, verbalized_skillset,
            schedule, verb_start, indexed_extensions=".pdf", enable_cache=enable_cache,
        )
        if run:
            run_indexer(client, verbalized_indexer)
            poll_indexer(client, verbalized_indexer, timeout_sec=1200)

    print(f"\n{'=' * 60}")
    print("✓ 멀티모달 파이프라인 설정 완료!")
