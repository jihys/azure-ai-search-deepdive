# PRD: 프로젝트 구조 정리 및 코드 중복 제거

**Status:** unspecified

## Problem Statement

Azure AI Search Deep Dive Lab 프로젝트에 중복된 데이터, 미사용 소스코드, 일관성 없는 모듈 구조가 누적되어 있다. `src/` 디렉토리의 12개 모듈 중 실제 사용되는 것은 1개뿐이고, `scripts/` 12개 중 노트북에서 호출되는 것은 2개뿐이다. 노트북은 `subprocess`로 스크립트를 호출하거나 REST API를 인라인으로 직접 호출하고 있어 코드 중복과 유지보수 부담이 크다. `data/` 디렉토리에는 9.4GB ZIP 파일, 0바이트 빈 파일, 불필요한 크롤링 샘플이 혼재되어 있다.

## Solution

`src/`를 **노트북 전용 라이브러리**로 재정의하고, 죽은 코드를 제거하며, 노트북이 `subprocess` 대신 `import`로 `src/` 모듈을 사용하도록 리팩터한다. 독립 배포 단위(`logic-apps/`, `skills-function/`)는 변경하지 않는다. 데이터 디렉토리를 정리하고, 리포트 파일을 `docs/reports/`로 이동한다.

## User Stories

1. As a 핸즈온 랩 참가자, I want `src/`에 실제 동작하는 코드만 있길, so that 불필요한 코드에 혼란받지 않고 학습에 집중할 수 있다.
2. As a 랩 참가자, I want 노트북에서 `import`로 파이프라인 기능을 호출하길, so that `subprocess` 호출의 에러 추적 어려움 없이 디버깅할 수 있다.
3. As a 랩 참가자, I want 인덱서 상태 폴링 코드가 한 곳에만 있길, so that nb03과 nb05에서 중복 코드를 보지 않아도 된다.
4. As a 랩 참가자, I want `notebooks/` 디렉토리에 `.ipynb` 파일만 있길, so that 어떤 노트북을 실행해야 하는지 한눈에 파악할 수 있다.
5. As a 프로젝트 관리자, I want 9.4GB ZIP 파일이 git에 추적되지 않길, so that 클론 시간이 합리적이다.
6. As a 프로젝트 관리자, I want 0바이트 빈 파일과 미사용 샘플 데이터가 없길, so that 프로젝트 상태가 깔끔하다.
7. As a 개발자, I want `scripts/`에 실제 사용되는 스크립트만 있길, so that 어떤 스크립트가 현행인지 고민하지 않아도 된다.
8. As a 개발자, I want 법률 파이프라인 설정 로직이 `src/pipeline/`에 모듈화되길, so that 노트북과 스크립트 양쪽에서 재사용할 수 있다.
9. As a 개발자, I want 멀티모달 파이프라인 설정 로직도 동일하게 모듈화되길, so that nb05에서 `import`로 호출할 수 있다.
10. As a 개발자, I want 리포트/실험 결과 파일이 `docs/reports/`에 모여있길, so that 문서를 한 곳에서 찾을 수 있다.
11. As a 개발자, I want `data/raw/*.pdf`가 멀티모달 테스트용으로 유지되길, so that 로컬에서 바로 테스트 가능하다.
12. As a 개발자, I want `logic-apps/`와 `skills-function/`이 독립 배포 단위로 유지되길, so that Azure Functions 배포 파이프라인이 깨지지 않는다.

## Implementation Decisions

### 1. `src/`의 역할: 노트북 전용 라이브러리

- `src/`는 **노트북에서 `import`하여 사용하는 코드만** 포함한다.
- 독립 배포 단위(`logic-apps/`, `skills-function/`)는 `src/`를 import하지 않고 자체 코드를 유지한다.
- Azure Functions은 배포 시 별도 패키징이 필요하므로 `src/`와의 의존성을 만들지 않는다.

### 2. `src/` 모듈 구조

**유지:**
- `src/search/legal_indexes.py` — 4개 법률 인덱스 스키마 정의 + 통합 검색 (nb03, nb04)
- `src/search/multimodal_index.py` — 멀티모달 인덱스 스키마 + 검색 (nb05, nb06)

