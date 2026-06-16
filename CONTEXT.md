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
| Custom Web API Skill | (미사용 — Built-in Skill로 전환됨) Azure Function으로 구현한 사용자 정의 스킬. REST endpoint를 통해 AI Search 파이프라인에 삽입 |
| markdown_split | (미사용 — Built-in Skill로 전환됨) Custom Skill — Markdown 헤더 기반 텍스트 분할 |
| pptx_page_split | (미사용 — Built-in Skill로 전환됨) Custom Skill — `<!-- PageBreak -->` 마커 기반 PPTX 슬라이드 분할 |
| verbalize | (미사용 — Built-in Skill로 전환됨) Custom Skill — GPT-5.4 Vision으로 이미지/차트를 텍스트로 변환 |
| SplitSkill | Built-in Skill — 텍스트를 고정 크기로 분할 (2000자 / 200자 overlap). Custom markdown_split / pptx_page_split 대체 |
| ChatCompletionSkill (GenAI Prompt) | Built-in Skill — 인덱싱 파이프라인 내에서 GPT 모델을 인라인 호출. Custom verbalize 대체. API `2026-04-01` GA |
| MergeSkill | Built-in Skill — 여러 필드를 하나로 병합. imageAction 결과와 텍스트를 결합하여 SplitSkill 입력 생성 |
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
| Content Understanding Skill | `ContentUnderstandingSkill` — DI Layout + 청킹 + AI 이미지 설명을 단일 스킬로 통합한 내장 스킬. Semantic chunking (단락/제목 경계), AI image description 지원. API `2026-04-01` GA (기본), `2026-05-01-preview` (semantic chunking + image desc) |
| GenAI Prompt Skill | `ChatCompletionSkill` — 인덱싱 파이프라인 내에서 GPT 모델을 인라인 호출하는 내장 스킬. API `2026-04-01` GA |
| Image Serving | Agentic Retrieval 시 문서 내 추출된 이미지를 원본 그대로 반환하는 기능. Content Understanding 인덱싱 시 이미지를 추출·저장하고, 검색 시 텍스트와 함께 이미지를 직접 제공. API `2026-05-01-preview` |
| Semantic Chunking | Content Understanding Skill의 청킹 모드. 고정 크기가 아닌 단락/제목 경계를 준수하여 의미 단위로 분할 |
| Data Preprocessing | raw-documents의 JSON 파일을 메타데이터 정규화 + JSONL 변환하여 processed-documents에 저장하는 단계. `func-preprocess` Function App이 담당 |
| Logic Apps Orchestration | 매일 06:00 KST 주기로 Crawl → Data Preprocessing → AI Search Indexer Run까지 E2E 파이프라인을 오케스트레이션하는 워크플로우 |

## Relationships

### Scenario A: 법률 문서 파이프라인
```
Logic Apps (매일 21:00 UTC / 06:00 KST Recurrence — E2E 오케스트레이터)
  ├─ Step 1: Durable Functions Orchestrator (Crawl + Data Preprocessing)
  │    ├─ Crawl (prec/detc/expc/admrul 병렬) → raw-documents/{source}/{date}/
  │    └─ Data Preprocessing (HTTP → func-preprocess) → processed-documents/{source}/{date}/
  ├─ Step 2: AI Search Indexer Run (4개 인덱서 Fire-and-forget, Managed Identity 인증)
  └─ Step 3: 결과 로깅 / 실패 시 종료
```

### Scenario B: 멀티모달 파이프라인

리소스 이름에 source prefix(`st-` 등)를 사용하지 않는다. Blob 경로에서 소스 구분: `raw/pdf/{source}/`, `raw/pptx/{source}/` (source: st, ss, ha).

