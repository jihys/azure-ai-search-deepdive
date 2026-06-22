# PRD: Built-in Skill 전환 후 문서 동기화

**Status:** unspecified

## Problem Statement

커밋 `e1ad50a`에서 Custom WebAPI Skill → Built-in Skill 전환이 완료되었으나, 7개 문서 파일에 31개의 구 참조가 남아 있다. 코드는 이미 Built-in Skill만 사용하지만 README, CONTEXT.md, 인프라 문서, 노트북 마크다운 셀 등이 여전히 Custom WebAPI Skill 아키텍처를 기술하고 있어 랩 참가자에게 혼란을 준다.

특히 `src/pipeline/indexer_ops.py`의 `API_VERSION`이 `2024-11-01-preview`로 남아 있어 GenAI Prompt Skill(`ChatCompletionSkill`)이 요구하는 `2026-04-01` 이상의 API 버전과 불일치한다. 이 상태로 인덱서를 실행하면 런타임 실패가 발생한다.

## Solution

모든 문서를 Built-in Skill 아키텍처에 맞게 갱신하고, `indexer_ops.py`의 API 버전을 `2026-04-01`로 수정한다.

## Scope

### 1. `src/pipeline/indexer_ops.py` — 1건 (CRITICAL)

| 항목 | 현재 | 변경 |
|------|------|------|
| `API_VERSION` | `2024-11-01-preview` | `2026-04-01` |

GenAI Prompt Skill GA 버전 요구사항. 이 수정 없이는 B-3/B-4 파이프라인 인덱서 실행이 실패한다.

### 2. `README.md` — 7건

| # | 섹션 | 변경 내용 |
|---|------|----------|
| 1 | B-1~B-4 파이프라인 다이어그램 | Custom Skill 이름(`markdown_split`, `pptx_page_split`, `verbalize`) → Built-in 이름(`SplitSkill`, `GenAI Prompt`, `MergeSkill`) |
| 2 | 리소스 테이블 | Skills Function App을 **미사용** (참고용 유지)으로 표시 |
| 3 | 파이프라인 설명 섹션 | Custom WebAPI Skill 호출 설명 → Built-in Skill 체인 설명 |
| 4 | Custom Skills 섹션 | 별도 섹션 제거, Built-in Skill로 대체되었다는 노트로 교체 |
| 5 | 프로젝트 구조 | `skills-function/` 설명에 **미사용** (Built-in Skill로 전환됨) 표기 |
| 6 | v2.1 변경 이력 | Built-in Skill 전환 항목 추가 |
| 7 | 사전 준비 사항 | Function App 3개 → 2개 (`crawl-function`, `preprocess-function`만 필요) |

### 3. `CONTEXT.md` — 5건

| # | 섹션 | 변경 내용 |
|---|------|----------|
| 1 | Language 테이블 | `Custom WebAPI Skill`, `markdown_split`, `pptx_page_split`, `verbalize` 용어 → `SplitSkill`, `GenAI Prompt ChatCompletionSkill`, `MergeSkill` |
| 2 | 파이프라인 관계 | Custom Skill 호출 체인 → Built-in Skill 체인 (`DI Layout → SplitSkill`, `imageAction → GenAI Prompt → MergeSkill → SplitSkill`) |
| 3 | 비교 설명 | Basic vs Verbalized 비교에서 Custom Skill 용어 → Built-in Skill 용어 |
| 4 | Entity 관계 | Custom WebAPI Skill 엔티티 → Built-in Skill 엔티티 |
| 5 | 해결된 결정 Q9/Q14 | Built-in Skill로 전환된 사실과 근거 추가 |

### 4. `AGENTS.md` — 1건

| # | 섹션 | 변경 내용 |
|---|------|----------|
| 1 | Tech Stack | `Azure Functions (3개: crawl, preprocess, skills)` → `Azure Functions (2개: crawl, preprocess)` |

### 5. `docs/infrastructure.md` — 7건

| # | 섹션 | 변경 내용 |
|---|------|----------|
| 1 | 개요 테이블 | 인덱스 개수 및 스킬 타입을 Built-in 기준으로 갱신 |
| 2 | 리소스 테이블 | Skills Function App 엔드포인트 제거 또는 미사용 표시 |
| 3 | B-2 파이프라인 섹션 | Custom `pptx_page_split` → Built-in `SplitSkill` |
| 4 | 비교 테이블 | "별도 Function App 필요" → "Function App 불필요" |
| 5 | 배포 섹션 | `skills-function` 배포 단계 제거 |
| 6 | 스킬셋 구성 설명 | Custom WebAPI Skill 구성 → Built-in Skill 구성 |
| 7 | 아키텍처 다이어그램 참조 | Custom Skill 흐름 → Built-in Skill 흐름 |

