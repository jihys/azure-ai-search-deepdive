# Azure AI Search Deep Dive Lab - 통합 실행 계획서 (2026-05-13)

## 1. 문서 목적

이 문서는 현재 저장소 구조와 실제 운영 상태를 기준으로, 아래 2개 시나리오를 일관된 방식으로 실행하기 위한 최신 기준 계획이다.

- 시나리오 A: 법령/판례 데이터 크롤링 + 전처리 + 검색
- 시나리오 B: 멀티모달(PDF/PPTX) 데이터 인덱싱 + 검색

## 2. 현재 기준 아키텍처

### 2.1 전체 구조

- Stage 1 (데이터 수집/정규화): Logic Apps + Azure Functions
- Stage 2 (인덱싱/검색): Azure AI Search Indexer + Skillset

```text
[External Sources / Files]
    |
    +--> (A) law.go.kr -> Crawl Function -> raw/ -> Preprocess Function -> processed/
    |
    +--> (B) PDF/PPTX Upload -> raw/

[Blob Storage: data lake role]
    |
    +--> AI Search Data Source
            |
            +--> Skillset (Text Split, Embedding, 필요 시 Custom)
                    |
                    +--> Index (Vector + Semantic + Hybrid)
```

### 2.2 시나리오 A 논리 경계

- Crawling pipeline은 별도 로지컬 영역으로 분리한다.
- Logic App은 다음 순서를 오케스트레이션한다.
1. `crawl-function` 호출
2. `preprocess-function` 병렬 호출
3. 상태 집계 및 실패 처리

### 2.3 시나리오 B 논리 경계

- 수동 업로드 데이터(PDF/PPTX)를 기준으로 Native 파이프라인과 Custom 파이프라인을 비교한다.
- Custom 파이프라인은 필요 시 문서 변환/보강 단계를 추가한다.

## 3. 저장소 기준 컴포넌트 맵

- 인프라
  - `infra/sweden/main.bicep`
  - `infra/sweden/modules/*`
  - `infra/korea/main.bicep`
  - `infra/korea/modules/*`
- 워크플로우
  - `logic-apps/crawl-workflow/workflow.json`
  - `logic-apps/rag-indexing-workflow/workflow.json`
  - `logic-apps/crawl-preprocess-workflow/workflow.json`
- 함수 앱 코드
  - `logic-apps/crawl-function/*`
  - `logic-apps/preprocess-function/*`
- 검색 파이프라인 코드
  - `scripts/setup_ai_search_pipeline.py`
  - `scripts/setup_ai_search_multimodal_pipeline.py`
  - `src/search/*`
- 노트북
  - `notebooks/01-infra-deployment.ipynb`
  - `notebooks/02-data-crawling.ipynb`
  - `notebooks/03-search-and-query.ipynb`
  - `notebooks/04-legal-multi-index.ipynb`
  - `notebooks/05-multi-index-search.ipynb` (정리/퇴역 대상)
  - `notebooks/06-multimodal-search.ipynb` (시나리오 B 별도 단계)

## 4. 운영 기준 리소스 (Sweden)

현재 운영 기준은 Sweden 환경을 기본으로 한다.

- Resource Group: `rg-rag-indexing-lab-swc`
- Crawl Function App: `func-crawl-ragi-dyn6dtfu`
- Preprocess Function App: `func-preprocess-ragi-dyn6dtfu`
- Logic App: `logic-crawl-ragi-dyn6dtfu`
- Storage Account: `stragidyn6dtfun6`

주의:
- 함수 앱은 Python 3.11 런타임 기준으로 유지한다.
- 로컬 Python 버전과 함수 런타임 불일치는 경고만 발생할 수 있으나, 배포는 Remote Build를 기준으로 수행한다.

## 5. 실행 원칙

1. 배포명 대신 Azure 서비스명을 문서/다이어그램에 표기한다.
2. 이미 배포된 리소스는 기본적으로 재생성하지 않고, 필요한 경우에만 최소 범위로 재배포한다.
3. Stage 1 실패 시 Stage 2를 실행하지 않는다.
4. 파일 경로, 워크플로우명, 함수 엔드포인트는 실제 배포 상태와 일치해야 한다.

## 6. 단계별 실행 계획

### Phase A. 인프라 검증/배포

목표:
- 인프라 모듈 상태를 검증하고, 필요한 컴포넌트만 선택적으로 배포한다.

작업:
1. `infra/sweden/main.bicep` 기준 파라미터 확인
2. Function 관련 모듈 상태 확인
3. Logic App 관련 모듈 상태 확인
4. 변경분만 배포

완료 기준:
- Function/Logic App/Storage/Search/OpenAI 리소스 조회 성공
- 필수 App Settings 및 Managed Identity 권한 검증 완료

### Phase B. Stage 1 파이프라인 정상화

