// ============================================
// Azure Function App (Preprocess - JSON → JSONL Integration)
// Flex Consumption FC1 (Linux Python 3.11) — 독립 플랜
//
// 역할:
//   Logic Apps `crawl-preprocess-workflow` 가 crawl 후 호출
//   → raw-documents/{source}/{date}/*.json
//   → date 필드 정규화 + 80 MiB JSONL 파트로 묶기
//   → processed-documents/{source}/{date}/docs-part-NNN.jsonl
//
// Storage 접근: Managed Identity
// ============================================

@description('배포 리전 (Flex Consumption 지원 리전이어야 함)')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Storage Account 이름')
param storageAccountName string

@description('Storage Account ID (RBAC용)')
param storageAccountId string

@description('Raw JSON 컨테이너 이름')
param rawContainerName string = 'raw-documents'

@description('Processed JSONL 컨테이너 이름')
param processedContainerName string = 'processed-documents'

@description('FC1 deployment 패키지를 보관할 Blob 컨테이너 이름')
param deploymentContainerName string = 'function-deployments'

@description('인스턴스 1개 메모리 (MB)')
param instanceMemoryMB int = 2048

@description('최대 동시 인스턴스 수')
param maximumInstanceCount int = 10

var planName = 'asp-preprocess-ragi-${take(suffix, 8)}'
var funcAppName = 'func-preprocess-ragi-${take(suffix, 8)}'

// ── RBAC Role IDs ──
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

// ── Deployment 컨테이너 (Function 패키지 zip 보관) ──
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storageAccount
  name: 'default'
}
resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

// ── Flex Consumption Plan ──
resource funcPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Function App (Flex Consumption, Python 3.11) ──
resource funcApp 'Microsoft.Web/sites@2024-04-01' = {
  name: funcAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: funcPlan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storageAccount.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        instanceMemoryMB: instanceMemoryMB
        maximumInstanceCount: maximumInstanceCount
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      cors: {
        allowedOrigins: ['https://portal.azure.com']
      }
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: storageAccountName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
        { name: 'AZURE_BLOB_CONTAINER_RAW', value: rawContainerName }
        { name: 'AZURE_BLOB_CONTAINER_PROCESSED', value: processedContainerName }
        { name: 'PREPROCESS_WORKERS', value: '16' }
      ]
    }
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── RBAC: Function App MI → Storage Blob Data Contributor ──
resource blobContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageBlobDataContributorRoleId, 'preprocess-fc1')
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource queueContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageQueueDataContributorRoleId, 'preprocess-fc1')
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource tableContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageTableDataContributorRoleId, 'preprocess-fc1')
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
