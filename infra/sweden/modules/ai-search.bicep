// ============================================
// Azure AI Search Service
// SPL(Shared Private Links)은 ai-search-spl.bicep에서 초회 배포 시에만 관리
// (SPL Approved 상태 후 재배포 시 ARM "conflicting update" 오류 발생하므로 분리)
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('AI Search SKU')
@allowed(['basic', 'standard', 'standard2'])
param sku string = 'basic'

@description('Storage Account 리소스 ID (RBAC용)')
param storageAccountId string

@description('AI Services 리소스 ID (RBAC용)')
param aiServicesId string

var searchServiceName = 'search-ragi-${take(suffix, 8)}'

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: searchServiceName
  location: location
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    // Private Network: 공개 인터넷 접근 차단
    publicNetworkAccess: 'disabled'
    semanticSearch: 'standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

// ── RBAC: AI Search → Storage Blob Data Reader ──
// ※ Shared Private Links는 ai-search-spl.bicep에서 초회 배포 시에만 관리
//   (SPL이 Approved 상태가 된 후 재배포하면 ARM "conflicting update" 오류 발생)
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
resource searchStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, searchService.id, storageBlobDataReaderRoleId)
  scope: resourceGroup()
  properties: {
    principalId: searchService.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReaderRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: AI Search → Cognitive Services User ──
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
resource searchCogRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServicesId, searchService.id, cognitiveServicesUserRoleId)
  scope: resourceGroup()
  properties: {
    principalId: searchService.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

output endpoint string = 'https://${searchService.name}.search.windows.net'
output searchServiceName string = searchService.name
output searchServiceId string = searchService.id
output searchServicePrincipalId string = searchService.identity.principalId
