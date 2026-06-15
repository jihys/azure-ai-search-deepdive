// ============================================
// Azure RAG Indexing Lab - Main Bicep Template
// Region: Sweden Central (swedencentral)
// Network: Full Private (VNet + Private Endpoints)
// Pipeline: AI Search Native Indexer + Skillset
//           (Logic Apps 대신 AI Search Skills 사용)
// ============================================

targetScope = 'subscription'

@description('리소스 그룹 이름')
param resourceGroupName string = 'rg-rag-indexing-lab-swc'

@description('배포 리전 - Sweden Central (Document Intelligence 지원)')
param location string = 'swedencentral'

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
// 일별 크롤 페이지 상한 (page_count). 100 items/page 기준.
//   10  = 평상시 (신규 분만 빠르게)
//   600 = 백필 모드 (LIST_MAX_WAVES 20 × LIST_PAGE_CHUNK 30 = 사이트 전체 훑기)
// 평상시로 되돌릴 때는 10 으로 변경.
param crawlerLimit int = 600

@description('JumpVM 관리자 계정명')
param jumpvmAdminUsername string = 'azureadmin'

@description('JumpVM 관리자 비밀번호')
@secure()
param jumpvmAdminPassword string

@description('JumpVM Entra ID 로그인을 허용할 사용자 Object ID 목록')
param jumpvmEntraUserObjectIds array = []

// ============================================
// Resource Group
// ============================================
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    project: 'rag-indexing-lab'
    environment: 'lab'
    region: 'swedencentral'
  }
}

// ============================================
// Virtual Network + Private DNS Zones
// ============================================
module vnet 'modules/vnet.bicep' = {
  scope: rg
  name: 'vnet-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
  }
}

// ============================================
// Storage Account (Private)
// ============================================
module storage 'modules/storage.bicep' = {
  scope: rg
  name: 'storage-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    containerName: blobContainerName
    userObjectIds: jumpvmEntraUserObjectIds
  }
}

// ============================================
// Azure AI Services (OpenAI) (Private)
// ============================================
module openai 'modules/openai.bicep' = {
  scope: rg
  name: 'openai-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    embeddingDeploymentName: embeddingDeploymentName
    gptDeploymentName: gptDeploymentName
    gptModelName: gptModelName
    gptModelVersion: gptModelVersion
    userObjectIds: jumpvmEntraUserObjectIds
  }
}

// ============================================
// Document Intelligence (Private)
// ============================================
module docIntelligence 'modules/doc-intelligence.bicep' = {
  scope: rg
  name: 'doc-intelligence-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
  }
}

// ============================================
// Azure AI Search + Shared Private Links (아웃바운드)
// AI Search Indexer + Skillset이 Storage/AI Services에 접근
// Logic Apps 인덱싱 워크플로우를 AI Search 네이티브로 대체
// ============================================
module aiSearch 'modules/ai-search.bicep' = {
  scope: rg
  name: 'ai-search-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    sku: searchSku
    storageAccountId: storage.outputs.storageAccountId
    aiServicesId: openai.outputs.accountId
  }
}

// AI Search MSI → AOAI RBAC (skillset 의 AzureOpenAIEmbeddingSkill MSI auth)
module searchToOpenAIRole 'modules/role-search-to-openai.bicep' = {
  scope: rg
  name: 'role-search-to-openai-${take(suffix, 8)}'
  params: {
    aoaiAccountName: openai.outputs.accountName
    aiSearchPrincipalId: aiSearch.outputs.searchServicePrincipalId
  }
}

// ============================================
// Azure Function App (크롤러) - EP1 + VNet Integration
// Python 크롤러를 Azure에서 실행 (로컬 실행 대체)
// snet-func → VNet → Storage PE로 아웃바운드 접근
// ============================================
module functionCrawler 'modules/function-crawler.bicep' = {
  scope: rg
  name: 'function-crawler-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: vnet.outputs.funcSubnetId
    storageAccountName: storage.outputs.storageAccountName
    storageAccountId: storage.outputs.storageAccountId
    blobContainerName: blobContainerName
    crawlerLimit: crawlerLimit
    preprocessFunctionAppName: functionPreprocess.outputs.funcAppName
  }
}

// ============================================
// Azure Function App (Preprocess) - 동일 EP1 플랜 공유
// crawl 후 raw JSON → processed JSONL (Integration) 수행
// ============================================
module functionPreprocess 'modules/function-preprocess.bicep' = {
  scope: rg
  name: 'function-preprocess-deployment-${take(suffix, 8)}'
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
// Azure Function App (Crawler, Flex Consumption FC1)
// Method B: Durable Functions + Activity 분할
//   - 기존 EP1 functionCrawler 와 병렬 배포 (이름 다름)
//   - identity-based deployment storage + VNet integration (snet-func 공유)
// ============================================
module functionCrawlerConsumption 'modules/function-crawler-consumption.bicep' = {
  scope: rg
  name: 'function-crawler-consumption-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: vnet.outputs.funcFc1SubnetId
    storageAccountName: storage.outputs.storageAccountName
    storageAccountId: storage.outputs.storageAccountId
    blobContainerName: blobContainerName
    preprocessFunctionAppName: functionPreprocess.outputs.funcAppName
  }
}

