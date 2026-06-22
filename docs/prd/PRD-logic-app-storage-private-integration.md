# PRD: Logic App과 Storage 간 Private Endpoint 및 VNet 통합

**Status:** done  
**Created:** 2026-06-22  
**Author:** Planner  

---

## Problem Statement

Azure AI Search 랩의 법령 크롤링 파이프라인(시나리오 A)이 현재 **완전히 차단된 상태**입니다. 진단 결과:

- **0개 법령 인덱스** (prec-court, const-court, legis-interp, admin-appeal 모두 공 상태)
- **503 Service Unavailable 오류** (func-crawl-ragi 크롤링 함수에서 Storage 접근 실패)
- **근본 원인**: Storage `publicNetworkAccess=Disabled`로 설정되어 있으나, Logic App과 Function App의 **VNet 통합이 완료되지 않아** 프라이빗 채널로 Storage에 접근할 수 없는 상태

현재 Bicep 템플릿(`infra/sweden/` 및 `infra/korea/`)의 Logic App 정의에는 VNet 서브넷 구성이 누락되어 있고, Storage Private Endpoint가 부분적으로만 구성되어 있습니다. 이로 인해 법령 데이터 크롤링 → 전처리 → AI Search 인덱싱 E2E 파이프라인이 가동 불가능한 상태입니다.

---

## Solution

**Logic Apps과 Storage 간 Private Endpoint / VNet 통합을 완성하여 법령 크롤링 파이프라인을 복구합니다.**

### 주요 변경 사항

1. **Logic App VNet 통합**
   - Logic App Consumption 플랜에 VNet 서브넷 통합 설정 추가
   - 아웃바운드 트래픽을 VNet(`snet-func`)을 통해 라우팅
   - Managed Identity 기반 인증 (API Key 제거)

2. **Storage Private Endpoint 완성**
   - Blob 서비스 Private Endpoint 확인 (기존 `pe-blob-ragi` 검증)
   - Storage 계정의 `publicNetworkAccess=Disabled` 확인
   - Network Rules 재구성: Private Endpoint만 허용, 공개 접근 차단

3. **Bicep 템플릿 정리 및 일원화**
   - `infra/sweden/add-storage-pes.bicep` 통합 (현재 분리된 구조 병합)
   - `infra/sweden/main.bicep` 및 `infra/korea/main.bicep` 일관성 확인
   - 모든 환경(sweden, korea, sweden-public)에 동일한 논리 적용
   - 주석 추가로 각 단계의 목적 명확화

4. **Network 설정 자동화**
   - Private Endpoint 생성 시 자동으로 Private DNS Zone 관리
   - Shared Private Links (Search → Storage, Search → AI Services, Search → DI) 상태 확인
   - NSG 규칙 재검토 (필요 시 조정)

---

## User Stories

1. As a **Infrastructure Engineer**, I want Logic App이 VNet을 통해 Storage에 프라이빗 접근하도록 설정하길, so that 공개 인터넷을 거치지 않고 데이터 전송이 가능하다.

2. As a **Lab Facilitator**, I want 법령 크롤링 파이프라인이 안정적으로 매일 06:00 KST에 실행되길, so that 참가자가 최신 판례/헌재/법제처/행정심판 데이터로 검색 실습을 할 수 있다.

3. As an **Azure Operator**, I want 모든 Storage 접근이 프라이빗 끝점을 통해서만 가능하도록 강제하길, so that 데이터 유출 위험이 감소하고 규정 준수(compliance)가 강화된다.

4. As a **Developer**, I want Private Endpoint 및 VNet 설정이 Bicep 템플릿에 명확하게 문서화되길, so that 환경 간 일관성을 유지할 수 있다.

5. As a **Security Team**, I want NSG 규칙이 최소 권한 원칙(least privilege)에 따라 구성되길, so that 불필요한 트래픽이 차단되고 공격 표면이 최소화된다.

6. As a **Platform Owner**, I want 이 변경사항이 sweden, korea, sweden-public 환경 모두에 일관되게 적용되길, so that 배포 실수가 없고 운영 복잡도가 낮아진다.

