# 0018 — B-1/B-2 Basic 파이프라인: DI Layout oneToMany + markdownHeaderDepth h2 전환

**Status**: done
**Parent**: [PRD-header-chunking.md](../prd/PRD-header-chunking.md)

## What to build

B-1/B-2 Basic 파이프라인의 청킹 전략을 고정 글자수(2000자) 분할에서
DI Layout `oneToMany` + `markdownHeaderDepth: "h2"` 기반 시맨틱 청킹으로 전환한다.

**`_create_basic_skillset()` 변경:**
1. DI Layout `outputMode`를 `oneToMany`로 변경
2. DI Layout `markdownHeaderDepth`를 `h2`로 설정
3. SplitSkill context를 `/document/markdown_sections/*`로 변경 (긴 섹션 안전망)
4. Embedding context를 `/document/markdown_sections/*/pages/*`로 변경
5. `content_type` mapping 추가

**`_index_projections()` 변경:**
- `sourceContext`: `/document/markdown_sections/*/pages/*`
- content/vector source 경로 업데이트
- `content_type` mapping 추가

## Acceptance criteria

- [x] DI Layout `outputMode`가 `oneToMany`
- [x] DI Layout `markdownHeaderDepth`가 `h2`
- [x] SplitSkill context가 `/document/markdown_sections/*`
- [x] Embedding context가 `/document/markdown_sections/*/pages/*`
- [x] Index projection `sourceContext`가 `/document/markdown_sections/*/pages/*`
- [x] `content_type` mapping 포함
- [x] 테스트 통과

## Changed files

- `src/pipeline/multimodal_pipeline.py`
