// ============================================
// Storage Account + Blob Container
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Blob 컨테이너 이름')
param containerName string = 'raw-documents'

@description('Storage Data 역할을 부여할 Entra ID 사용자 Object ID 배열')
param userObjectIds array = []

var storageAccountName = 'stragi${take(suffix, 10)}'

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
    allowSharedKeyAccess: false
    // Public network access enabled (workshop public variant)
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

// 전처리된 문서를 저장할 컨테이너
resource processedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'processed-documents'
  properties: {
    publicAccess: 'None'
  }
}

// ============================================
// RBAC: Storage Data 역할 부여
// ============================================

// Storage Blob Data Contributor
resource blobRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for userId in userObjectIds: {
  scope: storageAccount
  name: guid(storageAccount.id, userId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    principalId: userId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalType: 'User'
  }
}]

// Storage Queue Data Contributor
resource queueRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for userId in userObjectIds: {
  scope: storageAccount
  name: guid(storageAccount.id, userId, '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
  properties: {
    principalId: userId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
    principalType: 'User'
  }
}]

// Storage Table Data Contributor
resource tableRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for userId in userObjectIds: {
  scope: storageAccount
  name: guid(storageAccount.id, userId, '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
  properties: {
    principalId: userId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
    principalType: 'User'
  }
}]

output storageAccountName string = storageAccount.name
output storageAccountId string = storageAccount.id
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
