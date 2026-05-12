# Azure AI Search Deep Dive Lab

**Azure AI Search의 핵심 기능을 2개 실제 시나리오로 데모하는 Hands-on Lab**

| 시나리오 | 데이터 | 파이프라인 | 인덱스 |
|----------|------|---------|--------|
| **A. 법령 문서** | 한국 법령 (law.go.kr 크롤링) | Logic Apps 오케스트레이션 → AI Search Native Skillset | 4개 (prec / detc / expc / admrul) |
| **B. 멀티모달** | PDF / PPTX (수동 업로드) | AI Search Skillset 비교 (Native vs Custom+Native) | 2개 (비교용) |

모든 Azure 리소스는 **Private Network (VNet + Private Endpoints)** 내에 구성됩니다.

> **리전**: Sweden Central — Document Intelligence가 Korea Central 미지원이므로 Sweden Central 사용

## 시나리오 A: 법령 문서 인덱싱 파이프라인

```
╔══════════════════════════════════════════════════════════════╗
║ Stage 1: CRAWLING + DATA INTEGRATION  (Logic Apps 관장)         ║
║                                                              ║
║  [Logic Apps - 매일 06:00 KST]                               ║
║  Recurrence 트리거                                             ║
║      │ Step 1: Crawl Function HTTP POST                         ║
║      ▼                                                          ║
║  law.go.kr 크롤링 → raw-documents/{source}/{date}/           ║
║  (prec / detc / expc / admrul - 병렬)                         ║
║      │ Step 2: Data Integration Function HTTP POST (x4 병렬) ║
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
    ▼ Blob Storage: raw/pdf/{source}/
    │
    ├──────────────────────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  [Pipeline B-1: Native Only]       [Pipeline B-2: Custom+Native]  │
│  (Skillset 비교 기준)              (Skillset 비교 실제)              │
│                                                                    │
│  DI Layout → Markdown              DI Layout → Markdown           │
│  ↓                                  ↓                              │
│  Native Text Split                 Custom WebApiSkill              │
│  (markdown mode)                   (GPT-5.4 이미지 Verbalization)   │
│  ↓                                  ↓                              │
│  Embedding (3072D)                 Native Text Split               │
│  ↓                                  ↓                              │
│  multimodal-native-index           Embedding (3072D)              │
│                                    ↓                              │
│                                   multimodal-custom-index         │
└──────────────────────────────────────────────────────────────────────────────────────┘
         ↓
  검색 비교 (Native vs GPT Verbalization 음질 차이 데모)
```

**아키텍처 다이어그램**: [docs/architecture-sweden.drawio](docs/architecture-sweden.drawio), [docs/architecture-korea.drawio](docs/architecture-korea.drawio) (draw.io에서 열기)

## 배포되는 Azure 리소스

| 리소스 | 리전 | SKU | 공개 접근 |
|--------|------|-----|-----------|
| Resource Group | Sweden Central | - | - |
| Virtual Network (10.0.0.0/16) | Sweden Central | - | - |
| Storage Account | Sweden Central | Standard LRS | **차단** |
| Azure AI Services (gpt-5.4 + embedding) | Sweden Central | S0 | **차단** |
| Document Intelligence | Sweden Central | S0 | **차단** |
| Azure AI Search | Sweden Central | **Standard (S1)** | **차단** |
| Function App (Crawl) | Sweden Central | EP1 | 인바운드 공개 |
| Function App (Preprocess) | Sweden Central | EP1 | VNet 내부 |
| Logic App (Standard) | Sweden Central | WS1 | - |
| Private Endpoints × 4 | Sweden Central | - | VNet 내부만 |
| Private DNS Zones × 4 | Global | - | VNet 연결 |
| Shared Private Links × 3 | - | - | Search 아웃바운드 |

> 상세 설명: [docs/infrastructure.md](docs/infrastructure.md)

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
git clone https://github.com/jihys/azure-rag-indexing-lab.git
cd azure-rag-indexing-lab

uv venv .venv --python 3.10
source .venv/bin/activate
uv pip install -e .

cp sample.env .env
# .env 파일 편집하여 실제 값 입력
```

### 2. 인프라 배포 (Bicep)

```bash
az login

# Sweden Central에 배포 (~10분 소요)
az deployment sub create \
    --location swedencentral \
    --template-file infra/sweden/main.bicep \
    --parameters infra/sweden/parameters/main.bicepparam
```

### 3. Shared Private Link 승인

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
1. **crawl-preprocess-workflow** (매일 06:00 KST): 크롤링 → Data Integration (병렬 4개 소스)

`crawl-workflow`, `rag-indexing-workflow`는 레거시/디버그용으로 파일만 유지하며 기본 배포 대상에서 제외됩니다.

```bash
uv run python logic-apps/deploy_workflow.py
```

### 4-1. 전처리(Data Integration) 과정

시나리오 A의 전처리는 Logic Apps Stage 1에서 수행되며, 역할은 아래로 제한됩니다.

1. `raw-documents/{source}/{date}/` 입력 수집
2. 메타데이터 정규화 (source/date/file_id 등)
3. 포맷 정리 후 `processed-documents/{source}/{date}/` 저장

중요: 청크 분할(Text Split)과 임베딩 생성은 전처리 단계가 아니라, Stage 2의 AI Search Skillset이 담당합니다.

### 5. AI Search 파이프라인 설정

**시나리오 A — 법령 텍스트 (4개 인덱스)**:
```bash
# Index + Skillset(Text Split + Embedding) + DataSource + Indexer 생성
uv run python scripts/setup_ai_search_pipeline.py