**신규 생성:**
- `src/pipeline/legal_pipeline.py` — `scripts/setup_ai_search_pipeline.py`에서 핵심 로직 추출. 인덱스/스킬셋/데이터소스/인덱서 생성을 함수로 노출.
- `src/pipeline/multimodal_pipeline.py` — `scripts/setup_ai_search_multimodal_pipeline.py`에서 핵심 로직 추출.
- `src/pipeline/indexer_ops.py` — 인덱서 실행, 상태 폴링, 완료 대기 등 nb03/nb05 공용 유틸리티.

**삭제:**
- `src/blob/` 전체 (uploader.py — 미사용)
- `src/crawler/` 전체 (law_crawler.py, legal_data_generator.py, precedent_crawler.py — 미사용)
- `src/preprocessing/` 전체 (chunk_processor.py, legal_chunker.py, doc_intelligence.py, embedding.py, multimodal_processor.py — 미사용)
- `src/search/index_manager.py` (범용 베이스 — legal_indexes.py, multimodal_index.py가 독립적으로 동작하므로 불필요)

### 3. `scripts/` 정리

**삭제 완료 (10개, 4,515줄):**
- `reindex_all.py`, `reindex_with_metrics.py` — 파이프라인 래퍼, 노트북 미사용
- `seed_raw_documents.py`, `prepare_multimodal_raw_dataset.py`, `sample_zip_to_blob.py`, `bundle_seed_data.py`, `verify_crawl_preprocess.py` — 독립 도구, 노트북 미사용
- `run_cache_experiment.py`, `run_multimodal_cache_experiment.py`, `run_all_cache_experiments.py` — 캐싱 실험, 노트북 미사용

**삭제 완료 (2개):**
- `setup_ai_search_pipeline.py` — `src/pipeline/legal_pipeline.py`로 모듈화 후 삭제.
- `setup_ai_search_multimodal_pipeline.py` — `src/pipeline/multimodal_pipeline.py`로 모듈화 후 삭제.

### 4. 노트북 리팩터: `subprocess` → `import`

- nb03: `subprocess.run([..., "setup_ai_search_pipeline.py", ...])` → `from src.pipeline.legal_pipeline import create_pipeline`
- nb05: `subprocess.run([..., "setup_ai_search_multimodal_pipeline.py", ...])` → `from src.pipeline.multimodal_pipeline import create_pipeline`
- nb03/nb05 공통: 인덱서 상태 폴링 인라인 코드 → `from src.pipeline.indexer_ops import wait_for_indexer`

### 5. `data/` 정리

- `data/*.zip` (9.4GB) → `.gitignore`에 `data/*.zip` 추가, 로컬에만 유지
- `data/samples/` (0바이트 JSON 4개) → 삭제
- `data/raw/2026-04-15/`, `data/raw/2026-04-19/` (크롤링 샘플) → 삭제
- `data/raw/*.pdf` (테스트 PDF 2개) → 유지
- `data/processed/.gitkeep` → 유지

### 6. 리포트 파일 이동

`notebooks/`에서 `docs/reports/`로 이동:
- `cache_experiment_results.json`
- `full_experiment_results.json`
- `REPORT.md`
- `REPORT_CACHE.md`
- `REPORT_CACHE_MM.md`
- `multi-modal-report-v7.md`
- `multi-modal-report-en.md`

루트의 `multi-modal-report-en.md` → 삭제 (notebooks/ 버전과 중복)

### 7. 변경하지 않는 영역

- `logic-apps/` — 독립 배포 단위, 자체 코드 유지
- `skills-function/` — 독립 배포 단위, 자체 코드 유지
- `infra/` — Bicep IaC, 변경 없음

## Testing Decisions

이 PRD의 범위는 **구조 정리**이므로 새로운 테스트를 작성하지 않는다. 검증은 다음으로 수행:

- 각 노트북(01~06)이 정리 후에도 정상 실행되는지 순차적으로 확인
- `src/pipeline/` 모듈이 올바르게 import되는지 노트북 셀 실행으로 확인
- `.gitignore`가 ZIP 파일을 올바르게 제외하는지 `git status`로 확인

## Out of Scope

- `logic-apps/` 내부 코드 리팩터링 (독립 배포 단위)
- `skills-function/` 내부 코드 리팩터링 (독립 배포 단위)
- 노트북 내용(마크다운 설명, 학습 시나리오) 변경
- CI/CD 파이프라인 설정
- `infra/` Bicep 코드 변경
- `src/pipeline/` 모듈에 대한 단위 테스트 작성

