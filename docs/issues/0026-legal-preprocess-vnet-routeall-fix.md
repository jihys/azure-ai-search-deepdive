# 0026: 법령 4종 preprocessing 미동작 원인 분석 및 수정 (Private 배포)

**Status:** done
**Parent:** N/A (incident-response)

## 증상

- 법령 4종(`prec`, `detc`, `expc`, `admrul`)에서 crawl 이후 preprocess 단계가 정상 완료되지 않음
- 결과적으로 `processed-documents/{source}/...` 갱신이 실패하거나 지연되어 인덱싱 결과가 비정상

## 원인

- Private 배포(`infra/sweden`, `infra/korea`)에서 Storage는 `publicNetworkAccess: Disabled`
- preprocess Function App은 VNet Integration(`virtualNetworkSubnetId`)만 설정되어 있고,
  `vnetRouteAllEnabled`가 빠져 있어 Storage Private Endpoint 경로로의 아웃바운드 라우팅이 보장되지 않음

## 조치

- 아래 Bicep 모듈에 `vnetRouteAllEnabled: true` 추가
  - `infra/sweden/modules/function-preprocess.bicep`
  - `infra/korea/modules/function-preprocess.bicep`

## 검증

- `az bicep build --file infra/sweden/modules/function-preprocess.bicep` 성공
- `az bicep build --file infra/korea/modules/function-preprocess.bicep` 성공

## 재발 방지

- Storage Private Endpoint를 사용하는 Function App 모듈에서
  `virtualNetworkSubnetId`와 `vnetRouteAllEnabled`를 세트로 유지
