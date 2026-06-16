# 0021: 논문 분야 필터 필드 추가 (academic_field)

**Status:** 🔲 대기  
**Parent:** [PRD-themepark-and-academic-field](../prd/PRD-themepark-and-academic-field.md)

## 요약

기존 멀티모달 파이프라인(B-1~B-4)에 `academic_field` 필터 필드를 추가하여, 파일명 prefix(ST/SS/HA)에서 학문 분야를 자동 매핑한다.

## 상세

### 인덱스 스키마 변경

- `academic_field` 필드 추가: `Edm.String`, `filterable=true`, `facetable=true`

### 매핑 로직

파일명(`metadata_storage_name`) prefix로부터 `academic_field` 값 결정:

| Prefix | 값 |
|--------|-----|
| `ST_*` | `"과학기술"` |
| `SS_*` | `"사회과학"` |
| `HA_*` | `"인문학예술체육학"` |
| 기타 | `null` |

### 구현 방안

- Skillset에 ConditionalSkill 또는 Custom WebApiSkill 추가하여 prefix → `academic_field` 매핑
- 또는 Indexer `fieldMappings`에서 custom mapping function 사용
- Index projection에 `academic_field` 필드 매핑 추가

## 수용 기준

- [ ] `$filter=academic_field eq '과학기술'` 쿼리가 올바른 결과 반환
- [ ] `$filter=academic_field eq '사회과학'` 쿼리가 올바른 결과 반환
- [ ] `$filter=academic_field eq '인문학예술체육학'` 쿼리가 올바른 결과 반환
- [ ] prefix가 없는 파일은 `academic_field`가 `null`
- [ ] 기존 테스트(`tests/test_multimodal_pipeline.py`) 통과
- [ ] 새 테스트 추가: academic_field 매핑 로직 검증

## 변경 파일

- `src/search/multimodal_index.py` — 스키마에 `academic_field` 필드 추가
- `src/pipeline/multimodal_pipeline.py` — Skillset/Indexer에 매핑 로직 추가
- `tests/test_multimodal_pipeline.py` — academic_field 관련 테스트 추가

## 의존성

- 없음 (기존 파이프라인 확장)
