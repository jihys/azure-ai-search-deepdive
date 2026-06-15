# 전체 노트북 순차 실행 검증

## Parent

[PRD-cleanup.md](../prd/PRD-cleanup.md)

## What to build

구조 정리와 리팩터 완료 후, 노트북 01~06을 순차적으로 실행하여 깨진 부분이 없는지 확인한다. 각 노트북이 정상적으로 셀 실행을 완료하고, `src/pipeline/` import가 올바르게 동작하는지 검증한다.

**검증 항목:**
- nb01 (infra): Bicep 배포 관련 셀 정상 실행 (이미 배포된 환경에서는 skip 가능)
- nb02 (crawling): 크롤링 Function 호출 셀 정상 실행
- nb03 (indexing): `src.pipeline.legal_pipeline` import + 파이프라인 생성 + 인덱서 폴링 정상 동작
- nb04 (search): `src.search.legal_indexes` 검색 정상 동작
- nb05 (mm-indexing): `src.pipeline.multimodal_pipeline` import + 파이프라인 생성 + 인덱서 폴링 정상 동작
- nb06 (mm-search): 멀티모달 검색 정상 동작
- `.gitignore`가 `data/*.zip`을 올바르게 제외하는지 `git status`로 확인

## Acceptance criteria

- [ ] nb01~nb06 각각 전체 셀 실행 시 에러 없음
- [ ] `src.pipeline` import가 nb01/nb03/nb05에서 정상 동작
- [ ] `git status`에서 `data/*.zip` 파일이 표시되지 않음
- [ ] `notebooks/` 디렉토리에 `.ipynb` 외 파일 없음

## Blocked by

- [0002-pipeline-module-and-notebook-refactor.md](./0002-pipeline-module-and-notebook-refactor.md)
