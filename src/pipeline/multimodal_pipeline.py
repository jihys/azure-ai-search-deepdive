"""
멀티모달(PDF/PPTX) AI Search 인덱싱 파이프라인 설정.

파이프라인 구성 (Built-in Skill Only):
  B-1 Basic PDF           : DI Layout (oneToMany, h2) → SplitSkill (safety) → Embedding
  B-2 Basic PPTX          : DI Layout (oneToMany, h2) → SplitSkill (safety) → Embedding
  B-3 Verbalized PDF      : DI Layout (oneToMany, h2) → SplitSkill → Embedding (text) + GenAI Prompt → Embedding (images)
  B-4 Verbalized PPTX     : DI Layout (oneToMany, h2) → SplitSkill → Embedding (text) + GenAI Prompt → Embedding (images)

B-1/B-2: DI Layout으로 Markdown 헤더(H2) 기준 시맨틱 청킹 (이미지 이해 없음)
B-3/B-4: B-1/B-2와 동일한 텍스트 청킹 + GenAI 이미지 설명을 별도 청크로 인덱싱

리소스 네이밍: multimodal-{type}-{resource}-{format} (prefix-free)
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
    ai_services_subdomain: str = "",
) -> None:
    print(f"  [skillset] {skillset_name}  (file_type={file_type})")

    skillset_payload = {
        "name": skillset_name,
        "description": f"Multimodal {file_type.upper()}: DI Layout (oneToMany, h2) + SplitSkill (safety) + Embedding",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                "name": "di-layout-skill",
                "context": "/document",
                "outputMode": "oneToMany",
                "markdownHeaderDepth": "h2",
                "inputs": [{"name": "file_data", "source": "/document/file_data"}],
                "outputs": [{"name": "markdown_document", "targetName": "markdown_sections"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "split-skill",
                "context": "/document/markdown_sections/*",
                "textSplitMode": "pages",
                "maximumPageLength": 2000,
                "pageOverlapLength": 200,
                "inputs": [{"name": "text", "source": "/document/markdown_sections/*/content"}],
                "outputs": [{"name": "textItems", "targetName": "pages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "context": "/document/markdown_sections/*/pages/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [{"name": "text", "source": "/document/markdown_sections/*/pages/*"}],
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
    gpt_deployment: str = "gpt-5.4",
    ai_services_subdomain: str = "",
) -> None:
    print(f"  [skillset] {skillset_name}")

    # GenAI Prompt Skill URI: chat completions endpoint
    genai_uri = f"{openai_endpoint.rstrip('/')}/openai/deployments/{gpt_deployment}/chat/completions"

    skillset_payload = {
        "name": skillset_name,
        "description": "Multimodal Verbalized: DI Layout (oneToMany, h2) + SplitSkill + Embedding (text) + GenAI Prompt + Embedding (images)",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                "name": "di-layout-skill",
                "context": "/document",
                "outputMode": "oneToMany",
                "markdownHeaderDepth": "h2",
                "inputs": [{"name": "file_data", "source": "/document/file_data"}],
                "outputs": [{"name": "markdown_document", "targetName": "markdown_sections"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.ChatCompletionSkill",
                "name": "genai-verbalize-skill",
                "context": "/document/normalized_images/*",
                "uri": genai_uri,
                "inputs": [
                    {"name": "image", "source": "/document/normalized_images/*/data"},
                    {"name": "systemMessage", "source": "='당신은 문서에 포함된 이미지, 도표, 차트를 분석하여 한국어로 상세하게 설명하는 AI 어시스턴트입니다. 시각적 요소의 핵심 정보를 텍스트로 정확하게 전달하세요.'"},
                    {"name": "userMessage", "source": "='이 이미지를 분석하여 상세하게 설명해주세요. 도표나 차트인 경우 데이터와 트렌드를 포함하세요.'"},
                ],
                "outputs": [{"name": "response", "targetName": "description"}],
                "commonModelParameters": {"temperature": 0.3, "maxTokens": 2048},
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "split-skill",
                "context": "/document/markdown_sections/*",
                "textSplitMode": "pages",
                "maximumPageLength": 2000,
                "pageOverlapLength": 200,
                "inputs": [{"name": "text", "source": "/document/markdown_sections/*/content"}],
                "outputs": [{"name": "textItems", "targetName": "pages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "context": "/document/markdown_sections/*/pages/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [{"name": "text", "source": "/document/markdown_sections/*/pages/*"}],
                "outputs": [{"name": "embedding", "targetName": "chunk_vector"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill-image",
                "context": "/document/normalized_images/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [{"name": "text", "source": "/document/normalized_images/*/description"}],
                "outputs": [{"name": "embedding", "targetName": "chunk_vector"}],
            },
        ],
        "indexProjections": _index_projections(index_name, verbalized=True),
    }

    if ai_services_subdomain:
        skillset_payload["cognitiveServices"] = {
            "@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity",
            "subdomainUrl": ai_services_subdomain.rstrip("/") + "/",
            "identity": None,
        }

    client.request("PUT", f"/skillsets/{skillset_name}?skipIndexerResetRequirementForCache=true", skillset_payload)
    print(f"    ✓ upserted")


def _index_projections(index_name: str, *, verbalized: bool = False) -> dict:
    text_selector = {
        "targetIndexName": index_name,
        "parentKeyFieldName": "parent_id",
        "sourceContext": "/document/markdown_sections/*/pages/*",
        "mappings": [
            {"name": "content", "source": "/document/markdown_sections/*/pages/*"},
            {"name": "content_vector", "source": "/document/markdown_sections/*/pages/*/chunk_vector"},
            {"name": "content_type", "source": "='text'"},
            {"name": "source_file_name", "source": "/document/metadata_storage_name"},
            {"name": "source_blob_path", "source": "/document/metadata_storage_path"},
            {"name": "metadata_storage_last_modified", "source": "/document/metadata_storage_last_modified"},
        ],
    }

    if not verbalized:
        return {
            "selectors": [text_selector],
            "parameters": {"projectionMode": "skipIndexingParentDocuments"},
        }

    image_selector = {
        "targetIndexName": index_name,
        "parentKeyFieldName": "parent_id",
        "sourceContext": "/document/normalized_images/*",
        "mappings": [
            {"name": "content", "source": "/document/normalized_images/*/description"},
            {"name": "content_vector", "source": "/document/normalized_images/*/chunk_vector"},
            {"name": "content_type", "source": "='image_description'"},
            {"name": "source_file_name", "source": "/document/metadata_storage_name"},
            {"name": "source_blob_path", "source": "/document/metadata_storage_path"},
            {"name": "metadata_storage_last_modified", "source": "/document/metadata_storage_last_modified"},
        ],
    }

    return {
        "selectors": [text_selector, image_selector],
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
    image_action: str | None = None,
) -> None:
    print(f"  [indexer] {indexer_name}")

    config: dict = {
        "dataToExtract": "contentAndMetadata",
        "parsingMode": "default",
        "allowSkillsetToReadFileData": True,
    }
    if indexed_extensions:
        config["indexedFileNameExtensions"] = indexed_extensions
    if image_action:
        config["imageAction"] = image_action
        config["normalizedImageMaxWidth"] = 4200
        config["normalizedImageMaxHeight"] = 4200

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
        source: (deprecated) 리소스 이름에 사용하지 않음. 하위 호환용 유지
        pipeline: 'all', 'pdf', 'pptx', 'verbalized', 'verbalized-pptx', 'basic', 'both'
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
    gpt_deployment = _env("AZURE_OPENAI_GPT54_DEPLOYMENT", default="gpt-5.4")
    ai_services_subdomain = _env("AZURE_AI_SERVICES_ENDPOINT")
    container = container or _env("AZURE_STORAGE_CONTAINER_NAME", default="raw-documents")
    base_prefix = prefix if prefix is not None else "raw/"
    if not base_prefix.endswith("/"):
        base_prefix += "/"

    want_pdf = pipeline in ("all", "both", "basic", "pdf")
    want_pptx = pipeline in ("all", "both", "basic", "pptx")
    want_verbalized = pipeline in ("all", "verbalized")
    want_verbalized_pptx = pipeline in ("all", "verbalized", "verbalized-pptx")

    # 리소스 이름 (prefix-free 고정 네이밍)
    pdf_index = "multimodal-basic-index-pdf"
    pdf_skillset = "multimodal-basic-skillset-pdf"
    pdf_indexer = "multimodal-basic-indexer-pdf"
    pptx_index = "multimodal-basic-index-pptx"
    pptx_skillset = "multimodal-basic-skillset-pptx"
    pptx_indexer = "multimodal-basic-indexer-pptx"
    verbalized_index = "multimodal-verbalized-index-pdf"
    verbalized_skillset = "multimodal-verbalized-skillset-pdf"
    verbalized_indexer = "multimodal-verbalized-indexer-pdf"
    verbalized_pptx_index = "multimodal-verbalized-index-pptx"
    verbalized_pptx_skillset = "multimodal-verbalized-skillset-pptx"
    verbalized_pptx_indexer = "multimodal-verbalized-indexer-pptx"
    datasource_pdf = "multimodal-datasource-pdf"
    datasource_pptx = "multimodal-datasource-pptx"

    print("=" * 60)
    print("AI Search 멀티모달 파이프라인 설정")
    print(f"  pipeline: {pipeline}  (pdf={want_pdf}, pptx={want_pptx}, verbalized={want_verbalized}, verbalized_pptx={want_verbalized_pptx})")
    print(f"  container: {container}/{base_prefix}")
    print(f"  schedule: {schedule}")
    print("=" * 60)

    # 사전 정리
    print("\n[0] Cleanup dependent indexers")
    for idxr in (pdf_indexer, pptx_indexer, verbalized_indexer, verbalized_pptx_indexer):
        client.delete_if_exists(f"/indexers/{idxr}")

    # 데이터소스 (PDF / PPTX 분리)
    pdf_ds_prefix = base_prefix + "pdf/"
    pptx_ds_prefix = base_prefix + "pptx/"
    print("\n[1] Data Sources")
    if want_pdf or want_verbalized:
        _create_datasource(client, datasource_pdf, container, pdf_ds_prefix, storage_resource_id)
    if want_pptx or want_verbalized_pptx:
        _create_datasource(client, datasource_pptx, container, pptx_ds_prefix, storage_resource_id)

    if want_pdf:
        print(f"\n[2A] Pipeline PDF")
        _create_index(client, pdf_index, dimensions)
        _create_basic_skillset(
            client, pdf_skillset, pdf_index, "pdf",
            openai_endpoint, embedding_deployment, dimensions,
            ai_services_subdomain,
        )
        _create_indexer(
            client, pdf_indexer, datasource_pdf, pdf_index, pdf_skillset,
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
            ai_services_subdomain,
        )
        _create_indexer(
            client, pptx_indexer, datasource_pptx, pptx_index, pptx_skillset,
            schedule, start_time, indexed_extensions=".pptx", enable_cache=enable_cache,
        )
        if run:
            run_indexer(client, pptx_indexer)
            poll_indexer(client, pptx_indexer, timeout_sec=1200)

    if want_verbalized:
        print(f"\n[2C] Pipeline Verbalized PDF")
        _create_index(client, verbalized_index, dimensions)
        _create_verbalized_skillset(
            client, verbalized_skillset, verbalized_index,
            openai_endpoint, embedding_deployment, dimensions,
            gpt_deployment, ai_services_subdomain,
        )
        verb_start = start_time.replace("T07:00:", "T07:30:") if "T07:00:" in start_time else start_time
        _create_indexer(
            client, verbalized_indexer, datasource_pdf, verbalized_index, verbalized_skillset,
            schedule, verb_start, indexed_extensions=".pdf", enable_cache=enable_cache,
            image_action="generateNormalizedImages",
        )
        if run:
            run_indexer(client, verbalized_indexer)
            poll_indexer(client, verbalized_indexer, timeout_sec=1200)

    if want_verbalized_pptx:
        print(f"\n[2D] Pipeline Verbalized PPTX")
        _create_index(client, verbalized_pptx_index, dimensions)
        _create_verbalized_skillset(
            client, verbalized_pptx_skillset, verbalized_pptx_index,
            openai_endpoint, embedding_deployment, dimensions,
            gpt_deployment, ai_services_subdomain,
        )
        verb_pptx_start = start_time.replace("T07:00:", "T08:00:") if "T07:00:" in start_time else start_time
        _create_indexer(
            client, verbalized_pptx_indexer, datasource_pptx, verbalized_pptx_index, verbalized_pptx_skillset,
            schedule, verb_pptx_start, indexed_extensions=".pptx", enable_cache=enable_cache,
            image_action="generateNormalizedImages",
        )
        if run:
            run_indexer(client, verbalized_pptx_indexer)
            poll_indexer(client, verbalized_pptx_indexer, timeout_sec=1200)

    print(f"\n{'=' * 60}")
    print("✓ 멀티모달 파이프라인 설정 완료!")
