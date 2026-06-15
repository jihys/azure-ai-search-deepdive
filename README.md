# Azure AI Search Deep Dive Lab

**Azure AI Search의 핵심 기능을 2개 실제 시나리오로 데모하는 Hands-on Lab**

| 시나리오 | 데이터 | 파이프라인 | 인덱스 |
|----------|------|---------|--------|
| **A. 법령 문서** | 한국 법령 (law.go.kr 크롤링) | Logic Apps 오케스트레이션 → AI Search Native Skillset | 4개 (prec-court / const-court / legis-interp / admin-appeal) |
| **B. 멀티모달** | PDF / PPTX (수동 업로드) | AI Search Skillset 비교 (Basic / Verbalized / Content Understanding) | 6개 + Image Serving |

> **권장 배포**: `infra/sweden-public/` — 모든 리소스가 공개 엔드포인트로 접근 가능 (실습/워크샵용)
> **프로덕션 변형**: `infra/sweden/` — VNet + Private Endpoints 기반 (보안 강화)

> **리전**: Sweden Central — Document Intelligence가 Korea Central 미지원이므로 Sweden Central 사용

## 시나리오 A: 법령 문서 인덱싱 파이프라인

```
╔══════════════════════════════════════════════════════════════╗
║ Stage 1: CRAWLING + DATA PREPROCESSING  (Logic Apps 관장)       ║
║                                                              ║
║  [Logic Apps - 매일 21:00 UTC (06:00 KST)]                    ║
║  Recurrence 트리거                                             ║
║      │ Step 1: Crawl Function HTTP POST                         ║
║      ▼                                                          ║
║  law.go.kr 크롤링 → raw-documents/{source}/{date}/           ║
║  (prec / detc / expc / admrul - 병렬)                         ║
║      │ Step 2: Data Preprocessing Function HTTP POST (x4 병렬) ║
║      ▼                                                          ║
║  메타데이터 정규화 → processed-documents/{source}/{date}/     ║
╚═════════════════════════════════╟═══════════════════════════╝
                                 │
╔═════════════════════════════════▼═══════════════════════════╗
║ Stage 2: SPLIT + EMBEDDING + INGEST  (AI Search 관장)           ║
║                                                              ║
║  AI Search Indexer (매일 별도 스케줄, 증분 실행)             ║
║  ├─ [Native] Text Split Skill (2000자 / 200자 오버랩)       ║
║  └─ [Native] AzureOpenAIEmbeddingSkill (3072D)              ║
║                                                              ║
║  ┌────────────────────────────────────────────────┐  ║
║  │ 4개 인덱스 (법령 텍스트)                               │  ║
║  │  prec-court-index       판례                          │  ║
║  │  const-court-index      헌재결정례                    │  ║
║  │  legis-interp-index     법제처해석례                   │  ║
║  │  admin-appeal-index     행정심판재결례                 │  ║
║  └────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════╝
         ↓
  RAG 질의 (GPT-5.4 + Hybrid Search + Semantic Ranker)
```

## 시나리오 B: 멀티모달 PDF/PPTX 인덱싱 파이프라인

```
[PDF/PPTX 수동 업로드]
    │
    ▼ Blob Storage: raw/pdf/{source}/, raw/pptx/{source}/
    │
    ├─── [B-1] Basic PDF ──────────── DI Layout → markdown_split → Embed ──── multimodal-basic-index-pdf
    ├─── [B-2] Basic PPTX ─────────── DI Layout → pptx_page_split → Embed ── multimodal-basic-index-pptx
    ├─── [B-3] Verbalized PDF ─────── DI Layout → GPT-5.4 Verb. → Split → Embed ── multimodal-verbalized-index-pdf
    ├─── [B-4] Verbalized PPTX ────── DI Layout → GPT-5.4 Verb. → Split → Embed ── multimodal-verbalized-index-pptx
    ├─── [B-5] CU PDF ────────────── CU Skill (semantic chunk + image desc) → Embed ── multimodal-cu-index-pdf
    └─── [B-6] CU PPTX ───────────── CU Skill (semantic chunk + image desc) → Embed ── multimodal-cu-index-pptx
         + Image Serving via Agentic Retrieval (2026-05-01-preview)
         ↓
  검색 비교 (Basic vs Verbalized vs Content Understanding 품질 차이 데모)
```

**아키텍처 다이어그램**: [docs/architecture-sweden.drawio](docs/architecture-sweden.drawio), [docs/architecture-korea.drawio](docs/architecture-korea.drawio) (draw.io에서 열기)

## 배포되는 Azure 리소스

