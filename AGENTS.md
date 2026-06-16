# azure-ai-search-deepdive

Azure AI Search의 핵심 기능을 2개 실제 시나리오 (법률 문서 + 멀티모달)로 데모하는 딥다이브 랩

## Tech Stack

- **Language**: Python 3.13+ (.venv)
- **Search**: Azure AI Search (vector + keyword hybrid, semantic ranker, incremental enrichment cache)
- **AI**: Azure OpenAI (gpt-5.4, text-embedding-3-large 3072D)
- **Document**: Azure Document Intelligence (PDF/PPTX layout)
- **Orchestration**: Azure Logic Apps (daily crawling), Azure Functions (2개: crawl, preprocess)
- **Infra**: Bicep (Sweden Central 메인, Korea Central 보조)
- **Agent**: Azure AI Foundry IQ (Knowledge Source + Agentic Retrieval)
- **Test**: pytest
- **Notebook**: Jupyter (ipykernel)

## Implementation Structure

```
src/
├── pipeline/
│   ├── legal_pipeline.py       # 4 법률 인덱서 (판례/헌재/법제처/행정심판) + cache 지원
│   ├── multimodal_pipeline.py  # 4 멀티모달 파이프라인 (basic PDF/PPTX + verbalized PDF/PPTX)
│   └── indexer_ops.py          # AI Search REST API 클라이언트 (Bearer/APIKey 인증)
└── search/
    ├── legal_indexes.py        # 4 법률 인덱스 스키마 (HNSW 3072D, ko.microsoft)
    └── multimodal_index.py     # 멀티모달 인덱스 스키마 (text+image 벡터)
skills-function/                # Custom AI Search Skills (Azure Function) — 미사용 (Built-in Skill로 전환됨)
├── function_app.py             # 3 skills: markdown_split, pptx_page_split, verbalize (참고용)
logic-apps/                     # Logic Apps + Azure Functions
├── deploy_workflow.py          # 워크플로우 배포 (Kudu API)
├── crawl-function/             # law.go.kr 크롤러
├── preprocess-function/        # 메타데이터 정규화
└── crawl-preprocess-workflow/  # 운영 워크플로우 (매일 21:00 UTC (06:00 KST))
notebooks/                      # 01~07 핸즈온 랩
├── 01-infra-deployment        # Bicep 배포 + Function 배포 + SPL 승인
├── 02-data-crawling           # Logic App 트리거 + 크롤링 검증
├── 03-indexing                # 인덱스 스키마 + Skillset/Indexer 생성
├── 04-search-and-query        # Hybrid/Semantic/RAG 검색 + Agentic Retrieval
├── 05-multimodal-indexing     # PDF/PPTX 업로드 + B-1~B-4 파이프라인
├── 06-multimodal-search       # Basic vs Verbalized 검색 품질 비교
└── 07-content-understanding   # B-5/B-6 CU Skill + Image Serving + 비교
infra/                          # Bicep IaC
├── sweden/                    # 메인 배포 (Private Network)
├── sweden-public/             # 퍼블릭 변형
└── korea/                     # Korea Central 변형
docs/                           # 아키텍처 다이어그램, ADR, 리포트
data/                           # raw/ (크롤링), processed/ (정제)
```

## Naming

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/Variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Branches**: `feat/<issue-id>-short-desc`, `fix/<issue-id>-short-desc`
- **Commits**: `type(scope): description` (conventional commits)
- **Indexes**: `<domain>-<source>-index` (e.g., `prec-court-index`)

## Code Rules

- Type hints on all public functions
- Docstrings on all public classes and functions
- No hardcoded secrets — use environment variables or Azure Identity
- Prefer `DefaultAzureCredential` for authentication
- Use `.venv` virtual environment (Python 3.13)
- Notebook kernel: `.venv` Python environment

## Git Rules

- Squash merge to `main`
- Branch protection: require PR review
- No direct pushes to `main`

## Agent Skills

| Skill | Purpose |
|-------|---------|
| `notebook-lab-fixer` | 노트북 셀 오류 진단 및 수정 |
| `grill-me` | 도메인 지식 자가 점검 |
| `grill-with-docs` | 도메인 모델 검증 (CONTEXT.md 업데이트) |
| `tdd` | 레드-그린-리팩터 TDD 루프 |
| `diagnose` | 버그 진단 루프 |
| `prototype` | 스로어웨이 프로토타입 |
| `to-prd` | 대화 → PRD 변환 |
| `to-issues` | PRD → 이슈 분해 |
| `triage` | 이슈 트리아지 상태 머신 |
| `create-pr` | PR 생성 및 감사 |
| `zoom-out` | 코드 오리엔테이션 |
| `improve-codebase-architecture` | 아키텍처 개선 |