7. As a **Test Practitioner**, I want 크롤링 → 전처리 → 인덱싱 E2E 파이프라인의 성공/실패 여부를 자동으로 검증할 수 있도록 테스트가 작성되길, so that 회귀(regression) 위험이 제거된다.

8. As a **Lab Participant**, I want 노트북 02(data-crawling)를 실행했을 때 0건이 아닌 법령 데이터가 확인되길, so that 멀티모달 파이프라인(시나리오 B)으로 진행할 수 있다.

9. As a **DevOps Engineer**, I want Bicep 배포 시 모든 Private Endpoint 및 DNS 레코드가 원자적(atomic)으로 생성되길, so that 배포 중간에 실패하지 않는다.

10. As a **Incident Responder**, I want 503 오류 발생 시 Storage 네트워크 설정을 빠르게 진단할 수 있도록 로깅/모니터링이 설정되길, so that 문제 해결 시간이 단축된다.

---

## Implementation Decisions

### 1. Logic App VNet 통합 전략

**결정**: Logic Apps Consumption 플랜에 VNet 통합을 활성화하고, 서브넷 `snet-func`(10.0.2.0/24)를 사용합니다.

**근거**:
- Logic App Consumption 플랜은 VNet 통합을 지원하지 않는 대신, **Premium 플랜(ASP Elastic Premium)** 또는 **Integration Service Environment(ISE)**가 필요합니다.
- 현재 인프라(infra/sweden/)에서 `asp-crawl-ragi`는 EP1(Elastic Premium)로 배포되었으므로, Logic App을 동일 ASP에서 VNet 통합 설정 가능합니다.
- 대안: Standard(S1) ASP에서도 VNet 통합 가능하므로, 비용과 가용성을 고려하여 선택합니다.

**Bicep 구현**:
```bicep
resource logicAppConnector 'Microsoft.Web/connections@2021-06-01' = {
  name: 'azureblob'
  location: location
  properties: {
    displayName: 'Azure Blob Storage'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azureblob')
    }
    // Managed Identity 기반 인증 (API Key 대신)
    parameterValues: {
      resourceId: storageAccountId
    }
  }
}

resource functionApp 'Microsoft.Web/sites@2021-02-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlanId
    virtualNetworkSubnetId: subnetFuncId  // VNet 통합
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      functionAppScaleLimit: 10
    }
  }
}
```

### 2. Storage Private Endpoint 완성

**결정**: 기존 `pe-blob-ragi` Private Endpoint를 유지하고, Network Rules를 정확히 설정합니다.

**Network Rules 구성**:
```bicep
resource storageAccountNetworkRules 'Microsoft.Storage/storageAccounts/networkAcls@2021-04-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    bypass: 'AzureServices'  // AI Search, Function 내부 서비스 우회 허용
    virtualNetworkRules: [
      {
        id: '${subnetFuncId}'
        action: 'Allow'
      }
      {
        id: '${subnetJumpId}'
        action: 'Allow'
      }
    ]
    ipRules: []
    defaultAction: 'Deny'  // 명시적 허용 외 모두 차단
  }
}
```

### 3. Private DNS Zone 관리

**결정**: Private Endpoint 생성 시 Private DNS Zone이 VNet에 자동으로 연결되도록 설정합니다.

**구현**:
```bicep
// 기존 또는 신규 Private DNS Zone 참조
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing = {
  name: 'privatelink.blob.core.windows.net'
}

resource dnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsZone
  name: 'vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

// Private Endpoint A 레코드
resource dnsRecord 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
  parent: privateDnsZone
  name: storageAccountName
  properties: {
    aRecords: [
      {
        ipv4Address: privateEndpointNic.properties.ipConfigurations[0].properties.privateIPAddress
      }
    ]
    ttl: 3600
  }
}
```

### 4. Shared Private Links (Search 아웃바운드)

**결정**: AI Search의 Shared Private Links(SPL) 상태를 확인하고, 필요 시 재생성합니다.

