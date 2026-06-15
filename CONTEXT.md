# azure-ai-search-deepdive Context

This context defines the durable language for Azure AI Search 핵심 기능을 2개 실전 시나리오(법률 문서 + 멀티모달)로 학습하는 딥다이브 랩.

## Language

| Term | Definition |
|------|-----------|
| Hybrid Search | BM25 키워드 검색과 벡터 유사도 검색을 결합한 검색 방식 |
| Semantic Ranker | L2R(Learning to Rank) 기반 재순위 모델 |
| HNSW | Hierarchical Navigable Small World — 벡터 인덱싱 알고리즘 (cosine, m=4, ef=400) |
| Skillset | AI Search 인덱서에 부착되는 AI 보강 파이프라인 (Native / Custom) |
| Native Skillset | Azure 내장 스킬 (SplitSkill, AzureOpenAIEmbeddingSkill 등) |
| Custom Web API Skill | Azure Function으로 구현한 사용자 정의 스킬. REST endpoint를 통해 AI Search 파이프라인에 삽입 |
| markdown_split | Custom Skill — Markdown 헤더 기반 텍스트 분할 (2000자 / 200자 overlap) |
| pptx_page_split | Custom Skill — `<!-- PageBreak -->` 마커 기반 PPTX 슬라이드 분할 |
| verbalize | Custom Skill — GPT-5.4 Vision으로 이미지/차트를 텍스트로 변환 (Image Verbalization) |
| Image Verbalization | GPT-5.4 Vision으로 이미지를 텍스트 설명으로 변환하여 동일 임베딩 공간에서 검색 가능하게 하는 기법 |
| Document Intelligence | PDF/PPTX 레이아웃 분석 서비스 (표, 그림, 텍스트 추출) |
| Indexer | 데이터 소스 → Skillset → 인덱스로 데이터를 적재하는 파이프라인 |
| Incremental Enrichment Cache | AI Search 인덱서의 캐시 기능. 변경된 문서만 재처리하여 스킬 비용 절감. `enable_cache=True`로 활성화 |
| prec-court-index | 대법원 판례 인덱스 (source: prec, law.go.kr 크롤링) |
| const-court-index | 헌법재판소 결정례 인덱스 (source: detc) |
| legis-interp-index | 법제처 해석례 인덱스 (source: expc) |
| admin-appeal-index | 행정심판 재결례 인덱스 (source: admrul) |
| Chunk | SplitSkill로 분할된 텍스트 단위 (2000자 / 200자 overlap) |
| ko.microsoft | Azure AI Search 한국어 형태소 분석기 |
| Foundry IQ Knowledge Source | Azure AI Foundry의 지식 소스 등록 — AI Search 인덱스를 Foundry Agent에 연결 |
| Agentic Retrieval | Foundry Agent가 자율적으로 검색 전략을 선택하는 검색 패턴 (tool-calling 기반) |
| Logic Apps Orchestration | 매일 06:00 KST 주기로 law.go.kr 크롤링을 트리거하는 워크플로우 |

## Relationships

### Scenario A: 법률 문서 파이프라인
```
law.go.kr
  → Logic Apps (매일 06:00 KST Recurrence)
    → Azure Functions (Crawl: prec/detc/expc/admrul 병렬)
      → Blob Storage (raw-documents/{source}/{date}/)
    → Azure Functions (Preprocess: 메타데이터 정규화)
      → Blob Storage (processed-documents/{source}/{date}/)
  → AI Search Indexer + Native Skillset (SplitSkill + EmbeddingSkill)
    → 4 Legal Indexes (prec-court, const-court, legis-interp, admin-appeal)
```

### Scenario B: 멀티모달 파이프라인
```
PDF/PPTX (수동 업로드)
  → Blob Storage (raw/pdf/{source}/)
  → Pipeline B-1 (Basic):
      DI Layout → Custom markdown_split/pptx_page_split → Embedding → basic index
  → Pipeline B-2 (Verbalized):
      DI Layout → Custom verbalize (GPT-5.4 Vision) → Custom markdown_split → Embedding → verbalized index
```

### Entity Relationships
- Indexer → 1:1 → Skillset → 1:N → Skills (Native: Split, Embed / Custom: markdown_split, verbalize)
- Index → 1:N → Fields (text, vector 3072D, metadata)
- Embedding Model: text-embedding-3-large (3072D) → HNSW vector index
- AI Search Index → Foundry IQ Knowledge Source → Agentic Retrieval (Notebook 04)
- Indexer ↔ Incremental Enrichment Cache (opt-in via enable_cache)

## Flagged ambiguities

- Logic Apps 스케줄: README "매일 06:00 KST" vs infrastructure.md "21:00 UTC" — 실제 배포 시 확인 필요
- Foundry IQ Knowledge Source 등록: 코드 미구현, Notebook 04에서 agentic retrieval 패턴 확장 예정
