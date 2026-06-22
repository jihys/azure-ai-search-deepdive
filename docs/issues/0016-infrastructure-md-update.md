# 0016 — docs/infrastructure.md 업데이트

**Status:** done
**Parent:** [PRD-doc-sync.md](../prd/PRD-doc-sync.md)

## What to build

`docs/infrastructure.md`의 7개 위치에서 Custom WebAPI Skill 참조를 Built-in Skill 기준으로 갱신한다.

**변경 내용:**

| # | 섹션 | 변경 |
|---|------|------|
| 1 | 개요 테이블 | 인덱스 개수 및 스킬 타입을 Built-in 기준으로 갱신 |
| 2 | 리소스 테이블 | Skills Function App 엔드포인트 제거 또는 미사용 표시 |
| 3 | B-2 파이프라인 섹션 | Custom `pptx_page_split` → Built-in `SplitSkill` |
| 4 | 비교 테이블 | "별도 Function App 필요" → "Function App 불필요" |
| 5 | 배포 섹션 | `skills-function` 배포 단계 제거 |
| 6 | 스킬셋 구성 설명 | Custom WebAPI Skill 구성 → Built-in Skill 구성 |
| 7 | 아키텍처 다이어그램 참조 | Custom Skill 흐름 → Built-in Skill 흐름 |

## Acceptance criteria

- [x] 개요 테이블이 Built-in Skill 기준 인덱스/스킬 정보를 기술
- [x] 리소스 테이블에서 Skills Function App이 미사용 표시 또는 제거됨
- [x] B-2 파이프라인 섹션이 `SplitSkill`을 기술 (Custom `pptx_page_split` 없음)
- [x] 비교 테이블에 "별도 Function App 필요" 없음
- [x] 배포 섹션에서 `skills-function` 배포 단계 없음
- [x] 스킬셋 구성이 Built-in Skill 기준으로 기술됨
- [x] 아키텍처 다이어그램 참조가 Built-in Skill 흐름을 기술

## Blocked by

없음
