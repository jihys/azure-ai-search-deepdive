// Patch: Deploy Method B (Flex Consumption Crawler + Durable polling Logic App)
//   - 신규 FC1 Function App (function-crawler-consumption.bicep)
//   - 기존 Logic App workflow 를 Durable polling 패턴으로 교체
//   - 기존 EP1 functionCrawler / functionPreprocess 는 건드리지 않음
//
// 사용:
//   az deployment group create --resource-group rg-rag-indexing-lab-swc \
//     --template-file infra/sweden/patches/add-method-b.bicep \
//     --parameters funcSubnetId=<snet-func id> storageAccountName=<sa> storageAccountId=<sa-id> \
//                  preprocessFunctionAppName=<existing preprocess func>
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param suffix string = 'dyn6dtfu'
param funcSubnetId string
param storageAccountName string
param storageAccountId string

@description('기존 preprocess Function App 이름 (FC1 의 PREPROCESS_FUNCTION_URI 자동 구성용)')
param preprocessFunctionAppName string

@description('Detail 페이지 동시 요청 워커 수')
param detailWorkers int = 20

@description('수집할 페이지 수 (0=무제한). 테스트는 1~2 권장.')
param crawlerLimit int = 0

module functionCrawlerConsumption '../modules/function-crawler-consumption.bicep' = {
  name: 'function-crawler-consumption-patch'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: funcSubnetId
    storageAccountName: storageAccountName
    storageAccountId: storageAccountId
    blobContainerName: 'raw-documents'
    preprocessFunctionAppName: preprocessFunctionAppName
  }
}

module logicAppCrawl '../modules/logic-app-crawl.bicep' = {
  name: 'logic-app-crawl-patch-method-b'
  params: {
    location: location
    suffix: suffix
    orchestratorUrl: functionCrawlerConsumption.outputs.orchestratorTriggerUrl
    crawlerLimit: crawlerLimit
    detailWorkers: detailWorkers
  }
}

output funcCrawlerConsumptionName string = functionCrawlerConsumption.outputs.funcAppName
output orchestratorTriggerUrl string = functionCrawlerConsumption.outputs.orchestratorTriggerUrl
output workflowName string = logicAppCrawl.outputs.crawlWorkflowName
output deploymentContainerName string = functionCrawlerConsumption.outputs.deploymentContainerName
