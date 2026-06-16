# 0012 — Custom Skill 참조 제거 + 노트북 정리

**Status**: done
**Parent**: [PRD-builtin-skills.md](../prd/PRD-builtin-skills.md)

## What to build

Custom Skill이 더 이상 사용되지 않으므로 관련 참조를 모두 제거한다.

**`setup_multimodal_pipeline()` 변경:**
- `skills_function_url`/`skills_function_key` 환경변수 로드 제거
- 스킬셋 호출에서 해당 파라미터 전달 제거

**nb01 (`01-infra-deployment.ipynb`) 변경:**
- Cell#25 (skills-function 배포 확인): 건너뛰기 안내 추가 or 제거
- Cell#26 (Skills Function Key 조회): 건너뛰기 안내 추가 or 제거
- Cell#27 (파이프라인 등록): `SKILLS_FUNCTION_URL`/`SKILLS_FUNCTION_KEY` 환경변수 제거

**nb05 (`05-multimodal-indexing.ipynb`):**
- Skills Function 관련 참조 확인 및 제거

**`sample.env`:**
- `SKILLS_FUNCTION_URL`/`SKILLS_FUNCTION_KEY` 라인 제거 or 주석 처리

**`AGENTS.md`:**
- 파이프라인 설명에서 Custom Skill → Built-in Skill로 업데이트

## Acceptance criteria

- [x] `setup_multimodal_pipeline()`에 `skills_function` 관련 코드 없음
- [x] nb01에서 Skills Function Key 불필요 안내
- [x] nb01 cell#27에서 `SKILLS_FUNCTION_URL`/`KEY` 환경변수 제거
- [x] sample.env에서 Skills Function 라인 정리

## Blocked by

- [0010-basic-builtin-split.md](./0010-basic-builtin-split.md)
- [0011-verbalized-genai-prompt.md](./0011-verbalized-genai-prompt.md)
