"""
AI Search 멀티모달 인덱싱 파이프라인 설정 스크립트

두 가지 파이프라인을 생성하여 성능 비교:
  [Pipeline A] basic — DI Layout + Native SplitSkill (markdown mode) + Embedding (Function App 불필요)
  [Pipeline B] verbalized — DI Layout + GPT-5.4 이미지 설명 + Markdown 헤더 분할 + Embedding

동작 방식:
  - AI Search Indexer 스케줄 기반 자동 실행 (기본 24시간)
  - 신규/변경 데이터만 처리 (HighWaterMark Change Detection)
  - Markdown 헤더 분할은 Custom Web API Skill (Azure Function)로 처리
  - Verbalization은 GPT-5.4 Custom Web API Skill로 처리

대상:
  raw-documents 컨테이너의 raw/pdf/<source>/ 하위 PDF

사전 요구사항:
  1. skills-function/ 배포 완료 (Azure Function App)
  2. AI Search Managed Identity → Storage/OpenAI RBAC 설정
  3. Function App URL 환경변수 설정 (SKILLS_FUNCTION_URL, SKILLS_FUNCTION_KEY)

실행:
  # 두 파이프라인 모두 생성 + 즉시 실행
  uv run python scripts/setup_ai_search_multimodal_pipeline.py --run-indexer

  # basic 파이프라인만
  uv run python scripts/setup_ai_search_multimodal_pipeline.py --pipeline basic

  # verbalized 파이프라인만
  uv run python scripts/setup_ai_search_multimodal_pipeline.py --pipeline verbalized

  # 스케줄 12시간, 즉시 실행
  uv run python scripts/setup_ai_search_multimodal_pipeline.py --schedule PT12H --run-indexer
"""

from __future__ import annotations

import argparse
import os
import time

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

API_VERSION = "2024-11-01-preview"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create AI Search multimodal indexing pipelines (basic + verbalized).")
    parser.add_argument("--source", default="st", help="Source segment under raw/pdf/<source>/")
    parser.add_argument("--container", default=os.getenv("AZURE_STORAGE_CONTAINER_NAME", "raw-documents"))
    parser.add_argument("--prefix", default="", help="Override blob prefix (default: raw/pdf/<source>/)")
    parser.add_argument("--pipeline", choices=["both", "basic", "verbalized", "pdf", "pptx", "all"], default="all",
                        help="Which pipeline(s) to create. 'basic'=='all' (pdf+pptx), 'all' adds verbalized.")
    parser.add_argument("--run-indexer", action="store_true", help="Run indexer(s) immediately after creation")
    parser.add_argument("--dimensions", type=int, default=3072, help="Embedding vector dimensions")
    parser.add_argument("--schedule", default="PT24H",
                        help="Indexer schedule interval (ISO 8601, e.g. PT24H, PT12H). 'none' to disable.")
    parser.add_argument("--start-time", default="2026-01-01T07:00:00Z", help="Schedule start time (UTC)")
    parser.add_argument("--max-chunk-chars", type=int, default=2000, help="Max characters per markdown chunk")
    parser.add_argument("--overlap-chars", type=int, default=200, help="Character overlap between chunks")
    return parser.parse_args()