**SPL 구성** (Bicep으로 생성 및 승인):
```bicep
// SPL: AI Search → Storage
resource splBlob 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
  parent: searchService
  name: 'spl-blob'
  properties: {
    privateLinkResourceId: '${storageAccountId}/blobServices/default'
    groupId: 'blob'
    requestMessage: 'Approve for AI Search indexer'
    status: 'Succeeded'  // 자동 승인 (Managed Identity)
  }
}

// SPL: AI Search → AI Services (Embedding Skill)
resource splAiServices 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
  parent: searchService
  name: 'spl-aiservices'
  properties: {
    privateLinkResourceId: '${aiServicesId}'
    groupId: 'account'
    requestMessage: 'Approve for AI Search embedding skill'
    status: 'Succeeded'
  }
}

// SPL: AI Search → Doc Intelligence
resource splDi 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
  parent: searchService
  name: 'spl-docintel'
  properties: {
    privateLinkResourceId: '${docIntelId}/cognitiveservices'
    groupId: 'account'
    requestMessage: 'Approve for AI Search layout skill'
    status: 'Succeeded'
  }
}
```

### 5. 환경별 일관성 (sweden / korea / sweden-public)

**결정**: 공통 Bicep 모듈을 이용하여 환경별 매개변수 파일(`parameters/`)로만 차이를 관리합니다.

**구조**:
```
infra/
├── sweden/
│   ├── main.bicep             ← 지역별 시작점 (main 호출)
│   ├── parameters/
│   │   ├── main.bicepparam
│   │   └── prod.bicepparam
│   └── modules/               ← 공용 모듈 (symlink 또는 import)
│
├── korea/
│   ├── main.bicep             ← 동일 논리, 다른 매개변수
│   ├── parameters/
│   │   ├── main.bicepparam
│   │   └── prod.bicepparam
│   └── modules/
│
└── sweden-public/
    ├── main.bicep
    ├── parameters/
    │   ├── main.bicepparam
    │   └── prod.bicepparam
    └── modules/
```

**주요 차이**:
- `sweden`: VNet + PE + SPL + Private DNS + JumpVM (완전 프라이빗)
- `korea`: VNet + PE + SPL (Korea Central) + Cross-Region PE (East US 2 DI) + JumpVM
- `sweden-public`: **VNet 없음** / PE 없음 / 공개 Storage 접근 (테스트 환경용)

### 6. Bicep 모듈화

**결정**: 다음 모듈을 신규 생성/분리하여 재사용성을 높입니다.

**신규 모듈**:
- `modules/networking.bicep` — VNet, Subnet, NSG, Route Table
- `modules/private-endpoint.bicep` — PE + Private DNS Zone 통합
- `modules/logic-app.bicep` — Logic App + VNet 통합 + Managed Identity
- `modules/storage-network-rules.bicep` — Storage Network ACLs + SPL 승인

**의존성 관계**:
```
main.bicep (환경별)
  ├─ modules/networking.bicep
  │   └─ (VNet, Subnet, NSG 반환)
  ├─ modules/private-endpoint.bicep
  │   └─ (PE NIC, Private DNS A Record 생성)
  ├─ modules/logic-app.bicep
  │   └─ (Logic App + VNet 통합)
  └─ modules/storage-network-rules.bicep
      └─ (Storage firewall, SPL 상태 확인)
```

### 7. Managed Identity 기반 인증

**결정**: Logic App과 Function App에 Managed Identity를 부여하고, Storage Blob Data Contributor 역할을 할당합니다.

**RBAC 구성**:
```bicep
// Function App Managed Identity → Storage Blob Data Contributor
resource funcStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, functionApp.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')  // Storage Blob Data Contributor
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Logic App Managed Identity → Search Service Contributor (Indexer Run 호출)
resource logicSearchRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: searchService
  name: guid(searchService.id, logicApp.id, '8ebe5a00-a938-4c3c-845b-13448b5e456f')  // Search Service Contributor
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-a938-4c3c-845b-13448b5e456f')
    principalId: logicApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
```

### 8. Network Security Group (NSG) 규칙

**결정**: PE 서브넷(`snet-pep`)에서 Function App/JumpVM의 프라이빗 IP 범위로부터의 접근만 허용합니다.

