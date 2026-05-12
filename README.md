# Azure RAG Indexing Lab

**데이터 크롤링 → AI Search Skills 인덱싱 → Azure AI Search RAG 파이프라인 Hands-on Lab**

한국 법령 데이터를 자동 수집하고, **Azure AI Search 네이티브 Indexer + Skillset**으로 전처리·인덱싱하여 RAG 기반 검색을 수행하는 End-to-End 파이프라인입니다. 모든 Azure 리소스는 **Private Network(VNet + Private Endpoints)** 내에 구성됩니다.

> **리전**: Sweden Central — Document Intelligence가 Korea Central 미지원이므로 Sweden Central 사용

## 아키텍처

```
[Logic Apps - 매일 21:00 UTC]
  Recurrence 트리거
      │ HTTP POST
      ▼
┌──────────────────────────────────────────────────────────────┐
│  Azure Function App (EP1, Python 3.11)                       │
│  func-crawl-ragi  — 공개 HTTP 인바운드 / VNet 아웃바운드      │
│                                                              │
│  1. law.go.kr 크롤링 (공개 인터넷)                            │
│  2. Blob 업로드 (VNet → snet-func → snet-pep → Storage PE)  │
└──────────────────────┬───────────────────────────────────────┘
                       │ 업로드
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  VNet: vnet-ragi (10.0.0.0/16) — Sweden Central             │
│  snet-pep (10.0.1.0/24) — Private Endpoint 서브넷            │
│  snet-func (10.0.2.0/24) — Function VNet Integration 서브넷  │
│                                                              │
│  ┌──────────────┐   ┌──────────────────────────────────┐    │
│  │ Storage Acct │   │ Azure AI Search (Basic)           │    │
│  │ raw-docs     │◄──│ Indexer (매일 06:00 UTC)          │    │
│  │ proc-docs    │   │ Skillset:                         │    │
│  └──────────────┘   │  [1] Text Split (2000자/200자OV)  │    │
│         │           │  [2] OpenAI Embedding (3072D)     │    │
│  ┌──────┴───────┐   │ Index: vector+semantic             │    │
│  │ AI Services  │◄──│                                   │    │
│  │ gpt-5.4      │   └──────────────────────────────────┘    │
│  │ embedding-3L │         ▲ Shared Private Links             │
│  ├──────────────┤         │ (spl-blob, spl-ai, spl-di)      │
│  │ Doc Intel    │─────────┘                                  │
│  └──────────────┘   ※ DI Layout은 PDF 멀티모달 파이프라인에서 사용 │
└──────────────────────────────────────────────────────────────┘
         ↓
  RAG 질의 (GPT-5.4 + Hybrid Search)
```

**아키텍처 다이어그램**: [docs/architecture.drawio](docs/architecture.drawio) (draw.io에서 열기)

## 배포되는 Azure 리소스

| 리소스 | 리전 | SKU | 공개 접근 |
|--------|------|-----|----------|
| Resource Group | Sweden Central | - | - |
| Virtual Network (10.0.0.0/16) | Sweden Central | - | - |
| Storage Account | Sweden Central | Standard LRS | **차단** |
| Azure AI Services (gpt-5.4 + embedding) | Sweden Central | S0 | **차단** |
| Document Intelligence | Sweden Central | S0 | **차단** |
| Azure AI Search | Sweden Central | **Standard (S1)** | **차단** |
| Private Endpoints × 4 | Sweden Central | - | VNet 내부만 |
| Private DNS Zones × 4 | Global | - | VNet 연결 |
| Shared Private Links × 2 | - | - | Search 아웃바운드 |

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
    --template-file infra/main.bicep \
    --parameters infra/parameters/main.bicepparam
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

### 4. AI Search 파이프라인 설정

Logic Apps 대신 AI Search 네이티브 Indexer + Skillset을 사용합니다.