목표:
- `crawl -> preprocess` 연계가 엔드투엔드로 성공한다.

작업:
1. `logic-apps/crawl-function` Remote Build 배포
2. `logic-apps/preprocess-function` Remote Build 배포
3. Function 엔드포인트 응답 검증
4. Logic App 수동 실행
5. 액션별 결과 검증(특히 crawl 호출 단계)

완료 기준:
- `/api/crawl`가 NotFound(404)가 아니어야 함
- `/api/preprocess` 호출 성공
- Logic App 실행에서 crawl/preprocess 액션이 모두 성공

### Phase C. Stage 2 인덱싱 파이프라인 검증

목표:
- 데이터소스/스킬셋/인덱서/인덱스 구성의 유효성을 보장한다.

작업:
1. 법령 4개 인덱스 스키마 검증
2. 인덱서 실행 및 문서 유입 확인
3. 시맨틱/벡터 검색 품질 점검
4. 멀티모달 Native vs Custom 비교 검증

완료 기준:
- 목표 인덱스에 문서가 정상 적재
- 검색 쿼리 결과가 재현 가능

### Phase D. 노트북 정리 (01~04 우선 기준)

현재 기준 노트북 정리는 01~04를 우선 범위로 한다.

현재 상태 요약:
1. `01-infra-deployment.ipynb`: 일부 셀 실행됨, 후반부 오류 실행 이력 존재
2. `02-data-crawling.ipynb`: 미실행
3. `03-search-and-query.ipynb`: 미실행
4. `04-legal-multi-index.ipynb`: 미실행

실행 항목:
1. `01-infra-deployment.ipynb` 실행/오류 셀 정리 및 재실행 동선 고정
2. `02-data-crawling.ipynb`를 Stage 1 검증 흐름에 맞게 정리
3. `03-search-and-query.ipynb`를 단일 검색/질의 검증 흐름으로 정리
4. `04-legal-multi-index.ipynb`를 멀티 인덱스 통합 검증 흐름으로 정리
5. 01~04 전체 노트북 에러 검증

완료 기준:
- 01~04 각 노트북의 목적/입출력/검증 포인트가 명확히 분리됨
- 01~04 순차 실행 시 치명적 실행 에러 없음
- `05-multi-index-search.ipynb`는 중복 여부 검토 후 축소 또는 퇴역 결정

## 7. 워크플로우/함수 인터페이스 계약

### 7.1 Crawl Function

- Endpoint: `POST /api/crawl`
- 입력 최소 예시:

```json
{
  "source": "all",
  "triggered_by": "logic-app"
}
```

- 출력 요구사항:
  - 실행 성공/실패 상태
  - 소스별 처리 건수 또는 요약

### 7.2 Preprocess Function

- Endpoint: `POST /api/preprocess`
- 입력 최소 예시:

```json
{
  "source": "prec",
  "crawl_date": "2026-04-19",
  "triggered_by": "logic-app"
}
```

- 출력 요구사항:
  - 처리 파일 수
  - 실패 목록(있을 경우)

## 8. 검증 체크리스트

### 8.1 배포 검증

- Function App 2종 `Running`
- Logic App definition 최신 상태
- Storage 컨테이너 접근 권한 정상

### 8.2 기능 검증

- Crawl 단일 호출 성공
- Preprocess 단일 호출 성공
- Logic App 수동 1회 실행 성공
- 실패 액션 0건

### 8.3 데이터 검증

- raw 경로에 크롤링 산출물 생성
- processed 경로에 정규화 산출물 생성
- AI Search 인덱스 문서 카운트 증가

## 9. 리스크 및 대응

- 리스크: Function route 404 재발
  - 대응: 함수 메타데이터/라우트/배포 아티팩트 즉시 점검, Remote Build 재배포
- 리스크: Role assignment 충돌
  - 대응: 기존 role assignment 정리 후 모듈 재배포
- 리스크: 노트북과 실제 배포 상태 불일치
  - 대응: 노트북에 리소스 조회 셀을 기본 포함하여 선검증

## 10. 산출물 관리 원칙

- 문서, 다이어그램, 노트북은 동일한 서비스명/워크플로우명/엔드포인트를 사용한다.
- 레거시 파일은 즉시 삭제하지 않고, 운영 경로에서 제외 여부를 명시한다.
- 변경은 작은 단위로 검증 후 반영한다.

## 11. 최종 완료 정의 (Definition of Done)

아래를 모두 충족하면 본 계획 완료로 판단한다.

1. Stage 1: Logic App 기준 crawl + preprocess 연계 성공
2. Stage 2: 대상 인덱스 생성 및 데이터 적재 확인
3. 우선 범위 노트북(01~04) 정리 완료 및 실행 검증 통과
4. 문서/다이어그램/코드 기준 정보 일치
