// ============================================
// Azure Function App (Crawler) - Elastic Premium EP1
// Python 3.11 + VNet Integration (snet-func → Storage PE)
//
// 역할:
//   Logic Apps 스케줄 트리거 → HTTP 수신
//   → law.go.kr 크롤링 (공개 인터넷 아웃바운드)
//   → Blob Storage 업로드 (VNet → PE 아웃바운드)
//
// EP1 사용 이유:
//   Consumption Plan은 VNet integration 미지원 →
//   Private Storage PE에 아웃바운드 접근 불가.
//   EP1은 VNet integration 지원 (아웃바운드만)
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Function App VNet integration 서브넷 ID (snet-func)')
param funcSubnetId string

@description('Storage Account 이름 (크롤러가 업로드할 대상)')
param storageAccountName string

@description('Storage Account ID (RBAC용)')
param storageAccountId string

@description('Blob 컨테이너 이름')
param blobContainerName string = 'raw-documents'

@description('크롤러가 수집할 법령 건수')
param crawlerLimit int = 10

var planName = 'asp-crawl-ragi-${take(suffix, 8)}'
var funcAppName = 'func-crawl-ragi-${take(suffix, 8)}'

// ── RBAC Role IDs ──
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

// ── Elastic Premium Plan (Linux, EP1) ──
// EP1: 1 vCore, 3.5GB RAM, VNet integration 지원
resource funcPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: {
    name: 'EP1'
    tier: 'ElasticPremium'
  }
  kind: 'elastic'
  properties: {
    reserved: true   // Linux 필수
    maximumElasticWorkerCount: 5
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Function App (Python 3.11, Linux) ──
resource funcApp 'Microsoft.Web/sites@2023-12-01' = {
  name: funcAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: funcPlan.id
    httpsOnly: true
    // VNet integration: 아웃바운드 트래픽을 VNet으로 라우팅
    // → snet-func → VNet 라우팅 → snet-pep → Storage PE
    virtualNetworkSubnetId: funcSubnetId
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      // MI 기반 Storage 연결 (연결 문자열 없이 MI로 접근)
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        // AzureWebJobsStorage: MI 기반 (SharedKey 없이)
        { name: 'AzureWebJobsStorage__accountName', value: storageAccountName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        // 크롤러 설정
        { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
        { name: 'AZURE_BLOB_CONTAINER_NAME', value: blobContainerName }
        { name: 'CRAWLER_LIMIT', value: string(crawlerLimit) }
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
// 크롤러가 Blob에 파일을 쓰기 위한 권한
resource blobContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageBlobDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function App MI → Storage Queue Data Contributor ──
// Functions 런타임 큐 접근용
resource queueContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageQueueDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function App MI → Storage Table Data Contributor ──
// Functions 런타임 테이블 접근용
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
output hostingPlanId string = funcPlan.id
// Logic Apps가 호출할 HTTP 트리거 URL (인증: anonymous)
output crawlTriggerUrl string = 'https://${funcApp.properties.defaultHostName}/api/crawl'
