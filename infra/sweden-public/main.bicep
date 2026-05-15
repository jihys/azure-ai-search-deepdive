// ============================================
// Azure RAG Indexing Lab - Main Bicep Template (PUBLIC variant)
// Region: Sweden Central (swedencentral)
// Network: All resources publicly reachable (workshop / lab)
//          - No Private Endpoints
//          - No JumpVM
//          - VNet kept only for Function App egress (FC1/EP1)
// ============================================

targetScope = 'subscription'

@description('리소스 그룹 이름')
param resourceGroupName string = 'rg-rag-indexing-lab-swc-pub'

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
param crawlerLimit int = 10

@description('데이터 평면(Storage/AI Search/AI Services/Doc Intelligence) RBAC를 부여할 Entra ID 사용자 Object ID 배열 — 본인 노트북에서 핸즈온 시 본인 Object ID 입력')
param userObjectIds array = []

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
    networking: 'public'
  }
}

// ============================================
// Virtual Network + Private DNS Zones
// ============================================
module vnet 'modules/vnet.bicep' = {
  scope: rg
  name: 'vnet-deployment'
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
  name: 'storage-deployment'
  params: {
    location: location
    suffix: suffix
    containerName: blobContainerName
    userObjectIds: userObjectIds
  }
}

// ============================================
// Azure AI Services (OpenAI) (Private)
// ============================================
module openai 'modules/openai.bicep' = {
  scope: rg
  name: 'openai-deployment'
  params: {
    location: location
    suffix: suffix
    embeddingDeploymentName: embeddingDeploymentName
    gptDeploymentName: gptDeploymentName
    gptModelName: gptModelName
    gptModelVersion: gptModelVersion
    userObjectIds: userObjectIds
  }
}

// ============================================
// Document Intelligence (Private)
// ============================================
module docIntelligence 'modules/doc-intelligence.bicep' = {
  scope: rg
  name: 'doc-intelligence-deployment'
  params: {
    location: location
    suffix: suffix
    userObjectIds: userObjectIds
  }
}

// ============================================
// Azure AI Search + Shared Private Links (아웃바운드)
// AI Search Indexer + Skillset이 Storage/AI Services에 접근
// Logic Apps 인덱싱 워크플로우를 AI Search 네이티브로 대체
// ============================================
module aiSearch 'modules/ai-search.bicep' = {
  scope: rg
  name: 'ai-search-deployment'
  params: {
    location: location
    suffix: suffix
    sku: searchSku
    storageAccountId: storage.outputs.storageAccountId
    aiServicesId: openai.outputs.accountId
    userObjectIds: userObjectIds
  }
}

// AI Search MSI → AOAI RBAC (skillset 의 AzureOpenAIEmbeddingSkill MSI auth)
module searchToOpenAIRole 'modules/role-search-to-openai.bicep' = {
  scope: rg
  name: 'role-search-to-openai'
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
  scope: rg
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
// Azure Function App (Crawler, Flex Consumption FC1)
// Method B: Durable Functions + Activity 분할
//   - 기존 EP1 functionCrawler 와 병렬 배포 (이름 다름)
//   - identity-based deployment storage + VNet integration (snet-func 공유)
// ============================================
module functionCrawlerConsumption 'modules/function-crawler-consumption.bicep' = {
  scope: rg
  name: 'function-crawler-consumption-deployment'
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
  name: 'function-skills-deployment'
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
  name: 'logic-app-crawl-deployment'
  params: {
    location: location
    suffix: suffix
    orchestratorUrl: functionCrawlerConsumption.outputs.orchestratorTriggerUrl
    crawlerLimit: crawlerLimit
    detailWorkers: 20
  }
}

// ============================================
// Azure AI Foundry Hub + Project (Private AI Search 연결)
// Managed Network: AllowInternetOutbound
// Outbound PE: AI Search + AI Services
// ============================================
module foundryHub 'modules/foundry-hub.bicep' = {
  scope: rg
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
// (PUBLIC variant) No Private Endpoints / No JumpVM
// All services are reachable directly via their public endpoints.
// ============================================

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
output skillsFunctionUrl string = functionSkills.outputs.skillsFunctionUrl
output crawlLogicAppName string = logicAppCrawl.outputs.crawlWorkflowName
output foundryHubName string = foundryHub.outputs.hubName
output foundryProjectName string = foundryHub.outputs.projectName
output foundryKeyVaultName string = foundryHub.outputs.keyVaultName
