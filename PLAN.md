# Azure AI Search Deep Dive Lab - 실행 계획서

## 프로젝트 개요

**목표**: Azure AI Search의 핵심 기능을 **2개 실제 시나리오**로 데모하는 Hands-on Lab

| | 시나리오 A | 시나리오 B |
|--|------------|------------|
| **이름** | 법령 문서 인덱싱 | 멀티모달 PDF/PPTX 인덱싱 |
| **데이터** | law.go.kr 크롤링 (자동) | PDF/PPTX 수동 업로드 |
| **Stage 1** | Logic Apps 오케스트레이션 (Crawl + Data Integration) | Blob 업로드만 |
| **Stage 2** | AI Search Native Skillset (Text Split + Embedding) | Native Skillset vs Custom+Native Skillset 비교 |
| **인덱스** | 4개 (prec / detc / expc / admrul) | 2개 (native-index / custom-index) |
| **데모 포인트** | 증분 크롤링, High Water Mark, 멀티 인덱스 Cross-Search | Native vs GPT-5.4 Verbalization 검색 품질 비교 |

**핵심 아키텍처** — 2단계 파이프라인:
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Stage 1: CRAWLING + DATA INTEGRATION  (Logic Apps 관장)                 │
│                                                                         │
│  law.go.kr ──→ Crawl Function ──→ raw-documents/ (Blob)                 │
│                                       │                                 │
│                              Data Integration Function                  │
│                              (메타데이터 정규화, 포맷 통일)              │
│                                       │                                 │
│                              processed-documents/ (Blob)                │
└───────────────────────────────────────┬─────────────────────────────────┘
                                        │
┌───────────────────────────────────────▼─────────────────────────────────┐
│ Stage 2: SPLIT + EMBEDDING + INGEST  (AI Search 관장)                   │
│                                                                         │
│  processed-documents/ ──→ AI Search Indexer                             │
│                              │                                          │
│                     Skillset (Native + Custom)                          │
│                     ├─ [Native] Text Split Skill                        │
│                     ├─ [Native/Custom] Embedding Skill                  │
│                     └─ [Custom] Document Intelligence Skill (멀티모달)  │
│                              │                                          │
│                     AI Search Index (벡터 + 시맨틱 하이브리드)          │
└─────────────────────────────────────────────────────────────────────────┘
```

**총 인덱스**: 법령 텍스트 4개 + 멀티모달 2개 = **6개**

---

## Phase 1: 인프라 배포 (Bicep)

### 배포할 리소스 (Korea Central)
| 리소스 | 이름 패턴 | 용도 |
|--------|-----------|------|
| Resource Group | `rg-rag-indexing-lab` | 전체 리소스 그룹 |
| Storage Account | `stragindexinglab{suffix}` | Blob Storage - 크롤링 데이터 저장 |
| Azure OpenAI | `aoai-rag-indexing-lab` | text-embedding-3-large 모델 배포 |
| Azure AI Search | `search-rag-indexing-lab` | 벡터 인덱스 및 검색 |
| Document Intelligence | `di-rag-indexing-lab` | 문서 전처리 (OCR, Layout) |
| Logic App (Workflow) | `logic-rag-indexing-lab` | 데이터 전처리 워크플로우 |

### 배포 방법
```bash
# 1. Resource Group 생성
az group create --name rg-rag-indexing-lab --location koreacentral

# 2. Bicep 배포
az deployment group create \
  --resource-group rg-rag-indexing-lab \
  --template-file infra/sweden/main.bicep \
  --parameters infra/sweden/parameters/main.bicepparam
