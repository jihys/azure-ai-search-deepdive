// ============================================
// Azure AI Services (Foundry 호환) + Model Deployment + Foundry Project
// kind: AIServices = Azure AI Foundry 백엔드
// allowProjectManagement: true → Foundry Agent Service 활성화
// GPT-5.4 GlobalStandard (리전 무관 글로벌 배포)
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Embedding 모델 배포명')
param embeddingDeploymentName string = 'text-embedding-3-large'

@description('GPT-5.4 모델 배포명')
param gptDeploymentName string = 'gpt-5.4'

@description('GPT 모델 이름')
param gptModelName string = 'gpt-5.4'

@description('GPT 모델 버전')
param gptModelVersion string

@description('Foundry Agent Service 프로젝트 이름 (Scenario E)')
param foundryProjectName string = 'proj-ragi-default'

var accountName = 'ais-ragi-${take(suffix, 8)}'

resource openaiAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
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
    // Private Network: 공개 인터넷 접근 차단
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'  // Search → AOAI trusted call 허용 (Knowledge Agent planner)
    }
    // Foundry Agent Service 활성화 핵심 플래그 — project sub-resource 생성 허용
    allowProjectManagement: true
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openaiAccount
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: 120
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openaiAccount
  name: gptDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: gptModelName
      version: gptModelVersion
    }
  }
  dependsOn: [
    embeddingDeployment
  ]
}

// ── Foundry Agent Service Project (sub-resource) ──
// AIProjectClient endpoint: https://<accountName>.services.ai.azure.com/api/projects/<projectName>
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: openaiAccount
  name: foundryProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'RAG Indexing Lab Foundry Project'
    description: 'Foundry Agent Service project for legal RAG demo (notebook 04 Scenario E)'
  }
}

output endpoint string = openaiAccount.properties.endpoint
output accountName string = openaiAccount.name
output accountId string = openaiAccount.id
output gptDeploymentName string = gptDeployment.name
output foundryProjectName string = foundryProject.name
output foundryProjectId string = foundryProject.id
output foundryProjectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
