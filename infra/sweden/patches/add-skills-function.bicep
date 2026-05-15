// ============================================
// Skills Function App 추가 패치
// 노트북 05/06 멀티모달 파이프라인의 Custom WebApi Skills 호스트
//
// 사용법:
//   az deployment group create \
//     -g rg-rag-indexing-lab-swc \
//     --template-file infra/sweden/patches/add-skills-function.bicep
// ============================================

targetScope = 'resourceGroup'

var suffix = 'dyn6dtfu'
var location = resourceGroup().location

// 기존 리소스 참조
resource hostingPlan 'Microsoft.Web/serverfarms@2023-12-01' existing = {
  name: 'asp-crawl-ragi-${take(suffix, 8)}'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: 'stragidyn6dtfun6'
}

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: 'ais-ragi-${take(suffix, 8)}'
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' existing = {
  name: 'vnet-ragi-${take(suffix, 8)}'
}

module skills '../modules/function-skills.bicep' = {
  name: 'func-skills-deploy'
  params: {
    location: location
    suffix: suffix
    hostingPlanId: hostingPlan.id
    storageAccountName: storage.name
    storageAccountId: storage.id
    funcSubnetId: '${vnet.id}/subnets/snet-func'
    aiServicesAccountId: aiServices.id
    openaiEndpoint: 'https://${aiServices.name}.openai.azure.com/'
    gpt54Deployment: 'gpt-5.4'
    docIntelligenceEndpoint: 'https://${aiServices.name}.cognitiveservices.azure.com/'
  }
}

output skillsFunctionUrl string = skills.outputs.skillsFunctionUrl
output skillsFunctionName string = skills.outputs.funcAppName
