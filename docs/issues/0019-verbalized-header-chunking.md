# 0019 — B-3/B-4 Verbalized 파이프라인: Header 청킹 + 이미지 별도 청크

**Status:** done
**Parent:** [PRD-header-chunking.md](../prd/PRD-header-chunking.md)

## What to build

B-3/B-4 Verbalized 파이프라인을 Header 기반 시맨틱 청킹으로 전환하고,
이미지 설명을 별도 청크로 분리하여 독립적 이미지 검색을 지원한다.

**`_create_verbalized_skillset()` 변경:**
1. DI Layout 스킬 추가 (`outputMode: oneToMany`, `markdownHeaderDepth: h2`)
2. MergeSkill 제거
3. SplitSkill context를 `/document/markdown_sections/*`로 변경
4. 텍스트용 Embedding 스킬 (기존) — `/document/markdown_sections/*/pages/*` context
5. 이미지용 Embedding 스킬 추가 — GenAI Prompt 결과 임베딩

**`_index_projections()` 변경:**
- Index projection selector 2개 구성:
  - **텍스트 selector**: `sourceContext: /document/markdown_sections/*/pages/*`, `content_type='text'`
  - **이미지 selector**: 이미지 설명 청크, `content_type='image_description'`

## Acceptance criteria

- [x] MergeSkill이 스킬셋에 없음
- [x] DI Layout 스킬이 `oneToMany` + `h2`로 포함
- [x] Embedding 스킬 2개 (텍스트 + 이미지)
- [x] Index projection selector 2개 (텍스트 + 이미지)
- [x] 텍스트 청크 `content_type='text'`, 이미지 청크 `content_type='image_description'`
- [x] 테스트 통과

## Changed files

- `src/pipeline/multimodal_pipeline.py`
