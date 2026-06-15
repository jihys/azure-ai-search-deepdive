# Hub/VNet 모듈 제거 (sweden-public)

## Parent

[PRD-cleanup.md](../prd/PRD-cleanup.md)

## What to build

`infra/sweden-public/` PUBLIC variant에서 Hub(Foundry Hub/Project/KeyVault)와 VNet 관련 모듈을 제거한다.
PUBLIC variant는 모든 리소스가 공개적으로 접근 가능한 워크샵/랩 환경이므로, VNet이나 Foundry Hub가 불필요하다.

**main.bicep 수정:**
- `module vnet` 블록 전체 제거
- `module foundryHub` 블록 전체 제거
- 3개 FC1 Function App 모듈 호출에서 `funcSubnetId: vnet.outputs.funcFc1SubnetId` 파라미터 제거
- outputs에서 `vnetName`, `foundryHubName`, `foundryProjectName`, `foundryKeyVaultName` 제거
- 파일 상단 주석에서 VNet 관련 설명 제거

**FC1 모듈 수정 (3개):**
- `function-crawler-consumption.bicep`: `param funcSubnetId string` 및 `virtualNetworkSubnetId`, `vnetRouteAllEnabled` 제거
- `function-preprocess-fc1.bicep`: 동일
- `function-skills-fc1.bicep`: 동일

**모듈 파일 삭제:**
- `modules/vnet.bicep` 삭제
- `modules/foundry-hub.bicep` 삭제

## Acceptance criteria

- [ ] main.bicep에서 `vnet`, `foundryHub` 모듈 참조 완전 제거
- [ ] FC1 모듈 3개에서 `funcSubnetId` 관련 코드 완전 제거
- [ ] `modules/vnet.bicep` 삭제됨
- [ ] `modules/foundry-hub.bicep` 삭제됨
- [ ] outputs에서 VNet/Foundry 관련 출력 제거됨
- [ ] 남은 Bicep 코드에 `vnet`이나 `foundryHub` 참조가 없음
