// ============================================
// Azure AI Services (Foundry 호환) + Model Deployment
// kind: AIServices = Azure AI Foundry 백엔드
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

var accountName = 'ais-ragi-${take(suffix, 8)}'

resource openaiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    // Private Network: 공개 인터넷 접근 차단
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
    }
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

output endpoint string = openaiAccount.properties.endpoint
output accountName string = openaiAccount.name
output accountId string = openaiAccount.id
output gptDeploymentName string = gptDeployment.name
