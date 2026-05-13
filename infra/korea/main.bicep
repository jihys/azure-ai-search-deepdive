// ============================================
// Azure RAG Indexing Lab - Korea Central Version
// Primary: Korea Central (koreacentral)
// Doc Intelligence: East US 2 (eastus2) — 한국 리전 미지원
// Network: Full Private (VNet + Private Endpoints)
// ============================================

targetScope = 'subscription'

@description('메인 리소스 그룹 이름 (Korea Central)')
param resourceGroupName string = 'rg-rag-indexing-lab-krc'

@description('Doc Intelligence 리소스 그룹 (East US 2)')
param docIntelResourceGroupName string = 'rg-rag-indexing-lab-eus2'

@description('메인 배포 리전 - Korea Central')
param location string = 'koreacentral'

@description('Doc Intelligence 배포 리전 - East US 2 (한국 미지원)')
param docIntelLocation string = 'eastus2'

@description('리소스 이름 접미사 (고유성 보장)')
param suffix string = uniqueString(subscription().subscriptionId, resourceGroupName)

@description('Azure OpenAI embedding 모델 배포명')
param embeddingDeploymentName string = 'text-embedding-3-large'

@description('Azure OpenAI GPT-5.4 모델 배포명')
param gptDeploymentName string = 'gpt-5.4'

@description('GPT 모델 버전')
param gptModelVersion string

@description('GPT 모델 이름 (GlobalStandard)')
param gptModelName string = 'gpt-5.4'

@description('AI Search SKU')
@allowed(['basic', 'standard', 'standard2'])
param searchSku string = 'standard'

@description('Storage Account 컨테이너 이름')
param blobContainerName string = 'raw-documents'

@description('크롤러가 수집할 법령 건수')
param crawlerLimit int = 10

@description('JumpVM 관리자 계정명')
param jumpvmAdminUsername string = 'azureadmin'

@description('JumpVM 관리자 비밀번호')
@secure()
param jumpvmAdminPassword string

@description('JumpVM Entra ID 로그인을 허용할 사용자 Object ID 목록')
param jumpvmEntraUserObjectIds array = []

// ============================================
// Resource Groups
// ============================================
resource rgKorea 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    project: 'rag-indexing-lab'
    environment: 'lab'
    region: 'koreacentral'
    version: 'v2'
  }
}

resource rgDocIntel 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: docIntelResourceGroupName
  location: docIntelLocation
  tags: {
    project: 'rag-indexing-lab'
    environment: 'lab'
    region: 'eastus2'
    purpose: 'doc-intelligence-only'
    version: 'v2'
  }
}

// ============================================
// Virtual Network + Private DNS Zones (Korea Central)
// ============================================
module vnet 'modules/vnet.bicep' = {
  scope: rgKorea
  name: 'vnet-deployment'
  params: {
    location: location
    suffix: suffix
  }
}

// ============================================
// Storage Account (Korea Central, Private)
// ============================================
module storage 'modules/storage.bicep' = {
  scope: rgKorea
  name: 'storage-deployment'
  params: {
    location: location
    suffix: suffix
    containerName: blobContainerName
    userObjectIds: jumpvmEntraUserObjectIds
  }
}

// ============================================
// Azure AI Services (Korea Central, Private)
// ============================================
module openai 'modules/openai.bicep' = {
  scope: rgKorea
  name: 'openai-deployment'
  params: {
    location: location
    suffix: suffix
    embeddingDeploymentName: embeddingDeploymentName
    gptDeploymentName: gptDeploymentName
    gptModelName: gptModelName
    gptModelVersion: gptModelVersion
  }
}

// ============================================
// Document Intelligence (East US 2, Private)
// ※ 한국 리전 미지원 → Cross-Region PE로 접근
// ============================================
module docIntelligence 'modules/doc-intelligence.bicep' = {
  scope: rgDocIntel
  name: 'doc-intelligence-deployment'
  params: {
    location: docIntelLocation
    suffix: suffix
  }
}

// ============================================
// Azure AI Search + Shared Private Links
// ============================================
module aiSearch 'modules/ai-search.bicep' = {
  scope: rgKorea
  name: 'ai-search-deployment'
  params: {
    location: location
    suffix: suffix
    sku: searchSku
    storageAccountId: storage.outputs.storageAccountId
    aiServicesId: openai.outputs.accountId
  }
}

// ============================================
// Azure Function App (크롤러) - EP1 + VNet Integration
// ============================================
module functionCrawler 'modules/function-crawler.bicep' = {
  scope: rgKorea
  name: 'function-crawler-deployment'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: vnet.outputs.funcSubnetId
    storageAccountName: storage.outputs.storageAccountName
    storageAccountId: storage.outputs.storageAccountId
    blobContainerName: blobContainerName
    crawlerLimit: crawlerLimit
  }
}