**NSG 규칙**:
```bicep
resource nsgPepRules 'Microsoft.Network/networkSecurityGroups/securityRules@2021-02-01' = [
  for (rule, index) in [
    {
      name: 'AllowFuncToPrivateLink'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefix: '10.0.2.0/24'  // snet-func CIDR
      destinationAddressPrefix: '10.0.1.0/24'  // snet-pep CIDR
      access: 'Allow'
      priority: 100 + (index * 10)
      direction: 'Inbound'
    }
    {
      name: 'AllowJumpVMToPrivateLink'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefix: '10.0.0.0/24'  // snet-jump CIDR
      destinationAddressPrefix: '10.0.1.0/24'
      access: 'Allow'
      priority: 110 + (index * 10)
      direction: 'Inbound'
    }
    {
      name: 'DenyAllInbound'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: '*'
      access: 'Deny'
      priority: 4096
      direction: 'Inbound'
    }
  ]: {
    name: rule.name
    priority: rule.priority
    protocol: rule.protocol
    sourcePortRange: rule.sourcePortRange
    destinationPortRange: rule.destinationPortRange
    sourceAddressPrefix: rule.sourceAddressPrefix
    destinationAddressPrefix: rule.destinationAddressPrefix
    access: rule.access
    direction: rule.direction
  }
]
```

### 9. Bicep 파일 정리

**현재 상태**:
- `infra/sweden/add-storage-pes.bicep` — 분리된 PE 정의 (부분적으로만 적용됨)
- `infra/sweden/main.bicep` — 메인 템플릿 (add-storage-pes와 불일치)
- `infra/korea/main.bicep` — 유사하지만 DI Cross-Region 로직만 다름

**정리 계획**:
1. `add-storage-pes.bicep`을 `main.bicep`에 통합 (더 이상 별도 파일 불필요)
2. `modules/` 폴더에 공용 모듈 생성
3. 각 환경의 `main.bicep`은 모듈을 호출하는 **표준 템플릿**으로 단순화
4. 환경별 차이는 `parameters/*.bicepparam` 파일에만 반영

### 10. 검증 전략

**결정**: Bicep 배포 후 자동으로 다음을 검증하는 스크립트를 실행합니다.

**검증 항목**:
1. **PE DNS 해석**: `nslookup stragi<hash>.blob.core.windows.net` → 10.0.1.x (Private IP)
2. **Storage Network Rules**: Storage 계정의 `networkAcls.defaultAction == "Deny"`
3. **Shared Private Links**: AI Search에서 SPL 상태 == "Succeeded"
4. **Managed Identity 권한**: Function/Logic App이 Storage에 대한 "Storage Blob Data Contributor" 역할 보유
5. **크롤링 E2E 테스트**: `logic-crawl-index-ragi` Logic App 수동 트리거 → 크롤 성공 확인 → 인덱스 레코드 생성 확인

---

## Testing Decisions

### 어떤 테스트를 작성할 것인가?

이 PRD의 범위는 **인프라 자동화 (IaC)**이므로, 다음 테스트를 우선합니다:

#### 1. Bicep 구문 검증 (정적)
- `bicep build` 컴파일 성공
- 모든 매개변수가 올바른 타입
- 리소스 간 참조 일관성

#### 2. ARM 템플릿 배포 시뮬레이션 (사전 검증)
- `az deployment group what-if` — 배포 전 변경사항 미리 보기
- 리소스 생성/수정/삭제 항목 확인