## Further Notes

- `scripts/` 디렉토리는 모든 파일이 삭제되었으며, 파이프라인 로직은 `src/pipeline/`로 모듈화된다.
- git history에 삭제된 코드가 모두 보존되므로 필요 시 복구 가능.
- `data/*.zip` 파일의 다운로드 방법은 README에 별도 안내가 필요할 수 있다 (이 PRD 범위 밖).

---

## Execution Log

모든 실행 작업을 시간순으로 기록한다.

### 2026-05-28

#### ✅ 완료: scripts/ 미사용 스크립트 삭제 (10개)

노트북에서 호출되지 않는 스크립트 10개 삭제 (4,515줄):

```
rm scripts/reindex_all.py
rm scripts/reindex_with_metrics.py
rm scripts/seed_raw_documents.py
rm scripts/prepare_multimodal_raw_dataset.py
rm scripts/sample_zip_to_blob.py
rm scripts/bundle_seed_data.py
rm scripts/verify_crawl_preprocess.py
rm scripts/run_cache_experiment.py
rm scripts/run_multimodal_cache_experiment.py
rm scripts/run_all_cache_experiments.py
```

#### ✅ 완료: scripts/ 파이프라인 스크립트 삭제 (2개)

`src/pipeline/`로 모듈화 예정이므로 원본 스크립트 삭제 (1,446줄):

```
rm scripts/setup_ai_search_pipeline.py
rm scripts/setup_ai_search_multimodal_pipeline.py
```

`scripts/` 디렉토리는 이제 비어있음 (`__pycache__`만 잔존).

#### ✅ 완료: src/ 죽은 코드 삭제

`src/blob/`, `src/crawler/`, `src/preprocessing/`, `src/search/index_manager.py`, `__pycache__/` 삭제.
남은 모듈: `src/search/legal_indexes.py`, `src/search/multimodal_index.py`

#### ✅ 완료: data/ 정리

`data/samples/` 삭제, `data/raw/2026-04-15/`, `data/raw/2026-04-19/` 삭제.
`.gitignore`에 `data/*.zip` 이미 존재 확인. `data/raw/*.pdf`, `data/processed/.gitkeep` 유지.

#### ✅ 완료: 리포트 파일 이동

notebooks/ 리포트 7개 → `docs/reports/`로 이동. 루트 `multi-modal-report-en.md` 삭제.
`notebooks/`에는 `.ipynb` 파일만 남음.

#### ✅ 완료: src/pipeline/ 모듈 생성

- `src/pipeline/__init__.py` — 공개 API 재export
- `src/pipeline/indexer_ops.py` — SearchAdminClient + 인덱서 운영 유틸리티
- `src/pipeline/legal_pipeline.py` — 4개 법률 파이프라인 설정 (prec/detc/expc/admrul)
- `src/pipeline/multimodal_pipeline.py` — 3개 멀티모달 파이프라인 (pdf/pptx/verbalized)

#### ✅ 완료: 노트북 리팩터

- nb01 Cell 24: `subprocess.run(setup_ai_search_pipeline.py)` → `from src.pipeline import setup_legal_pipeline`
- nb01 Cell 28: `subprocess.run(setup_ai_search_multimodal_pipeline.py)` → `from src.pipeline import setup_multimodal_pipeline`
- nb03 Cell 10: `run_indexing()` 내 subprocess → `setup_legal_pipeline(run=True)` 직접 호출
- nb03 Cell 19: 실험 헬퍼 `run_setup()` → `setup_legal_pipeline()` + `SearchAdminClient` import
- nb05 Cell 3: 환경 설정 + `subprocess`/스크립트 참조 제거 → `src.pipeline` import
- nb05 Cell 8: 인덱서 확인 → `_client._headers()` 사용
- nb05 Cell 10: `run_indexer`/`wait_indexer` → `_pipeline_run_indexer` 위임
- nb05 Cell 19: 실험 헬퍼 `run_mm_setup()` → `setup_multimodal_pipeline()` 직접 호출
- nb05 Cell 20: 초기화 셀 → subprocess 제거, `setup_multimodal_pipeline()` 호출
