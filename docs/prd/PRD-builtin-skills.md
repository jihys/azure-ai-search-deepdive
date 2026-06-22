# PRD: Custom WebAPI Skill → Built-in Skill 전환

**Status:** unspecified

## Problem Statement

현재 멀티모달 파이프라인(B-1~B-4)이 Custom WebAPI Skill (Azure Function)에 의존하여 3가지 문제가 있다:

1. **B-3/B-4 verbalize 스킬이 PyMuPDF로 PDF를 페이지별 이미지로 렌더링** — Document Intelligence가 식별한 이미지 영역이 아닌, PyMuPDF의 부정확한 렌더링을 GPT에 전달하므로 품질이 낮다.
2. **B-1/B-2 markdown_split/pptx_page_split 스킬이 별도 Function App 필요** — Built-in SplitSkill로 대체 가능한 기능에 Function App 인프라를 운영하고 있다.
3. **인프라 오버헤드** — Function App 배포, 키 관리(`SKILLS_FUNCTION_KEY`), 타임아웃 설정, RBAC 등 관리 부담.

GenAI Prompt Skill (`ChatCompletionSkill`)이 2026-04-01 API에서 GA되어 Custom Skill 없이 이미지 verbalization이 가능해졌다.

## Solution

4개 파이프라인 모두 Built-in Skill만 사용하도록 재설계한다:

| 파이프라인 | 현재 (Custom Skill) | 변경 후 (Built-in Only) |
|---|---|---|
| B-1 Basic PDF | DI Layout → Custom `markdown_split` → Embedding | DI Layout (oneToOne) → SplitSkill → Embedding |
| B-2 Basic PPTX | DI Layout → Custom `pptx_page_split` → Embedding | DI Layout (oneToOne) → SplitSkill → Embedding |
| B-3 Verbalized PDF | DI Layout → Custom `verbalize` → Custom `markdown_split` → Embedding | `imageAction` → GenAI Prompt → MergeSkill → SplitSkill → Embedding |
| B-4 Verbalized PPTX | DI Layout → Custom `verbalize` → Custom `markdown_split` → Embedding | `imageAction` → GenAI Prompt → MergeSkill → SplitSkill → Embedding |

### B-1/B-2 Basic 파이프라인 상세

```
DI Layout (oneToOne) → /document/layout_markdown (단일 문자열)
  → SplitSkill (maximumPageLength=2000, pageOverlapLength=200) → /document/pages/*
    → EmbeddingSkill → /document/pages/*/chunk_vector
      → Index Projection (sourceContext: /document/pages/*)
```

### B-3/B-4 Verbalized 파이프라인 상세

```
Indexer: imageAction = "generateNormalizedImages"
  → GenAI Prompt Skill (context: /document/normalized_images/*)
      → 각 이미지 설명 → /document/normalized_images/*/description
  → MergeSkill (context: /document)
      → /document/content + 이미지 설명 inline 삽입 → /document/merged_content
  → SplitSkill → /document/pages/*
  → EmbeddingSkill → /document/pages/*/chunk_vector
  → Index Projection (sourceContext: /document/pages/*)
```

핵심 차이:
- B-1/B-2는 DI Layout의 고품질 markdown 텍스트 사용 (이미지 이해 없음)
- B-3/B-4는 표준 텍스트 추출 + `normalized_images`의 이미지 설명 inline 삽입 (이미지 이해 있음)
- 이 구조는 [Azure 공식 멀티모달 튜토리얼](https://learn.microsoft.com/en-us/azure/search/tutorial-multimodal)과 동일한 패턴

## Implementation Decisions

### 1. B-3/B-4에서 DI Layout을 사용하지 않는 이유

`normalized_images`의 `contentOffset`은 표준 텍스트 추출(`/document/content`)의 위치를 기준으로 한다.
DI Layout의 markdown 출력과는 오프셋이 일치하지 않아 MergeSkill로 inline 삽입이 불가능하다.
따라서 B-3/B-4는 표준 텍스트 추출을 사용한다.

### 2. GenAI Prompt Skill 인증

- Search Service의 System Managed Identity 사용 (키 불필요)
- `Cognitive Services OpenAI User` 역할이 이미 할당되어 있음
- `uri` 파라미터: OpenAI 엔드포인트의 chat completions URL

### 3. GenAI Prompt 30초 타임아웃

GenAI Prompt Skill은 요청당 30초 고정 제한이 있다.
이미지 단위(`/document/normalized_images/*`)로 context가 설정되므로 1개 이미지 처리에 30초면 충분하다.

### 4. Skills Function App

모든 Custom WebAPI Skill이 Built-in으로 대체되므로:
- `skills-function/` 디렉토리 유지 (참고용)
- nb01의 skills-function 배포 셀을 건너뛰기 가능으로 표시
- `.env`에서 `SKILLS_FUNCTION_URL`/`SKILLS_FUNCTION_KEY` 참조 제거
- `multimodal_pipeline.py`에서 `skills_function_url`/`skills_function_key` 파라미터 제거

### 5. Index Projection 경로 변경

| 파이프라인 | 현재 sourceContext | 변경 후 sourceContext |
|---|---|---|
| B-1/B-2 Basic | `/document/markdown_chunks/*` | `/document/pages/*` |
| B-3/B-4 Verbalized | `/document/markdown_chunks/*` | `/document/pages/*` |

### 6. API 버전

GenAI Prompt Skill 사용을 위해 `2026-04-01` API 버전 필요.

## Out of Scope

- `skills-function/` 디렉토리 삭제 (코드 참고용으로 유지)
- Bicep 인프라에서 Function App 리소스 제거 (기존 배포에 영향)
- B-5/B-6 추가 파이프라인 (향후 별도 이슈)
