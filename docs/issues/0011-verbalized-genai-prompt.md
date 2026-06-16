# 0011 — B-3/B-4 Verbalized 파이프라인: Custom Verbalize → GenAI Prompt Skill

**Status**: done
**Parent**: [PRD-builtin-skills.md](../prd/PRD-builtin-skills.md)

## What to build

B-3/B-4 Verbalized 파이프라인의 Custom WebApiSkill(`verbalize`, `markdown_split`)을
Built-in 스킬로 교체한다: GenAI Prompt(`ChatCompletionSkill`) + MergeSkill + SplitSkill.

**`_create_verbalized_skillset()` 변경:**
1. DI Layout 스킬 제거 (표준 텍스트 추출 사용)
2. Custom WebApiSkill(`verbalize`, `markdown_split`) 제거
3. GenAI Prompt Skill 추가 (context: `/document/normalized_images/*`, 이미지 설명)
4. MergeSkill 추가 (content + 이미지 설명 inline 삽입)
5. SplitSkill 추가 (`maximumPageLength: 2000`, `pageOverlapLength: 200`)
6. Embedding context를 `/document/pages/*`로 변경
7. `skills_function_url`/`skills_function_key` 파라미터 제거

**`_create_indexer()` 변경:**
- Verbalized 파이프라인용 `imageAction: "generateNormalizedImages"` 추가
- `normalizedImageMaxWidth`/`normalizedImageMaxHeight` 설정 (4200)

**인증:**
- GenAI Prompt Skill은 Search Service MI의 `Cognitive Services OpenAI User` 역할 사용
- `apiKey` 대신 MI 인증 → 키 파라미터 불필요

## Acceptance criteria

- [x] `_create_verbalized_skillset()`에 `WebApiSkill` 참조 없음
- [x] `ChatCompletionSkill`이 context `/document/normalized_images/*`에서 실행
- [x] MergeSkill이 `/document/content`와 이미지 설명을 병합
- [x] SplitSkill 설정 (maximumPageLength: 2000, pageOverlapLength: 200)
- [x] Verbalized indexer에 `imageAction: "generateNormalizedImages"` 설정
- [x] `skills_function_url`/`skills_function_key` 파라미터 없음
- [x] 테스트 통과

## Blocked by

- [0010-basic-builtin-split.md](./0010-basic-builtin-split.md) (index projection 공유)
