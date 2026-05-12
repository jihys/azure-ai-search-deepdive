# Azure RAG Indexing Lab - 실행 계획서

## 프로젝트 개요

**목표**: 한국 법령 데이터를 크롤링하고, Azure Logic Apps를 활용하여 전처리한 후, Azure AI Search 인덱스를 생성하는 End-to-End RAG 파이프라인 Hands-on Lab

**핵심 아키텍처**:
```
데이터 크롤링 → Blob Storage (날짜별 저장) → Logic Apps (전처리 워크플로우) → AI Search Index
     │                    │                         │                           │
  Python              날짜별 폴더            Doc Intelligence +           Vector Search +
  법령 크롤러         파일 업로드시           OpenAI Embedding             Hybrid Search
                     트리거 발동             Markdown/Table/Image
```

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
  --template-file infra/main.bicep \
  --parameters infra/parameters/main.bicepparam
```

### 파일 구조
```
infra/
├── main.bicep                    # 메인 오케스트레이션
├── modules/
│   ├── storage.bicep             # Storage Account + Blob Container
│   ├── openai.bicep              # Azure OpenAI + Embedding 모델 배포
│   ├── ai-search.bicep           # Azure AI Search 서비스
│   ├── doc-intelligence.bicep    # Document Intelligence
│   └── logic-app.bicep           # Logic App (Workflow Service Plan)
└── parameters/
    └── main.bicepparam           # 파라미터 파일
```

---

## Phase 2: 데이터 크롤링

### 크롤링 대상
- **소스**: 국가법령정보센터 (https://www.law.go.kr)
- **데이터**: 최근 개정 법령 목록 및 상세 내용
- **형식**: HTML → Markdown 변환 후 저장

### 크롤링 프로세스
1. `law.go.kr`에서 최근 개정 법령 목록 수집
2. 각 법령의 상세 내용 (본문, 부칙 등) 크롤링
3. Markdown 형태로 변환
4. **날짜별 폴더 구조**로 Blob Storage에 업로드
   ```
   raw-documents/
   ├── 2026-04-15/
   │   ├── law_001_민법개정안.md
   │   ├── law_002_상법개정안.md
   │   └── metadata.json
   ├── 2026-04-16/
   │   └── ...
   ```

### 파일 구조
```
src/
├── crawler/
│   ├── __init__.py
│   └── law_crawler.py           # 법령 크롤러 (requests + BeautifulSoup)
└── blob/
    ├── __init__.py
    └── uploader.py              # Blob Storage 업로더 (날짜별 폴더)
```

---

## Phase 3: Logic Apps 워크플로우

### 트리거 방식
- **Blob Trigger**: 새 파일이 Blob Storage에 업로드될 때 자동 실행
- **Schedule (대안)**: Recurrence trigger로 일정 주기(예: 매일 09:00) 실행

### 워크플로우 단계
```
1. Trigger: Blob 파일 감지 / 스케줄
     ↓
2. List Blobs: 미처리 파일 목록 조회
     ↓
3. For Each Document:
   a. Get Blob Content: 파일 내용 읽기
   b. Document Intelligence: 
      - Layout 분석 (Markdown layer)
      - 테이블 추출
      - 이미지 추출 + Verbalization (OpenAI GPT-4o)
   c. Chunking: 텍스트를 적절한 크기로 분할
   d. OpenAI Embedding: text-embedding-3-large로 벡터화
   e. Index to AI Search: 청크 + 벡터를 인덱스에 저장
     ↓
4. 완료 로그 기록
```

### Logic Apps 배포 방식
- **Option A**: Bicep으로 Logic App 리소스 + 워크플로우 JSON 배포
- **Option B**: Python SDK로 워크플로우 프로그래밍 방식 배포

### 참고 템플릿
- [Azure Logic Apps RAG Indexing Lab](https://azure.github.io/logicapps-labs/docs/ai-workloads-on-logicapps/automate-rag-indexing/)
- [Azure/logicapps AI-sample-demo](https://github.com/Azure/logicapps/tree/shahparth-lab-patch-2/AI-sample-demo)

### 파일 구조
```
logic-apps/
├── rag-indexing-workflow/
│   └── workflow.json            # Logic Apps 워크플로우 정의
├── connections.json             # 서비스 연결 설정
├── host.json                    # Logic Apps 호스트 설정
└── deploy_workflow.py           # Python을 통한 워크플로우 배포 스크립트
```

---

## Phase 4: AI Search 인덱스 구성

### 인덱스 스키마
| 필드명 | 타입 | 용도 |
|--------|------|------|
| `id` | Edm.String (Key) | 문서 청크 고유 ID |
| `documentName` | Edm.String | 원본 문서명 |
| `content` | Edm.String | 청크 텍스트 내용 |
| `embeddings` | Collection(Edm.Single) | 벡터 임베딩 (3072차원) |
| `category` | Edm.String | 법령 분류 |
| `crawledDate` | Edm.DateTimeOffset | 크롤링 날짜 |
| `sourceUrl` | Edm.String | 원본 법령 URL |
| `chunkIndex` | Edm.Int32 | 청크 순서 |

### 검색 기능
- **Vector Search**: HNSW 알고리즘 기반 벡터 검색
- **Hybrid Search**: 키워드 + 벡터 결합 검색
- **Semantic Ranker**: 의미 기반 재순위화

### 파일 구조
```
src/
├── preprocessing/
│   ├── __init__.py
│   ├── doc_intelligence.py      # Document Intelligence 처리
│   └── embedding.py             # OpenAI Embedding 생성
└── search/
    ├── __init__.py
    └── index_manager.py         # AI Search 인덱스 생성/관리
```

---

## Phase 5: Step-by-Step 노트북

### 노트북 목록
| 순서 | 파일명 | 내용 |
|------|--------|------|
| 1 | `01-infra-deployment.ipynb` | Bicep을 통한 인프라 배포 가이드 |
| 2 | `02-data-crawling.ipynb` | 법령 데이터 크롤링 및 Blob 업로드 |
| 3 | `03-logic-apps-setup.ipynb` | Logic Apps 워크플로우 설정 및 배포 |
| 4 | `04-search-and-query.ipynb` | AI Search 인덱스 쿼리 및 RAG 테스트 |

---

## 실행 순서 요약

```
Step 1: 환경 설정
  └─ uv venv 생성, 패키지 설치, .env 설정

Step 2: 인프라 배포 (Phase 1)
  └─ az deployment → RG, Storage, OpenAI, AI Search, Doc Intel, Logic App

Step 3: 데이터 크롤링 (Phase 2)
  └─ Python 크롤러 실행 → Blob Storage 날짜별 업로드

Step 4: Logic Apps 구성 (Phase 3)
  └─ 워크플로우 배포 → 자동 전처리 파이프라인 활성화

Step 5: 검색 테스트 (Phase 4)
  └─ AI Search 인덱스 쿼리 → RAG 기반 질의응답 테스트
```

---

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 패키지 관리 | uv |
| 크롤링 | requests, BeautifulSoup4 |
| 스토리지 | Azure Blob Storage |
| 전처리 | Azure Document Intelligence (Layout/Markdown) |
| 임베딩 | Azure OpenAI (text-embedding-3-large) |
| 검색 | Azure AI Search (Vector + Hybrid) |
| 워크플로우 | Azure Logic Apps (Workflow Service Plan) |
| 인프라 | Azure Bicep |
| 리전 | Korea Central |
