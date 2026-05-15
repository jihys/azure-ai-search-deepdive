// ============================================
// [HISTORICAL] Foundry Agent Service 활성화 패치
//
// ⚠️  이 패치의 내용은 이제 main에 통합되었습니다:
//     - allowProjectManagement: true
//     - bypass: 'AzureServices'
//     - foundryProject sub-resource
//     - SystemAssigned identity
//   → infra/sweden/modules/openai.bicep 참조
//
// 완전한 재배포 시에는 main.bicep 으로 충분합니다.
// 기존 환경의 운영중 패치 용도로만 유지됩니다.
//
// 사용법 (in-place patch only):
//   az deployment group create \
//     --resource-group rg-rag-indexing-lab-swc \
//     --template-file infra/sweden/patches/add-foundry-project.bicep \
//     --parameters accountName=ais-ragi-<suffix> location=swedencentral
// ============================================

@description('기존 AIServices 계정 이름 (예: ais-ragi-dyn6dtfu)')
param accountName string

@description('계정과 동일한 리전 (예: swedencentral)')
param location string

@description('생성할 Foundry Project 이름')
param projectName string = 'proj-ragi-default'

@description('Project display name')
param projectDisplayName string = 'RAG Indexing Lab Foundry Project'

// 기존 AIServices 계정을 동일 이름으로 PATCH
// allowProjectManagement: true 만 추가, 나머지 속성은 기존 값 유지
resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'  // Search → AOAI trusted call 허용 (Knowledge Agent planner)
    }
    // Foundry Agent Service 활성화 핵심 플래그
    allowProjectManagement: true
  }
}

// Foundry Project (신형 sub-resource — Hub/Project 와 별개)
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiAccount
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectDisplayName
    description: 'Foundry Agent Service project for legal RAG demo (Scenario E)'
  }
}

output projectName string = foundryProject.name
output projectId string = foundryProject.id
output foundryEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'
