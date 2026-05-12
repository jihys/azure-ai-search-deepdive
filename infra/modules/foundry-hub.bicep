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

// ── existing resources (RBAC scoping 용) ──
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

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
      defaultAction: 'Deny'
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
    publicNetworkAccess: 'Disabled'
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
    publicNetworkAccess: 'Disabled'
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

// ── RBAC: Hub MI → AI Search (Search Index Data Contributor) ──
resource hubSearchDataContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, searchService.id, '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
    )
    principalId: hub.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Hub MI → AI Search (Search Service Contributor) ──
resource hubSearchContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, searchService.id, '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
    )
    principalId: hub.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Hub MI → AI Services (Cognitive Services OpenAI User) ──
resource hubAiServicesRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, aiServices.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    )
    principalId: hub.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Hub MI → Storage (Storage Blob Data Contributor) ──
resource hubStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, storageAccount.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalId: hub.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Hub MI → Key Vault (Key Vault Administrator) ──
resource hubKvRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, keyVault.id, '00482a5a-887f-4fb3-b363-3b7fe8e74483')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '00482a5a-887f-4fb3-b363-3b7fe8e74483'
    )
    principalId: hub.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ──
output hubId string = hub.id
output hubName string = hub.name
output hubPrincipalId string = hub.identity.principalId
output projectName string = project.name
output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
