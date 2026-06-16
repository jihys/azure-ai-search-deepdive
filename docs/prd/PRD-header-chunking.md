# PRD: B-1~B-4 Markdown Header 기반 시맨틱 청킹 전환

**Status:** ✅ 구현 완료
**Author:** jihys
**Created:** 2026-06-16

---

## 요약

B-1~B-4 멀티모달 파이프라인의 청킹 전략을 고정 글자수(2000자) 분할에서 DI Layout `oneToMany` + `markdownHeaderDepth: "h2"` 기반 시맨틱 청킹으로 전환. SplitSkill은 긴 섹션에 대한 안전망으로 유지.

## 동기

1. 고정 글자수 분할은 문장/단락 경계를 무시하여 검색 품질 저하
2. DI Layout의 `oneToMany` + `markdownHeaderDepth`는 Built-in 기능으로 추가 인프라 불필요
3. B-3/B-4에서 이미지 설명을 별도 청크로 분리하여 독립적 이미지 검색 가능

## Before / After

### B-1/B-2 (Basic)

| | Before | After |
|---|---|---|
| 파이프라인 | DI Layout (`oneToOne`) → SplitSkill (2000자) → Embedding | DI Layout (`oneToMany`, `h2`) → SplitSkill (2000/200 safety) → Embedding |

### B-3/B-4 (Verbalized)

| | Before | After |
|---|---|---|
| 파이프라인 | GenAI Prompt → MergeSkill → SplitSkill (2000자) → Embedding | DI Layout (`oneToMany`, `h2`) → SplitSkill → Embedding (text) + GenAI Prompt → Embedding (images 별도) |
| 변경 사항 | — | MergeSkill 제거, 이미지는 별도 청크로 인덱싱 |

## 수용 기준

1. DI Layout `outputMode`가 `oneToMany`, `markdownHeaderDepth`가 `h2`
2. SplitSkill이 `/document/markdown_sections/*` context에서 동작
3. B-3/B-4: MergeSkill 제거, Embedding 스킬 2개 (text + image)
4. B-3/B-4: Index projection selector 2개 (text `content_type='text'`, image `content_type='image_description'`)
5. 21개 테스트 통과

## 변경 파일

- `src/pipeline/multimodal_pipeline.py`
- `tests/test_multimodal_pipeline.py`

## 리스크

- **H2 섹션 초과 길이**: H2 섹션이 매우 긴 경우 SplitSkill이 추가 분할하므로 시맨틱 경계가 깨질 수 있음
- **텍스트-이미지 연관성**: 이미지 별도 청크 방식은 inline 병합 대비 텍스트-이미지 연관성이 약할 수 있음

## 관련 이슈

- [0018 — B-1/B-2 Basic Header 청킹](../issues/0018-basic-header-chunking.md) ✅ Done
- [0019 — B-3/B-4 Verbalized Header 청킹](../issues/0019-verbalized-header-chunking.md) ✅ Done
- [0020 — Header 청킹 테스트 업데이트](../issues/0020-header-chunking-tests.md) ✅ Done