```

### 파일 구조
```
infra/
├── sweden/                       # Sweden Central 배포
│   ├── main.bicep                # 메인 오케스트레이션
│   ├── modules/
│   │   ├── storage.bicep         # Storage Account + Blob Container
│   │   ├── openai.bicep          # Azure OpenAI + Embedding 모델 배포
│   │   ├── ai-search.bicep       # Azure AI Search 서비스
│   │   ├── doc-intelligence.bicep # Document Intelligence
│   │   └── ...                   # 기타 모듈
│   └── parameters/
│       └── main.bicepparam       # Sweden Central 파라미터
│
└── korea/                        # Korea Central 배포
    ├── main.bicep                # 메인 (Korea Central + East US 2 DI)
    ├── modules/
    │   ├── storage.bicep         # Storage Account + Blob Container
    │   ├── openai.bicep          # Azure OpenAI + Embedding 모델 배포
    │   ├── ai-search.bicep       # Azure AI Search 서비스
    │   ├── doc-intelligence.bicep # Document Intelligence (East US 2)
    │   └── ...                   # 기타 모듈
    └── parameters/
        └── main.bicepparam       # Korea Central 파라미터
```

---

## Phase 2: Logic Apps 워크플로우 배포

> **역할**: Stage 1 전체 오케스트레이션 — 크롤링 + 데이터 통합(전처리)만 담당  
> Split/Embedding/Ingest는 AI Search가 자체적으로 처리 (Stage 2)

### 기본 1개의 워크플로우
1. **crawl-preprocess-workflow** (메인, 매일 06:00 KST)
   - Step 1: law.go.kr 크롤링 (모든 소스 병렬) → raw-documents/
   - Step 2: 데이터 통합 (4개 소스 병렬: prec, detc, expc, admrul)
     - 메타데이터 정규화, 소스별 포맷 통일
     - → processed-documents/ 저장 (AI Search Indexer 입력)
   - Step 3: 결과 수집 및 alert

> `crawl-workflow`, `rag-indexing-workflow`는 레거시/디버그용으로 저장소에만 유지하며 기본 운영/배포에서는 사용하지 않습니다.

### 배포
```bash
uv run python logic-apps/deploy_workflow.py
```

---

## Phase 3: 데이터 크롤링 Function

### 크롤링 Function
- **URI**: `func-crawl-ragi` (Azure Function App)
- **트리거**: HTTP POST (Logic App에서 호출)
- **입력**:
  ```json
  {
    "source": "all" | "prec" | "detc" | "expc" | "admrul",
    "max_pages": 0,
    "detail_workers": 5,
    "triggered_by": "logic-app-crawl-preprocess"
  }
  ```
- **저장 경로**: `raw-documents/{source}/{YYYY-MM-DD}/`

### 파일 구조
```
logic-apps/crawl-function/
├── function_app.py              # 크롤링 Function 메인 로직
├── precedent_crawler.py         # 4개 소스별 크롤러 (병렬 처리)
├── requirements.txt
├── host.json
└── local.settings.json.example
```

---

## Phase 4: 데이터 통합(Data Integration) Function

> **중요**: 텍스트 분할(Split)은 여기서 하지 않음 → AI Search Skillset이 처리

### 데이터 통합 Function
- **URI**: `func-preprocess-ragi` (Azure Function App)
- **트리거**: HTTP POST (Logic App에서 호출, 4개 소스 병렬)
- **입력**:
  ```json
  {
    "source": "prec" | "detc" | "expc" | "admrul",
    "crawl_date": "2026-04-19",
    "triggered_by": "logic-app-crawl-preprocess"
  }
  ```
- **처리 단계**:
  1. `raw-documents/{source}/{crawl_date}/` JSON 파일 읽기
  2. 소스별 필드 정규화 (필드명 통일, 날짜 포맷, null 처리)
  3. AI Search Indexer가 읽을 수 있는 형태로 변환
  4. `processed-documents/{source}/{crawl_date}/{file_id}.json` 저장

> **Split/Embedding은 AI Search가 담당**: Indexer가 processed-documents를 읽어 Text Split Skill → Embedding Skill 순서로 처리

### 파일 구조
```
logic-apps/preprocess-function/
├── function_app.py              # 데이터 통합 Function 메인 로직
├── requirements.txt
├── host.json
└── local.settings.json.example