class SearchAdminClient:
    def __init__(self, endpoint: str, admin_key: str):
        self.endpoint = endpoint.rstrip("/")
        self.admin_key = admin_key
        # VM Managed Identity는 해당 사용자의 Search RBAC를 공유하지 않으므로 제외
        self.credential = (
            DefaultAzureCredential(
                exclude_managed_identity_credential=True,
                exclude_workload_identity_credential=True,
            )
            if not admin_key
            else None
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.admin_key:
            headers["api-key"] = self.admin_key
        else:
            token = self.credential.get_token("https://search.azure.com/.default")
            headers["Authorization"] = f"Bearer {token.token}"
        return headers

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        sep = "&" if "?" in path else "?"
        url = f"{self.endpoint}{path}{sep}api-version={API_VERSION}"
        resp = requests.request(method, url, headers=self._headers(), json=payload, timeout=120)
        if resp.status_code not in (200, 201, 202, 204):
            print(f"[ERROR] {method} {path} -> {resp.status_code}")
            print(resp.text[:1500])
            resp.raise_for_status()
        return resp.json() if resp.content else {}


def delete_if_exists(client: SearchAdminClient, path: str) -> None:
    url = f"{client.endpoint}{path}?api-version={API_VERSION}"
    resp = requests.delete(url, headers=client._headers(), timeout=120)
    if resp.status_code in (200, 202, 204):
        print(f"  - deleted existing {path}")
    elif resp.status_code == 404:
        pass
    else:
        print(f"  - skip delete {path}: {resp.status_code}")


# ═══════════════════════════════════════════════════════════════
# Index 생성 (두 파이프라인 공통 스키마)
# ═══════════════════════════════════════════════════════════════

def create_index(client: SearchAdminClient, index_name: str, dimensions: int) -> None:
    print(f"  [index] {index_name}")

    index_payload = {
        "name": index_name,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True, "analyzer": "keyword"},
            {"name": "parent_id", "type": "Edm.String", "filterable": True},
            {"name": "source_file_name", "type": "Edm.String", "searchable": True, "filterable": True},
            {"name": "source_blob_path", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "content_type", "type": "Edm.String", "filterable": True, "facetable": True},
            # 분류 필터용 — blob 사용자 메타데이터에서 enrichment
            {"name": "file_type", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
            {"name": "source_category", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
            {"name": "content", "type": "Edm.String", "searchable": True, "analyzer": "ko.lucene"},
            {
                "name": "content_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "retrievable": False,
                "dimensions": dimensions,
                "vectorSearchProfile": "mm-vector-profile",
            },
            {"name": "metadata_storage_last_modified", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True},
        ],
        "vectorSearch": {
            "profiles": [{"name": "mm-vector-profile", "algorithm": "mm-hnsw"}],
            "algorithms": [{"name": "mm-hnsw", "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}],
        },
        "semantic": {
            "configurations": [
                {
                    "name": "mm-semantic-config",
                    "prioritizedFields": {
                        "titleField": {"fieldName": "source_file_name"},
                        "prioritizedContentFields": [{"fieldName": "content"}],
                    },
                }
            ]
        },
    }

    delete_if_exists(client, f"/indexes/{index_name}")
    client.request("PUT", f"/indexes/{index_name}", index_payload)
    print(f"    ✓ created")


# ═══════════════════════════════════════════════════════════════
# Skillset 생성
# ═══════════════════════════════════════════════════════════════

def create_basic_skillset(
    client: SearchAdminClient,
    skillset_name: str,
    index_name: str,
    openai_endpoint: str,
    embedding_deployment: str,
    dimensions: int,
    skills_function_url: str,
    skills_function_key: str,
    file_type: str,                    # 'pdf' 또는 'pptx'
    max_chunk_chars: int,
    overlap_chars: int,
    ai_services_subdomain: str = "",
) -> None:
    """ト 파이프라인 (basic, file-type 별로 분리):
      - PDF  : DI Layout → Custom markdown_split (헤더+길이) → Embedding
      - PPTX : DI Layout → Custom pptx_page_split (슬라이드 단위) → Embedding
    공통: indexProjections → 동일 인덱스. file_type 필드로 분리 가능."""
    print(f"  [skillset] {skillset_name}  (file_type={file_type})")

    if file_type == "pdf":
        split_route = "markdown_split"
        split_desc = "Markdown 헤더/길이 기반 분할 (PDF)"
        split_inputs = [
            {"name": "text", "source": "/document/layout_markdown"},
        ]
    elif file_type == "pptx":
        split_route = "pptx_page_split"
        split_desc = "PPTX <!-- PageBreak --> 기반 슬라이드 분할"
        split_inputs = [
            {"name": "text", "source": "/document/layout_markdown"},
        ]
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    skillset_payload = {
        "name": skillset_name,
        "description": f"Multimodal {file_type.upper()}: DI Layout + Custom {split_route} + Embedding",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                "name": "di-layout-skill",
                "description": f"Extract markdown from {file_type.upper()} using Document Intelligence Layout",
                "context": "/document",
                "outputMode": "oneToMany",
                "inputs": [
                    {"name": "file_data", "source": "/document/file_data"},
                ],
                "outputs": [
                    {"name": "markdown_document", "targetName": "layout_markdown"},
                ],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
                "name": f"{file_type}-split-skill",
                "description": split_desc,
                "context": "/document",
                "uri": f"{skills_function_url}/api/{split_route}",
                "httpMethod": "POST",
                "timeout": "PT60S",
                # 병렬화: 여러 record 를 동시에 함수로 전송.
                # split 은 순수 파싱이라 가벼우므로 batchSize 크게 잡고 병렬도 높게.
                "batchSize": 10,
                "degreeOfParallelism": 10,
                "httpHeaders": {
                    "x-functions-key": skills_function_key,
                },
                "inputs": split_inputs,
                "outputs": [
                    {"name": "chunks", "targetName": "markdown_chunks"},
                ],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "description": "Generate embedding for each chunk",
                "context": "/document/markdown_chunks/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [
                    {"name": "text", "source": "/document/markdown_chunks/*"},
                ],
                "outputs": [
                    {"name": "embedding", "targetName": "chunk_vector"},
                ],
            },
        ],
        "indexProjections": {
            "selectors": [
                {
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
                }
            ],
            "parameters": {"projectionMode": "skipIndexingParentDocuments"},
        },
    }

    # AI Services 첨부 (free quota 20 docs 제한 해제). identity-based (Search MI).
    if ai_services_subdomain:
        skillset_payload["cognitiveServices"] = {
            "@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity",
            "subdomainUrl": ai_services_subdomain.rstrip("/") + "/",
            "identity": None,
        }

    # 캐시 보존: skillset 을 다시 PUT 해도 cache HIT 이 유지되도록
    # ?skipIndexerResetRequirementForCache=true 쿼리 파라미터 사용.
    # delete + PUT 은 etag 가 새로 발급되어 cache 가 무효화될 수 있으므로 upsert(PUT) 로만.
    client.request("PUT", f"/skillsets/{skillset_name}?skipIndexerResetRequirementForCache=true", skillset_payload)
    print(f"    ✓ upserted (DI Layout → {split_route} → Embedding)")


