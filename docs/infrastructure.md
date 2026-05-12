# 인프라 상세 설명

> **리전**: Sweden Central (`swedencentral`) / Korea Central (`koreacentral`)  
> **Sweden Central**: DI, OpenAI, AI Search 모두 지원하는 단일 리전 배포  
> **Korea Central**: Document Intelligence가 미지원이므로 East US 2에 별도 배포 + Cross-Region PE  
> **네트워크**: 모든 리소스가 Private Network(VNet + Private Endpoints) 전용 구성  
> **Bicep 구조**: `infra/sweden/` 및 `infra/korea/` 리전별 분리

---

## 목차

1. [배포되는 Azure 리소스 전체 목록](#1-배포되는-azure-리소스-전체-목록)
2. [네트워크 아키텍처](#2-네트워크-아키텍처)
3. [각 리소스 상세 설명](#3-각-리소스-상세-설명)
4. [RBAC 권한 구성](#4-rbac-권한-구성)
5. [파이프라인 구성 (Logic App → 크롤 + 인덱서 트리거)](#5-파이프라인-구성-logic-app--크롤--인덱서-트리거)
6. [인덱싱 파이프라인 (AI Search Skills)](#6-인덱싱-파이프라인-ai-search-skills)
7. [배포 순서 및 의존성](#7-배포-순서-및-의존성)
8. [Bicep 파일 구조](#8-bicep-파일-구조)
9. [Function App 코드 배포](#9-function-app-코드-배포)
10. [Private Network 접근 방법](#10-private-network-접근-방법)
11. [Shared Private Link 승인 절차](#11-shared-private-link-승인-절차)

---

## 1. 배포되는 Azure 리소스 전체 목록

### Sweden Central (단일 리전)

| # | 리소스 타입 | 이름 패턴 | SKU | 용도 |
|---|------------|-----------|-----|------|
| 1 | Resource Group | `rg-rag-indexing-lab-swc` | - | 모든 리소스 컨테이너 |
| 2 | Virtual Network | `vnet-ragi-<suffix>` | - | 프라이빗 네트워크 격리 |
| 3 | Network Security Group | `nsg-pep-ragi-<suffix>` | - | PE 서브넷 보안 규칙 |
| 4 | Storage Account | `stragi<suffix>` | Standard LRS | 원본 문서 및 처리 결과 저장 |
| 5 | Blob Container | `raw-documents` | - | 크롤링된 원본 문서 (PDF, MD) |
| 6 | Blob Container | `processed-documents` | - | 처리 완료 문서 / 추출 이미지 보관 |
| 7 | Azure AI Services | `ais-ragi-<suffix>` | S0 | OpenAI GPT-5.4 + Embedding 통합 |
| 8 | Model Deployment | `gpt-5.4` | GlobalStandard 30K | 이미지 Verbalization + RAG 질의응답 |
| 9 | Model Deployment | `text-embedding-3-large` | Standard 120K | 3072차원 벡터 임베딩 |
| 10 | Document Intelligence | `di-ragi-<suffix>` | S0 | PDF/문서 레이아웃 분석 → Markdown |
| 11 | Azure AI Search | `search-ragi-<suffix>` | **Standard (S1)** | 벡터+시맨틱 하이브리드 검색 |
| 12 | App Service Plan | `asp-crawl-ragi-<suffix>` | EP1 (Elastic Premium) | Function App 호스팅 플랜 (VNet integration 지원) |
| 13 | Function App | `func-crawl-ragi-<suffix>` | Python 3.11 / Linux | 크롤러 + GPT-5.4 Verbalization + Markdown Split |
| 14 | Logic App | `logic-crawl-index-ragi-<suffix>` | Consumption | 크롤 + 인덱서 트리거 스케줄러 (매일 21:00 UTC) |
| 15 | JumpVM | `jumpvmragi01` | Standard_B2s_v2 (Windows) | VNet 내부에서 PE 리소스 접근 |
| 16 | Private Endpoint (Storage) | `pe-blob-ragi-<suffix>` | - | VNet → Storage 프라이빗 접근 |
| 17 | Private Endpoint (Search) | `pe-search-ragi-<suffix>` | - | VNet → AI Search 프라이빗 접근 |
| 18 | Private Endpoint (AI Services) | `pe-aiservices-ragi-<suffix>` | - | VNet → AI Services 프라이빗 접근 |
| 19 | Private Endpoint (Doc Intel) | `pe-docintel-ragi-<suffix>` | - | VNet → Doc Intelligence 프라이빗 접근 |
| 20 | Private DNS Zone | `privatelink.blob.core.windows.net` | - | Storage PE DNS 해석 |
| 21 | Private DNS Zone | `privatelink.search.windows.net` | - | AI Search PE DNS 해석 |
| 22 | Private DNS Zone | `privatelink.cognitiveservices.azure.com` | - | AI Services / DI PE DNS 해석 |
| 23 | Private DNS Zone | `privatelink.openai.azure.com` | - | AI Services OpenAI 엔드포인트 DNS |
| 24 | Shared Private Link | `spl-blob` (Search→Storage) | - | AI Search 인덱서 아웃바운드 접근 |
| 25 | Shared Private Link | `spl-aiservices` (Search→AI Svc) | - | Embedding Skill 아웃바운드 접근 |
| 26 | Shared Private Link | `spl-docintel` (Search→DI) | - | DI Layout Skill 아웃바운드 접근 |

> `<suffix>`는 구독 ID + RG 이름으로 생성되는 고유 8자리 해시

### Korea Central (2개 리전)

| # | 리소스 타입 | 이름 패턴 | 리전 | SKU | 용도 |
|---|------------|-----------|------|-----|------|
| 1 | Resource Group | `rg-rag-indexing-lab-krc` | Korea Central | - | 메인 리소스 컨테이너 |
| 2 | Resource Group | `rg-rag-indexing-lab-eus2` | East US 2 | - | Doc Intelligence 전용 (Korea 미지원) |
| 3 | Virtual Network | `vnet-ragi-<suffix>` | Korea Central | - | 프라이빗 네트워크 격리 |
| 4 | Storage Account | `stragi<suffix>` | Korea Central | Standard LRS | 원본 문서 및 처리 결과 저장 |
| 5 | Azure AI Services | `ais-ragi-<suffix>` | Korea Central | S0 | OpenAI GPT-5.4 + Embedding 통합 |
| 6 | Document Intelligence | `di-ragi-<suffix>` | **East US 2** | S0 | PDF/문서 레이아웃 분석 |
| 7 | Azure AI Search | `search-ragi-<suffix>` | Korea Central | **Standard (S1)** | 벡터+시맨틱 하이브리드 검색 |
| 8 | Function App | `func-crawl-ragi-<suffix>` | Korea Central | EP1 | 크롤러 + Verbalization + Markdown Split |
| 9 | Logic App | `logic-crawl-ragi-<suffix>` | Korea Central | Consumption | 크롤 스케줄러 |
| 10 | JumpVM | `jumpvmragi01` | Korea Central | Standard_B2s_v2 | VNet 내부에서 PE 리소스 접근 |
| 11 | Private Endpoint (Storage) | `pe-blob-ragi-<suffix>` | Korea Central | - | VNet → Storage |
| 12 | Private Endpoint (Search) | `pe-search-ragi-<suffix>` | Korea Central | - | VNet → AI Search |
| 13 | Private Endpoint (AI Svc) | `pe-aiservices-ragi-<suffix>` | Korea Central | - | VNet → AI Services |
| 14 | Private Endpoint (Doc Intel) | `pe-docintel-ragi-<suffix>` | Korea Central | - | **Cross-Region** VNet → East US 2 Doc Intelligence |
| 15 | AI Foundry Hub | `hub-ragi-<suffix>` | Korea Central | Basic | AI Foundry 허브 (BYO VNet) |
| 16 | Key Vault | `kv-ragi-<suffix>` | Korea Central | Standard | Foundry Hub 종속 |

> **Korea Central 특이사항**: Document Intelligence는 Korea Central에서 지원되지 않으므로 East US 2에 별도 Resource Group으로 배포합니다. Korea Central VNet에서 East US 2 DI로의 접근은 **Cross-Region Private Endpoint**로 처리됩니다.

---

## 2. 네트워크 아키텍처

### Sweden Central

```
외부 인터넷 (공개)
    │
    │  law.go.kr (법령 데이터)
    │         ▲ 크롤링 (HTTP GET)
    │         │
    │  [Logic App - 매일 21:00 UTC]
    │  HTTP POST → func-crawl-ragi.azurewebsites.net/api/crawl
    │  ↓ 크롤 성공 시 → AI Search Indexer 트리거 (3개)
    │
    ├─────────▼─────────────────────────────────────────────┐
    │  Azure Function App (func-crawl-ragi)                 │
    │  공개 인바운드: HTTPS /api/crawl, /api/verbalize,     │
    │                      /api/markdown_split              │
    │  아웃바운드: VNet Integration (snet-func)             │
    └────────────────────────┬──────────────────────────────┘
                             │ VNet 아웃바운드
                             ▼
┌────────────────────────────────────────────────────────────┐
│  Virtual Network: vnet-ragi (10.0.0.0/16)                  │
│  Location: Sweden Central                                   │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  snet-jump (10.0.0.0/24) - JumpVM 서브넷             │  │
│  │  Windows VM (jumpvmragi01) — PE 접근용 관리자 VM      │  │
│  │  접근: Public IP + RDP (운영 시 Azure Bastion 권장)   │  │
│  └──────────────────────────────────────────────────────┘  │
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
  Verbalize: AI Search → Custom WebApiSkill → Function (공개 HTTPS) → GPT-5.4
  쿼리:   JumpVM (snet-jump) → snet-pep → pe-search-ragi → AI Search
```

### Korea Central (Cross-Region DI)

Korea Central은 Sweden Central과 동일한 VNet 구조를 사용하지만, **Document Intelligence만 East US 2**에 배포됩니다.

```
┌────────────────────────────────────────────────────────────┐
│  Resource Group: rg-rag-indexing-lab-krc (Korea Central)    │
│                                                            │
│  VNet: vnet-ragi (10.0.0.0/16) ─ Korea Central             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  snet-pep (10.0.1.0/24) — Private Endpoints           │ │
│  │                                                        │ │
│  │  ● pe-blob       → Storage (Korea Central)             │ │
│  │  ● pe-search     → AI Search (Korea Central)           │ │
│  │  ● pe-aiservices → AI Services (Korea Central)         │ │
│  │  ● pe-docintel   → Doc Intelligence (East US 2)  ←─┐  │ │
│  │                                    Cross-Region PE  │  │ │
│  └─────────────────────────────────────────────────────┘  │ │
│                                                            │
│  AI Search → [spl-docintel] → DI (East US 2)  ←── SPL     │
│                                                            │
└────────────────────────────────────────────────────────────┘
        │                                          │
        │ Cross-Region PE                          │ Cross-Region SPL
        ▼                                          ▼
┌────────────────────────────────────────────────────────────┐
│  Resource Group: rg-rag-indexing-lab-eus2 (East US 2)      │
│                                                            │
│  Document Intelligence: di-ragi-<suffix>                   │
│  Kind: FormRecognizer | SKU: S0                            │
│  publicNetworkAccess: Disabled                             │
└────────────────────────────────────────────────────────────┘
```

> **Cross-Region PE**: Korea Central VNet의 `snet-pep`에 생성된 Private Endpoint가 East US 2의 DI에 연결됩니다. Azure Private Link는 리전 간 연결을 지원하므로 정상 동작합니다.
> **Cross-Region SPL**: AI Search Managed VNet도 리전 간 Shared Private Link를 지원합니다.

---

## 3. 각 리소스 상세 설명

### 3.1 Virtual Network (`vnet-ragi`)

| 항목 | 값 |
|------|-----|
| 주소 공간 | `10.0.0.0/16` |
| 서브넷 1 | `snet-jump` (`10.0.0.0/24`) — JumpVM (관리자 VM) |
| 서브넷 2 | `snet-pep` (`10.0.1.0/24`) — Private Endpoint 전용 |
| 서브넷 3 | `snet-func` (`10.0.2.0/24`) — Function App VNet Integration 전용 |
| snet-pep 설정 | `privateEndpointNetworkPolicies: Disabled` (PE 필수 설정) |
| snet-func 설정 | Delegation: `Microsoft.Web/serverFarms` (Function App 아웃바운드 전용) |

Private DNS Zone 4개가 이 VNet에 연결되어, VNet 내부에서 프라이빗 IP로 각 서비스에 접근합니다.

---

### 3.2 JumpVM (`jumpvmragi01`)

| 항목 | Sweden Central | Korea Central |
|------|---------------|---------------|
| SKU | Standard_B2s_v2 | Standard_B2s_v2 |
| OS | Windows 11 Pro (24H2) | Windows 11 Pro (24H2) |
| 서브넷 | `snet-jump` (10.0.0.0/24) | `snet-jump` (10.0.0.0/24) |
| computerName | `jumpvm` | `jumpvmkrc` |
| 접근 | Public IP + RDP (3389) | Public IP + RDP (3389) |
| 인증 | Entra ID Login (AADLoginForWindows) | Entra ID Login (AADLoginForWindows) |
| RBAC | Virtual Machine Administrator Login | Virtual Machine Administrator Login |

**자동 설치 도구 (Chocolatey):**
- Visual Studio Code
- Git (Git Bash 포함)
- GitHub CLI (gh)
- Azure CLI
- Python 3.x

> **운영 환경 권장**: Azure Bastion 사용 또는 NSG로 소스 IP 제한
> **computerName 차이**: Entra ID 디바이스 등록 충돌 방지를 위해 리전별로 다릅니다.

---

### 3.3 Storage Account (`stragi<suffix>`)

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
- `raw-documents`: Python 크롤러가 업로드하는 원본 법령 문서 + PDF
- `processed-documents`: 추출 이미지(.png) 및 처리 완료 데이터

---

### 3.4 Azure AI Services (`ais-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| Kind | `AIServices` (OpenAI + Cognitive Services 통합) |
| SKU | S0 |
| 공개 네트워크 | **비활성화** |
| 인증 | Managed Identity (RBAC), 키 인증 차단 |

**배포된 모델:**

| 모델 | 배포명 | 타입 | TPM | 용도 |
|------|--------|------|-----|------|
| `gpt-5.4` | `gpt-5.4` | GlobalStandard | 30K | **이미지 Verbalization + RAG 질의응답** |
| `text-embedding-3-large` | `text-embedding-3-large` | Standard | 120K | 3072D 벡터 생성 |

---

### 3.5 Document Intelligence (`di-ragi<suffix>`)

| 항목 | Sweden Central | Korea Central |
|------|---------------|---------------|
| Kind | `FormRecognizer` | `FormRecognizer` |
| SKU | S0 | S0 |
| **배포 리전** | **Sweden Central** (동일 리전) | **East US 2** (별도 RG) |
| **Resource Group** | `rg-rag-indexing-lab-swc` | `rg-rag-indexing-lab-eus2` |
| 공개 네트워크 | 비활성화 | 비활성화 |
| VNet 접근 | 동일 리전 PE | **Cross-Region PE** (Korea → EUS2) |
| 사용 모델 | `prebuilt-layout` | `prebuilt-layout` |

**prebuilt-layout 모델 기능:**
- PDF, DOCX, PPTX, 이미지(JPG/PNG/TIFF)에서 텍스트 + Figure 추출
- 표(Table) 구조 보존 → Markdown 테이블 변환
- 섹션 헤더 인식 → 계층 구조 보존
- 출력 형식: Markdown (`outputContentFormat: markdown`)

> **Korea Central 미지원**: Document Intelligence는 Korea Central 리전에서 제공되지 않아 East US 2에 별도 배포합니다. Korea Central VNet에서는 Cross-Region Private Endpoint로 접근하며, AI Search의 Shared Private Link도 Cross-Region SPL로 정상 동작합니다.

---

### 3.6 Azure AI Search (`search-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| SKU | **Standard (S1)** |
| Replicas | 1 |
| Partitions | 1 |
| Semantic Search | Standard (포함) |
| 공개 네트워크 | **비활성화** |
| Identity | System Assigned Managed Identity |

**AI Search 파이프라인 구성 (스크립트로 설정):**

| 파이프라인 | Data Source | Index | Skillset | Indexer |
|-----------|------------|-------|----------|---------|
| 법령 텍스트 | `law-blob-datasource` | `law-documents-index` | `law-rag-skillset` | `law-blob-indexer` |
| 멀티모달 Basic | `<src>-raw-pdf-datasource` | `<src>-multimodal-basic-index` | `<src>-multimodal-basic-skillset` | `<src>-multimodal-basic-indexer` |
| 멀티모달 Verbalized | `<src>-raw-pdf-datasource` | `<src>-multimodal-verbalized-index` | `<src>-multimodal-verbalized-skillset` | `<src>-multimodal-verbalized-indexer` |

**Shared Private Links (아웃바운드):**

| 이름 | 대상 | GroupId | 용도 |
|------|------|---------|------|
| `spl-blob` | Storage Account | `blob` | 인덱서가 Blob에서 문서 읽기 |
| `spl-aiservices` | AI Services | `cognitiveservices_account` | Embedding Skill API 호출 |
| `spl-docintel` | Doc Intelligence | `account` | DI Layout Skill 호출 |

> Shared Private Link는 AI Search가 자체 Managed VNet에서 Private Endpoint를 생성하여 아웃바운드 연결을 맺는 방식입니다. 배포 후 **대상 리소스에서 승인 필요** (섹션 10 참조).

---

### 3.7 Azure Function App (`func-crawl-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| 플랜 | Elastic Premium EP1 (1 vCore, 3.5GB RAM) |
| 런타임 | Python 3.11 / Linux |
| VNet Integration | `snet-func` (10.0.2.0/24) — 아웃바운드 전용 |
| 인바운드 | 공개 HTTPS |
| 인증 | Function Key 또는 MI |
| Storage 접근 | Managed Identity (`AzureWebJobsStorage__credential: managedidentity`) |

**제공하는 HTTP Trigger:**

| 엔드포인트 | 용도 | 호출자 |
|-----------|------|--------|
| `/api/crawl` | law.go.kr 법령 크롤링 → Blob 업로드 | Logic App |
| `/api/verbalize` | GPT-5.4 Vision 이미지 Verbalization | AI Search (Custom WebApiSkill) |
| `/api/markdown_split` | Markdown 헤더 기반 텍스트 분할 | AI Search (Custom WebApiSkill) |

**EP1 플랜 선택 이유:**
Consumption Plan은 VNet Integration을 지원하지 않아 Private Storage PE로의 아웃바운드 접근이 불가능합니다. EP1은 VNet Integration을 지원하며, Function App이 `snet-func`를 통해 VNet 내부 라우팅으로 Storage Private Endpoint에 접근합니다.

---

### 3.8 Logic App (`logic-crawl-index-ragi<suffix>`)

| 항목 | 값 |
|------|-----|
| 플랜 | Consumption (서버리스) |
| 스케줄 | 매일 21:00 UTC (= 한국 06:00 KST) |
| 트리거 | Recurrence (일별 반복) |
| Identity | System Assigned Managed Identity |

**워크플로우 흐름:**

```
[Recurrence 트리거 - 매일 21:00 UTC]
    │
    ▼
[Step 1] HTTP POST → Function App /api/crawl
    body: { "limit": 10, "triggered_by": "logic-apps-pipeline" }
    auth: ManagedServiceIdentity
    retryPolicy: { count: 3, interval: PT1M }
    │
    ▼
[Step 2] Check_New_Data (total_uploaded > 0 ?)
    │
    ├─ YES → [Step 3a] Run_Law_Indexer (POST /indexers/law-blob-indexer/run)
    │         [Step 3b] Run_Basic_Indexer (POST /indexers/st-multimodal-basic-indexer/run)
    │         [Step 3c] Run_Verbalized_Indexer (POST /indexers/st-multimodal-verbalized-indexer/run)
    │         auth: ManagedServiceIdentity (audience: https://search.azure.com)
    │
    └─ NO  → Skip_Indexing (로그만 기록)
    │
    ▼
[Step 4] Log_Pipeline_Result
```

> Logic App은 **크롤 + 인덱서 트리거**만 담당합니다. 실제 인덱싱(DI Layout → Skill → Embedding → 인덱스)은 AI Search Indexer가 수행합니다.

---

### 3.9 Private Endpoints

각 서비스에 대해 VNet의 `snet-pep` 서브넷에 Private Endpoint가 생성됩니다.

| PE 이름 | 대상 서비스 | GroupId | DNS Zone |
|---------|------------|---------|----------|
| `pe-blob-ragi` | Storage Account | `blob` | `privatelink.blob.core.windows.net` |
| `pe-search-ragi` | AI Search | `searchService` | `privatelink.search.windows.net` |
| `pe-aiservices-ragi` | AI Services | `account` | `privatelink.cognitiveservices.azure.com` + `privatelink.openai.azure.com` |
| `pe-docintel-ragi` | Doc Intelligence | `account` | `privatelink.cognitiveservices.azure.com` |

---

## 4. RBAC 권한 구성

모든 서비스 간 접근은 Managed Identity + RBAC으로 구성됩니다 (API 키 사용 없음).

| 주체 | 대상 리소스 | 역할 | 용도 |
|------|------------|------|------|
| Function App (MI) | Storage Account | Storage Blob Data Contributor | 크롤러가 Blob에 문서 쓰기 |
| Function App (MI) | Storage Account | Storage Queue Data Contributor | Functions 런타임 큐 접근 |
| Function App (MI) | Storage Account | Storage Table Data Contributor | Functions 런타임 테이블 접근 |
| AI Search (MI) | Storage Account | Storage Blob Data Reader | 인덱서가 문서 읽기 |
| AI Search (MI) | AI Services | Cognitive Services User | Embedding/DI Skill 호출 |
| Logic App (MI) | AI Search | Search Index Data Reader | 인덱서 실행 트리거 |
| Logic App (MI) | Function App | - | MSI 인증 크롤 호출 |
| JumpVM | (수동) | 개발자 역할 | PE 리소스 접근 테스트 |

---

## 5. 파이프라인 구성 (Logic App → 크롤 + 인덱서 트리거)

전체 데이터 처리 오케스트레이션:

```
[Logic App - logic-crawl-index-ragi]
매일 21:00 UTC (= 한국 06:00 KST)
    │
    │ ① HTTP POST (MSI 인증)
    ▼
[Function App - func-crawl-ragi]
    │ law.go.kr DRF API → Blob Storage 업로드
    │ (VNet Integration → PE → Storage)
    │
    │ 크롤 결과: { total_uploaded: N }
    ▼
[Logic App - 신규 데이터 확인]
    │
    ├─ N > 0 → ② AI Search Indexer 트리거 (3개 순차)
    │           POST /indexers/{name}/run (MSI 인증)
    │           → law-blob-indexer
    │           → st-multimodal-basic-indexer
    │           → st-multimodal-verbalized-indexer
    │
    └─ N = 0 → 스킵 (로그만 기록)
```

**중요 구분:**
- **Logic App**: 스케줄링 + 크롤 트리거 + 인덱서 실행 트리거 (오케스트레이터)
- **Function App**: 크롤러 코드 실행 + GPT-5.4 Verbalization + Markdown Split (워커)
- **AI Search Indexer**: 실제 인덱싱 파이프라인 실행 (DI Layout → Skill → Embedding → 인덱스)

---

## 6. 인덱싱 파이프라인 (AI Search Skills)

AI Search Indexer가 실행하는 3가지 파이프라인입니다. 모든 파이프라인은 **AI Search 내부에서 실행**됩니다.

### Pipeline A: Basic (Native SplitSkill — Function App 불필요)

```
Blob Storage (raw/pdf/<source>/)
    │  AI Search Indexer
    │  ← Shared Private Link (spl-blob)
    ▼
[Skill 1] #Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill
    ├─ 입력: file_data (PDF 바이너리)
    ├─ 처리: prebuilt-layout → Markdown 변환
    └─ 출력: markdown_document (전체 Markdown 텍스트)
    │
    ▼
[Skill 2] #Microsoft.Skills.Text.SplitSkill (네이티브)
    ├─ textSplitMode: "markdown"
    ├─ maximumPageLength: 2000
    ├─ pageOverlapLength: 200
    └─ 출력: pages[] (Markdown 구조 인식 청크)
    │
    ▼
[Skill 3] #Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill
    ├─ 입력: 각 page 텍스트
    ├─ 처리: text-embedding-3-large (3072D)
    └─ 출력: content_vector
    │
    ▼
AI Search Index (<source>-multimodal-basic-index)
```

### Pipeline B: Verbalized (Custom WebApiSkill — Function App 필요)

```
Blob Storage (raw/pdf/<source>/)
    │  AI Search Indexer
    │  ← Shared Private Link (spl-blob)
    ▼
[Skill 1] #Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill
    ├─ 출력: markdown_document
    │
    ▼
[Skill 2] #Microsoft.Skills.Custom.WebApiSkill (verbalize)
    ├─ URI: func-crawl-ragi.../api/verbalize
    ├─ 처리: GPT-5.4 Vision으로 이미지/도표 → 풍부한 자연어 설명
    └─ 출력: verbalized_markdown
    │
    ▼
[Skill 3] #Microsoft.Skills.Custom.WebApiSkill (markdown_split)
    ├─ URI: func-crawl-ragi.../api/markdown_split
    ├─ 처리: Markdown 헤더 기반 분할
    └─ 출력: pages[]
    │
    ▼
[Skill 4] #Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill
    ├─ 처리: text-embedding-3-large (3072D)
    └─ 출력: content_vector
    │
    ▼
AI Search Index (<source>-multimodal-verbalized-index)
```

### 네이티브 이미지 스킬 vs GPT-5.4 Verbalization

| 스킬 | @odata.type | 기능 | 한계 |
|------|------------|------|------|
| **ImageAnalysisSkill** | `#Microsoft.Skills.Vision.ImageAnalysisSkill` | AI Vision 4.0 caption/tags | 단순 캡션, 도면 의미 파악 불가 |
| **OcrSkill** | `#Microsoft.Skills.Vision.OcrSkill` | 이미지 내 텍스트 추출 | 텍스트만, 구조 설명 없음 |
| **VectorizeSkill** | `#Microsoft.Skills.Vision.VectorizeSkill` | 이미지 → 벡터 | 자연어 설명 없음, RAG 인용 불가 |

> **GPT-5.4 Verbalization이 필요한 이유**: 네이티브 ImageAnalysisSkill은 "a chart showing data" 수준이지만, GPT-5.4는 "이 단선도는 154kV 변전소의 전력 계통을 나타내며, 변압기(TR-1, 154/22.9kV, 45MVA)를 거쳐..." 수준의 풍부한 기술적 설명을 생성합니다. 복잡한 도면/다이어그램의 RAG 검색에는 GPT-5.4 Verbalization이 필수입니다.

---

## 7. 배포 순서 및 의존성

```
1. Resource Group
   │
2. VNet + Private DNS Zones + NSG (병렬 가능)
   │
3. Storage + AI Services + Doc Intelligence (병렬 가능)
   │
4. AI Search (Storage, AI Services, DI ID 참조)
   │
5. Function App EP1 Plan + Function App (VNet, Storage 참조)
   Logic App (Function URL, AI Search 엔드포인트 참조)
   JumpVM (snet-jump 서브넷 참조)
   │
6. Private Endpoints (모든 서비스 ID 참조)
   │
7. [코드 배포] crawl-function/ → Function App (섹션 8)
   │
8. [수동] Shared Private Link 승인 (섹션 10)
   │
9. [스크립트] AI Search 파이프라인 설정
   (setup_ai_search_multimodal_pipeline.py)
```

Bicep 1~6단계는 단일 `az deployment sub create` 명령으로 자동 처리됩니다.

---

## 8. Bicep 파일 구조

Bicep 템플릿은 리전별로 분리되어 `infra/sweden/`과 `infra/korea/` 디렉토리에 배치됩니다.

```
infra/
├── sweden/                           # Sweden Central 배포
│   ├── main.bicep                    # 메인 오케스트레이션 (subscription scope)
│   ├── main.json                     # ARM 변환 결과
│   ├── modules/
│   │   ├── vnet.bicep                # VNet + Private DNS Zones + NSG
│   │   ├── private-endpoints.bicep   # 모든 서비스 Private Endpoints
│   │   ├── storage.bicep             # Storage Account (Private)
│   │   ├── openai.bicep              # AI Services + 모델 배포
│   │   ├── ai-search.bicep           # AI Search + Shared Private Links
│   │   ├── ai-search-spl.bicep       # SPL 초회 배포 전용 (별도 실행)
│   │   ├── doc-intelligence.bicep    # Document Intelligence (Same Region)
│   │   ├── foundry-hub.bicep         # AI Foundry Hub (Optional)
│   │   ├── function-crawler.bicep    # Function App EP1 + VNet Integration
│   │   ├── jumpvm.bicep              # JumpVM (Windows 11, snet-jump)
│   │   ├── logic-app-crawl-index.bicep # Logic App Consumption
│   │   └── logic-storage.bicep       # Logic App 전용 Storage
│   └── parameters/
│       └── main.bicepparam           # Sweden Central 파라미터
│
└── korea/                            # Korea Central 배포
    ├── main.bicep                    # 메인 (Korea Central + East US 2 DI)
    ├── main.json                     # ARM 변환 결과
    ├── modules/
    │   ├── vnet.bicep                # VNet + Private DNS Zones (snet-jump: 10.0.3.0/24)
    │   ├── private-endpoints.bicep   # PE (Cross-Region DI PE 포함)
    │   ├── storage.bicep             # Storage Account (Private)
    │   ├── openai.bicep              # AI Services + 모델 배포
    │   ├── ai-search.bicep           # AI Search + Shared Private Links
    │   ├── doc-intelligence.bicep    # Document Intelligence (East US 2 별도 RG)
    │   ├── foundry-hub.bicep         # AI Foundry Hub (Optional)
    │   ├── function-crawler.bicep    # Function App EP1 + VNet Integration
    │   └── jumpvm.bicep              # JumpVM (Windows 11, snet-jump)
    └── parameters/
        └── main.bicepparam           # Korea Central 파라미터
```

### 배포 명령

```bash
# Sweden Central 배포
az deployment sub create \
    --location swedencentral \
    --template-file infra/sweden/main.bicep \
    --parameters infra/sweden/parameters/main.bicepparam \
    --parameters jumpvmAdminPassword='<password>' \
    --parameters jumpvmEntraUserObjectIds='["<object-id>"]'

# Korea Central 배포
az deployment sub create \
    --location koreacentral \
    --template-file infra/korea/main.bicep \
    --parameters infra/korea/parameters/main.bicepparam \
    --parameters jumpvmAdminPassword='<password>' \
    --parameters jumpvmEntraUserObjectIds='["<object-id>"]'
```

### 리전별 주요 차이점

| 항목 | Sweden Central | Korea Central |
|------|---------------|---------------|
| **Resource Group** | 1개 (`rg-rag-indexing-lab-swc`) | 2개 (`rg-rag-indexing-lab-krc` + `rg-rag-indexing-lab-eus2`) |
| **Document Intelligence** | 동일 리전 배포 (Sweden Central) | East US 2 별도 RG + **Cross-Region PE** |
| **DI Private Endpoint** | 동일 리전 PE | Cross-Region PE (Korea→EUS2) |
| **JumpVM computerName** | `jumpvm` | `jumpvmkrc` (Entra ID 충돌 방지) |
| **Logic App** | Consumption (크롤+인덱서 오케스트레이션) | Consumption (크롤 스케줄러) |
| **Foundry Hub RBAC** | 플랫폼 자동 생성 (Bicep 미포함) | 플랫폼 자동 생성 (Bicep 미포함) |
| **OpenAI 파라미터** | `gptDeploymentName`, `gptModelName`, `gptModelVersion` | 동일 |
| **GPT 모델** | gpt-5.4 GlobalStandard 30K TPM | 동일 (리전 무관 글로벌 배포) |
| **Embedding 모델** | text-embedding-3-large Standard 120K TPM | 동일 |

> **핵심 원칙**: Document Intelligence 배포 리전을 제외하면 양 리전의 Bicep 모듈은 **동일**합니다. 주석과 computerName만 의도적으로 다릅니다.

---

## 9. Function App 코드 배포

Bicep으로 Function App 인프라를 배포한 후, 크롤러 + 스킬 코드(`crawl-function/`)를 Function App에 배포합니다.

### Azure Functions Core Tools 사용

```bash
cd crawl-function
func azure functionapp publish func-crawl-ragi-<suffix> --python
```

### Azure CLI ZIP 배포 사용

```bash
cd crawl-function
zip -r ../func-crawl.zip .

# Sweden
az functionapp deployment source config-zip \
    --name func-crawl-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --src ../func-crawl.zip

# Korea
az functionapp deployment source config-zip \
    --name func-crawl-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-krc \
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

---

## 10. Private Network 접근 방법

모든 서비스가 `publicNetworkAccess: Disabled`이므로, 개발자는 다음 방법으로 접근합니다.

### 옵션 A: JumpVM (현재 배포됨)

```bash
# RDP로 JumpVM 접속 (Public IP)
# Windows 11 VM이 snet-jump (10.0.0.0/24)에 위치
# VNet 내부이므로 PE 리소스에 직접 접근 가능

# JumpVM 내에서 AI Search API 테스트
curl https://search-ragi-<suffix>.search.windows.net/indexes?api-version=2024-11-01-preview
```

### 옵션 B: 임시 Public Access 허용 (데모/개발용)

```bash
# 설정 스크립트 실행 전 임시 허용
az search service update \
    --name search-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --public-network-access enabled

# 스크립트 실행
uv run python scripts/setup_ai_search_multimodal_pipeline.py

# 다시 비활성화
az search service update \
    --name search-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --public-network-access disabled
```

---

## 11. Shared Private Link 승인 절차

AI Search가 아웃바운드 Shared Private Link를 생성하면, 각 대상 리소스에서 연결 요청을 **승인**해야 합니다.

### Storage Account 승인

```bash
az network private-endpoint-connection list \
    --name stragi<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --type Microsoft.Storage/storageAccounts

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
# Sweden (동일 리전)
az network private-endpoint-connection approve \
    --name <connection-name> \
    --resource-name di-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-swc \
    --type Microsoft.CognitiveServices/accounts \
    --description "Approved for AI Search DI Layout skill"

# Korea (Cross-Region — East US 2 RG)
az network private-endpoint-connection approve \
    --name <connection-name> \
    --resource-name di-ragi-<suffix> \
    --resource-group rg-rag-indexing-lab-eus2 \
    --type Microsoft.CognitiveServices/accounts \
    --description "Approved for AI Search DI Layout skill (Cross-Region)"
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