### 6. `notebooks/01-infra-deployment.ipynb` — 6건

| # | 셀 유형 | 변경 내용 |
|---|---------|----------|
| 1 | Markdown | Skills Function App 배포 안내 텍스트 → 미사용 안내로 교체 |
| 2 | Markdown | 3개 Function App 목록 → 2개로 수정 |
| 3 | Markdown | Skills Function 환경 변수 설정 안내 제거 |
| 4 | Code | `skills-function` 배포 코드 셀에 건너뛰기 안내 추가 |
| 5 | Markdown | 배포 검증 체크리스트에서 skills-function 제거 또는 optional 표시 |
| 6 | Markdown | 전체 아키텍처 설명에서 Custom Skill 참조 → Built-in Skill |

### 7. `notebooks/05-multimodal-indexing.ipynb` — 1건

| # | 셀 유형 | 변경 내용 |
|---|---------|----------|
| 1 | Markdown | 파이프라인 아키텍처 테이블에서 Custom Skill 이름 → Built-in Skill 이름 |

### 8. `.github/copilot-instructions.md` — 3건

| # | 섹션 | 변경 내용 |
|---|------|----------|
| 1 | 프로젝트 구조 테이블 | 노트북 범위 `01~06` → `01~07` |
| 2 | `skills-function/` 설명 | `Custom Skills Azure Function` → `Custom Skills Azure Function — 미사용 (Built-in Skill로 전환됨)` |
| 3 | 시나리오 B 설명 | `AI Search Skillset 비교 (Native vs Custom+Native)` → `AI Search Skillset 비교 (Basic vs Verbalized, Built-in Skill)` |

## User Stories

1. As a 핸즈온 랩 참가자, I want README의 파이프라인 다이어그램이 실제 코드와 일치하길, so that Custom Skill 설정 지침을 따라가다 실패하는 일이 없다.
2. As a 핸즈온 랩 참가자, I want nb01에서 skills-function 배포를 건너뛸 수 있다는 안내가 있길, so that 불필요한 Function App 배포에 시간을 낭비하지 않는다.
3. As a 개발자, I want `indexer_ops.py`의 API 버전이 `2026-04-01`이길, so that GenAI Prompt Skill이 포함된 인덱서가 정상 실행된다.
4. As a Copilot 에이전트, I want `CONTEXT.md`의 도메인 용어가 현행 아키텍처를 반영하길, so that 코드 생성 시 구 용어를 사용하지 않는다.

## Implementation Decisions

### 1. `skills-function/` 디렉토리 유지

코드 참고용으로 디렉토리를 삭제하지 않는다. 문서에서 **미사용** 표시만 추가한다. Custom → Built-in 전환 과정을 학습할 수 있는 before/after 참고 자료로 가치가 있다.

### 2. API 버전 단일 수정

`indexer_ops.py`의 `API_VERSION` 상수 하나만 수정한다. 이 상수를 참조하는 모든 REST 호출이 자동으로 `2026-04-01`을 사용하게 된다.

### 3. 노트북 코드 셀은 최소 변경

nb01의 skills-function 배포 코드 셀은 삭제하지 않고, 마크다운 셀에 "Built-in Skill 전환으로 이 셀은 건너뛰어도 됩니다" 안내를 추가한다. 참가자가 여전히 Custom Skill을 실험해볼 수 있도록 옵션을 남겨둔다.

## Testing Decisions

이 PRD의 범위는 **문서 동기화**이므로 코드 테스트는 `indexer_ops.py` API 버전 수정 1건만 해당한다:

- `indexer_ops.py`의 `API_VERSION`이 `2026-04-01`인지 grep으로 확인
- 각 문서 파일에서 `Custom WebAPI Skill`, `skills-function` 키워드를 검색하여 구 참조가 적절히 처리(제거 또는 미사용 표시)되었는지 확인
- 노트북 마크다운 셀의 파이프라인 다이어그램/테이블이 Built-in Skill 이름을 사용하는지 확인

## Out of Scope

- `skills-function/` 디렉토리 삭제 (코드 참고용으로 유지)
- Bicep 인프라 변경 (기존 Function App 리소스는 배포에 영향 없음)
- 파이프라인 코드 수정 (PRD-builtin-skills에서 이미 완료)
- B-5/B-6 Content Understanding 파이프라인 문서화 (별도 이슈)