def create_verbalized_skillset(
    client: SearchAdminClient,
    skillset_name: str,
    index_name: str,
    openai_endpoint: str,
    embedding_deployment: str,
    dimensions: int,
    skills_function_url: str,
    skills_function_key: str,
    max_chunk_chars: int,
    overlap_chars: int,
    ai_services_subdomain: str = "",
) -> None:
    """Pipeline B: DI Layout → GPT-5.4 Verbalization (Custom) → Markdown Header Split (Custom) → Embedding"""
    print(f"  [skillset] {skillset_name}")

    skillset_payload = {
        "name": skillset_name,
        "description": "Multimodal PDF: DI Layout + GPT-5.4 Verbalization + Markdown Header Split + Embedding",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                "name": "di-layout-skill",
                "description": "Extract markdown from PDF using Document Intelligence Layout",
                "context": "/document",
                "outputMode": "oneToMany",
                "inputs": [
                    {"name": "file_data", "source": "/document/file_data"},
                ],
                "outputs": [
                    {"name": "markdown_document", "targetName": "layout_markdown"},
                ],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
                "name": "verbalize-skill",
                "description": "GPT-5.4 Vision으로 이미지/도표 설명 생성",
                "context": "/document",
                "uri": f"{skills_function_url}/api/verbalize",
                "httpMethod": "POST",
                "timeout": "PT230S",
                # 병렬화: GPT 호출이 무거움(파일당 수분) → batchSize=1 유지하되
                # 서로 다른 record 를 여러 HTTP 호출로 동시 처리.
                "batchSize": 1,
                "degreeOfParallelism": 10,
                "httpHeaders": {
                    "x-functions-key": skills_function_key,
                },
                "inputs": [
                    {"name": "markdown_text", "source": "/document/layout_markdown"},
                    {"name": "file_data", "source": "/document/file_data"},
                ],
                "outputs": [
                    {"name": "verbalized_text", "targetName": "verbalized_markdown"},
                ],
            },
            {
                "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
                "name": "markdown-split-skill",
                "description": "Markdown 헤더 기반 분할 (verbalized text)",
                "context": "/document",
                "uri": f"{skills_function_url}/api/markdown_split",
                "httpMethod": "POST",
                "timeout": "PT60S",
                "batchSize": 10,
                "degreeOfParallelism": 10,
                "httpHeaders": {
                    "x-functions-key": skills_function_key,
                },
                "inputs": [
                    {"name": "text", "source": "/document/verbalized_markdown"},
                ],
                "outputs": [
                    {"name": "chunks", "targetName": "markdown_chunks"},
                ],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embedding-skill",
                "description": "Generate embedding for each markdown chunk",
                "context": "/document/markdown_chunks/*",
                "resourceUri": openai_endpoint,
                "deploymentId": embedding_deployment,
                "modelName": "text-embedding-3-large",
                "dimensions": dimensions,
                "inputs": [
                    {"name": "text", "source": "/document/markdown_chunks/*"},
                ],
                "outputs": [
                    {"name": "embedding", "targetName": "chunk_vector"},
                ],
            },
        ],
        "indexProjections": {
            "selectors": [
                {
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
                }
            ],
            "parameters": {"projectionMode": "skipIndexingParentDocuments"},
        },
    }

    # AI Services 첨부 (free quota 20 docs 제한 해제). identity-based (Search MI).
    if ai_services_subdomain:
        skillset_payload["cognitiveServices"] = {
            "@odata.type": "#Microsoft.Azure.Search.AIServicesByIdentity",
            "subdomainUrl": ai_services_subdomain.rstrip("/") + "/",
            "identity": None,
        }

    # 캐시 보존: skillset 을 다시 PUT 해도 cache HIT 이 유지되도록
    # ?skipIndexerResetRequirementForCache=true 쿼리 파라미터 사용.
    client.request("PUT", f"/skillsets/{skillset_name}?skipIndexerResetRequirementForCache=true", skillset_payload)
    print(f"    ✓ upserted (DI Layout → GPT-5.4 Verbalize → Markdown Split → Embedding)")


