# 0014 — README.md 업데이트

**Status:** done
**Parent:** [PRD-doc-sync.md](../prd/PRD-doc-sync.md)

## What to build

README.md의 7개 위치에서 Custom WebAPI Skill 참조를 Built-in Skill 기준으로 갱신한다.

**변경 내용:**

| # | 섹션 | 변경 |
|---|------|------|
| 1 | B-1~B-4 파이프라인 다이어그램 | Custom Skill 이름(`markdown_split`, `pptx_page_split`, `verbalize`) → Built-in 이름(`SplitSkill`, `GenAI Prompt`, `MergeSkill`) |
| 2 | 리소스 테이블 | Skills Function App을 **미사용** (참고용 유지)으로 표시 |
| 3 | 파이프라인 설명 섹션 | Custom WebAPI Skill 호출 설명 → Built-in Skill 체인 설명 |
| 4 | Custom Skills 섹션 | 별도 섹션 제거, Built-in Skill로 대체되었다는 노트로 교체 |
| 5 | 프로젝트 구조 | `skills-function/` 설명에 **미사용** (Built-in Skill로 전환됨) 표기 |
| 6 | v2.1 변경 이력 | Built-in Skill 전환 항목 추가 |
| 7 | 사전 준비 사항 | Function App 3개 → 2개 (`crawl-function`, `preprocess-function`만 필요) |

## Acceptance criteria

- [x] 파이프라인 다이어그램에 `markdown_split`, `pptx_page_split`, `verbalize` 이름 없음
- [x] 리소스 테이블에서 Skills Function App이 **미사용** 표시됨
- [x] 파이프라인 설명이 Built-in Skill 체인(`SplitSkill`, `GenAI Prompt`, `MergeSkill`)을 기술
- [x] Custom Skills 별도 섹션이 Built-in Skill 전환 노트로 교체됨
- [x] 프로젝트 구조에서 `skills-function/` 항목에 미사용 표기
- [x] 변경 이력에 Built-in Skill 전환 항목 존재
- [x] 사전 준비 사항에서 필요한 Function App이 2개(`crawl-function`, `preprocess-function`)로 기술됨

## Blocked by

없음