```
PDF/PPTX (로컬 data/raw/ 에서 수동 업로드)
  → Blob Storage (raw/pdf/{source}/, raw/pptx/{source}/)
  → Pipeline B-1 (Basic PDF):           multimodal-basic-indexer-pdf
      DI Layout (oneToOne) → SplitSkill → Embedding → multimodal-basic-index-pdf
  → Pipeline B-2 (Basic PPTX):          multimodal-basic-indexer-pptx
      DI Layout (oneToOne) → SplitSkill → Embedding → multimodal-basic-index-pptx
  → Pipeline B-3 (Verbalized PDF):      multimodal-verbalized-indexer-pdf
      imageAction → GenAI Prompt → MergeSkill → SplitSkill → Embedding → multimodal-verbalized-index-pdf
  → Pipeline B-4 (Verbalized PPTX):     multimodal-verbalized-indexer-pptx
      imageAction → GenAI Prompt → MergeSkill → SplitSkill → Embedding → multimodal-verbalized-index-pptx
  → Pipeline B-5 (Content Understanding PDF): multimodal-cu-indexer-pdf   [Notebook 07]
      Content Understanding Skill (semantic chunking + AI image description) → Embedding → multimodal-cu-index-pdf
  → Pipeline B-6 (Content Understanding PPTX): multimodal-cu-indexer-pptx [Notebook 07]
      Content Understanding Skill (semantic chunking + AI image description) → Embedding → multimodal-cu-index-pptx
```

### Scenario B 비교 구도
```
[비교 1: PDF 인덱싱 전략]
  B-1 Basic PDF (DI Layout + SplitSkill)
  vs B-3 Verbalized PDF (imageAction + GenAI Prompt + MergeSkill + SplitSkill)
  vs B-5 Content Understanding PDF (CU Skill 단일, semantic chunking + image desc)

[비교 2: PPTX 인덱싱 전략]
  B-2 Basic PPTX (DI Layout + SplitSkill)
  vs B-4 Verbalized PPTX (imageAction + GenAI Prompt + MergeSkill + SplitSkill)
  vs B-6 Content Understanding PPTX (CU Skill 단일, semantic chunking + image desc)

[비교 3: 검색 시 이미지 활용 — Agentic Retrieval]
  Verbalized (이미지→텍스트 변환 후 텍스트 검색)
  vs Image Serving (원본 이미지 직접 반환, 모델이 이미지 reasoning)
  → Knowledge Source의 contentExtractionMode: "standard" + Image Serving 활성화
```

### Entity Relationships
- Indexer → 1:1 → Skillset → 1:N → Skills (Built-in: SplitSkill, EmbeddingSkill, ChatCompletionSkill, MergeSkill)
- Index → 1:N → Fields (text, vector 3072D, metadata)
- Embedding Model: text-embedding-3-large (3072D) → HNSW vector index
- AI Search Index → Foundry IQ Knowledge Source → Agentic Retrieval (Notebook 04)
- Indexer ↔ Incremental Enrichment Cache (opt-in via enable_cache)
- Logic App → Managed Identity → AI Search (Search Service Contributor 역할로 Indexer Run 호출)

## Flagged ambiguities

- ~~Logic Apps 스케줄: README "매일 06:00 KST" vs infrastructure.md "21:00 UTC"~~ → **해결**: 동일 시각. 정식 표기 `21:00 UTC (06:00 KST)` 병기
- Foundry IQ Knowledge Source 등록: 코드 미구현, Notebook 04에서 agentic retrieval 패턴 확장 예정

## Resolved decisions (grill-with-docs 2026-06-15)