src/preprocessing/
├── __init__.py
├── doc_intelligence.py          # Document Intelligence 처리 (멀티모달)
└── embedding.py                 # (참조용) Embedding 설정
```

---

## Phase 5: Logic Apps 오케스트레이션 워크플로우

> **Stage 1 전체를 담당** — 크롤링 + 데이터 통합만. Split/Embedding/Ingest는 AI Search Stage 2.

### 워크플로우: crawl-preprocess-workflow
- **트리거**: Recurrence (매일 06:00 KST)
- **Step 1**: 모든 소스 병렬 크롤링 (Crawl Function)
- **Step 2**: 4개 소스 병렬 데이터 통합 (Data Integration Function)
- **Step 3**: 최종 결과 로깅 + 에러 알림

### 워크플로우 단계
```
[Daily Schedule: 06:00 KST]
    │
    ▼
┌──────────────────────────────────────────┐
│ Step 1: CRAWLING (All Sources)           │
│ HTTP POST: /api/crawl                    │
│ body: { "source": "all" }                │
│ → raw-documents/{source}/{date}/         │
└──────────────────────────────────────────┘
    │
    ├─ SUCCESS? ──────────────────────┐
    │                                 │
    │              ┌──────────────────▼──────────────────────┐
    │              │ Step 2: DATA INTEGRATION (Parallel)     │
    │              │ ├─ POST /api/preprocess (prec)          │
    │              │ ├─ POST /api/preprocess (detc)          │
    │              │ ├─ POST /api/preprocess (expc)          │
    │              │ └─ POST /api/preprocess (admrul)        │
    │              │ → processed-documents/{source}/{date}/  │
    │              └──────────────────┬──────────────────────┘
    │                                 │
    │              ┌──────────────────▼──────────┐
    │              │ Step 3: Log Results         │
    │              └─────────────────────────────┘
    │
    └─ FAILURE? ──────────────────┐
                                  │
                         ┌────────▼────────────┐
                         │ Send Alert Email    │
                         │ (SendGrid)          │
                         └─────────────────────┘

