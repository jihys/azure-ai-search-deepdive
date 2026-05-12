// ============================================
// Azure Document Intelligence (East US 2)
// ※ 한국 리전(Korea Central)에서 Document Intelligence 미지원
//   → East US 2에 배포 후 Cross-Region Private Endpoint로 접근
//   (PE는 Korea Central VNet에 생성, 서비스는 East US 2)
// ============================================

@description('배포 리전 (East US 2)')
param location string

@description('리소스 이름 접미사')
param suffix string

var docIntelName = 'di-ragi-${take(suffix, 8)}'

resource docIntelligence 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: docIntelName
  location: location
  kind: 'FormRecognizer'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: docIntelName
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
    }
  }
  tags: {
    project: 'rag-indexing-lab'
    region: 'eastus2'
    purpose: 'cross-region-doc-intelligence'
  }
}

output endpoint string = docIntelligence.properties.endpoint
output docIntelligenceName string = docIntelligence.name
output docIntelligenceId string = docIntelligence.id
