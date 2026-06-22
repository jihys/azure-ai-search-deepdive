# 0015 — CONTEXT.md + AGENTS.md + copilot-instructions.md 업데이트

**Status:** done
**Parent:** [PRD-doc-sync.md](../prd/PRD-doc-sync.md)

## What to build

3개 파일의 도메인 용어와 아키텍처 설명을 Built-in Skill 기준으로 갱신한다.

### CONTEXT.md — 5건

| # | 섹션 | 변경 |
|---|------|------|
| 1 | Language 테이블 | `Custom WebAPI Skill`, `markdown_split`, `pptx_page_split`, `verbalize` 용어 → `SplitSkill`, `GenAI Prompt ChatCompletionSkill`, `MergeSkill` |
| 2 | 파이프라인 관계 | Custom Skill 호출 체인 → Built-in Skill 체인 (`DI Layout → SplitSkill`, `imageAction → GenAI Prompt → MergeSkill → SplitSkill`) |
| 3 | 비교 설명 | Basic vs Verbalized 비교에서 Custom Skill 용어 → Built-in Skill 용어 |
| 4 | Entity 관계 | Custom WebAPI Skill 엔티티 → Built-in Skill 엔티티 |
| 5 | 해결된 결정 Q9/Q14 | Built-in Skill로 전환된 사실과 근거 추가 |

### AGENTS.md — 1건

| # | 섹션 | 변경 |
|---|------|------|
| 1 | Tech Stack | `Azure Functions (3개: crawl, preprocess, skills)` → `Azure Functions (2개: crawl, preprocess)` |

### .github/copilot-instructions.md — 3건

| # | 섹션 | 변경 |
|---|------|------|
| 1 | 프로젝트 구조 테이블 | 노트북 범위 `01~06` → `01~07` |
| 2 | `skills-function/` 설명 | `Custom Skills Azure Function` → `Custom Skills Azure Function — 미사용 (Built-in Skill로 전환됨)` |
| 3 | 시나리오 B 설명 | `AI Search Skillset 비교 (Native vs Custom+Native)` → `AI Search Skillset 비교 (Basic vs Verbalized, Built-in Skill)` |

## Acceptance criteria

- [x] CONTEXT.md Language 테이블에 `Custom WebAPI Skill`, `markdown_split`, `pptx_page_split`, `verbalize` 없음
- [x] CONTEXT.md 파이프라인 관계가 Built-in Skill 체인을 기술
- [x] CONTEXT.md Basic vs Verbalized 비교에서 Built-in Skill 용어 사용
- [x] CONTEXT.md Entity 관계에서 Custom WebAPI Skill 엔티티 제거
- [x] CONTEXT.md Q9/Q14에 Built-in Skill 전환 근거 기록
- [x] AGENTS.md Tech Stack에 `Azure Functions (2개: crawl, preprocess)` 기술
- [x] copilot-instructions.md 노트북 범위가 `01~07`
- [x] copilot-instructions.md `skills-function/` 항목에 미사용 표기
- [x] copilot-instructions.md 시나리오 B가 `Basic vs Verbalized, Built-in Skill` 기술

## Blocked by

없음
