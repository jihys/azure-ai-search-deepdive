"""
4개 법률 데이터 인덱스 스키마 정의 및 관리

인덱스별 설계 원칙:
- Vector(embedding): 요지/핵심 내용만 임베딩 → 비용 절약
- Keyword Search: 본문, 제목 등 전체 텍스트 검색 (ko.microsoft 형태소 분석기)
- Filter: 메타데이터 (날짜, 심급, 법원명 등)
- Collection(String): relatedLaws/keywords 다중값 정확 필터 지원
- Semantic Search: L2R 재랭킹으로 검색 품질 향상
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
from azure.search.documents.models import QueryCaptionType, QueryType, VectorizedQuery


# ──────────────────────────────────────────────
# 공통 설정 헬퍼
# ──────────────────────────────────────────────
def _vector_search_config() -> VectorSearch:
    """text-embedding-3-large (3072차원) HNSW 벡터 검색 설정"""
    return VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
                parameters=HnswParameters(metric="cosine", m=4, ef_construction=400, ef_search=500),
            ),
        ],
        profiles=[
            VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw-config"),
        ],
    )


def _semantic_config(
    config_name: str,
    title_field: str,
    content_fields: list[str],
    keyword_fields: list[str],
) -> SemanticSearch:
    """Semantic Ranker(L2R) 재랭킹 설정"""
    return SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=config_name,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name=title_field),
                    content_fields=[SemanticField(field_name=f) for f in content_fields],
                    keywords_fields=[SemanticField(field_name=f) for f in keyword_fields],
                ),
            )
        ]
    )


# ──────────────────────────────────────────────
# 1. 판례 인덱스 (Court Precedents)
# ──────────────────────────────────────────────
PREC_INDEX = "prec-court-index"
PREC_SEMANTIC = "prec-semantic"


def prec_fields(dimensions: int = 3072) -> list:
    return [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        # ── 필터용 메타데이터 ──
        SearchableField(name="courtName", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="caseNumber", type=SearchFieldDataType.String, filterable=True, sortable=True),  # [Fix 5] 사건번호 텍스트 검색 지원
        SimpleField(name="judgmentDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SearchableField(name="courtLevel", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="caseType", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="status", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(  # [Fix 1] Collection(String)으로 다중값 정확 필터 지원
            name="relatedLaws",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SearchableField(  # [Fix 1] Collection(String)으로 다중값 정확 필터 지원
            name="keywords",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SimpleField(name="registrationDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        # ── 키워드 검색용 본문 (ko.microsoft 형태소 분석기) ──
        SearchableField(name="caseName", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="holdings", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="summary", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="fullText", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        # ── 벡터 검색 (요지만 임베딩, hidden=True로 응답 페이로드 제외) ──
        SearchField(  # [Fix 2] hidden=True로 3072-float 응답 페이로드 제거
            name="summaryEmbedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,
            vector_search_dimensions=dimensions,
            vector_search_profile_name="vector-profile",
        ),
    ]


def prec_semantic() -> SemanticSearch:  # [Fix 3]
    return _semantic_config(
        config_name=PREC_SEMANTIC,
        title_field="caseName",
        content_fields=["holdings", "summary"],
        keyword_fields=["keywords", "relatedLaws"],
    )


# ──────────────────────────────────────────────
# 2. 헌재결정례 인덱스 (Constitutional Court)
# ──────────────────────────────────────────────
CONST_INDEX = "const-court-index"
CONST_SEMANTIC = "const-semantic"


def const_fields(dimensions: int = 3072) -> list:
    return [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        # ── 필터용 메타데이터 ──
        SearchableField(name="caseNumber", type=SearchFieldDataType.String, filterable=True, sortable=True),  # [Fix 5]
        SimpleField(name="decisionDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SearchableField(name="decisionType", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(  # [Fix 1]
            name="relatedLaws",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SearchableField(  # [Fix 1]
            name="keywords",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SimpleField(name="fiscalYear", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="registrationDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        # ── 키워드 검색용 본문 ──
        SearchableField(name="caseName", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="holdings", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="summary", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="fullText", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        # ── 벡터 ──
        SearchField(  # [Fix 2]
            name="summaryEmbedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,
            vector_search_dimensions=dimensions,
            vector_search_profile_name="vector-profile",
        ),
    ]


def const_semantic() -> SemanticSearch:  # [Fix 3]
    return _semantic_config(
        config_name=CONST_SEMANTIC,
        title_field="caseName",
        content_fields=["holdings", "summary"],
        keyword_fields=["keywords", "relatedLaws"],
    )


# ──────────────────────────────────────────────
# 3. 법제처 해석례 인덱스 (Legislation Interpretation)
# ──────────────────────────────────────────────
INTERP_INDEX = "legis-interp-index"
INTERP_SEMANTIC = "interp-semantic"


def interp_fields(dimensions: int = 3072) -> list:
    return [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        # ── 필터용 메타데이터 ──
        SearchableField(name="docNumber", type=SearchFieldDataType.String, filterable=True, sortable=True),  # [Fix 5]
        SimpleField(name="replyDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SearchableField(name="interpType", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(  # [Fix 1]
            name="relatedLaws",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SearchableField(  # [Fix 1]
            name="keywords",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SimpleField(name="registrationDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        # ── 키워드 검색용 본문 ──
        SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="querySummary", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="reply", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="reason", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        # ── 벡터 ──
        SearchField(  # [Fix 2]
            name="summaryEmbedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,
            vector_search_dimensions=dimensions,
            vector_search_profile_name="vector-profile",
        ),
    ]


def interp_semantic() -> SemanticSearch:  # [Fix 3]
    return _semantic_config(
        config_name=INTERP_SEMANTIC,
        title_field="title",
        content_fields=["querySummary", "reply"],
        keyword_fields=["keywords", "relatedLaws"],
    )


# ──────────────────────────────────────────────
# 4. 행정심판 재결례 인덱스 (Administrative Appeals)
# ──────────────────────────────────────────────
ADMIN_INDEX = "admin-appeal-index"
ADMIN_SEMANTIC = "admin-semantic"


def admin_fields(dimensions: int = 3072) -> list:
    return [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        # ── 필터용 메타데이터 ──
        SearchableField(name="caseNumber", type=SearchFieldDataType.String, filterable=True, sortable=True),  # [Fix 5]
        SimpleField(name="decisionDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SearchableField(name="decisionType", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(  # [Fix 1]
            name="relatedLaws",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SearchableField(  # [Fix 1]
            name="keywords",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
        ),
        SearchableField(name="committee", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="registrationDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        # ── 키워드 검색용 본문 ──
        SearchableField(name="caseName", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="order", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="reasonSummary", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        SearchableField(name="fullText", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"),
        # ── 벡터 ──
        SearchField(  # [Fix 2]
            name="summaryEmbedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,
            vector_search_dimensions=dimensions,
            vector_search_profile_name="vector-profile",
        ),
    ]


def admin_semantic() -> SemanticSearch:  # [Fix 3]
    return _semantic_config(
        config_name=ADMIN_SEMANTIC,
        title_field="caseName",
        content_fields=["order", "reasonSummary"],
        keyword_fields=["keywords", "relatedLaws"],
    )


# ──────────────────────────────────────────────
# 인덱스 매니저
# ──────────────────────────────────────────────
class LegalIndexManager:
    """4개 법률 인덱스 통합 관리"""

    INDEX_CONFIGS: dict[str, tuple] = {
        PREC_INDEX: (prec_fields, prec_semantic),
        CONST_INDEX: (const_fields, const_semantic),
        INTERP_INDEX: (interp_fields, interp_semantic),
        ADMIN_INDEX: (admin_fields, admin_semantic),
    }

    EMBEDDING_FIELDS: dict[str, list[str]] = {
        PREC_INDEX: ["holdings", "summary"],
        CONST_INDEX: ["holdings", "summary"],
        INTERP_INDEX: ["querySummary", "reply"],
        ADMIN_INDEX: ["order", "reasonSummary"],
    }

    SEMANTIC_CONFIG_NAMES: dict[str, str] = {
        PREC_INDEX: PREC_SEMANTIC,
        CONST_INDEX: CONST_SEMANTIC,
        INTERP_INDEX: INTERP_SEMANTIC,
        ADMIN_INDEX: ADMIN_SEMANTIC,
    }

    def __init__(self, endpoint: str, admin_key: str | None = None):
        self.endpoint = endpoint
        if admin_key:
            self.credential = AzureKeyCredential(admin_key)
        else:
            self.credential = DefaultAzureCredential()
        self.index_client = SearchIndexClient(endpoint=endpoint, credential=self.credential)

    def create_all_indexes(self, dimensions: int = 3072) -> None:
        """4개 인덱스 모두 생성"""
        vs = _vector_search_config()
        for index_name, (fields_fn, semantic_fn) in self.INDEX_CONFIGS.items():
            index = SearchIndex(
                name=index_name,
                fields=fields_fn(dimensions),
                vector_search=vs,
                semantic_search=semantic_fn(),
            )
            self.index_client.create_or_update_index(index)
            print(f"[인덱스] {index_name} 생성/업데이트 완료")

    def create_index(self, index_name: str, dimensions: int = 3072) -> None:
        """특정 인덱스 생성"""
        vs = _vector_search_config()
        fields_fn, semantic_fn = self.INDEX_CONFIGS[index_name]
        index = SearchIndex(
            name=index_name,
            fields=fields_fn(dimensions),
            vector_search=vs,
            semantic_search=semantic_fn(),
        )
        self.index_client.create_or_update_index(index)
        print(f"[인덱스] {index_name} 생성/업데이트 완료")

    def upload_documents(self, index_name: str, documents: list[dict]) -> dict:
        """문서 업로드 (배치 100건)"""
        client = SearchClient(endpoint=self.endpoint, index_name=index_name, credential=self.credential)
        total_ok, total_fail = 0, 0
        for i in range(0, len(documents), 100):
            batch = documents[i: i + 100]
            result = client.upload_documents(documents=batch)
            total_ok += sum(1 for r in result if r.succeeded)
            total_fail += sum(1 for r in result if not r.succeeded)
        print(f"[업로드] {index_name}: 성공={total_ok}, 실패={total_fail}")
        return {"succeeded": total_ok, "failed": total_fail}

    def search(
        self,
        index_name: str,
        query: str,
        embedding: list[float] | None = None,
        top: int = 5,
        filter_expr: str | None = None,
        select: list[str] | None = None,
        use_semantic: bool = True,
    ) -> list[dict]:
        """하이브리드 검색 (키워드 + 벡터 + 선택적 Semantic Ranker)"""
        client = SearchClient(endpoint=self.endpoint, index_name=index_name, credential=self.credential)
        vector_queries = None
        if embedding:
            vector_queries = [VectorizedQuery(vector=embedding, k_nearest_neighbors=top, fields="summaryEmbedding")]

        search_kwargs: dict = dict(
            search_text=query,
            vector_queries=vector_queries,
            top=top,
            filter=filter_expr,
            select=select,
        )
        if use_semantic and index_name in self.SEMANTIC_CONFIG_NAMES:
            search_kwargs["query_type"] = QueryType.SEMANTIC
            search_kwargs["semantic_configuration_name"] = self.SEMANTIC_CONFIG_NAMES[index_name]
            search_kwargs["query_caption"] = "extractive"

        results = client.search(**search_kwargs)
        docs = []
        for r in results:
            doc = {k: v for k, v in r.items() if not k.startswith("@") and k != "summaryEmbedding"}
            doc["score"] = r.get("@search.reranker_score") or r["@search.score"]
            docs.append(doc)
        return docs

    def get_stats(self, index_name: str) -> dict:
        """인덱스 통계"""
        client = SearchClient(endpoint=self.endpoint, index_name=index_name, credential=self.credential)
        return {"index_name": index_name, "document_count": client.get_document_count()}

    def get_all_stats(self) -> list[dict]:
        """모든 인덱스 통계"""
        return [self.get_stats(name) for name in self.INDEX_CONFIGS]

    def get_embedding_text(self, index_name: str, doc: dict) -> str:
        """인덱스별 임베딩 대상 텍스트 추출"""
        fields = self.EMBEDDING_FIELDS.get(index_name, [])
        parts = [doc.get(f, "") for f in fields if doc.get(f)]
        return "\n\n".join(parts)
