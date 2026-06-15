# azure-ai-search-deepdive Context

This context defines the durable language for Azure AI Search 핵심 기능을 실전 시나리오로 학습하는 딥다이브 랩.

## Language

| Term | Definition |
|------|-----------|
| Hybrid Search | BM25 키워드 검색과 벡터 유사도 검색을 결합한 검색 방식 |
| Semantic Ranker | L2R(Learning to Rank) 기반 재순위 모델 |
| HNSW | Hierarchical Navigable Small World — 벡터 인덱싱 알고리즘 (cosine, m=4, ef=400) |
| Skillset | AI Search 인덱서에 부착되는 AI 보강 파이프라인 (Native / Custom) |
| Native Skillset | Azure 내장 스킬 (SplitSkill, AzureOpenAIEmbeddingSkill 등) |
| Custom Skillset | Azure Function으로 구현한 사용자 정의 스킬 |
| Image Verbalization | GPT-5.4로 이미지를 텍스트로 변환하여 임베딩하는 기법 |
| Document Intelligence | PDF/PPTX 레이아웃 분석 서비스 (표, 그림, 텍스트 추출) |
| Indexer | 데이터 소스 → Skillset → 인덱스로 데이터를 적재하는 파이프라인 |
| prec-court | 대법원 판례 인덱스 (law.go.kr 크롤링) |
| const-court | 헌법재판소 결정례 인덱스 |
| legis-interp | 법제처 해석례 인덱스 |
| admin-appeal | 행정심판 재결례 인덱스 |
| Chunk | SplitSkill로 분할된 텍스트 단위 (2000자 / 200자 overlap) |
| ko.microsoft | Azure AI Search 한국어 형태소 분석기 |

## Relationships

- Scenario A: law.go.kr → Logic Apps → Azure Functions (Crawl) → Blob Storage → Indexer + Native Skillset → 4 Legal Indexes
- Scenario B: PDF/PPTX → Blob Storage → Indexer + Skillset (Native vs Custom+Native) → 2 Multimodal Indexes
- Indexer → 1:1 → Skillset → 1:N → Skills (Split, Embed, DI, Custom)
- Index → 1:N → Fields (text, vector, metadata)
- Embedding Model: text-embedding-3-large (3072D) → HNSW vector index

## Flagged ambiguities

<!-- 해결이 필요한 모호한 용어를 여기에 기록합니다. -->
