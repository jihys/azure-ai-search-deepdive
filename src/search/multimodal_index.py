"""
Azure AI Search 멀티모달 인덱스 관리자
- 텍스트 + 이미지를 동일한 벡터 공간에서 검색
- Image Verbalization → 텍스트 임베딩 방식
- 참고: https://learn.microsoft.com/en-us/azure/search/multimodal-search-overview
"""

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery


class MultimodalIndexManager:
    """멀티모달 검색을 위한 AI Search 인덱스 관리"""

    def __init__(
        self,
        endpoint: str,
        admin_key: str | None = None,
        index_name: str = "multimodal-documents-index",
    ):
        self.endpoint = endpoint
        self.index_name = index_name

        if admin_key:
            self.credential = AzureKeyCredential(admin_key)
        else:
            self.credential = DefaultAzureCredential()

        self.index_client = SearchIndexClient(
            endpoint=endpoint, credential=self.credential
        )

    def create_index(self, dimensions: int = 3072) -> None:
        """멀티모달 인덱스 생성 (텍스트 + 이미지 컨텐츠)"""
        fields = [
            SimpleField(
                name="content_id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SimpleField(
                name="document_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(
                name="document_title",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
                facetable=True,
            ),
            # text 또는 image
            SimpleField(
                name="content_type",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            # 텍스트 청크 또는 이미지 verbalization 텍스트
            SearchableField(
                name="content_text",
                type=SearchFieldDataType.String,
            ),
            # 텍스트/이미지 verbalization의 임베딩 벡터
            SearchField(
                name="content_embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=dimensions,
                vector_search_profile_name="multimodal-vector-profile",
            ),
            # 이미지 blob 경로 (이미지 타입인 경우)
            SimpleField(
                name="image_path",
                type=SearchFieldDataType.String,
                filterable=False,
            ),
            # 페이지 번호
            SimpleField(
                name="page_number",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
            # 청크 인덱스
            SimpleField(
                name="chunk_index",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
            # 바운딩 폴리곤 (JSON 문자열)
            SimpleField(
                name="bounding_polygons",
                type=SearchFieldDataType.String,
                filterable=False,
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="multimodal-hnsw",
                    parameters=HnswParameters(
                        metric="cosine",
                        m=4,
                        ef_construction=400,
                        ef_search=500,
                    ),
                ),
            ],
            profiles=[
                VectorSearchProfile(
                    name="multimodal-vector-profile",
                    algorithm_configuration_name="multimodal-hnsw",
                ),
            ],
        )

        semantic_search = SemanticSearch(
            default_configuration_name="multimodal-semantic",
            configurations=[
                SemanticConfiguration(
                    name="multimodal-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="document_title"),
                        content_fields=[SemanticField(field_name="content_text")],
                    ),
                )
            ],
        )

        index = SearchIndex(
            name=self.index_name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=semantic_search,
        )

        self.index_client.create_or_update_index(index)
        print(f"[멀티모달 인덱스] 생성/업데이트 완료: {self.index_name}")

    def delete_index(self) -> None:
        self.index_client.delete_index(self.index_name)
        print(f"[멀티모달 인덱스] 삭제 완료: {self.index_name}")

    def upload_documents(self, documents: list[dict]) -> dict:
        """문서를 인덱스에 업로드"""
        search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )

        batch_size = 100
        total_succeeded = 0
        total_failed = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            result = search_client.upload_documents(documents=batch)
            succeeded = sum(1 for r in result if r.succeeded)
            failed = sum(1 for r in result if not r.succeeded)
            total_succeeded += succeeded
            total_failed += failed
            print(f"[멀티모달 인덱스] 배치 {i + len(batch)}/{len(documents)}: 성공={succeeded}, 실패={failed}")

        return {"succeeded": total_succeeded, "failed": total_failed}

    def search(
        self,
        query: str,
        embedding: list[float] | None = None,
        top: int = 10,
        content_type: str | None = None,
    ) -> list[dict]:
        """하이브리드 검색 (키워드 + 벡터), content_type 필터 지원"""
        search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )

        vector_queries = None
        if embedding:
            vector_queries = [
                VectorizedQuery(
                    vector=embedding,
                    k=top,
                    fields="content_embedding",
                )
            ]

        filter_expr = None
        if content_type:
            filter_expr = f"content_type eq '{content_type}'"

        results = search_client.search(
            search_text=query,
            vector_queries=vector_queries,
            top=top,
            filter=filter_expr,
            select=[
                "content_id", "document_title", "content_type",
                "content_text", "image_path", "page_number", "chunk_index",
            ],
        )

        docs = []
        for result in results:
            docs.append({
                "content_id": result["content_id"],
                "document_title": result.get("document_title", ""),
                "content_type": result.get("content_type", ""),
                "content_text": result.get("content_text", ""),
                "image_path": result.get("image_path", ""),
                "page_number": result.get("page_number", 0),
                "score": result["@search.score"],
            })
        return docs