# ═══════════════════════════════════════════════════════════════
# Data Source 생성 (공유: 두 파이프라인이 같은 datasource 사용)
# ═══════════════════════════════════════════════════════════════

def create_datasource(
    client: SearchAdminClient,
    datasource_name: str,
    container_name: str,
    prefix: str,
    storage_resource_id: str,
) -> None:
    print(f"  [datasource] {datasource_name}")

    if not storage_resource_id:
        raise ValueError("AZURE_STORAGE_RESOURCE_ID is required for managed identity datasource.")

    ds_payload = {
        "name": datasource_name,
        "type": "azureblob",
        "credentials": {
            "connectionString": f"ResourceId={storage_resource_id}",
        },
        "container": {
            "name": container_name,
            "query": prefix,
        },
        "dataChangeDetectionPolicy": {
            "@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy",
            "highWaterMarkColumnName": "metadata_storage_last_modified",
        },
    }

    delete_if_exists(client, f"/datasources/{datasource_name}")
    client.request("PUT", f"/datasources/{datasource_name}", ds_payload)
    print(f"    ✓ created ({container_name}/{prefix})")


# ═══════════════════════════════════════════════════════════════
# Indexer 생성
# ═══════════════════════════════════════════════════════════════

def create_indexer(
    client: SearchAdminClient,
    indexer_name: str,
    datasource_name: str,
    index_name: str,
    skillset_name: str,
    run_now: bool,
    schedule_interval: str,
    schedule_start_time: str,
    indexed_extensions: str | None = None,   # 예: ".pdf" 또는 ".pptx"
    excluded_extensions: str | None = None,
) -> None:
    print(f"  [indexer] {indexer_name}")

    config = {
        "dataToExtract": "contentAndMetadata",
        "parsingMode": "default",
        "allowSkillsetToReadFileData": True,
    }
    if indexed_extensions:
        config["indexedFileNameExtensions"] = indexed_extensions
    if excluded_extensions:
        config["excludedFileNameExtensions"] = excluded_extensions

    indexer_payload = {
        "name": indexer_name,
        "dataSourceName": datasource_name,
        "targetIndexName": index_name,
        "skillsetName": skillset_name,
        "parameters": {
            # 인덱서가 한 번에 읽어 skillset 에 흠려주는 문서 수.
            # 멀티모달(GPT 호출 포함) 경우 batch 가 클수록 스킬 병렬성 증가.
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

    # Incremental enrichment cache (옵션): SETUP_ENABLE_CACHE=1 일 때만 활성화
    # 멀티모달 파이프라인은 DI Layout / GPT-비전 호출 비용이 매우 크므로 캐시 효과가 가장 큼
    if os.environ.get("SETUP_ENABLE_CACHE") == "1":
        storage_resource_id = os.environ.get("AZURE_STORAGE_RESOURCE_ID", "")
        if storage_resource_id:
            indexer_payload["cache"] = {
                "storageConnectionString": f"ResourceId={storage_resource_id};",
                "enableReprocessing": True,
            }
            print(f"    cache: enabled (Storage MSI 'Storage Blob Data Contributor' 권한 필요)")

    # 스케줄 설정 — 신규 데이터 없으면 Indexer가 자동으로 skip
    if schedule_interval.lower() != "none":
        indexer_payload["schedule"] = {
            "interval": schedule_interval,
            "startTime": schedule_start_time,
        }

    # delete + PUT 은 cache state 를 잃을 수 있으므로 upsert(PUT) 로만.
    client.request("PUT", f"/indexers/{indexer_name}", indexer_payload)

    schedule_msg = f"every {schedule_interval}" if schedule_interval.lower() != "none" else "no schedule"
    print(f"    ✓ upserted ({schedule_msg})")

    if run_now:
        client.request("POST", f"/indexers/{indexer_name}/run", {})
        print(f"    → run triggered")


def wait_indexer(client: SearchAdminClient, indexer_name: str, timeout_sec: int = 1200) -> None:
    start = time.time()
    while True:
        status = client.request("GET", f"/indexers/{indexer_name}/status")
        last = status.get("lastResult") or {}
        state = last.get("status", "unknown")
        processed = last.get("itemsProcessed", 0)
        failed = last.get("itemsFailed", 0)
        print(f"    status={state} processed={processed} failed={failed}")

        if state in {"success", "transientFailure", "persistentFailure", "reset"}:
            break
        if (time.time() - start) > timeout_sec:
            print("    timeout reached")
            break
        time.sleep(20)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    load_dotenv()
    args = parse_args()

    # ── 환경 변수 ──
    search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT") or os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT", "")
    search_admin_key = os.getenv("AZURE_SEARCH_ADMIN_KEY", "")
    openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
    storage_resource_id = os.getenv("AZURE_STORAGE_RESOURCE_ID", "")
    skills_function_url = os.getenv("SKILLS_FUNCTION_URL", "")
    skills_function_key = os.getenv("SKILLS_FUNCTION_KEY", "")
    ai_services_subdomain = os.getenv("AZURE_AI_SERVICES_ENDPOINT", "")

    if not search_endpoint:
        raise ValueError("AZURE_SEARCH_SERVICE_ENDPOINT (or AZURE_SEARCH_ENDPOINT) is required.")
    if not openai_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT is required.")

    # 'basic' 은 pdf+pptx 두 파이프라인을 말함
    pipeline = args.pipeline
    want_pdf = pipeline in ("all", "both", "basic", "pdf")
    want_pptx = pipeline in ("all", "both", "basic", "pptx")
    want_verbalized = pipeline in ("all", "verbalized")

    if (want_pdf or want_pptx or want_verbalized) and not skills_function_url:
        raise ValueError("SKILLS_FUNCTION_URL is required (deploy skills-function via notebook 01 §5.5).")

    # 데이터소스 prefix는 raw/ (pdf+pptx 서브폴더 모두 포함). args.prefix로 재정의 가능.
    prefix = args.prefix or "raw/"

    # ── 리소스 이름 (file-type 별로 분리) ──
    pdf_index = f"{args.source}-multimodal-pdf-index"
    pdf_skillset = f"{args.source}-multimodal-pdf-skillset"
    pdf_indexer = f"{args.source}-multimodal-pdf-indexer"

    pptx_index = f"{args.source}-multimodal-pptx-index"
    pptx_skillset = f"{args.source}-multimodal-pptx-skillset"
    pptx_indexer = f"{args.source}-multimodal-pptx-indexer"

    verbalized_index = f"{args.source}-multimodal-verbalized-index"
    verbalized_skillset = f"{args.source}-multimodal-verbalized-skillset"
    verbalized_indexer = f"{args.source}-multimodal-verbalized-indexer"

    datasource_name = f"{args.source}-raw-datasource"

    # ── 설정 출력 ──
    print("=" * 60)
    print("AI Search 멀티모달 파이프라인 설정")
    print("=" * 60)
    print(f"  search      : {search_endpoint}")
    print(f"  container   : {args.container}/{prefix}")
    print(f"  skills func : {skills_function_url}")
    print(f"  pipeline    : {pipeline}  (pdf={want_pdf}, pptx={want_pptx}, verbalized={want_verbalized})")
    print(f"  schedule    : {args.schedule} (start: {args.start_time})")
    print(f"  chunk       : max {args.max_chunk_chars} chars, overlap {args.overlap_chars}")
    print()

    client = SearchAdminClient(endpoint=search_endpoint, admin_key=search_admin_key)

    # ── 사전 정리: datasource 를 참조하는 기존 인덱서 먼저 삭제 ──
    #    (datasource 재생성 시 의존 인덱서의 change-tracking state 충돌 방지)
    print("[0] Cleanup dependent indexers (so datasource can be recreated)")
    for _idxr in (pdf_indexer, pptx_indexer, verbalized_indexer):
        delete_if_exists(client, f"/indexers/{_idxr}")
    print()

    # ── Data Source (3개 인덱서 공유) ──
    print("[1] Data Source")
    create_datasource(
        client, datasource_name=datasource_name,
        container_name=args.container, prefix=prefix,
        storage_resource_id=storage_resource_id,
    )
    print()

    # ── Pipeline PDF ──
    if want_pdf:
        print("[2A] Pipeline PDF (DI Layout → markdown_split[header+length] → Embedding)")
        create_index(client, index_name=pdf_index, dimensions=args.dimensions)
        create_basic_skillset(
            client, skillset_name=pdf_skillset, index_name=pdf_index,
            openai_endpoint=openai_endpoint, embedding_deployment=embedding_deployment,
            dimensions=args.dimensions,
            skills_function_url=skills_function_url,
            skills_function_key=skills_function_key,
            file_type="pdf",
            max_chunk_chars=args.max_chunk_chars, overlap_chars=args.overlap_chars,
            ai_services_subdomain=ai_services_subdomain,
        )
        create_indexer(
            client, indexer_name=pdf_indexer, datasource_name=datasource_name,
            index_name=pdf_index, skillset_name=pdf_skillset,
            run_now=args.run_indexer, schedule_interval=args.schedule,
            schedule_start_time=args.start_time,
            indexed_extensions=".pdf",
        )
        if args.run_indexer:
            wait_indexer(client, indexer_name=pdf_indexer)
        print()

    # ── Pipeline PPTX ──
    if want_pptx:
        print("[2B] Pipeline PPTX (DI Layout → pptx_page_split[slide] → Embedding)")
        create_index(client, index_name=pptx_index, dimensions=args.dimensions)
        create_basic_skillset(
            client, skillset_name=pptx_skillset, index_name=pptx_index,
            openai_endpoint=openai_endpoint, embedding_deployment=embedding_deployment,
            dimensions=args.dimensions,
            skills_function_url=skills_function_url,
            skills_function_key=skills_function_key,
            file_type="pptx",
            max_chunk_chars=args.max_chunk_chars, overlap_chars=args.overlap_chars,
            ai_services_subdomain=ai_services_subdomain,
        )
        create_indexer(
            client, indexer_name=pptx_indexer, datasource_name=datasource_name,
            index_name=pptx_index, skillset_name=pptx_skillset,
            run_now=args.run_indexer, schedule_interval=args.schedule,
            schedule_start_time=args.start_time,
            indexed_extensions=".pptx",
        )
        if args.run_indexer:
            wait_indexer(client, indexer_name=pptx_indexer)
        print()

    # ── Pipeline Verbalized (PDF만) ──
    if want_verbalized:
        print("[2C] Pipeline VERBALIZED (DI Layout → GPT-5.4 → Markdown Split → Embedding)")
        create_index(client, index_name=verbalized_index, dimensions=args.dimensions)
        create_verbalized_skillset(
            client,
            skillset_name=verbalized_skillset, index_name=verbalized_index,
            openai_endpoint=openai_endpoint, embedding_deployment=embedding_deployment,
            dimensions=args.dimensions,
            skills_function_url=skills_function_url,
            skills_function_key=skills_function_key,
            max_chunk_chars=args.max_chunk_chars, overlap_chars=args.overlap_chars,
            ai_services_subdomain=ai_services_subdomain,
        )
        verb_start = args.start_time.replace("T07:00:", "T07:30:") if "T07:00:" in args.start_time else args.start_time
        create_indexer(
            client, indexer_name=verbalized_indexer, datasource_name=datasource_name,
            index_name=verbalized_index, skillset_name=verbalized_skillset,
            run_now=args.run_indexer, schedule_interval=args.schedule,
            schedule_start_time=verb_start,
            indexed_extensions=".pdf",   # verbalized는 PDF 대상
        )
        if args.run_indexer:
            wait_indexer(client, indexer_name=verbalized_indexer)
        print()

    # ── 완료 ──
    print("=" * 60)
    print("✓ 파이프라인 설정 완료!")
    if args.schedule.lower() != "none":
        print(f"  Indexer가 매 {args.schedule} 간격으로 자동 실행됩니다.")
    print()
    print("  인덱스:")
    if want_pdf:
        print(f"    [PDF]        {pdf_index}        — markdown header+length split")
    if want_pptx:
        print(f"    [PPTX]       {pptx_index}       — slide-level page split")
    if want_verbalized:
        print(f"    [Verbalized] {verbalized_index} — GPT-5.4 image description")


if __name__ == "__main__":
    main()
