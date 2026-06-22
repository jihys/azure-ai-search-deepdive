# Triage Labels

이 저장소는 문서 기반 트래커를 사용하므로, 라벨 대신 상태 문자열을 문서 메타데이터로 기록한다.

| Canonical role | 저장소 상태 문자열 | 의미 |
|---|---|---|
| `needs-triage` | `needs-triage` | 검토 필요 |
| `needs-info` | `needs-info` | 추가 정보 대기 |
| `ready-for-agent` | `ready-for-agent` | AFK 에이전트 실행 준비 완료 |
| `ready-for-human` | `ready-for-human` | 사람 구현 필요 |
| `done` | `done` | 구현/검증 완료 |
| `wontfix` | `wontfix` | 미수용 |

문서 기반 이슈에서는 `Status` 필드에 위 문자열 중 하나를 직접 기록한다.