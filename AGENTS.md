# azure-ai-search-deepdive

Azure AI Search 핵심 기능을 실전 시나리오로 학습하는 딥다이브 랩

## Tech Stack

- **Language**: Python 3.13+ (.venv)
- **Search**: Azure AI Search (vector + keyword hybrid, semantic ranker)
- **AI**: Azure OpenAI (gpt-5.4, text-embedding-3-large 3072D)
- **Document**: Azure Document Intelligence (PDF/PPTX layout)
- **Orchestration**: Azure Logic Apps, Azure Functions
- **Infra**: Bicep (Korea Central, Sweden Central, Sweden Public)
- **Test**: pytest
- **Notebook**: Jupyter (ipykernel)

## Implementation Structure

```
src/
├── pipeline/
│   ├── legal_pipeline.py       # 4 한국 법률 인덱서 (판례/헌재/법제처/행정심판)
│   ├── multimodal_pipeline.py  # PDF/PPTX 멀티모달 파이프라인
│   └── indexer_ops.py          # AI Search REST API 클라이언트
└── search/
    ├── legal_indexes.py        # 4 법률 인덱스 스키마 (HNSW, ko.microsoft)
    └── multimodal_index.py     # 이미지+텍스트 벡터 검색
notebooks/                      # 01~06 핸즈온 랩
infra/                          # Bicep IaC (korea/, sweden/, sweden-public/)
logic-apps/                     # Logic Apps + Azure Functions (crawl, preprocess)
skills-function/                # Custom AI Search Skills (Azure Function)
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
