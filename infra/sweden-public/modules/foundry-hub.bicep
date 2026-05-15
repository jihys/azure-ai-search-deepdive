// ============================================
// Azure AI Foundry Hub + Project
// BYO VNet 방식: 기존 VNet + Private Endpoint 활용
// - Hub PE는 private-endpoints.bicep에서 생성
// - AI Search, AI Services는 기존 PE/DNS Zone으로 접근
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('기존 Storage Account 리소스 ID')
param storageAccountId string

@description('기존 Storage Account 이름')
param storageAccountName string

@description('AI Search 서비스 리소스 ID')
param searchServiceId string

@description('AI Search 서비스 이름')
param searchServiceName string

@description('AI Search 엔드포인트')
param searchEndpoint string

@description('AI Services 리소스 ID')
param aiServicesId string

@description('AI Services 계정 이름')
param aiServicesName string

@description('AI Services 엔드포인트')
param aiServicesEndpoint string

var hubName = 'hub-ragi-${take(suffix, 8)}'
var projectName = 'proj-ragi-${take(suffix, 8)}'
var keyVaultName = 'kv-ragi-${take(suffix, 8)}'

// ── Key Vault (Hub 필수 종속성) ──
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── AI Foundry Hub (BYO VNet) ──
// Managed Network 없이 배포 → 기존 VNet의 PE/DNS Zone 활용
// Hub 자체 PE는 private-endpoints.bicep에서 snet-pep에 생성
resource hub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: hubName
  location: location
  kind: 'Hub'
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'RAG Indexing Lab Hub'
    description: 'Private AI Search 연결용 Azure AI Foundry Hub (BYO VNet)'
    storageAccount: storageAccountId
    keyVault: keyVault.id
    publicNetworkAccess: 'Enabled'
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── AI Foundry Project ──
resource project 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = {
  name: projectName
  location: location
  kind: 'Project'
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'RAG Indexing Lab Project'
    hubResourceId: hub.id
    publicNetworkAccess: 'Enabled'
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Connection: AI Search ──
resource searchConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: hub
  name: 'aisearch'
  properties: {
    category: 'CognitiveSearch'
    target: searchEndpoint
    authType: 'AAD'
    metadata: {
      ApiType: 'azure'
      ApiVersion: '2024-07-01'
      ResourceId: searchServiceId
    }
  }
}

// ── Connection: AI Services (OpenAI) ──
resource aiServicesConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = {
  parent: hub
  name: 'aiservices'
  properties: {
    category: 'AzureOpenAI'
    target: aiServicesEndpoint
    authType: 'AAD'
    metadata: {
      ApiType: 'azure'
      ApiVersion: '2024-10-01'
      ResourceId: aiServicesId
    }
  }
}

// ── RBAC ──
// Hub/Foundry 플랫폼이 자동으로 필요한 RBAC를 생성함:
//   - Search Index Data Contributor (AI Search)
//   - Search Service Contributor (AI Search)
//   - Cognitive Services OpenAI User (AI Services)
//   - Storage Blob Data Contributor (Storage)
//   - Storage File Data Privileged Contributor (Storage)
//   - Key Vault Administrator (Key Vault)
//   - Azure AI Administrator (RG)
// 따라서 명시적 RBAC 정의를 제거하여 재배포 시 충돌 방지

// ── Outputs ──
output hubId string = hub.id
output hubName string = hub.name
output hubPrincipalId string = hub.identity.principalId
output projectName string = project.name
output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
