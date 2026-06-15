---
name: create-pr
description: >
  Create a pull request after auditing the development workflow sequence and
  writing a structured PR body with a summary, workflow audit checklist, and
  risk analysis. Use when the user says "create a PR", "make a PR", "open a
  pull request", or wants to ship a branch.
---

# Create PR

Open a pull request only after auditing the workflow sequence and writing a
structured body that helps reviewers understand the change quickly.

## Reference docs

- `AGENTS.md` — repo-wide conventions and branch-naming rules
- `docs/agents/issue-tracker.md` — scratch tracker layout
- `docs/adr/**` — architectural decisions in scope

---

## Phase 1 — Gather context

1. Run `git status` and `git log --oneline origin/main..HEAD` (or the target
   base branch) to confirm the branch has commits and is not already merged.
2. Collect the full diff: `git diff origin/main...HEAD -- . ':(exclude)*.lock'`.
   For very large diffs, use `git diff --stat` plus per-directory diffs to
   keep context manageable.
3. Read `CONTEXT.md` and `docs/orchestrator_architecture/spec/architecture.md`
   (or equivalent top-level architecture doc) to recall the domain model.

---

## Phase 2 — Workflow alignment audit

Check that the work followed this required sequence. Evidence is file timestamps
(`git log --diff-filter=A --name-only`) and commit history.

| # | Artifact type | Where to look | Required? |
|---|---|---|---|
| 1 | **Architecture doc** | `docs/orchestrator_architecture/spec/architecture.md` or `docs/adr/**` | **Yes** |
| 2 | **Module spec(s)** | `docs/orchestrator_architecture/spec/*.md` touching changed modules | **Yes** |
| 3 | **PRD** | `.scratch/prds/**` | Optional (may not exist) |
| 4 | **Issues** | `.scratch/issues/**` | Optional (may not exist) |
| 5 | **Tests** | `app/tests/**` or `tests/**` matching changed modules | **Yes** |
| 6 | **Implementation** | `app/src/**` | **Yes** |

Rules for the audit:

- Architecture or spec docs for a module **must exist before** implementation
  files for that module were first committed. Use
  `git log --diff-filter=A --format="%ai %s" -- <path>` to check creation
  order.
- Tests for a module **must be committed before or alongside** the
  implementation of new behaviour (TDD contract). Pure refactors (no new
  behaviour) are exempt — note the exemption explicitly.
- If PRD or issues are absent, note it as "optional artifacts absent — acceptable
  per issue-tracker config" and continue.
- If any **required** artifact is missing or was committed *after* its
  dependent artefact, record it as a **BLOCKER** and stop before creating the
  PR. Report the violation clearly and ask the user to resolve it first.

Produce an audit table in the PR body (see Phase 5 template).

---

## Phase 3 — Change summary

Group changed files by domain layer and write a concise Korean summary:

1. **무엇이 바뀌었는지** — describe the intent, not just file names.
2. **왜 바뀌었는지** — reference the spec, ADR, or issue that drove the work.
3. **어떻게 바뀌었는지** — key design decisions, new abstractions introduced, or
   interfaces modified.

Keep each section to ≤ 5 bullet points. If a section would exceed 5 points,
split by sub-module.

---

## Phase 4 — Risk analysis

For each changed area, identify risks across these dimensions:

| Dimension | Questions to ask |
|---|---|
| **Contract breaks** | Does any public interface, DTO shape, or tool signature change in a way that affects callers not in this branch? |
| **Test coverage gaps** | Are there important paths through changed code that have no test? |
| **Data integrity** | Do any schema migrations, store writes, or serialization formats change in a backward-incompatible way? |
| **Concurrency / async** | Are there new awaitable call chains, shared mutable state, or race conditions? |
| **External dependencies** | Does anything now depend on a new third-party library, API endpoint, or environment variable that isn't documented? |
| **Performance** | Are there new O(n²) loops, unbounded queries, or large in-memory structures? |
| **Security (OWASP Top 10)** | Input validation, auth, injection, data exposure? |

Rate each risk in Korean as **낮음 / 중간 / 높음**. Suppress Low risks to keep
the body readable. Include at least one risk entry even if all are Low — write
"높은 리스크는 확인되지 않았으며, 경미한 리스크는 아래와 같습니다."

---

## Phase 5 — Draft and submit the PR

### PR title

Write a concise Korean title without commit-type or scope prefixes. Do not use
prefixes such as `feat:`, `fix:`, `docs:`, or `feat(scope):`.

The title should describe what the PR changes directly, for example
`메모리 컨텍스트 조립 흐름 개선`.

### PR body template

Fill every section in Korean. Do not leave placeholder text.

````markdown
## 요약

<!-- 2–4문장: 이 PR이 무엇을 제공하고 왜 필요한지 -->

## 계층별 변경 사항

<!-- 도메인 계층별 bullet group. 관련 spec section이 있으면 참조. -->

### 문서 / 스펙
- ...

### 테스트
- ...

### 구현
- ...

## 워크플로우 감사

| 산출물 | 상태 | 비고 |
|---|---|---|
| 아키텍처 문서 | ✅ 있음 / ❌ 없음 | 경로 또는 "해당 없음" |
| 모듈 스펙 | ✅ 있음 / ❌ 없음 | 경로 |
| PRD | ✅ 있음 / ⚠️ 없음(선택) | 경로 또는 "scratch에 없음" |
| 이슈 | ✅ 있음 / ⚠️ 없음(선택) | 경로 또는 "scratch에 없음" |
| 구현 전 테스트 | ✅ 확인됨 / ❌ 위반 / ⚠️ 예외(리팩터) | 세부 내용 |

## 리스크 분석

| 영역 | 리스크 | 심각도 | 완화 방안 |
|---|---|---|---|
| ... | ... | 중간 | ... |

## 체크리스트

- [ ] 필수 워크플로우 산출물이 모두 존재하며 순서대로 작성됨
- [ ] 테스트가 주요 성공 경로와 최소 하나의 오류/엣지 케이스를 다룸
- [ ] 문서화되지 않은 새 환경 변수나 secret이 추가되지 않음
- [ ] 도메인 용어나 모듈 경계가 바뀐 경우 `CONTEXT.md`를 업데이트함
- [ ] 아키텍처 결정이 생긴 경우 관련 ADR을 생성하거나 업데이트함
````

### Submit

Run:

```bash
gh pr create \
   --title "<prefix 없는 한글 제목>" \
   --body "<한글 본문>" \
  --base main \
  --draft
```

Open as **draft** by default unless the user explicitly says "ready for review"
or "not draft". After submission, print the PR URL.

---

## Blockers — when NOT to open the PR

Stop and report a blocker if any of the following is true:

1. A **required** workflow artifact is missing (architecture doc or module spec
   for touched modules).
2. Implementation commits predate the spec for the same module by more than one
   commit (i.e., implementation was not driven by the spec).
3. There are **zero tests** for newly introduced behaviour (excluding pure
   documentation or config-only changes).
4. `git status` shows uncommitted changes that appear load-bearing.

For each blocker, state:

> **BLOCKER:** `<what is missing>` — `<what the user needs to do to unblock>`

Do not create workaround PRs or bypass blockers silently.
