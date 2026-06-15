---
name: notebook-lab-fixer
description: "Fix errors in notebook-based hands-on labs. Use when: running notebook cells fails; diagnosing and fixing notebook errors; executing hands-on lab step-by-step; applying fixes to source origin (src/, infra/, scripts/) instead of one-off workarounds; re-running cells after fix; pre-checking environment and dependencies before cell execution."
argument-hint: "Notebook number or cell to run (e.g., '03', '04 cell 5', 'all from 01')"
---

# Notebook Lab Fixer

순서대로 노트북 셀을 실행하고, 에러 발생 시 **원본 위치에 수정을 적용**하는 스킬.
일회성 우회(workaround)를 최소화하고, 재현 가능한 수정을 보장한다.

## When to Use

- 노트북 기반 핸즈온랩을 순서대로 실행할 때
- 셀 실행 중 에러가 발생해 원인 분석과 수정이 필요할 때
- 수정사항을 노트북이 아닌 원본 소스(src/, infra/, scripts/)에 적용해야 할 때
- 실행 전 환경/의존성 점검이 필요할 때

## Core Principle: Fix at Origin

```
에러 발생 → 근본 원인 파악 → 원본 파일에 수정 적용 → 셀 재실행으로 검증
```

수정 적용 우선순위:

| 우선순위 | 수정 위치 | 조건 |
|---------|----------|------|
| 1 | `src/` 모듈 | 노트북이 import하는 모듈의 버그인 경우 |
| 2 | `infra/` Bicep 파일 | 인프라 리소스 설정 문제인 경우 |
| 3 | `scripts/` 스크립트 | subprocess로 호출하는 스크립트 문제인 경우 |
| 4 | `.env` / 환경 설정 | 환경변수 누락/오류인 경우 |
| 5 | 노트북 셀 코드 | 셀 자체의 로직 에러인 경우 (import 경로, API 호출 등) |
| 6 | `requirements.txt` | 패키지 버전 호환성 문제인 경우 |

**절대 하지 않는 것:**
- 노트북 셀에서 try/except로 에러를 삼키는 우회
- 하드코딩된 값으로 임시 대체
- 원본 파일 대신 노트북 셀에 중복 함수 작성

## Procedure

### Phase 0: Pre-flight Check (셀 실행 전)

대상 노트북을 열기 전에 환경을 점검한다.

1. **환경변수 확인**:
   - `.env` 파일 존재 여부 확인
   - 노트북의 첫 번째 코드 셀(또는 마크다운 셀)에서 `os.environ["..."]`, `os.getenv("...")`,
     `AZURE_*` 패턴을 파싱하여 해당 노트북에 필요한 환경변수 목록을 동적으로 추출
   - 추출한 키가 `.env`에 모두 존재하고 빈 값이 아닌지 점검
   - 누락된 키가 있으면 `sample.env`와 비교하여 안내
2. **의존성 확인**: `requirements.txt`의 패키지가 설치되어 있는지 점검
3. **Azure 인증 확인**: `az account show`로 로그인 상태 확인
4. **커널 상태 확인**: 노트북 커널이 반드시 `.venv` 가상환경을 사용하는지 확인
   - Python 경로: `.venv/bin/python` (Python 3.13)
   - 터미널 명령 실행 시에도 `source .venv/bin/activate` 로 활성화 후 사용
   - `.venv`가 아닌 다른 환경(venv, conda base 등)이 활성화되어 있으면 전환
5. **이전 노트북 완료 여부**: 노트북 번호가 순서대로 실행되는 구조이므로, 이전 번호의 노트북이 이미 실행 완료되었는지 확인

### Phase 1: Cell Execution (셀 실행)

1. `copilot_getNotebookSummary`로 노트북 구조 파악
2. 마크다운 셀의 설명을 읽어 각 셀의 목적 이해
3. 셀을 **순서대로** 실행 (`run_notebook_cell`)
4. 각 셀 실행 후 `read_notebook_cell_output`으로 결과 확인
5. 성공한 셀은 다음으로 진행, 에러 발생 시 Phase 2로 이동

### Phase 2: Error Diagnosis (에러 진단)

에러 발생 시 다음 순서로 근본 원인을 분석한다:

1. **에러 메시지 정독**: 전체 traceback을 읽고 에러 유형 분류
   - `ImportError` / `ModuleNotFoundError` → 패키지 또는 경로 문제
   - `EnvironmentError` / `KeyError(os.environ)` → 환경변수 누락
   - `HttpResponseError` / `ResourceNotFoundError` → Azure 리소스 문제
   - `ValidationError` / `TypeError` → 코드 로직/API 변경 문제
   - `AuthenticationError` → 인증/권한 문제

