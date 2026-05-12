// ============================================
// Logic App 런타임 전용 Storage Account
// Logic App Standard는 WEBSITE_CONTENTAZUREFILECONNECTIONSTRING 필수
// 메인 Storage는 구독 정책으로 SharedKey 차단 → 별도 계정 사용
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

var storageAccountName = 'stlogic${take(suffix, 10)}'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
  }
  tags: {
    project: 'rag-indexing-lab'
    purpose: 'logic-app-runtime'
  }
}

output storageAccountName string = storageAccount.name
output connectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'