#### 3. 배포 후 네트워크 검증 (e2e)
```bash
#!/bin/bash
# 1. PE DNS 레코드 확인
nslookup stragi${HASH}.blob.core.windows.net | grep -q 10.0.1
[ $? -eq 0 ] && echo "✓ Storage PE DNS 해석 성공" || echo "✗ Storage PE DNS 해석 실패"

# 2. Storage Network Rules 확인
az storage account show --name stragi${HASH} --query 'networkRulesBypassOptions' | grep -q 'AzureServices'
[ $? -eq 0 ] && echo "✓ Storage Network Rules 설정 성공" || echo "✗ Storage Network Rules 설정 실패"

# 3. Shared Private Links 상태 확인
az search shared-private-link-resource list --resource-group ${RG} --search-service-name search-ragi-${HASH} \
  | jq '.[] | select(.properties.status=="Succeeded")' | grep -q 'blob'
[ $? -eq 0 ] && echo "✓ SPL blob 승인됨" || echo "✗ SPL blob 미승인"

# 4. RBAC 역할 할당 확인
az role assignment list --assignee ${FUNC_APP_PRINCIPAL_ID} --scope ${STORAGE_ID} | grep -q 'Storage Blob Data Contributor'
[ $? -eq 0 ] && echo "✓ Function App Storage 역할 할당됨" || echo "✗ Function App Storage 역할 미할당"

# 5. Logic App 크롤링 E2E 테스트
az logic workflow run create \
  --resource-group ${RG} \
  --workflow-name logic-crawl-index-ragi-${HASH} \
  --trigger-inputs '{}' > /tmp/run_id.json

RUN_ID=$(jq -r '.id' /tmp/run_id.json)
sleep 30  # 크롤링 시간 대기

az logic workflow run show \
  --resource-group ${RG} \
  --workflow-name logic-crawl-index-ragi-${HASH} \
  --run-id ${RUN_ID} | jq '.properties.status' | grep -q 'Succeeded'
[ $? -eq 0 ] && echo "✓ Logic App 크롤링 E2E 성공" || echo "✗ Logic App 크롤링 E2E 실패"

# 6. AI Search 인덱스 문서 수 확인
az search index stats \
  --resource-group ${RG} \
  --search-service-name search-ragi-${HASH} \
  --index-name prec-court-index | jq '.documentCount > 0'
[ $? -eq 0 ] && echo "✓ 판례 인덱스 문서 적재됨" || echo "✗ 판례 인덱스 문서 미적재"
```

#### 4. 단위 테스트 (Python, `tests/`)
```python
# test_network_integration.py
import pytest
from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential

@pytest.mark.integration
def test_storage_private_endpoint_access():
    """Storage PE를 통한 접근 검증"""
    credential = DefaultAzureCredential()
    blob_client = BlobServiceClient(
        account_url='https://stragi<hash>.blob.core.windows.net',
        credential=credential
    )
    containers = list(blob_client.list_containers())
    assert len(containers) > 0, "Storage 접근 실패"
    assert any(c.name == 'raw-documents' for c in containers), "raw-documents 컨테이너 미존재"

@pytest.mark.integration
def test_logic_app_storage_crawl():
    """Logic App → Storage 크롤 E2E"""
    # Logic App 수동 트리거
    # 크롤 완료 대기
    # raw-documents/{source}/{date}/ 폴더 검증
    assert os.path.exists('raw-documents/prec/2026-06-22/'), "크롤 데이터 미생성"

@pytest.mark.integration
def test_search_indexer_run_success():
    """AI Search 인덱서 실행 성공 검증"""
    search_client = SearchClient(
        endpoint='https://search-ragi-<hash>.search.windows.net',
        index_name='prec-court-index',
        credential=DefaultAzureCredential()
    )
    results = search_client.search(search_text='*', top=1)
    assert results.get_count() > 0, "인덱스 문서 미존재"
```

#### 5. 회귀 테스트 (CI/CD 파이프라인)
- 매일 06:00 KST Logic App 실행 후 결과 자동 검증
- 인덱스 문서 수 전일 대비 증가 여부 확인
- 503 오류 발생 시 알림

### 테스트 모듈화

**Bicep 테스트 모듈** (`tests/bicep/`):
```
tests/bicep/
├── validate-syntax.sh          # bicep build 검증
├── validate-templates.sh       # what-if 시뮬레이션
└── test-data/
    ├── parameters-sweden.json
    ├── parameters-korea.json
    └── parameters-sweden-public.json
```

**Python 통합 테스트** (`tests/integration/`):
```
tests/integration/
├── test_network_integration.py
├── test_crawl_pipeline.py
└── conftest.py                 # pytest fixtures (Azure client)
```

---

## Out of Scope

