// ============================================
// Azure Logic App (Workflow Service Plan)
// Managed Identity 기반 Storage + Cognitive Services + Search 접근
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Storage Account 이름')
param storageAccountName string

@description('Storage Account ID')
param storageAccountId string

@description('AI Services 계정 이름')
param aiServicesName string

@description('AI Services 엔드포인트')
param aiServicesEndpoint string

@description('Document Intelligence 계정 이름')
param docIntelligenceName string

@description('Document Intelligence 엔드포인트')
param docIntelligenceEndpoint string

@description('AI Search 서비스 이름')
param searchServiceName string

@description('AI Search 엔드포인트')
param searchServiceEndpoint string

@description('Storage 연결 문자열 (Logic App 런타임 필수)')
@secure()
param storageConnectionString string

var logicAppName = 'logic-ragi-${take(suffix, 8)}'
var appServicePlanName = 'asp-ragi-${take(suffix, 8)}'

// Storage 역할 정의 ID
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageAccountContributorRoleId = '17d1049b-9a84-46fb-8f53-869881c3d3ab'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageFileDataPrivilegedContributorRoleId = '69566ab7-960f-475b-8e7c-b3118f30c6bd'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

// Cognitive Services + Search 역할 정의 ID
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

// 기존 리소스 참조 (키 조회용)
resource aiServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesName
}
resource docIntelAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: docIntelligenceName
}
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

// Logic App용 App Service Plan (Workflow Standard)
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'WS1'
    tier: 'WorkflowStandard'
  }
  kind: 'elastic'
  properties: {
    maximumElasticWorkerCount: 20
    isSpot: false
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

// Logic App (Standard) - MI + 서비스 연결 설정
resource logicApp 'Microsoft.Web/sites@2023-12-01' = {
  name: logicAppName
  location: location
  kind: 'functionapp,workflowapp'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      netFrameworkVersion: 'v6.0'
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'dotnet' }
        { name: 'APP_KIND', value: 'workflowApp' }
        // 런타임 전용 Storage (SharedKey 허용 별도 계정)
        { name: 'AzureWebJobsStorage', value: storageConnectionString }
        { name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING', value: storageConnectionString }
        { name: 'WEBSITE_CONTENTSHARE', value: logicAppName }
        { name: 'WEBSITE_SKIP_CONTENTSHARE_VALIDATION', value: '1' }
        // Extension Bundle
        { name: 'AzureFunctionsJobHost__extensionBundle__id', value: 'Microsoft.Azure.Functions.ExtensionBundle.Workflows' }
        { name: 'AzureFunctionsJobHost__extensionBundle__version', value: '[1.*, 2.0.0)' }
        // 워크플로우 연결 설정 (서비스 제공자용)
        { name: 'AZURE_OPENAI_ENDPOINT', value: aiServicesEndpoint }
        { name: 'AZURE_OPENAI_KEY', value: aiServicesAccount.listKeys().key1 }
        { name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', value: docIntelligenceEndpoint }
        { name: 'AZURE_DOCUMENT_INTELLIGENCE_KEY', value: docIntelAccount.listKeys().key1 }
        { name: 'AZURE_SEARCH_SERVICE_ENDPOINT', value: searchServiceEndpoint }
        { name: 'AZURE_SEARCH_ADMIN_KEY', value: searchService.listAdminKeys().primaryKey }
        { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
        { name: 'AZURE_RESOURCE_GROUP', value: resourceGroup().name }
        { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
      ]
    }
    httpsOnly: true
  }
  tags: {
    project: 'rag-indexing-lab'
  }
}

// Storage Blob Data Owner
resource blobDataOwnerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, storageBlobDataOwnerRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Storage Account Contributor
resource storageContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, storageAccountContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageAccountContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Storage Queue Data Contributor
resource queueDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, storageQueueDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Storage File Data Privileged Contributor
resource fileDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, storageFileDataPrivilegedContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageFileDataPrivilegedContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Storage Table Data Contributor
resource tableDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, storageTableDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

output logicAppName string = logicApp.name
output logicAppId string = logicApp.id
output logicAppPrincipalId string = logicApp.identity.principalId

// ============================================
// Managed API Connections (MI 기반)
// ============================================
resource blobConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'azureblob'
  location: location
  kind: 'V2'
  properties: {
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azureblob')
    }
    displayName: 'Azure Blob Storage (MI)'
    parameterValueType: 'Alternative'
  }
}

resource searchConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'azureaisearch'
  location: location
  kind: 'V2'
  properties: {
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azureaisearch')
    }
    displayName: 'Azure AI Search (MI)'
    parameterValueType: 'Alternative'
  }
}

// Logic App → API Connection 접근 정책
resource blobAccessPolicy 'Microsoft.Web/connections/accessPolicies@2016-06-01' = {
  parent: blobConnection
  name: '${logicAppName}-blob-policy'
  location: location
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        tenantId: subscription().tenantId
        objectId: logicApp.identity.principalId
      }
    }
  }
}

resource searchAccessPolicy 'Microsoft.Web/connections/accessPolicies@2016-06-01' = {
  parent: searchConnection
  name: '${logicAppName}-search-policy'
  location: location
  properties: {
    principal: {
      type: 'ActiveDirectory'
      identity: {
        tenantId: subscription().tenantId
        objectId: logicApp.identity.principalId
      }
    }
  }
}

// ============================================
// Cognitive Services + Search RBAC
// ============================================
resource cogServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, cognitiveServicesUserRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource searchDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, searchIndexDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource searchSvcContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, searchServiceContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

output blobConnectionRuntimeUrl string = reference(blobConnection.id, '2016-06-01', 'full').properties.connectionRuntimeUrl
output searchConnectionRuntimeUrl string = reference(searchConnection.id, '2016-06-01', 'full').properties.connectionRuntimeUrl
