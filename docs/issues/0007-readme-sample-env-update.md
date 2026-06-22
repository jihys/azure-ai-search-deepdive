# 0007: README.md / sample.env sweden-public 기본 배포 기준 업데이트

**Status:** done
**Parent:** N/A (legacy issue)

**Created**: 2026-06-15

## 요약

README.md와 sample.env를 `infra/sweden-public/` 기본 배포 기준으로 업데이트한다.
Private 변형(`infra/sweden/`)은 조건부 안내로 유지.

## 변경 사항

### README.md

1. **네트워크 설명**: Private 전용 → sweden-public 권장 / sweden private 선택
2. **리소스 테이블**: EP1/VNet/PE 기준 → FC1/공개 엔드포인트 기준 + Private 변형 안내
3. **배포 명령**: `infra/sweden/` → `infra/sweden-public/` 기본, private는 주석 처리
4. **SPL 승인 섹션**: sweden-public 시 건너뛰기 안내 추가
5. **Private Network 섹션**: sweden private 변형에만 해당됨을 명시
6. **변경이력 v2.1 추가**: 권장 배포, FC1, 공개 엔드포인트, Foundry Hub, 폴링 타임아웃

### sample.env

1. `AZURE_RESOURCE_GROUP` → `rg-rag-indexing-lab-swc-pub`
2. `AZURE_LOCATION` → `swedencentral`
3. `AZURE_STORAGE_CONNECTION_STRING` → 주석 처리 (MI 기반 인증)
4. `FOUNDRY_PROJECT_ENDPOINT` 추가

## Acceptance Criteria

- [x] README에서 sweden-public이 권장 배포로 명시
- [x] 리소스 테이블이 FC1/공개 기준
- [x] 배포 명령이 sweden-public 기본
- [x] SPL 승인 섹션에 조건부 안내
- [x] 변경이력 v2.1 추가
- [x] sample.env 업데이트 완료
