# 0017 — 노트북 마크다운 업데이트

**Status**: done
**Parent**: [PRD-doc-sync.md](../prd/PRD-doc-sync.md)

## What to build

2개 노트북의 마크다운 셀에서 Custom WebAPI Skill 참조를 Built-in Skill 기준으로 갱신한다.

### nb01 (`notebooks/01-infra-deployment.ipynb`) — 6건

| # | 셀 유형 | 변경 |
|---|---------|------|
| 1 | Markdown | Skills Function App 배포 안내 텍스트 → 미사용 안내로 교체 |
| 2 | Markdown | 3개 Function App 목록 → 2개로 수정 |
| 3 | Markdown | Skills Function 환경 변수 설정 안내 제거 |
| 4 | Code | `skills-function` 배포 코드 셀에 건너뛰기 안내 추가 |
| 5 | Markdown | 배포 검증 체크리스트에서 skills-function 제거 또는 optional 표시 |
| 6 | Markdown | 전체 아키텍처 설명에서 Custom Skill 참조 → Built-in Skill |

### nb05 (`notebooks/05-multimodal-indexing.ipynb`) — 1건

| # | 셀 유형 | 변경 |
|---|---------|------|
| 1 | Markdown | 파이프라인 아키텍처 테이블에서 Custom Skill 이름 → Built-in Skill 이름 |

**구현 원칙:** 코드 셀은 삭제하지 않고 마크다운 안내만 수정한다. 참가자가 Custom Skill을 실험해볼 수 있도록 옵션을 남겨둔다.

## Acceptance criteria

- [x] nb01 마크다운에서 Skills Function App이 미사용으로 안내됨
- [x] nb01 Function App 목록이 2개(`crawl-function`, `preprocess-function`)로 수정됨
- [x] nb01 Skills Function 환경 변수 설정 안내가 제거 또는 optional 표시됨
- [x] nb01 `skills-function` 배포 코드 셀에 건너뛰기 안내 존재
- [x] nb01 배포 검증 체크리스트에서 skills-function이 optional 표시됨
- [x] nb01 아키텍처 설명이 Built-in Skill을 기술
- [x] nb05 파이프라인 아키텍처 테이블이 Built-in Skill 이름(`SplitSkill`, `GenAI Prompt`, `MergeSkill`)을 사용

## Blocked by

없음
