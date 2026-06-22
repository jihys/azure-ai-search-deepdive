// ============================================
// Azure Function App (Preprocess - JSON → JSONL Integration)
// Elastic Premium EP1 (Linux Python 3.11) on shared plan
//
// 역할:
//   Logic Apps `crawl-preprocess-workflow` 가 crawl 후 호출
//   → raw-documents/{source}/{date}/*.json
//   → date 필드 정규화 + 80 MiB JSONL 파트로 묶기
//   → processed-documents/{source}/{date}/docs-part-NNN.jsonl
//
// Storage 접근: Managed Identity (VNet Integration → Storage PE)
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Function App VNet integration 서브넷 ID (snet-func). 비워두면 VNet integration 미설정 (배포 후 az CLI로 추가)')
param funcSubnetId string = ''

@description('공유 Elastic Premium 플랜 ID (function-crawler.bicep 의 asp-crawl 플랜)')
param hostingPlanId string

@description('Storage Account 이름')
param storageAccountName string

@description('Storage Account ID (RBAC용)')
param storageAccountId string

@description('Raw JSON 컨테이너 이름')
param rawContainerName string = 'raw-documents'

@description('Processed JSONL 컨테이너 이름')
param processedContainerName string = 'processed-documents'

var funcAppName = 'func-preprocess-ragi-${take(suffix, 8)}'

// ── RBAC Role IDs ──
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

// ── Function App (Python 3.11, Linux) ──
resource funcApp 'Microsoft.Web/sites@2023-12-01' = {
  name: funcAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: hostingPlanId
    httpsOnly: true
    virtualNetworkSubnetId: empty(funcSubnetId) ? null : funcSubnetId
    // Storage publicNetworkAccess=Disabled 환경에서 Private Endpoint 경유 아웃바운드를 강제
    vnetRouteAllEnabled: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        // MI 기반 AzureWebJobsStorage
        { name: 'AzureWebJobsStorage__accountName', value: storageAccountName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        // Preprocess 설정
        { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
        { name: 'AZURE_BLOB_CONTAINER_RAW', value: rawContainerName }
        { name: 'AZURE_BLOB_CONTAINER_PROCESSED', value: processedContainerName }
        { name: 'PREPROCESS_WORKERS', value: '16' }
      ]
      cors: {
        allowedOrigins: ['https://portal.azure.com']
      }
      minTlsVersion: '1.2'
    }
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── RBAC: Function App MI → Storage Blob Data Contributor ──
resource blobContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageBlobDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function App MI → Storage Queue Data Contributor (runtime) ──
resource queueContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageQueueDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function App MI → Storage Table Data Contributor (runtime) ──
resource tableContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageTableDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ──
output funcAppName string = funcApp.name
output funcAppHostname string = funcApp.properties.defaultHostName
output funcAppId string = funcApp.id
output funcAppPrincipalId string = funcApp.identity.principalId
output preprocessTriggerUrl string = 'https://${funcApp.properties.defaultHostName}/api/preprocess'