| 리소스 | 리전 | SKU | 비고 |
|--------|------|-----|------|
| Resource Group | Sweden Central | - | `rg-rag-indexing-lab-swc-pub` |
| Storage Account | Sweden Central | Standard LRS | Managed Identity 인증 (`allowSharedKeyAccess=false`) |
| Azure AI Services (gpt-5.4 + embedding) | Sweden Central | S0 | Foundry Agent Service 포함 |
| Document Intelligence | Sweden Central | S0 | PDF/PPTX Layout 분석 |
| Azure AI Search | Sweden Central | **Standard (S1)** | Hybrid + Semantic Ranker |
| Function App (Crawl) | Sweden Central | FC1 (Flex Consumption) | Durable Functions orchestrator |
| Function App (Preprocess) | Sweden Central | FC1 (Flex Consumption) | JSON → JSONL 정규화 |
| Function App (Skills) | Sweden Central | FC1 (Flex Consumption) | Custom AI Search Skills |
| Logic App | Sweden Central | Consumption | 매일 21:00 UTC (06:00 KST) 크롤링 스케줄러 |

> **Private 변형** (`infra/sweden/`): 위 리소스에 VNet, Private Endpoints × 4, Private DNS Zones × 4, Shared Private Links × 3, JumpVM이 추가됩니다. 상세: [docs/infrastructure.md](docs/infrastructure.md)

## 사전 요구사항