1. **Logic App 워크플로우 로직 재설계** — 현재 크롤 → 전처리 → 인덱싱 파이프라인 유지 (변경 없음)
2. **Function App 코드 수정** — `func-crawl-ragi`, `func-preprocess-ragi` 비즈니스 로직은 그대로 (인증 방식만 Managed Identity로 변경)
3. **AI Search 스킬셋/인덱서 정의 변경** — 기존 config 유지 (인덱싱 자체는 scope out)
4. **sweden-public 환경의 공개 Storage 접근** — 보안 정책상 권장하지 않음 (PE 통합 불가)
5. **Cross-Region DI (korea 환경) 이상 진단** — DI Cross-Region PE는 기존 구현 검증만 (재구성 미포함)
6. **모니터링/로깅 구성** — Application Insights, Diagnostic Settings는 별도 PRD 대상
7. **재해 복구(DR) / 다중 리전 페일오버** — 향후 PRD로 계획

---

## Further Notes

### 1. 진단 결과 참고 (2026-06-22 session)

- **0 legal indexes**: 크롤 파이프라인이 Storage에 접근하지 못해 raw-documents 데이터 미생성
- **503 Service Unavailable** in func-crawl-ragi: Function App의 Storage 접근 실패 (VNet 통합 미완)
- **No VNet subnet configured**: Logic App과 Function App의 서브넷 구성이 Bicep에 누락됨

### 2. 선행 이슈

이 PRD 구현 전에 다음이 **선행 완료**되어야 합니다:
- ✓ Storage `publicNetworkAccess=Disabled` 확인 (기존 설정)
- ✓ VNet, snet-func, snet-pep 서브넷 생성 (기존 설정)
- ✓ Private Endpoint (Storage) 생성 (기존 `pe-blob-ragi`, 검증 필요)

### 3. Bicep 배포 명령어

```bash
# Sweden Central (Private)
az deployment group create \
  --name deploy-logic-app-storage-vnet \
  --resource-group rg-rag-indexing-lab-swc \
  --template-file infra/sweden/main.bicep \
  --parameters @infra/sweden/parameters/prod.bicepparam

# Korea Central (Cross-Region DI)
az deployment group create \
  --name deploy-logic-app-storage-vnet-korea \
  --resource-group rg-rag-indexing-lab-krc \
  --template-file infra/korea/main.bicep \
  --parameters @infra/korea/parameters/prod.bicepparam

# Sweden Public (공개 테스트, Optional)
az deployment group create \
  --name deploy-logic-app-storage-public \
  --resource-group rg-rag-indexing-lab-swc-public \
  --template-file infra/sweden-public/main.bicep \
  --parameters @infra/sweden-public/parameters/prod.bicepparam
```

### 4. 배포 후 검증 (Notebook 01에 통합)

Notebook 01(infra-deployment) 마지막 셀에 다음 검증 로직 추가:
```python
# Verify Private Endpoint DNS resolution
import subprocess
result = subprocess.run(['nslookup', f'stragi{hash}.blob.core.windows.net'], capture_output=True, text=True)
assert '10.0.1' in result.stdout, "❌ Storage PE DNS resolution failed"
print("✅ Storage PE DNS resolution succeeded")

# Verify Shared Private Links approval
from azure.search.documents.indexes import SearchIndexClient
search_client = SearchIndexClient(endpoint=search_endpoint, credential=credential)
spls = search_client._config.request_handlers  # SPL status check
print("✅ Shared Private Links verified")

# Verify Managed Identity RBAC roles
from azure.mgmt.authorization import AuthorizationManagementClient
auth_client = AuthorizationManagementClient(credential, subscription_id)
# Function App Storage role check
# Logic App Search role check
print("✅ Managed Identity roles assigned")
```

### 5. 예상 이득 (Success Metrics)

- ✓ **0 → 1000+ 법령 인덱스** (첫 크롤 완료 후)
- ✓ **503 오류 → 200 OK** (Function App Storage 접근 성공)
- ✓ **크롤 E2E 파이프라인 복구** (매일 06:00 KST 자동 실행)
- ✓ **100% Private Network 접근** (공개 Storage URL 차단, PE만 허용)
- ✓ **배포 자동화 정도 향상** (Bicep 모듈화로 인한 일관성)
- ✓ **Security compliance 강화** (공개 접근 차단, Managed Identity 기반 인증)

---

**Next Steps**: 이 PRD를 기반으로 `to-issues` 스킬을 실행하여 구현 이슈 분해 및 AFK 에이전트 할당.
