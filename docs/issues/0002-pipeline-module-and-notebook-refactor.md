# src/pipeline/ 모듈 생성 + 노트북 리팩터

**Status**: done
**Parent**: [PRD-cleanup.md](../prd/PRD-cleanup.md)

## What to build

삭제된 `scripts/setup_ai_search_pipeline.py`와 `setup_ai_search_multimodal_pipeline.py`의 핵심 로직을 `src/pipeline/`로 모듈화하고, 노트북의 `subprocess` 호출을 `import`로 교체한다. 인덱서 상태 폴링 코드를 공용 유틸로 추출하여 nb03/nb05 중복을 제거한다.

**src/pipeline/ 모듈 생성:**
- `src/pipeline/__init__.py`
- `src/pipeline/indexer_ops.py` — 인덱서 실행(`run`), 상태 폴링(`get_status`), 완료 대기(`wait_for_indexer`) 등 공용 유틸. REST API 기반. nb03/nb05가 공유.
- `src/pipeline/legal_pipeline.py` — 4개 법률 소스별 AI Search 파이프라인(인덱스/스킬셋/데이터소스/인덱서) 생성. `setup_ai_search_pipeline.py`에서 추출.
- `src/pipeline/multimodal_pipeline.py` — Basic/Verbalized 멀티모달 파이프라인 생성. `setup_ai_search_multimodal_pipeline.py`에서 추출.

**노트북 리팩터:**
- nb01: 파이프라인 설정 `subprocess` 호출을 `from src.pipeline import ...`으로 교체
- nb03: 법률 파이프라인 설정 + 인덱서 폴링 인라인 코드를 `src.pipeline` import로 교체
- nb05: 멀티모달 파이프라인 설정 + 인덱서 폴링 인라인 코드를 `src.pipeline` import로 교체

원본 스크립트 로직은 git history에 보존됨 (삭제 완료 상태).

## Acceptance criteria

- [x] `src/pipeline/indexer_ops.py` 존재하고, 인덱서 실행·폴링·대기 함수 제공
- [x] `src/pipeline/legal_pipeline.py` 존재하고, 4개 법률 파이프라인 생성 함수 제공
- [x] `src/pipeline/multimodal_pipeline.py` 존재하고, Basic/Verbalized 파이프라인 생성 함수 제공
- [x] nb01에서 `subprocess` 호출 없이 `src.pipeline` import로 파이프라인 설정 가능
- [x] nb03에서 `subprocess` 호출 없이 `src.pipeline` import로 파이프라인 설정 + 인덱서 폴링 가능
- [x] nb05에서 `subprocess` 호출 없이 `src.pipeline` import로 파이프라인 설정 + 인덱서 폴링 가능
- [x] nb03과 nb05의 인덱서 폴링 코드가 `indexer_ops.py`를 공유 (중복 없음)

## Blocked by

- [0001-file-cleanup.md](./0001-file-cleanup.md)