// ============================================
// Azure Function App (Preprocess) - 동일 EP1 플랜 공유
// crawl 후 raw JSON → processed JSONL (Integration) 수행
// ============================================
module functionPreprocess 'modules/function-preprocess.bicep' = {
  scope: rgKorea
  name: 'function-preprocess-deployment'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: vnet.outputs.funcSubnetId
    hostingPlanId: functionCrawler.outputs.hostingPlanId
    storageAccountName: storage.outputs.storageAccountName
    storageAccountId: storage.outputs.storageAccountId
    rawContainerName: blobContainerName
    processedContainerName: 'processed-documents'
  }
}

// ============================================
// Logic App (Consumption) - 크롤 + 전처리 통합 스케줄러
//   Daily 21:00 UTC: crawl → 4-source parallel preprocess (JSON→JSONL)
// ============================================
module logicAppCrawl 'modules/logic-app-crawl.bicep' = {
  scope: rgKorea
  name: 'logic-app-crawl-deployment'
  params: {
    location: location
    suffix: suffix
    crawlFunctionUrl: functionCrawler.outputs.crawlTriggerUrl
    preprocessFunctionUrl: functionPreprocess.outputs.preprocessTriggerUrl
    crawlerLimit: crawlerLimit
  }
}

// ============================================
// Azure AI Foundry Hub + Project
// ============================================
module foundryHub 'modules/foundry-hub.bicep' = {
  scope: rgKorea
  name: 'foundry-hub-deployment'
  params: {
    location: location
    suffix: suffix
    storageAccountId: storage.outputs.storageAccountId
    storageAccountName: storage.outputs.storageAccountName
    searchServiceId: aiSearch.outputs.searchServiceId
    searchServiceName: aiSearch.outputs.searchServiceName
    searchEndpoint: aiSearch.outputs.endpoint
    aiServicesId: openai.outputs.accountId
    aiServicesName: openai.outputs.accountName
    aiServicesEndpoint: openai.outputs.endpoint
  }
}

// ============================================
// Private Endpoints (Korea Central VNet)
// ※ Doc Intelligence PE는 Cross-Region (Korea→EUS2)
// ============================================
module privateEndpoints 'modules/private-endpoints.bicep' = {
  scope: rgKorea
  name: 'private-endpoints-deployment'
  params: {
    location: location
    suffix: suffix
    pepSubnetId: vnet.outputs.pepSubnetId
    storageAccountId: storage.outputs.storageAccountId
    searchServiceId: aiSearch.outputs.searchServiceId
    aiServicesId: openai.outputs.accountId
    docIntelligenceId: docIntelligence.outputs.docIntelligenceId
    hubId: foundryHub.outputs.hubId
    keyVaultId: foundryHub.outputs.keyVaultId
    blobDnsZoneId: vnet.outputs.blobDnsZoneId
    searchDnsZoneId: vnet.outputs.searchDnsZoneId
    cogServicesDnsZoneId: vnet.outputs.cogServicesDnsZoneId
    openaiDnsZoneId: vnet.outputs.openaiDnsZoneId
    azuremlDnsZoneId: vnet.outputs.azuremlDnsZoneId
    notebooksDnsZoneId: vnet.outputs.notebooksDnsZoneId
    vaultDnsZoneId: vnet.outputs.vaultDnsZoneId
  }
}

// ============================================
// JumpVM (Korea Central)
// ============================================
module jumpvm 'modules/jumpvm.bicep' = {
  scope: rgKorea
  name: 'jumpvm-deployment'
  params: {
    location: location
    jumpSubnetId: vnet.outputs.jumpSubnetId
    adminUsername: jumpvmAdminUsername
    adminPassword: jumpvmAdminPassword
    entraUserObjectIds: jumpvmEntraUserObjectIds
  }
}

// ============================================
// Outputs
// ============================================
output resourceGroupName string = rgKorea.name
output docIntelResourceGroupName string = rgDocIntel.name
output location string = location
output docIntelLocation string = docIntelLocation
output vnetName string = vnet.outputs.vnetName
output storageAccountName string = storage.outputs.storageAccountName
output storageAccountBlobEndpoint string = storage.outputs.blobEndpoint
output openaiEndpoint string = openai.outputs.endpoint
output openaiAccountName string = openai.outputs.accountName
output gptDeploymentName string = openai.outputs.gptDeploymentName
output aiSearchEndpoint string = aiSearch.outputs.endpoint
output aiSearchName string = aiSearch.outputs.searchServiceName
output docIntelligenceEndpoint string = docIntelligence.outputs.endpoint
output aiSearchPrincipalId string = aiSearch.outputs.searchServicePrincipalId
output crawlFunctionUrl string = functionCrawler.outputs.crawlTriggerUrl
output crawlFunctionName string = functionCrawler.outputs.funcAppName
output crawlLogicAppName string = logicAppCrawl.outputs.crawlWorkflowName
output jumpvmName string = jumpvm.outputs.vmName
output jumpvmPublicIp string = jumpvm.outputs.publicIpAddress
output foundryHubName string = foundryHub.outputs.hubName
output foundryProjectName string = foundryHub.outputs.projectName
output foundryKeyVaultName string = foundryHub.outputs.keyVaultName
