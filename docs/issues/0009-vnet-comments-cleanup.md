# 0009 — Bicep 주석 및 docstring VNet/PE 설명 정확화

- **Status**: done
- **Type**: fix/docs

## 문제

`infra/sweden-public/` Bicep 모듈과 `logic-apps/` Function App docstring에서
VNet Integration / Private Endpoint를 전제로 한 주석이 남아 있어
실제 배포 구성과 불일치.

## 변경 내역

| 파일 | 변경 |
|------|------|
| `infra/sweden-public/modules/function-crawler-consumption.bicep` | L3 주석에서 VNet Integration 제거, L17 FC1 설명에서 VNet integration 제거 |
| `logic-apps/crawl-function/function_app.py` | docstring: `VNet Integration → Storage Private Endpoint` → `공개 엔드포인트 또는 VNet Integration` |
| `logic-apps/preprocess-function/function_app.py` | docstring: 동일 패턴 수정 |
| `docs/infrastructure.md` | 문서 상단에 `sweden-public` 배포 차이 안내 추가 |

`infra/sweden-public/modules/function-preprocess-fc1.bicep`와 `function-skills-fc1.bicep`는
VNet 관련 주석이 이미 없어 변경 불필요.
