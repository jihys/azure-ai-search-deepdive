// Patch deployment: add preprocess Function App + update Logic App workflow
// (Avoids re-deploying existing VNet/Storage that conflict with active allocations)
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param suffix string = 'dyn6dtfu'
param funcSubnetId string
param hostingPlanId string
param storageAccountName string
param storageAccountId string
param crawlFunctionUrl string

module functionPreprocess '../modules/function-preprocess.bicep' = {
  name: 'function-preprocess-patch'
  params: {
    location: location
    suffix: suffix
    funcSubnetId: ''
    hostingPlanId: hostingPlanId
    storageAccountName: storageAccountName
    storageAccountId: storageAccountId
    rawContainerName: 'raw-documents'
    processedContainerName: 'processed-documents'
  }
}

module logicAppCrawl '../modules/logic-app-crawl.bicep' = {
  name: 'logic-app-crawl-patch'
  params: {
    location: location
    suffix: suffix
    crawlFunctionUrl: crawlFunctionUrl
    preprocessFunctionUrl: functionPreprocess.outputs.preprocessTriggerUrl
    crawlerLimit: 0
  }
}

output preprocessFunctionName string = functionPreprocess.outputs.funcAppName
output preprocessFunctionUrl string = functionPreprocess.outputs.preprocessTriggerUrl
output workflowName string = logicAppCrawl.outputs.crawlWorkflowName