- Azure 구독 (Contributor 권한)
- Azure CLI (`az login` 완료)
- [Bicep CLI](https://learn.microsoft.com/azure/azure-resource-manager/bicep/install) (인프라 배포)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local#install-the-azure-functions-core-tools) (Function App 배포)
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (Python 패키지 관리)

```bash
# Bicep CLI 설치 (Azure CLI 확장)
az bicep install && az bicep upgrade

# Azure Functions Core Tools v4 설치 (Ubuntu/Debian)
curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg
sudo mv microsoft.gpg /etc/apt/trusted.gpg.d/microsoft.gpg
sudo sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/repos/microsoft-ubuntu-$(lsb_release -cs)-prod $(lsb_release -cs) main" > /etc/apt/sources.list.d/dotnetdev.list'
sudo apt-get update && sudo apt-get install -y azure-functions-core-tools-4
```

## 빠른 시작

### 1. 환경 설정

```bash
git clone https://github.com/jihys/azure-ai-search-deepdive.git
cd azure-ai-search-deepdive

uv venv .venv --python 3.10
source .venv/bin/activate
uv pip install -e .

cp sample.env .env
# .env 파일 편집하여 실제 값 입력
```

### 2. 인프라 배포 (Bicep)

```bash
az login

# sweden-public 배포 (권장 — 공개 엔드포인트, VNet 없음)
az deployment sub create \
    --location swedencentral \
    --template-file infra/sweden-public/main.bicep \
    --parameters infra/sweden-public/parameters/main.bicepparam

# sweden 배포 (Private Network — VNet + PE)
# az deployment sub create \
#     --location swedencentral \
#     --template-file infra/sweden/main.bicep \
#     --parameters infra/sweden/parameters/main.bicepparam
```

### 3. Shared Private Link 승인

> ⚠️ **sweden-public 배포 시 이 단계를 건너뛸 수 있습니다.** Shared Private Link는 private 변형(`infra/sweden/`)에서만 필요합니다.

Bicep 배포 후 AI Search의 아웃바운드 Private Link 연결을 승인합니다.

```bash
RG="rg-rag-indexing-lab-swc"
SEARCH_NAME=$(az search service list -g $RG --query "[0].name" -o tsv)

# 승인 대기 목록 확인
az search shared-private-link-resource list \
    --service-name $SEARCH_NAME \
    --resource-group $RG \
    --query "[].{name:name, status:properties.status}" \
    --output table

# 각 대상 리소스에서 승인 (docs/infrastructure.md §8 참조)
```

### 4. Logic Apps 워크플로우 배포

기본 1개의 워크플로우를 배포합니다:
1. **crawl-preprocess-workflow** (매일 21:00 UTC (06:00 KST)): 크롤링 → Data Preprocessing (병렬 4개 소스)

`crawl-workflow`, `rag-indexing-workflow`는 레거시/디버그용으로 파일만 유지하며 기본 배포 대상에서 제외됩니다.

```bash
uv run python logic-apps/deploy_workflow.py
```

### 4-1. 전처리(Data Preprocessing) 과정

시나리오 A의 전처리는 Logic Apps Stage 1에서 수행되며, 역할은 아래로 제한됩니다.

1. `raw-documents/{source}/{date}/` 입력 수집
2. 메타데이터 정규화 (source/date/file_id 등)
3. 포맷 정리 후 `processed-documents/{source}/{date}/` 저장

중요: 청크 분할(Text Split)과 임베딩 생성은 전처리 단계가 아니라, Stage 2의 AI Search Skillset이 담당합니다.

### 5. AI Search 파이프라인 설정

**시나리오 A — 법령 텍스트 (4개 인덱스)**:

Notebook `03-indexing.ipynb`에서 `src.pipeline.legal_pipeline`을 사용하여 설정합니다:
- Index (4개) + Native Skillset (SplitSkill + EmbeddingSkill) + DataSource + Indexer
- 캐시 활성화: `enable_cache=True` 옵션으로 Incremental Enrichment Cache 사용

**시나리오 B — 멀티모달 (6개 파이프라인, 비교용)**:

Notebook `05-multimodal-indexing.ipynb`에서 `src.pipeline.multimodal_pipeline`을 사용합니다:

- **Pipeline B-1 (Basic PDF)**: DI Layout → Custom `markdown_split` → Embedding
- **Pipeline B-2 (Basic PPTX)**: DI Layout → Custom `pptx_page_split` → Embedding
- **Pipeline B-3 (Verbalized)**: DI Layout → Custom `verbalize` (GPT-5.4 Vision) → Custom `markdown_split` → Embedding

### 5-1. Custom AI Search Skills (시나리오 B 전용)

`skills-function/function_app.py`에 구현된 3개 Custom Web API Skill (시나리오 B 파이프라인에서 사용):

| Skill | Route | 용도 |
|-------|-------|------|
| `markdown_split` | `/api/markdown_split` | Markdown 헤더 기반 텍스트 분할 (2000자 / 200자 overlap) |
| `pptx_page_split` | `/api/pptx_page_split` | `<!-- PageBreak -->` 마커 기반 슬라이드 분할 |
| `verbalize` | `/api/verbalize` | GPT-5.4 Vision으로 이미지/차트를 텍스트 설명으로 변환 |

### 5-2. Incremental Enrichment Cache

초기 테스트 시 캐시 비활성화 → 이후 `enable_cache=True`로 활성화:
- 변경된 문서만 재처리하여 스킬 실행 비용 절감
- Azure Storage Resource ID를 캐시 백엔드로 사용
- `enableReprocessing: True` 설정으로 캐시된 문서도 재보강 가능

### 6. 노트북 실행

#### 공통 준비 (시나리오 A·B 공통)
| 순서 | 노트북 | 설명 |
|------|--------|------|
| 1 | `notebooks/01-infra-deployment.ipynb` | Bicep 배포 + Function 코드 배포 + Shared PL 승인 + Logic Apps 워크플로우 배포 |

#### 시나리오 A: 법령 문서 인덱싱
| 순서 | 노트북 | 설명 |
|------|--------|------|
| 2 | `notebooks/02-data-crawling.ipynb` | Logic App 트리거 + AI Search 인덱서 모니터링 + Blob 결과 검증 |
| 3 | `notebooks/03-indexing.ipynb` | 4개 인덱스 스키마 생성 + Skillset/Indexer 설정 + Cache 활성화 테스트 |
| 4 | `notebooks/04-search-and-query.ipynb` | Hybrid/Semantic/RAG 검색 + Multi-Index 검색 + Agentic Retrieval |

#### 시나리오 B: 멀티모달 PDF/PPTX 인덱싱
| 순서 | 노트북 | 설명 |
|------|--------|------|
| 5 | `notebooks/05-multimodal-indexing.ipynb` | PDF/PPTX 업로드 + B-1~B-4 파이프라인 실행 |
| 6 | `notebooks/06-multimodal-search.ipynb` | Basic vs Verbalized 검색 품질 비교 + 이미지 검색 데모 |
| 7 | `notebooks/07-content-understanding.ipynb` | B-5/B-6 CU Skill 인덱싱 + Image Serving + DI Layout 대비 비교 |

## 프로젝트 구조

```
azure-ai-search-deepdive/
├── src/                             # Python 소스 코드
│   ├── pipeline/
│   │   ├── legal_pipeline.py        # 4 법률 인덱서 + Skillset + Cache 설정
│   │   ├── multimodal_pipeline.py   # 4 멀티모달 파이프라인 (basic PDF/PPTX + verbalized PDF/PPTX)
│   │   └── indexer_ops.py           # AI Search REST API 클라이언트
│   └── search/
│       ├── legal_indexes.py         # 4 법률 인덱스 스키마 (HNSW 3072D, ko.microsoft)
│       └── multimodal_index.py      # 멀티모달 인덱스 스키마 (text+image 벡터)
│
├── skills-function/                 # Custom AI Search Skills (Azure Function)
│   └── function_app.py              # 3 skills: markdown_split, pptx_page_split, verbalize
│
├── logic-apps/
│   ├── deploy_workflow.py           # Logic Apps 워크플로우 배포 (Kudu API)
│   ├── crawl-function/              # law.go.kr 크롤러 (Azure Function)
│   ├── preprocess-function/         # 메타데이터 정규화 (Azure Function)
│   └── crawl-preprocess-workflow/   # 운영 워크플로우 (매일 21:00 UTC (06:00 KST))
│
├── notebooks/                       # Step-by-Step 핸즈온 랩
│   ├── 01-infra-deployment.ipynb    # Bicep 배포 + Function 배포 + SPL 승인
│   ├── 02-data-crawling.ipynb       # Logic App 트리거 + 크롤링 검증
│   ├── 03-indexing.ipynb            # 인덱스/Skillset/Indexer 생성 + Cache 테스트
│   ├── 04-search-and-query.ipynb    # Hybrid/Semantic/RAG + Agentic Retrieval
│   ├── 05-multimodal-indexing.ipynb # B-1~B-4 파이프라인 실행
│   ├── 06-multimodal-search.ipynb   # Basic vs Verbalized 검색 품질 비교
│   └── 07-content-understanding.ipynb # B-5/B-6 CU Skill + Image Serving + 비교
│
├── infra/                           # Bicep 인프라 템플릿 (리전별 분리)
│   ├── sweden/                      # 메인 배포 (Private Network)
│   ├── sweden-public/               # 퍼블릭 변형
│   └── korea/                       # Korea Central 변형
│
├── docs/                            # 아키텍처 다이어그램, ADR, 리포트
│   ├── infrastructure.md            # 인프라 상세 설명
│   ├── architecture-sweden.drawio   # Sweden 아키텍처 다이어그램
│   ├── issues/                      # ADR 스타일 의사결정
│   └── reports/                     # 실험 결과, 캐시 분석
│
└── data/
    ├── raw/                         # 크롤링 원본 (날짜별)
    └── processed/                   # 전처리 결과
```

## 변경 이력

### v2.0 (2026-05-07)

| 변경 항목 | 이전 | 이후 |
|----------|------|------|
| 리전 | East US / Korea Central | **Sweden Central** (DI 지원) |
| 네트워크 | 공개 인터넷 | **완전 Private** (VNet + PE) |
| 인덱싱 파이프라인 | Logic Apps Consumption | **AI Search Skills** (Indexer + Skillset) |
| 인프라 모듈 | storage, openai, ai-search, doc-intel, logic-app | + vnet, private-endpoints |

**Logic Apps 운영 정책:**
1. 기본 운영 워크플로우는 `crawl-preprocess-workflow` 1개
2. `crawl-workflow`, `rag-indexing-workflow`는 레거시/디버그용으로 저장소에만 유지
3. Split/Embedding/Ingest는 AI Search 네이티브 Skillset이 담당

### v2.1 (2026-06-15)

| 변경 항목 | 이전 | 이후 |
|----------|------|------|
| 권장 배포 | sweden (Private) | **sweden-public** (공개 엔드포인트) |
| Function App | EP1 (Elastic Premium) | **FC1** (Flex Consumption, 사용량 기반 과금) |
| 네트워크 | VNet + PE 필수 | **공개 엔드포인트** (sweden-public), VNet+PE 선택 (sweden) |
| Foundry Hub | Hub + Project + KeyVault 별도 배포 | **AI Services 하위 프로젝트** (Hub 불필요) |
| 폴링 타임아웃 | PT4H (4시간) | **PT24H** (24시간) |

## Private Network 접근 방법

> ℹ️ 이 섹션은 `infra/sweden/` (Private 변형) 배포 시에만 해당됩니다. `sweden-public` 배포 시에는 모든 서비스가 공개 엔드포인트로 직접 접근 가능합니다.

모든 서비스가 Private Endpoint 전용이므로 개발자 접근 방법:

```bash
# 옵션 A: 임시 Public Access 허용 (데모/개발)
az search service update --name <search-name> \
    --resource-group rg-rag-indexing-lab-swc \
    --public-network-access enabled

# 옵션 B: Azure Bastion + VM (프로덕션 권장)
# 옵션 C: 개발자 IP를 Storage/Search 방화벽에 추가
```

자세한 내용: [docs/infrastructure.md §7](docs/infrastructure.md#7-private-network-접근-방법)

## 참고 자료

- [Azure AI Search Skillsets](https://learn.microsoft.com/azure/search/cognitive-search-working-with-skillsets)
- [Document Intelligence Layout Model](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept-layout)
- [AI Search Shared Private Links](https://learn.microsoft.com/azure/search/search-indexer-howto-access-private)
- [Azure AI Search with Document Intelligence](https://github.com/jihys/azure-ai-search-with-doc-intelligence)
- [법령 개정 알림 크롤링](https://dev-grace.tistory.com/entry/Python-법령-개정-알림-서비스-구축하기-1-기본-설계-및-크롤링-구현)

## 라이선스

MIT License
