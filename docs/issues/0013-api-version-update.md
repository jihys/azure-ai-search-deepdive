# 0013 — Critical: API 버전 업데이트

**Status:** done
**Parent:** [PRD-doc-sync.md](../prd/PRD-doc-sync.md)

## What to build

`src/pipeline/indexer_ops.py`의 `API_VERSION` 상수를 `2024-11-01-preview` → `2026-04-01`로 수정한다.

GenAI Prompt Skill(`ChatCompletionSkill`)이 `2026-04-01` 이상의 API 버전을 요구하므로, 이 수정 없이는 B-3/B-4 파이프라인 인덱서 실행이 런타임 실패한다. 이 상수를 참조하는 모든 REST 호출이 자동으로 새 버전을 사용하게 된다.

**변경 대상:**

| 파일 | 현재 | 변경 |
|------|------|------|
| `src/pipeline/indexer_ops.py` | `API_VERSION = "2024-11-01-preview"` | `API_VERSION = "2026-04-01"` |

## Acceptance criteria

- [x] `src/pipeline/indexer_ops.py`의 `API_VERSION`이 `"2026-04-01"`이다
- [x] `grep -r '2024-11-01-preview' src/`가 결과 없음
- [x] 기존 테스트(`tests/test_multimodal_pipeline.py`)가 통과

## Blocked by

없음 — 이 이슈가 다른 모든 이슈의 선행 조건이다.
