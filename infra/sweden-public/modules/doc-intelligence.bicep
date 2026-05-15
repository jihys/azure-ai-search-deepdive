// ============================================
// Azure Document Intelligence
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Document Intelligence 사용자 RBAC를 부여할 Entra ID 사용자 Object ID 배열')
param userObjectIds array = []

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

// ============================================
// RBAC: 사용자 → Document Intelligence (Cognitive Services User)
// ============================================
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
resource userCogUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for userId in userObjectIds: {
  scope: docIntelligence
  name: guid(docIntelligence.id, userId, cognitiveServicesUserRoleId)
  properties: {
    principalId: userId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'User'
  }
}]
