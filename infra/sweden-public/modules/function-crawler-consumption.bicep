// ============================================
// Azure Function App (Crawler) - Flex Consumption (FC1)
// Python 3.11 (Flex Consumption FC1, 공개 엔드포인트)
//
// 역할 (Method B):
//   Durable Functions Orchestrator + Activity 분할
//     - http_start_crawl_preprocess  (HTTP starter)
//     - crawl_preprocess_orchestrator (top-level)
//     - source_pipeline_orchestrator  (sub-orchestrator per source)
//     - activity_list_seqs            (목록 수집)
//     - activity_crawl_detail_batch   (상세 배치, Consumption 10분 한도 호환)
//     - activity_preprocess_source    (preprocess HTTP)
//
// Flex Consumption (FC1) 사용 이유:
//   - Y1 Consumption: VNet integration 가능하나 content share 가 SharedKey 강제 →
//     storage allowSharedKeyAccess=false 환경과 호환 불가
//   - FC1 (Flex Consumption): identity-based deployment storage 지원
//     소비량 기반 과금 + 자동 스케일 (Durable Functions fan-out 에 유리)
// ============================================

@description('배포 리전 (Flex Consumption 지원 리전이어야 함)')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Storage Account 이름 (raw/processed + deployment 컨테이너 공용)')
param storageAccountName string

@description('Storage Account ID (RBAC 스코프용)')
param storageAccountId string

@description('Blob (raw) 컨테이너 이름')
param blobContainerName string = 'raw-documents'

@description('FC1 deployment 패키지를 보관할 Blob 컨테이너 이름 (Functions 런타임이 Identity 로 접근)')
param deploymentContainerName string = 'function-deployments'

@description('Preprocess Function App 이름 (PREPROCESS_FUNCTION_URI 자동 구성용). 비우면 직접 설정 필요.')
param preprocessFunctionAppName string = ''

@description('인스턴스 1개 메모리 (MB). 2048/4096 가능')
param instanceMemoryMB int = 2048

@description('최대 동시 인스턴스 수 (자동 스케일 상한)')
param maximumInstanceCount int = 40

var planName = 'asp-crawl-cons-ragi-${take(suffix, 8)}'
var funcAppName = 'func-crawl-cons-ragi-${take(suffix, 8)}'

// ── RBAC Role IDs ──
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

// ── Deployment 컨테이너 (Function 패키지 zip 보관) ──
// 기존 storage account 의 blob service 에 컨테이너 추가
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
        // AzureWebJobsStorage: identity-based (Durable Functions 의 Task Hub 가 사용)
        { name: 'AzureWebJobsStorage__accountName', value: storageAccountName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        // 크롤러 + 전처리 호출
        { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
        { name: 'AZURE_BLOB_CONTAINER_NAME', value: blobContainerName }
        { name: 'CRAWLER_DETAIL_BATCH_SIZE', value: '50' }
        { name: 'CRAWL_DETAIL_WORKERS', value: '5' }
        { name: 'PREPROCESS_TIMEOUT_SECONDS', value: '3600' }
        {
          name: 'PREPROCESS_FUNCTION_URI'
          value: empty(preprocessFunctionAppName)
            ? ''
            : 'https://${preprocessFunctionAppName}.azurewebsites.net/api/preprocess'
        }
      ]
    }
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── RBAC: Function App MI → Storage Blob Data Contributor ──
//   - Durable Functions task hub blob lease
//   - raw-documents/ 업로드
//   - function-deployments/ 패키지 읽기 (Flex Consumption deployment)
resource blobContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageBlobDataContributorRoleId, 'fc1')
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function App MI → Storage Queue Data Contributor (Durable runtime) ──
resource queueContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageQueueDataContributorRoleId, 'fc1')
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function App MI → Storage Table Data Contributor (Durable Task Hub) ──
resource tableContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageTableDataContributorRoleId, 'fc1')
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
output hostingPlanId string = funcPlan.id
output deploymentContainerName string = deploymentContainerName
// Durable Functions HTTP starter URL
output orchestratorTriggerUrl string = 'https://${funcApp.properties.defaultHostName}/api/orchestrators/crawl_preprocess'