// ============================================
// Azure Function App (Skills) - 동일 EP1 플랜 공유
// AI Search 멀티모달 skillset 의 Custom WebApi Skills 호스트
// (markdown_split / pptx_page_split / verbalize)
// ============================================
module functionSkills 'modules/function-skills.bicep' = {
  scope: rg
  name: 'function-skills-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: vnet.outputs.funcSubnetId
    hostingPlanId: functionCrawler.outputs.hostingPlanId
    storageAccountName: storage.outputs.storageAccountName
    storageAccountId: storage.outputs.storageAccountId
    aiServicesAccountId: openai.outputs.accountId
    openaiEndpoint: openai.outputs.endpoint
    gpt54Deployment: gptDeploymentName
    docIntelligenceEndpoint: docIntelligence.outputs.endpoint
  }
}

// ============================================
// Logic App (Consumption) - 크롤 + 전처리 통합 스케줄러
// 매일 21:00 UTC (= 06:00 KST)
//   Call_Crawl_Function → Parallel preprocess (prec/detc/expc/admrul)
// ============================================
module logicAppCrawl 'modules/logic-app-crawl.bicep' = {
  scope: rg
  name: 'logic-app-crawl-deployment-${take(suffix, 8)}'
  params: {
    location: location
    suffix: suffix
    orchestratorUrl: functionCrawlerConsumption.outputs.orchestratorTriggerUrl
    crawlerLimit: crawlerLimit
    detailWorkers: 20
    searchEndpoint: aiSearch.outputs.endpoint
    searchServiceId: aiSearch.outputs.searchServiceId
  }
}

// ============================================
// Azure AI Foundry Hub + Project (Private AI Search 연결)
// Managed Network: AllowInternetOutbound
// Outbound PE: AI Search + AI Services
// ============================================
module foundryHub 'modules/foundry-hub.bicep' = {
  scope: rg
  name: 'foundry-hub-deployment-${take(suffix, 8)}'
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
// Private Endpoints (인바운드 - VNet 내부 접근)
// ============================================
module privateEndpoints 'modules/private-endpoints.bicep' = {
  scope: rg
  name: 'private-endpoints-deployment-${take(suffix, 8)}'
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
    queueDnsZoneId: vnet.outputs.queueDnsZoneId
    tableDnsZoneId: vnet.outputs.tableDnsZoneId
    fileDnsZoneId: vnet.outputs.fileDnsZoneId
    searchDnsZoneId: vnet.outputs.searchDnsZoneId
    cogServicesDnsZoneId: vnet.outputs.cogServicesDnsZoneId
    openaiDnsZoneId: vnet.outputs.openaiDnsZoneId
    azuremlDnsZoneId: vnet.outputs.azuremlDnsZoneId
    notebooksDnsZoneId: vnet.outputs.notebooksDnsZoneId
    vaultDnsZoneId: vnet.outputs.vaultDnsZoneId
    servicesAiDnsZoneId: vnet.outputs.servicesAiDnsZoneId
  }
}

// ============================================
// JumpVM - AI Search / Private Endpoint 접근용 관리 VM
// publicNetworkAccess=Disabled 서비스에 VNet 내부에서만 접근
// snet-jump (10.0.0.0/24) → snet-pep → Private Endpoint → Service
// ============================================
module jumpvm 'modules/jumpvm.bicep' = {
  scope: rg
  name: 'jumpvm-deployment-${take(suffix, 8)}'
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
output resourceGroupName string = rg.name
output location string = location
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
output preprocessFunctionUrl string = functionPreprocess.outputs.preprocessTriggerUrl
output crawlFunctionName string = functionCrawler.outputs.funcAppName
output preprocessFunctionName string = functionPreprocess.outputs.funcAppName
output skillsFunctionName string = functionSkills.outputs.funcAppName
output crawlConsFunctionName string = functionCrawlerConsumption.outputs.funcAppName
output skillsFunctionUrl string = functionSkills.outputs.skillsFunctionUrl
output crawlLogicAppName string = logicAppCrawl.outputs.crawlWorkflowName
output jumpvmName string = jumpvm.outputs.vmName
output jumpvmPublicIp string = jumpvm.outputs.publicIpAddress
output foundryHubName string = foundryHub.outputs.hubName
output foundryProjectName string = foundryHub.outputs.projectName
output foundryProjectEndpoint string = openai.outputs.foundryProjectEndpoint
output foundryKeyVaultName string = foundryHub.outputs.keyVaultName
