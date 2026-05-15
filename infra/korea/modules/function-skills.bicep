// ============================================
// Azure Function App (Skills - AI Search Custom WebApi Skills)
// Elastic Premium EP1 (Linux Python 3.11) on shared plan
//
// 역할:
//   AI Search 멀티모달 skillset 의 Custom WebApiSkill 호스트
//   - /api/markdown_split   : Markdown 헤더 기반 텍스트 분할
//   - /api/pptx_page_split  : PPTX 페이지(슬라이드) 단위 분할
//   - /api/verbalize        : GPT-5.4 Vision 으로 PDF 이미지/도표 자연어 설명
//
// Storage 접근 / AOAI 호출 : Managed Identity
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Function App VNet integration 서브넷 ID (snet-func)')
param funcSubnetId string

@description('공유 Elastic Premium 플랜 ID (asp-crawl-...)')
param hostingPlanId string

@description('Storage Account 이름 (Functions runtime 용)')
param storageAccountName string

@description('Storage Account ID (RBAC용)')
param storageAccountId string

@description('Azure OpenAI / AI Services account ID (RBAC용)')
param aiServicesAccountId string

@description('Azure OpenAI endpoint (https://<account>.openai.azure.com/ 또는 cognitiveservices.azure.com/)')
param openaiEndpoint string

@description('GPT-5.4 deployment name')
param gpt54Deployment string = 'gpt-5.4'

@description('Document Intelligence endpoint (verbalize 용)')
param docIntelligenceEndpoint string = ''

var funcAppName = 'func-skills-ragi-${take(suffix, 8)}'

// ── RBAC Role IDs ──
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
// Cognitive Services OpenAI User
var openaiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

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
    virtualNetworkSubnetId: funcSubnetId
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'AzureWebJobsStorage__accountName', value: storageAccountName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AZURE_OPENAI_ENDPOINT', value: openaiEndpoint }
        { name: 'AZURE_OPENAI_GPT54_DEPLOYMENT', value: gpt54Deployment }
        { name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', value: docIntelligenceEndpoint }
      ]
      cors: {
        allowedOrigins: ['https://portal.azure.com']
      }
      minTlsVersion: '1.2'
    }
  }
  tags: { project: 'rag-indexing-lab' }
}

resource blobContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageBlobDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource queueContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageQueueDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource tableContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, funcApp.id, storageTableDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource openaiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServicesAccountId, funcApp.id, openaiUserRoleId)
  scope: resourceGroup()
  properties: {
    principalId: funcApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openaiUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

output funcAppName string = funcApp.name
output funcAppHostname string = funcApp.properties.defaultHostName
output funcAppId string = funcApp.id
output funcAppPrincipalId string = funcApp.identity.principalId
output skillsFunctionUrl string = 'https://${funcApp.properties.defaultHostName}'