# 즉시 첫 인덱싱 실행 (Full Build)
uv run python scripts/setup_ai_search_pipeline.py --run
```

**시나리오 B — 멀티모달 (2개 인덱스, 비교용)**:
```bash
# PDF/PPTX를 Blob에 수동 업로드
uv run python scripts/prepare_multimodal_raw_dataset.py --source {source}

# Pipeline B-1: Native-only Skillset (DI Layout → Text Split → Embedding)
# Pipeline B-2: Custom+Native Skillset (DI Layout → GPT-5.4 Verbalization → Split → Embedding)
uv run python scripts/setup_ai_search_multimodal_pipeline.py --source {source} --run-indexer
```

### 6. 데이터 크롤링 (선택 사항)

Logic App 스케줄이 아닌 수동으로 크롤링하려면:

```bash
# 법령 데이터 수집 및 Blob 업로드 (단일 실행)
uv run python -m src.crawler.law_crawler
```

### 7. 노트북 실행

#### 공통 준비 (시나리오 A·B 공통)
| 순서 | 노트북 | 설명 |
|------|--------|------|
| 1 | `notebooks/01-infra-deployment.ipynb` | Bicep 배포 + Function 코드 배포 + Shared PL 승인 + Logic Apps 워크플로우 배포 |

#### 시나리오 A: 법령 문서 인덱싱
| 순서 | 노트북 | 설명 |
|------|--------|------|
| 2 | `notebooks/02-data-crawling.ipynb` | Logic App 트리거 + AI Search 인덱서 모니터링 + Blob 결과 검증 |
| 3 | `notebooks/03-indexing.ipynb` | 인덱싱 샘플 실행 및 필요 시 전체 인덱스 삭제 후 인덱서 재실행 |
| 4 | `notebooks/04-search-and-query.ipynb` | AI Search 하이브리드 검색 + GPT-5.4 RAG 질의응답 |
| 5 | `notebooks/05-multi-index-search.ipynb` | 멀티 인덱스 통합 검색 및 Cross-Index RAG |

#### 시나리오 B: 멀티모달 PDF/PPTX 인덱싱
| 순서 | 노트북 | 설명 |
|------|--------|------|
| 6 | `notebooks/06-multimodal-search.ipynb` | PDF 업로드 → Native vs Custom+Native Skillset 비교 → 멀티모달 검색 데모 |

## 프로젝트 구조

```
azure-rag-indexing-lab/
├── infra/                           # Bicep 인프라 템플릿 (리전별 분리)
│   ├── sweden/                      # Sweden Central 배포
│   │   ├── main.bicep               # 메인 (Sweden Central, Private Network)
│   │   ├── modules/
│   │   │   ├── vnet.bicep            # VNet + Private DNS Zones
│   │   │   ├── private-endpoints.bicep # 모든 서비스 Private Endpoints
│   │   │   ├── storage.bicep         # Storage Account (Private)
│   │   │   ├── openai.bicep          # AI Services (Private)
│   │   │   ├── ai-search.bicep       # AI Search + Shared Private Links
│   │   │   └── doc-intelligence.bicep # Document Intelligence (Private)
│   │   └── parameters/
│   │       └── main.bicepparam       # Sweden Central 파라미터
│   │
│   └── korea/                       # Korea Central 배포
│       ├── main.bicep               # 메인 (Korea Central + East US 2 DI)
│       ├── modules/
│       │   ├── vnet.bicep            # VNet + Private DNS Zones
│       │   ├── private-endpoints.bicep # PE (Cross-Region DI PE 포함)
│       │   ├── storage.bicep         # Storage Account (Private)
│       │   ├── openai.bicep          # AI Services (Private)
│       │   ├── ai-search.bicep       # AI Search + Shared Private Links
│       │   └── doc-intelligence.bicep # Document Intelligence (East US 2)
│       └── parameters/
│           └── main.bicepparam       # Korea Central 파라미터
│
├── scripts/
│   ├── setup_ai_search_pipeline.py             # 기존 법령 텍스트 인덱서/스킬셋 설정
│   ├── prepare_multimodal_raw_dataset.py       # raw_pdf ZIP 해제/분류/업로드
│   └── setup_ai_search_multimodal_pipeline.py  # 별도 멀티모달 인덱스 파이프라인 설정
│
├── logic-apps/
│   ├── deploy_workflow.py                      # Logic Apps 워크플로우 배포 스크립트
│   ├── crawl-function/                         # Crawl Function 코드
│   ├── preprocess-function/                    # Data Integration Function 코드
│   ├── crawl-preprocess-workflow/              # 운영 워크플로우 (기본)
│   ├── crawl-workflow/                         # 레거시/디버그용
│   └── rag-indexing-workflow/                  # 레거시/디버그용
│
├── docs/
│   ├── infrastructure.md            # 인프라 상세 설명  [NEW]
│   ├── architecture-sweden.drawio   # Sweden 아키텍처 다이어그램
│   └── architecture-korea.drawio    # Korea 아키텍처 다이어그램
│
├── src/                             # Python 소스 코드
│   ├── crawler/law_crawler.py       # 법령 크롤러 (law.go.kr)
│   ├── blob/uploader.py             # Blob Storage 업로더
│   ├── preprocessing/               # Document Intelligence, Embedding
│   └── search/                      # AI Search 인덱스 관리
│
├── notebooks/                       # Step-by-Step 노트북
│   ├── 01-infra-deployment.ipynb
│   ├── 02-data-crawling.ipynb
│   ├── 03-indexing.ipynb
│   ├── 04-search-and-query.ipynb
│   ├── 05-multi-index-search.ipynb
│   └── 06-multimodal-search.ipynb
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

## Private Network 접근 방법

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