| # | 결정 | 상세 |
|---|------|------|
| Q1 | 용어 통일 = `Data Preprocessing` | "Data Integration" / "Preprocess" 혼용 → `Data Preprocessing`으로 통일. 코드(`func-preprocess`)와 일치 |
| Q2 | Orchestrator = Durable Functions | Logic App → Durable Functions Orchestrator가 Crawl + Data Preprocessing 모두 관장 (현재 구현 유지) |
| Q3 | Logic App 유지 이유 | Logic App = 스케줄러 + 감시자. Indexer Run 호출까지 담당하면 E2E 오케스트레이터로 존재 이유 명확 |
| Q4 | Logic App이 Indexer Run 호출 | Crawl → Data Preprocessing → Indexer Run까지 Logic App이 E2E 오케스트레이션 (Step 2 추가) |
| Q5 | Indexer Run 인증 = Managed Identity | Logic App에 `Search Service Contributor` 역할 부여. API Key 없이 Bearer 토큰 사용 |
| Q6 | Indexer Run = Fire-and-forget | 4개 Indexer Run 호출 후 완료 대기 없이 바로 종료. Indexer 실패는 AI Search 자체 모니터링에 위임 |
| Q7 | 스케줄 시간 = `21:00 UTC (06:00 KST)` | 둘 다 병기. 코드/인프라에서는 UTC, 문서에서는 KST 추가 표기 |
| Q8 | `func-preprocess` 독립 유지 | crawl에 통합하지 않음. 수동 백필 / 단일 소스 재처리 등 독립 호출 시나리오 존재 |
| Q9 | `func-skills` = 시나리오 B 전용 | AI Search Skillset이 인덱싱 중 호출하는 Custom Web API Skill. 시나리오 A (법률)에서는 미사용 (v2.1에서 Built-in Skill로 전환됨) |
| Q10 | 시나리오 B = 3개 파이프라인 | Basic PDF (B-1), Basic PPTX (B-2), Verbalized (B-3). README의 "Native Only" 2개 다이어그램은 수정 필요 |
| Q11 | 인덱서/인덱스 이름 확정 | prefix 없이 `multimodal-{type}-indexer-{format}` / `multimodal-{type}-index-{format}` 패턴 |
| Q12 | `st` prefix 의미 = 불명 → 제거 | `st`는 의미 불명 (사용자도 모름). 리소스 이름에서 source prefix 전면 제거 |
| Q13 | Verbalized PPTX 추가 | B-4 Verbalized PPTX 파이프라인 추가. 총 4개 DI Layout 기반 파이프라인 |
| Q14 | Verbalized PPTX split = `markdown_split` | verbalize 출력이 이미 텍스트화된 Markdown이므로 pptx_page_split이 아닌 markdown_split 사용 (v2.1에서 Built-in Skill로 전환됨) |
| Q15 | CU Skill + Image Serving 추가 | Content Understanding Skill (B-5/B-6) + Image Serving 비교 추가. 총 6개 파이프라인 + Image Serving |
| Q16 | CU/Image Serving = 별도 노트북 07 | API 버전(`2026-05-01-preview`)이 다르고, 기존 DI Layout 파이프라인과 설정 방식이 다름 |
| Q17 | `st-` prefix 제거 | 리소스 이름에서 source prefix 제거. 네임스페이스는 Blob 경로 `raw/{format}/{source}/`로 구분 |
| Q18 | Blob 소스 구분 | `raw/pdf/st/`, `raw/pdf/ss/`, `raw/pdf/ha/` — 3종 소스. PPTX도 동일 구조 |
| Q19 | `main.json` ARM 템플릿 삭제 | Bicep 직접 배포이므로 생성된 ARM 템플릿 불필요 |
| Q20 | CU + Image Serving → 별도 노트북 07 | 05는 B-1~B-4, 06은 Basic vs Verbalized 검색 비교, 07은 CU + Image Serving |
| Seed | 로컬 업로드로 전환 | Seed blob 삭제됨. 법령 4종 → `/mnt/code`에 압축 저장, 멀티모달 → `data/raw/`에 수동 배치 |

## Notebook 구조 (최종)

| # | 파일 | 범위 |
|---|------|------|
| 01 | infra-deployment | Bicep 배포 + Function 배포 + SPL 승인 |
| 02 | data-crawling | Logic App 트리거 + 크롤링 검증 |
| 03 | indexing | 법률 인덱스 스키마 + Skillset/Indexer 생성 |
| 04 | search-and-query | Hybrid/Semantic/RAG 검색 + Agentic Retrieval |
| 05 | multimodal-indexing | B-1~B-4 (DI Layout 기반) 인덱싱 + Caching 실험 |
| 06 | multimodal-search | Basic vs Verbalized 검색 품질 비교 |
| **07** | **content-understanding** | **B-5/B-6 CU Skill 인덱싱 + Image Serving + DI Layout 대비 비교** |