※ Split + Embedding + Ingest는 AI Search Indexer가 별도 스케줄로 처리
```

### 파일 구조
```
logic-apps/
├── crawl-preprocess-workflow/
│   └── workflow.json            # 새로운 통합 워크플로우 ⭐
├── crawl-workflow/
│   └── workflow.json            # 기존 크롤링 워크플로우 (유지)
├── rag-indexing-workflow/
│   └── workflow.json            # 기존 인덱싱 워크플로우
├── connections.json             # 서비스 연결 설정
├── host.json                    # Logic Apps 호스트 설정
└── deploy_workflow.py           # 워크플로우 배포 스크립트 (수정됨)
```

---

## Phase 6: AI Search 인덱싱 (Stage 2)

> **Stage 2 전체를 AI Search가 담당**: Indexer가 Blob에서 읽어 Skillset(Split+Embedding) 실행 후 Index에 저장

### 총 6개 인덱스

#### 법령 텍스트 인덱스 (4개) — processed-documents/ 소스
| 인덱스명 | 소스 | 설명 |
|---------|------|------|
| `prec-court-index` | prec | 판례 (대법원, 각급 법원) |
| `const-court-index` | detc | 헌재 결정례 |
| `legis-interp-index` | expc | 법제처 해석례 |
| `admin-appeal-index` | admrul | 행정심판 재결례 |

**Skillset (법령 텍스트 공통)**:
```
processed-documents/{source}/{date}/*.json
    │
    ▼ [Native] Text Split Skill
    │  (maximumPageLength: 2000, pageOverlapLength: 200)
    ▼ [Native] AzureOpenAIEmbeddingSkill
    │  (text-embedding-3-large, 3072차원)
    ▼ AI Search Index (vector + semantic hybrid)
```

#### 멀티모달 인덱스 (2개) — PDF 수동 업로드 소스
| 인덱스명 | Skillset 구성 | 설명 |
|---------|-------------|------|
| `{source}-multimodal-native-index` | Native only | Text Split + Embedding (비교 기준) |
| `{source}-multimodal-custom-index` | Custom + Native | DI Layout → Custom Verbalize → Split + Embedding |

**Native-only Skillset**:
```
raw/pdf/{source}/*.pdf
    │
    ▼ [Native] DocumentIntelligenceLayoutSkill → Markdown
    ▼ [Native] Text Split Skill (markdown mode)
    ▼ [Native] AzureOpenAIEmbeddingSkill
    ▼ {source}-multimodal-native-index
```

**Custom + Native Skillset**:
```
raw/pdf/{source}/*.pdf
    │
    ▼ [Native] DocumentIntelligenceLayoutSkill → Markdown
    ▼ [Custom WebApi] Verbalize Skill (GPT-5.4 이미지/도표 설명 생성)
    ▼ [Native] Text Split Skill (markdown mode)
    ▼ [Native] AzureOpenAIEmbeddingSkill
    ▼ {source}-multimodal-custom-index
```

### 인덱싱 설정 스크립트
```bash
# 법령 텍스트 4개 인덱스 (prec/detc/expc/admrul)
uv run python scripts/setup_ai_search_pipeline.py --run

# 멀티모달 2개 인덱스 (native / custom+native 비교)
uv run python scripts/setup_ai_search_multimodal_pipeline.py --source {source} --run-indexer
```

### 파일 구조
```
scripts/
├── setup_ai_search_pipeline.py             # 법령 텍스트 4개 인덱스 설정
├── setup_ai_search_multimodal_pipeline.py  # 멀티모달 2개 인덱스 설정
└── prepare_multimodal_raw_dataset.py       # PDF 업로드 전 데이터 준비

src/search/
├── __init__.py
├── index_manager.py         # 인덱스/스킬셋/인덱서 생성 관리
└── legal_indexes.py         # 법령 텍스트 인덱스 스키마 정의
```

---

## Phase 7: Step-by-Step 노트북

### 공통 준비
| 순서 | 파일명 | 내용 |
|------|--------|------|
| 1 | `01-infra-deployment.ipynb` | Bicep 배포 + Function App 배포 + Shared PL 승인 + Logic Apps 배포 + AI Search 설정 |

### 시나리오 A: 법령 문서 인덱싱
| 순서 | 파일명 | 내용 |
|------|--------|------|
| 2 | `02-data-crawling.ipynb` | Logic App 크롤-통합 트리거 + 인덱서 모니터링 + Blob 결과 검증 |
| 3 | `03-indexing.ipynb` | 인덱싱 샘플 실행 및 필요 시 전체 인덱스 삭제 + 인덱서 실행 |
| 4 | `04-search-and-query.ipynb` | AI Search 하이브리드 검색 + GPT-5.4 RAG 질의응답 |
| 5 | `05-multi-index-search.ipynb` | 멀티 인덱스 통합 검색 및 Cross-Index RAG |

### 시나리오 B: 멀티모달 PDF/PPTX 인덱싱
| 순서 | 파일명 | 내용 |
|------|--------|------|
| 6 | `06-multimodal-search.ipynb` | PDF Blob 업로드 → Native vs Custom+Native Skillset 비교 → 멀티모달 검색 데모 |

---

## 실행 순서 요약

```
Step 1: 환경 설정
  ├─ uv venv 생성, 패키지 설치
  ├─ .env 설정 (Azure 구독, 리소스 이름 등)
  └─ Bicep CLI, Azure Functions Core Tools 설치

Step 2: 인프라 배포 (Phase 1)
  ├─ Resource Group 생성
  ├─ Storage, AI Services, AI Search, DI 등 배포
  └─ Private Network 구성 (VNet, PE, Private DNS Zone)

Step 3: Function App 배포 (Phase 3, 4)
  ├─ Crawl Function 코드 배포 (logic-apps/crawl-function/)
  ├─ Data Integration Function 코드 배포 (logic-apps/preprocess-function/)
  └─ VNet Integration 확인

Step 4: Logic App 워크플로우 배포 (Phase 5)
  ├─ crawl-preprocess-workflow 배포
  ├─ crawl-workflow 배포
  ├─ 연결 설정 (Storage, HTTP)
  └─ 트리거 활성화 (매일 06:00 KST)

Step 5: Stage 1 실행 — 크롤링 + 데이터 통합
  ├─ Logic App 수동 실행 (초기 Full Build)
  ├─ raw-documents/ 확인 (크롤링 결과)
  ├─ processed-documents/ 확인 (데이터 통합 결과)
  └─ 실패 로그 분석

Step 6: Stage 2 설정 — AI Search 인덱싱 (Phase 6)
  ├─ [법령 4개] setup_ai_search_pipeline.py 실행
  │   Index + Skillset(Text Split + Embedding) + DataSource + Indexer 생성
  ├─ [멀티모달 2개] PDF를 Blob에 수동 업로드
  │   setup_ai_search_multimodal_pipeline.py 실행
  │   (native-only 인덱스 + custom+native 인덱스 비교)
  └─ 초기 인덱서 Full Build 실행 (--run)

Step 7: 검색 테스트 (Phase 7)
  ├─ Vector Search 테스트
  ├─ Hybrid Search 테스트
  └─ RAG 쿼리 테스트

Step 8: 자동화 스케줄 활성화
  ├─ Logic App 스케줄 확인
  └─ 모니터링 설정 (실패 알림)
```

---

## 배포 의존성

```
┌─────────────────┐
│ Bicep (Phase 1) │ ← 먼저 실행
└────────┬────────┘
         │
         ▼
┌──────────────────────────┐
│ Crawl Function           │ ← Phase 3 배포
│ Data Integration Function│   (Phase 4)
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────┐
│ Logic App Workflows  │ ← Phase 5 배포
│ (Connections 포함)   │
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ AI Search Indexers   │ ← Phase 6 배포
└──────────────────────┘
```

---

## 초기 빌드 vs 증분 업데이트

### 초기 빌드 (첫 실행)
```
[Stage 1 - Logic Apps]
Logic App 수동 실행 → 크롤링 (1-2시간) → 데이터 통합 (30분)
→ processed-documents/ 생성 완료

[Stage 2 - AI Search]
setup_ai_search_pipeline.py --run → Indexer Full Build (20분)
  └─ Skillset: Text Split → Embedding → Index 저장
```

### 증분 업데이트 (일별 자동)
```
[Stage 1 - Logic Apps, 매일 06:00 KST]
Logic App 스케줄 실행 → 크롤링 (10-30분) → 데이터 통합 (5분)
→ processed-documents/{오늘날짜}/ 추가

[Stage 2 - AI Search, 별도 스케줄]
Indexer 증분 실행 → lastModified 기준 신규 파일만 처리
  └─ Skillset: Text Split → Embedding → Index 추가
```

### 구현 방식
- `raw-documents/`: 날짜별 폴더 (2026-04-19/, 2026-04-20/) — 크롤링 원본
- `processed-documents/`: 날짜별 폴더 (동일) — AI Search Indexer 입력
- **Stage 1 증분**: Logic App이 매일 신규 날짜 폴더에만 쓰기
- **Stage 2 증분**: AI Search Indexer `metadata_storage_last_modified` High Water Mark

---

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 패키지 관리 | uv |
| 크롤링 (시나리오 A) | requests, BeautifulSoup4 |
| 스토리지 | Azure Blob Storage |
| 문서 분석 (시나리오 B) | Azure Document Intelligence (Layout/Markdown) |
| 임베딩 | Azure OpenAI (text-embedding-3-large) |
| 검색 | Azure AI Search (Vector + Hybrid + Semantic) |
| 온케스트레이션 (시나리오 A) | Azure Logic Apps (Standard) |
| 이미지 Verbalization (시나리오 B) | Azure OpenAI GPT-5.4 Vision |
| 인프라 | Azure Bicep |
| 리전 | Sweden Central |
