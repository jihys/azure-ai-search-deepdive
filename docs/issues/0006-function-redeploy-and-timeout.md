# Function App 올바른 코드 재배포 및 타임아웃 확장

**Status**: done
**Parent**: N/A (legacy issue)

## What to build

3개 Function App이 모두 crawl-function 코드로 잘못 배포되어 있는 문제를 해결한다.
각 Function App에 올바른 소스 코드를 재배포하고, Logic App 폴링 타임아웃을 24시간으로 확장한다.

**문제:**
- `func-preprocess-ragi-63325wdo`: crawl 코드가 배포됨 → `preprocess` 함수 없음 (404)
- `func-skills-ragi-63325wdo`: crawl 코드가 배포됨 → `markdown_split` 등 함수 없음 (404)
- Logic App 폴링 타임아웃이 4시간으로 제한됨

**수정:**
- `logic-apps/preprocess-function/` → `func-preprocess-ragi-63325wdo` 재배포
- `skills-function/` → `func-skills-ragi-63325wdo` 재배포
- `logic-apps/crawl-function/` → `func-crawl-cons-ragi-63325wdo` 재배포 (VNet 제거 후 정합성)
- `.funcignore` 파일 추가 (preprocess, skills)
- `logic-app-crawl.bicep` 폴링 타임아웃 PT4H → PT24H, 횟수 480 → 2880
- 배포된 Logic App에도 PT24H 반영
- `crawl-preprocess-workflow/workflow.json` HTTP 타임아웃 PT24H로 통일

## Acceptance criteria

- [x] `func-preprocess-ragi-63325wdo`에 `preprocess` 함수 등록됨
- [x] `func-skills-ragi-63325wdo`에 `markdown_split`, `pptx_page_split`, `verbalize` 함수 등록됨
- [x] `func-crawl-cons-ragi-63325wdo`에 crawl/orchestrator 함수 등록됨
- [x] Logic App 폴링 타임아웃 PT24H 적용됨
- [x] `.funcignore` 파일 추가됨 (preprocess-function, skills-function)

## Blocked by

- [0004-hub-vnet-removal.md](./0004-hub-vnet-removal.md) (VNet 제거 선행)
