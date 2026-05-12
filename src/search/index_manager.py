"""
Azure AI Search 인덱스 관리자
- 인덱스 생성/삭제
- 문서 업로드
- 검색 쿼리
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
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery


class IndexManager:
    """AI Search 인덱스 생성 및 관리"""

    def __init__(
        self,
        endpoint: str,
        admin_key: str | None = None,
        index_name: str = "law-documents-index",
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
        """벡터 검색이 가능한 AI Search 인덱스 생성"""
        fields = [
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SearchableField(
                name="documentName",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
            ),
            SearchableField(
                name="content",
                type=SearchFieldDataType.String,
                analyzer_name="ko.microsoft",
            ),
            SearchField(
                name="embeddings",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=dimensions,
                vector_search_profile_name="vector-profile",
            ),
            SearchableField(
                name="category",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(
                name="crawledDate",
                type=SearchFieldDataType.DateTimeOffset,
                filterable=True,
                sortable=True,
            ),
            SearchableField(
                name="sourceUrl",
                type=SearchFieldDataType.String,
            ),
            SimpleField(
                name="chunkIndex",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="vector-config",
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
                    name="vector-profile",
                    algorithm_configuration_name="vector-config",
                ),
            ],
        )

        index = SearchIndex(
            name=self.index_name,
            fields=fields,
            vector_search=vector_search,
        )

        self.index_client.create_or_update_index(index)
        print(f"[AI Search] 인덱스 생성/업데이트 완료: {self.index_name}")

    def delete_index(self) -> None:
        """인덱스 삭제"""
        self.index_client.delete_index(self.index_name)
        print(f"[AI Search] 인덱스 삭제 완료: {self.index_name}")

    def upload_documents(self, documents: list[dict]) -> dict:
        """문서를 인덱스에 업로드"""
        search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )

        # 배치 단위 업로드 (1000개씩)
        batch_size = 1000
        total_succeeded = 0
        total_failed = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            result = search_client.upload_documents(documents=batch)

            succeeded = sum(1 for r in result if r.succeeded)
            failed = sum(1 for r in result if not r.succeeded)
            total_succeeded += succeeded
            total_failed += failed

            print(f"[AI Search] 배치 업로드 {i + len(batch)}/{len(documents)}: 성공={succeeded}, 실패={failed}")

        return {"succeeded": total_succeeded, "failed": total_failed}

    def search(
        self,
        query: str,
        embedding: list[float] | None = None,
        top: int = 5,
        filter_expr: str | None = None,
    ) -> list[dict]:
        """하이브리드 검색 (키워드 + 벡터)"""
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
                    fields="embeddings",
                )
            ]

        results = search_client.search(
            search_text=query,
            vector_queries=vector_queries,
            top=top,
            filter=filter_expr,
            select=["id", "documentName", "content", "category", "crawledDate", "sourceUrl", "chunkIndex"],
        )

        docs = []
        for result in results:
            docs.append({
                "id": result["id"],
                "documentName": result.get("documentName", ""),
                "content": result.get("content", ""),
                "score": result["@search.score"],
                "category": result.get("category", ""),
                "sourceUrl": result.get("sourceUrl", ""),
            })

        return docs

    def get_index_stats(self) -> dict:
        """인덱스 통계 조회"""
        search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )
        count = search_client.get_document_count()
        return {"index_name": self.index_name, "document_count": count}
