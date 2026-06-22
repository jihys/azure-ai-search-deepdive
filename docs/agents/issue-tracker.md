# Issue Tracker

이 저장소는 GitHub Issues 대신 문서 기반 로컬 트래커를 사용한다.

## 트래커 경로

- PRD: `docs/prd/PRD-*.md`
- 구현 이슈: `docs/issues/NNNN-*.md`
- 보류/제외 항목(필요 시): `.scratch/out-of-scope/*.md`

## 발행 규칙

- PRD를 먼저 발행하고, 해당 PRD를 Parent로 가지는 구현 이슈를 발행한다.
- 구현 시작 단위는 PRD가 아니라 개별 이슈 문서다.
- 이슈 번호는 `docs/issues/`의 최신 번호 다음 값을 사용한다.

## 상태 표기 규칙

각 문서 상단에 아래 메타데이터를 유지한다.

```md
**Status:** ready-for-agent
**Parent:** [PRD-...](../prd/PRD-....md)
```

상태 문자열은 `docs/agents/triage-labels.md`의 용어를 따른다.

운영 장애 대응 이슈처럼 PRD를 선행하지 않는 예외 케이스는 아래 형식을 허용한다.

```md
**Status:** done
**Parent:** N/A (incident-response)
```