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
    // RBAC + API key 둘 다 허용 (기본값은 apiKeyOnly 이므로 명시 필요 — 안 그러면 Bearer 토큰 403)
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http403'
      }
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

// ── RBAC: AI Search → Storage Blob Data Contributor ──
// ※ Shared Private Links는 ai-search-spl.bicep에서 초회 배포 시에만 관리
//   (SPL이 Approved 상태가 된 후 재배포하면 ARM "conflicting update" 오류 발생)
// Contributor (not Reader) — incremental enrichment cache 가 blob 에 쓰기 필요
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
resource searchStorageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, searchService.id, storageBlobDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: searchService.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: AI Search → Storage Table Data Contributor (indexer cache 메타) ──
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
resource searchStorageTableRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, searchService.id, storageTableDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: searchService.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
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
