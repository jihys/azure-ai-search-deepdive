# 0010 — B-1/B-2 Basic 파이프라인: Custom Split → Built-in SplitSkill

**Status:** done
**Parent:** [PRD-builtin-skills.md](../prd/PRD-builtin-skills.md)

## What to build

B-1/B-2 Basic 파이프라인의 Custom WebApiSkill(`markdown_split`, `pptx_page_split`)을
Built-in `SplitSkill`(`#Microsoft.Skills.Text.SplitSkill`)로 교체한다.

**`_create_basic_skillset()` 변경:**
1. DI Layout `outputMode`를 `oneToMany` → `oneToOne`으로 변경
2. Custom WebApiSkill 제거
3. Built-in SplitSkill 추가 (`textSplitMode: "pages"`, `maximumPageLength: 2000`, `pageOverlapLength: 200`)
4. Embedding context를 `/document/pages/*`로 변경
5. `skills_function_url`/`skills_function_key` 파라미터 제거

**`_index_projections()` 변경:**
- `sourceContext`: `/document/markdown_chunks/*` → `/document/pages/*`
- content source: `/document/pages/*`
- vector source: `/document/pages/*/chunk_vector`
- phantom 필드(`file_type`, `source_category`) 제거

## Acceptance criteria

- [x] `_create_basic_skillset()`에 `WebApiSkill` 참조 없음
- [x] SplitSkill이 `maximumPageLength: 2000`, `pageOverlapLength: 200` 설정
- [x] DI Layout `outputMode`가 `oneToOne`
- [x] Index projection sourceContext가 `/document/pages/*`
- [x] `skills_function_url`/`skills_function_key` 파라미터 없음
- [x] 테스트 통과
