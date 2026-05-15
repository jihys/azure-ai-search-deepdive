// ============================================
// Azure Document Intelligence
// ============================================

@description('배포 리전')
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
    // Private Network: 공개 인터넷 접근 차단
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

output endpoint string = docIntelligence.properties.endpoint
output docIntelligenceName string = docIntelligence.name
output docIntelligenceId string = docIntelligence.id
