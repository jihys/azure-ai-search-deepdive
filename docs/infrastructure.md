# 인프라 상세 설명

> **리전**: Sweden Central (`swedencentral`)  
> **이유**: Document Intelligence는 Korea Central에서 미지원. Sweden Central은 DI, OpenAI, AI Search 모두 지원.  
> **네트워크**: 모든 리소스가 Private Network(VNet + Private Endpoints) 전용 구성

---

## 목차

1. [배포되는 Azure 리소스 전체 목록](#1-배포되는-azure-리소스-전체-목록)
2. [네트워크 아키텍처](#2-네트워크-아키텍처)
3. [각 리소스 상세 설명](#3-각-리소스-상세-설명)
4. [RBAC 권한 구성](#4-rbac-권한-구성)
5. [크롤 파이프라인 (Logic Apps + Function App)](#5-크롤-파이프라인-logic-apps--function-app)
6. [인덱싱 파이프라인 (AI Search Skills)](#6-인덱싱-파이프라인-ai-search-skills)
7. [배포 순서 및 의존성](#7-배포-순서-및-의존성)
8. [Function App 코드 배포](#8-function-app-코드-배포)
9. [Private Network 접근 방법](#9-private-network-접근-방법)
10. [Shared Private Link 승인 절차](#10-shared-private-link-승인-절차)

---

## 1. 배포되는 Azure 리소스 전체 목록

| # | 리소스 타입 | 이름 패턴 | SKU | 용도 |
|---|------------|-----------|-----|------|
| 1 | Resource Group | `rg-rag-indexing-lab-swc` | - | 모든 리소스 컨테이너 |
| 2 | Virtual Network | `vnet-ragi-<suffix>` | - | 프라이빗 네트워크 격리 |
| 3 | Network Security Group | `nsg-pep-ragi-<suffix>` | - | PE 서브넷 보안 규칙 |
| 4 | Storage Account | `stragi<suffix>` | Standard LRS | 원본 문서 및 처리 결과 저장 |
| 5 | Blob Container | `raw-documents` | - | 크롤링된 원본 문서 (PDF, MD) |
| 6 | Blob Container | `processed-documents` | - | 처리 완료 문서 보관 |
| 7 | Azure AI Services | `ais-ragi-<suffix>` | S0 | OpenAI GPT-5.4 + Embedding 통합 |
| 8 | Model Deployment | `gpt-5.4` | GlobalStandard 30K | 질의응답, 텍스트 생성 |
| 9 | Model Deployment | `text-embedding-3-large` | Standard 120K | 3072차원 벡터 임베딩 |
| 10 | Document Intelligence | `di-ragi-<suffix>` | S0 | PDF/문서 레이아웃 분석 → Markdown |
| 11 | Azure AI Search | `search-ragi-<suffix>` | **Standard (S1)** | 벡터+시맨틱 하이브리드 검색 |
| 12 | App Service Plan | `asp-crawl-ragi-<suffix>` | EP1 (Elastic Premium) | Function App 호스팅 플랜 (VNet integration 지원) |
| 13 | Function App | `func-crawl-ragi-<suffix>` | Python 3.11 / Linux | 법령 크롤러 (law.go.kr → Blob) |
| 14 | Logic App | `logic-crawl-ragi-<suffix>` | Consumption | 크롤 스케줄러 (매일 21:00 UTC) |
| 15 | Private Endpoint (Storage) | `pe-blob-ragi-<suffix>` | - | VNet → Storage 프라이빗 접근 |
| 16 | Private Endpoint (Search) | `pe-search-ragi-<suffix>` | - | VNet → AI Search 프라이빗 접근 |
| 17 | Private Endpoint (AI Services) | `pe-aiservices-ragi-<suffix>` | - | VNet → AI Services 프라이빗 접근 |
| 18 | Private Endpoint (Doc Intel) | `pe-docintel-ragi-<suffix>` | - | VNet → Doc Intelligence 프라이빗 접근 |
| 19 | Private DNS Zone | `privatelink.blob.core.windows.net` | - | Storage PE DNS 해석 |
| 20 | Private DNS Zone | `privatelink.search.windows.net` | - | AI Search PE DNS 해석 |
| 21 | Private DNS Zone | `privatelink.cognitiveservices.azure.com` | - | AI Services / DI PE DNS 해석 |
| 22 | Private DNS Zone | `privatelink.openai.azure.com` | - | AI Services OpenAI 엔드포인트 DNS |
| 23 | Shared Private Link | `spl-blob` (Search→Storage) | - | AI Search 인덱서 아웃바운드 접근 |
| 24 | Shared Private Link | `spl-aiservices` (Search→AI Svc) | - | Embedding Skill 아웃바운드 접근 |
| 25 | Shared Private Link | `spl-docintel` (Search→DI) | - | DI Layout Skill 아웃바운드 접근 |

> `<suffix>`는 구독 ID + RG 이름으로 생성되는 고유 8자리 해시

---

## 2. 네트워크 아키텍처

```
외부 인터넷 (공개)
    │
    │  law.go.kr (법령 데이터)
    │         ▲ 크롤링 (HTTP GET)
    │         │
    │  [Logic App - 매일 21:00 UTC]
    │  HTTP POST → func-crawl-ragi.azurewebsites.net
    │         │
    ├─────────▼─────────────────────────────────────────────┐
    │  Azure Function App (func-crawl-ragi)                 │
    │  공개 인바운드: HTTPS /api/crawl                       │
    │  아웃바운드: VNet Integration (snet-func)             │
    └────────────────────────┬──────────────────────────────┘
                             │ VNet 아웃바운드
                             ▼
┌────────────────────────────────────────────────────────────┐
│  Virtual Network: vnet-ragi (10.0.0.0/16)                  │
│  Location: Sweden Central                                   │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  snet-func (10.0.2.0/24) - Function VNet Integration │  │
│  │  Delegation: Microsoft.Web/serverFarms               │  │
│  │  (Function App 아웃바운드 트래픽 진입점)               │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │ VNet 내부 라우팅                  │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  snet-pep (10.0.1.0/24) - Private Endpoint 서브넷    │  │
│  │  NSG: 인바운드/아웃바운드 기본 차단                    │  │
│  │                                                      │  │
│  │  ● pe-blob-ragi      → Storage Account               │  │
│  │  ● pe-search-ragi    → AI Search                     │  │
│  │  ● pe-aiservices-ragi→ AI Services (OpenAI)          │  │
│  │  ● pe-docintel-ragi  → Document Intelligence         │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘

Private DNS Zones (VNet 연결):
  privatelink.blob.core.windows.net          → Storage PE IP
  privatelink.search.windows.net             → Search PE IP
  privatelink.cognitiveservices.azure.com    → AI Svc / DI PE IP
  privatelink.openai.azure.com               → AI Svc OpenAI PE IP

AI Search 아웃바운드 (Shared Private Links):
  AI Search → [spl-blob]       → Storage (인덱서 읽기)
  AI Search → [spl-aiservices] → AI Services (Embedding Skill)
  AI Search → [spl-docintel]   → Doc Intelligence (Layout Skill)

트래픽 흐름 요약:
  크롤:   Logic App → Function (공개 HTTPS) → VNet(snet-func) → PE → Storage
  인덱싱: AI Search (내부) → Shared PL → Storage/AI Svc/DI (Private)
  쿼리:   클라이언트 → AI Search PE (VNet 내부 또는 임시 Public)
```

---

## 3. 각 리소스 상세 설명

### 3.1 Virtual Network (`vnet-ragi`)

| 항목 | 값 |
|------|-----|
| 주소 공간 | `10.0.0.0/16` |
| 서브넷 1 | `snet-pep` (`10.0.1.0/24`) — Private Endpoint 전용 |
| 서브넷 2 | `snet-func` (`10.0.2.0/24`) — Function App VNet Integration 전용 |
| snet-pep 설정 | `privateEndpointNetworkPolicies: Disabled` (PE 필수 설정) |
| snet-func 설정 | Delegation: `Microsoft.Web/serverFarms` (Function App 아웃바운드 전용) |

Private DNS Zone 4개가 이 VNet에 연결되어, VNet 내부에서 프라이빗 IP로 각 서비스에 접근합니다. 공개 DNS로 쿼리 시 NXDOMAIN 또는 공개 IP가 반환되지만, VNet 내부에서는 PE의 프라이빗 IP가 반환됩니다.

`snet-func`의 Delegation은 Azure Function App(EP1)이 VNet Integration을 통해 아웃바운드 트래픽을 VNet으로 라우팅할 수 있도록 합니다. 이 서브넷의 트래픽이 `snet-pep`의 Storage Private Endpoint로 라우팅되어 프라이빗 Storage 접근이 가능합니다.

---

### 3.2 Storage Account (`stragi<suffix>`)

| 항목 | 값 |
|------|-----|
| SKU | Standard LRS |
| TLS | 최소 1.2 |
| 공개 Blob | 차단 (`allowBlobPublicAccess: false`) |
| SharedKey | 차단 (`allowSharedKeyAccess: false`) |
| 공개 네트워크 | **비활성화** (`publicNetworkAccess: Disabled`) |
| 접근 방법 | Managed Identity (RBAC) 또는 VNet 내부 PE |
| Bypass | AzureServices (ARM 배포 등 Microsoft 신뢰 서비스 허용) |

**컨테이너:**
- `raw-documents`: Python 크롤러가 업로드하는 원본 법령 문서
- `processed-documents`: 인덱싱 완료 후 이동 대상 (옵션)

---

### 3.3 Azure AI Services (`ais-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| Kind | `AIServices` (OpenAI + Cognitive Services 통합) |
| SKU | S0 |
| 공개 네트워크 | **비활성화** |
| 인증 | Managed Identity (RBAC), 키 인증 차단 |

**배포된 모델:**

| 모델 | 배포명 | 타입 | TPM | 용도 |
|------|--------|------|-----|------|
| `gpt-5.4` | `gpt-5.4` | GlobalStandard | 30K | **RAG 질의응답** |
| `text-embedding-3-large` | `text-embedding-3-large` | Standard | 120K | 3072D 벡터 생성 |

> `gpt54ModelVersion`은 `infra/parameters/main.bicepparam`에서 설정합니다.  
> Azure Portal → Azure AI Services → 모델 배포에서 사용 가능한 gpt-5.4 버전을 확인하세요.

> `kind: AIServices`는 Azure AI Foundry 백엔드로, 단일 엔드포인트에서 OpenAI API와 Cognitive Services API를 모두 사용할 수 있습니다.

---

### 3.4 Document Intelligence (`di-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| Kind | `FormRecognizer` |
| SKU | S0 |
| 공개 네트워크 | **비활성화** |
| 사용 모델 | `prebuilt-layout` |

**prebuilt-layout 모델 기능:**
- PDF, DOCX, PPTX, 이미지(JPG/PNG/TIFF)에서 텍스트 추출
- 표(Table) 구조 보존 → Markdown 테이블 변환
- 섹션 헤더 인식 → 계층 구조 보존
- 다중 컬럼 레이아웃 처리
- 출력 형식: Markdown (`outputContentFormat: markdown`)

> **Korea Central 미지원**: Document Intelligence는 Korea Central 리전에서 제공되지 않습니다. Sweden Central을 사용합니다.

---

### 3.5 Azure AI Search (`search-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| SKU | **Standard (S1)** |
| Replicas | 1 |
| Partitions | 1 |
| Semantic Search | Standard (포함) |
| 공개 네트워크 | **비활성화** |
| Identity | System Assigned Managed Identity |

**AI Search 구성 요소 (Bicep 외 스크립트로 설정):**

| 구성 요소 | 이름 | 설명 |
|----------|------|------|
| Data Source | `law-blob-datasource` | `raw-documents` 컨테이너 감시 |
| Index | `law-documents-index` | 벡터(3072D) + 텍스트 + 시맨틱 |
| Skillset | `law-rag-skillset` | DI Layout → Split → Embedding |
| Indexer | `law-blob-indexer` | 일별 06:00 UTC 자동 실행 |

**Shared Private Links (아웃바운드):**

| 이름 | 대상 | GroupId | 용도 |
|------|------|---------|------|
| `spl-blob` | Storage Account | `blob` | 인덱서가 Blob에서 문서 읽기 |
| `spl-aiservices` | AI Services | `cognitiveservices_account` | Embedding Skill API 호출 |

> Shared Private Link는 AI Search가 자체 Managed VNet에서 Private Endpoint를 생성하여 아웃바운드 연결을 맺는 방식입니다. 배포 후 **대상 리소스에서 승인 필요** (섹션 8 참조).

---

### 3.6 Azure Function App (`func-crawl-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| 플랜 | Elastic Premium EP1 (1 vCore, 3.5GB RAM) |
| 런타임 | Python 3.11 / Linux |
| VNet Integration | `snet-func` (10.0.2.0/24) — 아웃바운드 전용 |
| 인바운드 | 공개 HTTPS (`https://func-crawl-ragi-<suffix>.azurewebsites.net/api/crawl`) |
| 인증 | ANONYMOUS (Logic Apps가 직접 URL로 호출) |
| Storage 접근 | Managed Identity (`AzureWebJobsStorage__credential: managedidentity`) |

**EP1 플랜 선택 이유:**

Consumption Plan(소비 계획)은 VNet Integration을 지원하지 않아 Private Storage PE로의 아웃바운드 접근이 불가능합니다. EP1(Elastic Premium)은 VNet Integration을 지원하며, Function App이 `snet-func`를 통해 VNet 내부 라우팅으로 Storage Private Endpoint에 접근합니다.

**환경 변수:**

| 변수명 | 값 | 용도 |
|--------|-----|------|
| `FUNCTIONS_EXTENSION_VERSION` | `~4` | Functions v4 런타임 |
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Python 워커 |
| `AzureWebJobsStorage__accountName` | Storage 계정명 | MI 기반 런타임 스토리지 |
| `AzureWebJobsStorage__credential` | `managedidentity` | SharedKey 없이 MI 인증 |
| `AZURE_STORAGE_ACCOUNT_NAME` | Storage 계정명 | 크롤러 Blob 업로드 대상 |
| `AZURE_BLOB_CONTAINER_NAME` | `raw-documents` | 업로드 컨테이너 |
| `CRAWLER_LIMIT` | `10` (기본값) | 수집할 법령 건수 |

---

### 3.7 Logic App (`logic-crawl-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| 플랜 | Consumption (서버리스) |
| 스케줄 | 매일 21:00 UTC (= 한국 06:00 KST) |
| 트리거 | Recurrence (일별 반복) |
| 액션 | HTTP POST → Function App `/api/crawl` |
| 재시도 | 3회, 1분 간격 |
| VNet | 불필요 (Function은 공개 인바운드 허용) |

**Logic Apps Consumption + VNet 제약:**

Logic Apps Consumption Plan은 VNet Integration을 지원하지 않습니다. 이 아키텍처에서는 Logic Apps가 **공개 인터넷**으로 Function App을 호출하고, Function App이 **VNet Integration**을 통해 Private Storage에 접근하는 방식으로 설계되어 두 서비스의 제약을 모두 우회합니다.

**워크플로우 흐름:**

```
[Recurrence 트리거 - 매일 21:00 UTC]
    │
    ▼
[HTTP POST] → func-crawl-ragi.azurewebsites.net/api/crawl
    body: { "limit": 10, "triggered_by": "logic-apps-schedule", "trigger_time": "..." }
    retryPolicy: { count: 3, interval: PT1M }
    │
    ▼
[Compose - Log_Result]
    실행 결과 캡처 (성공/실패/타임아웃 모두 포함)
```

---

### 3.8 Private Endpoints

각 서비스에 대해 VNet의 `snet-pep` 서브넷에 Private Endpoint가 생성됩니다.

| PE 이름 | 대상 서비스 | GroupId | DNS Zone |
|---------|------------|---------|----------|
| `pe-blob-ragi` | Storage Account | `blob` | `privatelink.blob.core.windows.net` |
| `pe-search-ragi` | AI Search | `searchService` | `privatelink.search.windows.net` |
| `pe-aiservices-ragi` | AI Services | `account` | `privatelink.cognitiveservices.azure.com` + `privatelink.openai.azure.com` |
| `pe-docintel-ragi` | Doc Intelligence | `account` | `privatelink.cognitiveservices.azure.com` |

각 PE는 Private DNS Zone Group을 통해 자동으로 DNS A 레코드를 등록합니다.

---

## 4. RBAC 권한 구성

모든 서비스 간 접근은 Managed Identity + RBAC으로 구성됩니다 (API 키 사용 없음).

| 주체 | 대상 리소스 | 역할 | 용도 | 설정 방식 |
|------|------------|------|------|----------|
| Function App (MI) | Storage Account | Storage Blob Data Contributor | 크롤러가 Blob에 문서 쓰기 | Bicep 자동 |
| Function App (MI) | Storage Account | Storage Queue Data Contributor | Functions 런타임 큐 접근 | Bicep 자동 |
| Function App (MI) | Storage Account | Storage Table Data Contributor | Functions 런타임 테이블 접근 | Bicep 자동 |
| AI Search (MI) | Storage Account | Storage Blob Data Reader | 인덱서가 문서 읽기 | Bicep 자동 |
| AI Search (MI) | AI Services | Cognitive Services User | Embedding/DI Skill 호출 | Bicep 자동 |
| 개발자 계정 | Storage Account | Storage Blob Data Contributor | 문서 업로드/관리 | 수동 할당 |
| 개발자 계정 | AI Search | Search Index Data Contributor | 인덱스 쿼리/관리 | 수동 할당 |
| 개발자 계정 | AI Services | Cognitive Services OpenAI User | GPT-5.4 API 호출 | 수동 할당 |

> Bicep 배포 시 Function App MI 및 AI Search MI에 대한 RBAC이 자동 설정됩니다.  
> 개발자 계정 권한은 배포 후 수동으로 할당합니다 (섹션 9 참조).

---

## 5. 크롤 파이프라인 (Logic Apps + Function App)

법령 데이터를 자동으로 수집하여 Blob Storage에 저장하는 크롤 파이프라인입니다.

```
[Logic App - logic-crawl-ragi]
매일 21:00 UTC (= 한국 06:00 KST)
    │
    │ HTTP POST (공개 인터넷)
    │ body: { "limit": 10, "triggered_by": "logic-apps-schedule" }
    ▼
[Function App - func-crawl-ragi]  ← 공개 HTTPS 인바운드
    │
    ├─ 1. law.go.kr DRF API 호출 (법령 목록 수집)
    │     GET /DRF/lawSearch.do?target=law&type=JSON&display=10
    │
    ├─ 2. 각 법령 상세 페이지 크롤링
    │     GET /LSW/lsInfoP.do?lsiSeq={법령일련번호}
    │     → BeautifulSoup으로 본문 추출 → Markdown 변환
    │
    └─ 3. Blob Storage 업로드 (VNet Integration 경유)
          snet-func → VNet 라우팅 → snet-pep → pe-blob-ragi → Storage
          저장 경로: {YYYY-MM-DD}/law_{id}.json
                   {YYYY-MM-DD}/law_{id}.md
                   {YYYY-MM-DD}/law_list.json
```

**저장 파일 형식:**

| 파일명 | 내용 |
|--------|------|
| `{날짜}/law_list.json` | 수집된 법령 목록 (id, title, url, pub_date) |
| `{날짜}/law_{id}.json` | 법령 상세 (title, content, markdown, url, crawled_at) |
| `{날짜}/law_{id}.md` | Markdown 형식 법령 본문 (AI Search 인덱싱 대상) |

**폴백(Fallback) 처리:**

API 접근 실패 시 샘플 법령 데이터(개인정보 보호법, AI 산업 육성법 등)로 대체하여 파이프라인이 중단되지 않도록 합니다.

---

## 6. 인덱싱 파이프라인 (AI Search Skills)

AI Search 네이티브 Indexer + Skillset으로 크롤된 문서를 벡터 인덱싱합니다.

```
Blob Storage (raw-documents)
    │
    │  AI Search Indexer (일별 스케줄)
    │  ← Shared Private Link로 접근
    ▼
[Skill 1] DocumentIntelligenceLayoutSkill
    ├─ 입력: file_data (Blob 바이너리)
    ├─ 처리: prebuilt-layout 모델로 분석
    └─ 출력: markdown_sections[] (헤더별 Markdown 섹션)
    │
    ▼
[Skill 2] SplitSkill
    ├─ 입력: 각 markdown_section.content
    ├─ 처리: 2000자 청크, 200자 오버랩
    └─ 출력: pages[] (텍스트 청크 배열)
    │
    ▼
[Skill 3] AzureOpenAIEmbeddingSkill
    ├─ 입력: 각 page 텍스트
    ├─ 처리: text-embedding-3-large (3072D)
    └─ 출력: content_vector (float32 배열)
    │
    ▼
AI Search Index (law-documents-index)
    ├─ content: 텍스트 청크
    ├─ content_vector: 3072D 벡터
    ├─ metadata_storage_name: 파일명
    ├─ metadata_storage_path: Blob 경로
    └─ metadata_storage_last_modified: 수정 시각
```

**Logic Apps 대비 장점:**

| 항목 | Logic Apps (이전) | AI Search Skills (현재) |
|------|-----------------|----------------------|
| 구성 | 6단계 워크플로우 JSON | 선언형 Skillset JSON |
| Private Network | Consumption Plan 미지원 | Shared Private Link 완전 지원 |
| 오류 처리 | 수동 재시도 로직 필요 | 내장 재시도 + 부분 실패 허용 |
| 모니터링 | Logic Apps 실행 이력 | AI Search 인덱서 상태 API |
| 비용 | 실행당 과금 | AI Search 서비스 비용 포함 |
| 확장성 | 수동 병렬화 | batchSize 파라미터로 제어 |

---

## 7. 배포 순서 및 의존성

```
1. Resource Group
   │
2. VNet + Private DNS Zones (병렬 가능)
   │
3. Storage + AI Services + Doc Intelligence (병렬 가능)
   │
4. AI Search (Storage, AI Services, DI ID 참조)
   │
5. Function App EP1 Plan + Function App (VNet, Storage 참조)
   Logic App Consumption (Function URL 참조)
   │
6. Private Endpoints (모든 서비스 ID 참조)
   │
7. [코드 배포] crawl-function/ → Function App (섹션 8)
   │
8. [수동] Shared Private Link 승인 (섹션 10)
   │
9. [스크립트] AI Search 파이프라인 설정
   (setup_ai_search_pipeline.py)
```

Bicep 1~6단계는 단일 `az deployment sub create` 명령으로 자동 처리됩니다.

---

## 8. Function App 코드 배포

Bicep으로 Function App 인프라를 배포한 후, 크롤러 코드(`crawl-function/`)를 Function App에 배포합니다.

### Azure Functions Core Tools 사용

```bash
# Azure Functions Core Tools 설치 (미설치 시)
npm install -g azure-functions-core-tools@4

# 배포
cd crawl-function
func azure functionapp publish func-crawl-ragi-<suffix> --python
```

### Azure CLI ZIP 배포 사용

```bash
cd crawl-function
zip -r ../func-crawl.zip .

az functionapp deployment source config-zip \
    --name func-crawl-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --src ../func-crawl.zip
```

### 배포 확인

```bash
# Function 목록 확인
az functionapp function list \
    --name func-crawl-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --query "[].{name:name, invokeUrlTemplate:invokeUrlTemplate}" \
    --output table

# 수동 테스트 (즉시 크롤 실행)
curl -X POST "https://func-crawl-ragi-<suffix>.azurewebsites.net/api/crawl" \
    -H "Content-Type: application/json" \
    -d '{"limit": 3, "triggered_by": "manual-test"}'
```

### 로컬 개발 환경 설정

```bash
cd crawl-function
cp local.settings.json.example local.settings.json
# local.settings.json 편집하여 실제 Storage 계정명 입력

# 로컬 실행 (Azurite 또는 실제 Storage 사용)
pip install -r requirements.txt
func start
```

---

## 9. Private Network 접근 방법

모든 서비스가 `publicNetworkAccess: Disabled`이므로, 개발자는 다음 방법 중 하나로 접근합니다.

### 옵션 A: Azure Bastion + VM (권장, 프로덕션)

```bash
# VNet 내 VM 생성 (별도 서브넷)
az vm create --resource-group rg-rag-indexing-lab-swc \
    --name vm-jumpbox \
    --vnet-name vnet-ragi-<suffix> \
    --subnet snet-pep \
    --image Ubuntu2204 \
    --generate-ssh-keys

# Azure Bastion으로 접속 후 스크립트 실행
```

### 옵션 B: 임시 Public Access 허용 (데모/개발용)

```bash
# 설정 스크립트 실행 전 임시 허용
az search service update \
    --name search-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --public-network-access enabled

# 스크립트 실행
uv run python scripts/setup_ai_search_pipeline.py

# 다시 비활성화
az search service update \
    --name search-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --public-network-access disabled
```

### 옵션 C: 개발자 IP 허용 (방화벽 규칙)

```bash
MY_IP=$(curl -s ifconfig.me)

# Storage: IP 허용
az storage account update \
    --name stragi<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --public-network-access Enabled \
    --default-action Deny

az storage account network-rule add \
    --account-name stragi<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --ip-address $MY_IP
```

---

## 10. Shared Private Link 승인 절차

AI Search가 아웃바운드 Shared Private Link를 생성하면, 각 대상 리소스에서 연결 요청을 **승인**해야 합니다. Bicep 배포 후 약 5~10분 내에 승인이 가능해집니다.

### Storage Account 승인

```bash
# 연결 요청 목록 확인
az network private-endpoint-connection list \
    --name stragi<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --type Microsoft.Storage/storageAccounts

# 승인 (connection-name은 위 목록에서 확인)
az network private-endpoint-connection approve \
    --name <connection-name> \
    --resource-name stragi<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --type Microsoft.Storage/storageAccounts \
    --description "Approved for AI Search indexer"
```

### AI Services 승인

```bash
az network private-endpoint-connection approve \
    --name <connection-name> \
    --resource-name ais-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --type Microsoft.CognitiveServices/accounts \
    --description "Approved for AI Search skillset"
```

### Document Intelligence 승인

```bash
az network private-endpoint-connection approve \
    --name <connection-name> \
    --resource-name di-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --type Microsoft.CognitiveServices/accounts \
    --description "Approved for AI Search DI Layout skill"
```

### 승인 상태 확인

```bash
az search shared-private-link-resource list \
    --service-name search-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --query "[].{name:name, status:properties.status}" \
    --output table
```

모든 항목이 `Approved` 상태가 되면 AI Search 파이프라인 설정 스크립트를 실행할 수 있습니다.