```bash
# Private Network 외부에서 실행 시 임시 Public Access 허용 필요
# (또는 VPN/Bastion 경유)

uv run python scripts/setup_ai_search_pipeline.py

# 즉시 인덱싱 실행
uv run python scripts/setup_ai_search_pipeline.py --run
```

멀티모달(PDF/이미지 고려) 별도 인덱스 파이프라인은 아래 2개 스크립트로 분리합니다.

```bash
# (Step 1~2) raw_pdf ZIP 해제 + 파일 유형 분류 + Blob raw/{pdf|pptx|image|other}/<source>/ 업로드
uv run python scripts/prepare_multimodal_raw_dataset.py --source st

# (Step 3~4) 별도 인덱스/스킬셋/인덱서 생성 (DI Layout + page split + embedding)
uv run python scripts/setup_ai_search_multimodal_pipeline.py --source st --run-indexer
```

### 5. 데이터 크롤링

```bash
# 법령 데이터 수집 및 Blob 업로드
uv run python -m src.crawler.law_crawler
```

### 6. 노트북 실행

| 순서 | 노트북 | 설명 |
|------|--------|------|
| 1 | `notebooks/01-infra-deployment.ipynb` | Bicep 배포 + Function App 코드 배포 + Shared PL 승인 + **AI Search 파이프라인 설정** |
| 2 | `notebooks/02-data-crawling.ipynb` | Azure Function App 수동 트리거 + Logic App 스케줄 확인 + Blob 결과 검증 |
| 3 | `notebooks/03-search-and-query.ipynb` | AI Search 하이브리드 검색 + **GPT-5.4 RAG** 질의응답 (**내부망 연결 Remote VM에서 실행 필수**) |
| 4 | `notebooks/04-legal-multi-index.ipynb` | 법률 데이터 4종 멀티 인덱스 구축 |
| 5 | `notebooks/05-multi-index-search.ipynb` | 멀티 인덱스 통합 검색 및 Cross-Index RAG |
| 6 | `notebooks/06-multimodal-search.ipynb` | 멀티모달 검색 (이미지 + 텍스트) |

## 프로젝트 구조

```
azure-rag-indexing-lab/
├── infra/                           # Bicep 인프라 템플릿
│   ├── main.bicep                   # 메인 (Sweden Central, Private Network)
│   ├── modules/
│   │   ├── vnet.bicep               # VNet + Private DNS Zones  [NEW]
│   │   ├── private-endpoints.bicep  # 모든 서비스 Private Endpoints  [NEW]
│   │   ├── storage.bicep            # Storage Account (Private)
│   │   ├── openai.bicep             # AI Services (Private)
│   │   ├── ai-search.bicep          # AI Search + Shared Private Links
│   │   └── doc-intelligence.bicep  # Document Intelligence (Private)
│   └── parameters/
│       └── main.bicepparam          # Sweden Central 파라미터
│
├── scripts/
│   ├── setup_ai_search_pipeline.py             # 기존 법령 텍스트 인덱서/스킬셋 설정
│   ├── prepare_multimodal_raw_dataset.py       # raw_pdf ZIP 해제/분류/업로드
│   └── setup_ai_search_multimodal_pipeline.py  # 별도 멀티모달 인덱스 파이프라인 설정
│
├── docs/
│   ├── infrastructure.md            # 인프라 상세 설명  [NEW]
│   └── architecture.drawio          # 아키텍처 다이어그램 (draw.io)  [NEW]
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
│   ├── 03-logic-apps-setup.ipynb    # → AI Search Skills 설정으로 변경
│   └── 04-search-and-query.ipynb
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

**Logic Apps 제거 이유:**
1. Consumption Plan은 VNet integration 미지원 → Private Network 불가
2. AI Search 네이티브 Skillset으로 동일 파이프라인을 선언형으로 구성 가능
3. Python 크롤러가 이미 크롤 기능을 담당하므로 Logic Apps 크롤 워크플로우도 불필요

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
