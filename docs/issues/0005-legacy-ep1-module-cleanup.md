# 레거시 EP1 Bicep 모듈 삭제

**Status**: done
**Parent**: [PRD-cleanup.md](../prd/PRD-cleanup.md)

## What to build

`infra/sweden-public/modules/`에서 사용하지 않는 레거시 EP1 (Elastic Premium) Function App 모듈 3개를 삭제한다.
이 모듈들은 FC1 (Flex Consumption) 모듈로 대체되어 main.bicep에서 참조되지 않는다.

**삭제 대상:**
- `function-crawler.bicep` — EP1 크롤러 (→ `function-crawler-consumption.bicep`으로 대체됨)
- `function-preprocess.bicep` — EP1 전처리 (→ `function-preprocess-fc1.bicep`으로 대체됨)
- `function-skills.bicep` — EP1 스킬 (→ `function-skills-fc1.bicep`으로 대체됨)

## Acceptance criteria

- [x] `modules/function-crawler.bicep` 삭제됨
- [x] `modules/function-preprocess.bicep` 삭제됨
- [x] `modules/function-skills.bicep` 삭제됨
- [x] main.bicep에서 해당 파일들을 참조하지 않음