2. **원인 위치 추적**: 에러가 발생한 코드가 어디서 온 것인지 추적
   ```
   traceback의 파일 경로 확인:
   - src/*.py → src/ 모듈 수정
   - scripts/*.py → scripts/ 수정
   - 셀 내부 (<ipython-input>) → 셀 코드 수정
   - Azure API 응답 → infra/ 또는 .env 점검
   ```

3. **Fix-at-Origin 판단**: [수정 우선순위 표]를 참고해 수정 위치 결정

### Phase 3: Fix Application (수정 적용)

1. **수정 대상 파일 읽기**: 수정할 파일의 현재 내용을 반드시 먼저 확인
2. **최소 범위 수정**: 에러를 해결하는 최소한의 변경만 적용
3. **수정 적용**:
   - `.py` 파일: `replace_string_in_file` 또는 `multi_replace_string_in_file`
   - `.bicep` 파일: 동일하게 파일 수정 도구 사용
   - `.ipynb` 파일: `edit_notebook_file` 사용 (주의: 전체 셀 내용을 newCode로 제공)
   - `.env` 파일: 수정 전 사용자에게 값 확인 요청
4. **수정 검증**: `get_errors`로 구문 오류 없는지 확인

> **노트북 셀 편집 주의사항**: `edit_notebook_file`은 작은 oldCode/newCode 쌍으로 편집 시
> 셀 전체가 newCode로 잘릴 수 있다. 항상 전체 셀 내용을 oldCode/newCode로 제공하거나,
> `replace_string_in_file`로 .ipynb JSON을 직접 편집한다.

### Phase 3.5: Repeated Pattern Check (반복 패턴 공통화)

같은 수정 패턴이 여러 노트북에 걸쳐 반복되는 경우를 감지한다:

1. 현재 수정한 코드 패턴이 다른 노트북(01~06)에도 존재하는지 `grep_search`로 확인
2. **3회 이상** 동일 패턴이 반복되면:
   - `src/`에 공통 유틸리티 함수/클래스 추출을 **제안** (자동 적용하지 않음)
   - 제안 시 어떤 노트북의 어떤 셀에서 반복되는지 목록 제시
   - 사용자 승인 후에만 리팩토링 적용
3. 2회 이하이면 각 노트북에서 개별 수정

### Phase 4: Verification (검증)

1. **수정된 셀 재실행**: 에러가 발생했던 셀을 다시 실행
2. **후속 셀 실행**: 수정이 후속 셀에 영향을 미치지 않는지 확인
3. **결과 확인**: `read_notebook_cell_output`으로 출력이 정상인지 검증

### Phase 5: Session Recording (기록)

수정 사항을 세션 메모리에 기록한다:

```
/memories/session/lab-fixes.md에 기록:
- 날짜/시간
- 노트북 번호와 셀 번호
- 에러 유형과 메시지 (요약)
- 수정한 파일과 변경 내용 (요약)
- Fix-at-Origin 여부 (원본 수정 vs 셀 수정)
```

## Decision Tree: Where to Fix

```
에러 발생
│
├─ traceback에 src/*.py 경로가 있는가?
│  └─ YES → src/ 모듈 수정
│
├─ traceback에 scripts/*.py 경로가 있는가?
│  └─ YES → scripts/ 수정
│
├─ Azure API 에러인가? (HttpResponseError, 404, 403 등)
│  ├─ 리소스가 존재하지 않음 → infra/ Bicep 확인 & 배포
│  ├─ 권한 부족 → infra/ 역할 할당 확인
│  └─ 설정값 불일치 → .env 또는 infra/parameters/ 확인
│
├─ Import/패키지 에러인가?
│  ├─ src/ 모듈 import 실패 → sys.path 또는 __init__.py 확인
│  └─ 외부 패키지 없음 → requirements.txt에 추가 & 설치
│
└─ 위 모두 아님 → 셀 코드 자체 수정
```

## Project-Specific Context

이 워크스페이스의 노트북 구조:

| 노트북 | 목적 | 주요 의존성 |
|--------|------|------------|
| 01-infra-deployment | Bicep 인프라 배포 | `infra/`, Azure CLI |
| 02-data-crawling | Logic App 크롤링 검증 | Azure Blob, Logic App |
| 03-indexing | AI Search 인덱스 생성 | `src/search/legal_indexes.py` |
| 04-search-and-query | 검색 기법 테스트 + RAG | `src/search/`, OpenAI |
| 05-multimodal-indexing | 멀티모달 인덱싱 | `src/preprocessing/`, `scripts/` |
| 06-multimodal-search | 멀티모달 검색 + RAG | `src/search/multimodal_index.py` |

공통 패턴:
- 모든 노트북: `sys.path.insert(0, os.path.abspath('..'))` 으로 root에서 import
- 모든 노트북: `load_dotenv('../.env')` 로 환경변수 로드
- 인증: `AzureCliCredential(tenant_id=...)` 사용
