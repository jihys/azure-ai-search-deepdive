# 0020 — Header 청킹 테스트 업데이트

**Status**: ✅ Done
**Parent**: [PRD-header-chunking.md](../prd/PRD-header-chunking.md)

## What to build

B-1~B-4 Header 기반 시맨틱 청킹 전환에 따른 테스트 추가 및 업데이트.
기존 테스트를 새 파이프라인 구조에 맞게 수정하고, 신규 검증 항목을 추가한다.

**Basic 파이프라인 테스트 (0018 검증):**
1. `test_di_layout_one_to_many` — DI Layout `oneToMany` + `h2` 설정 확인
2. `test_content_type_mapping` — `content_type` mapping 존재 확인

**Verbalized 파이프라인 테스트 (0019 검증):**
3. `test_no_merge_skill` — MergeSkill 미포함 확인
4. `test_has_di_layout_one_to_many` — DI Layout `oneToMany` + `h2` 설정 확인
5. `test_two_embedding_skills` — Embedding 스킬 2개 확인
6. `test_two_projection_selectors` — Index projection selector 2개 확인

## Acceptance criteria

- [x] 위 6개 테스트 케이스 포함
- [x] 전체 21개 테스트 통과 (`pytest tests/test_multimodal_pipeline.py`)
- [x] 기존 테스트 회귀 없음

## Changed files

- `tests/test_multimodal_pipeline.py`
