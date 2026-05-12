// ============================================
// Azure Logic App (Consumption Plan)
// 구독 정책으로 Storage SharedKey 차단 → Consumption 사용
// Managed Identity 기반 Blob/Search/Cognitive 접근
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Storage Account 이름 (데이터 Blob)')
param storageAccountName string

@description('Storage Account ID')
param storageAccountId string

@description('AI Services 엔드포인트')
param aiServicesEndpoint string

@description('Document Intelligence 엔드포인트')
param docIntelligenceEndpoint string

@description('AI Search 서비스 이름')
param searchServiceName string

@description('AI Search 엔드포인트')
param searchServiceEndpoint string

// ── 역할 정의 ID ──
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

// ── 기존 리소스 참조 ──
// AI Services: disableLocalAuth=true (정책 강제) → listKeys() 불가 → MI 인증 사용
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

// ── Managed API Connections (MI 기반) ──
resource blobConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'azureblob-mi'
  location: location
  properties: {
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azureblob')
    }
    displayName: 'Azure Blob (MI)'
    parameterValueSet: {
      name: 'managedIdentityAuth'
      values: {}
    }
  }
}

// ── RAG Indexing Workflow (Blob 트리거 → DI → Chunk → Embed → Index) ──
resource indexingWorkflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-index-${take(suffix, 8)}'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      triggers: {
        When_a_blob_is_added_or_modified: {
          type: 'ApiConnection'
          inputs: {
            host: {
              connection: {
                name: '@parameters(\'$connections\')[\'azureblob\'][\'connectionId\']'
              }
            }
            method: 'get'
            path: '/v2/datasets/@{encodeURIComponent(\'${storageAccountName}\')}/triggers/batch/onupdatedfile'
            queries: {
              folderId: 'JTJmcmF3LWRvY3VtZW50cw=='
              maxFileCount: 10
            }
          }
          recurrence: {
            frequency: 'Minute'
            interval: 3
          }
          splitOn: '@triggerBody()'
          metadata: {
            'JTJmcmF3LWRvY3VtZW50cw==': '/raw-documents'
          }
        }
      }
      actions: {
        Get_Blob_Content: {
          type: 'ApiConnection'
          inputs: {
            host: {
              connection: {
                name: '@parameters(\'$connections\')[\'azureblob\'][\'connectionId\']'
              }
            }
            method: 'get'
            path: '/v2/datasets/@{encodeURIComponent(\'${storageAccountName}\')}/files/@{encodeURIComponent(triggerBody()?[\'Path\'])}/content'
            queries: {
              inferContentType: true
            }
          }
          runAfter: {}
        }
        Analyze_with_DI: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: '${docIntelligenceEndpoint}documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30&outputContentFormat=markdown'
            headers: {
              'Content-Type': 'application/octet-stream'
            }
            body: '@body(\'Get_Blob_Content\')'
            authentication: {
              type: 'ManagedServiceIdentity'
              audience: 'https://cognitiveservices.azure.com'
            }
          }
          runAfter: {
            Get_Blob_Content: [ 'Succeeded' ]
          }
        }
        Delay_for_Analysis: {
          type: 'Wait'
          inputs: {
            interval: {
              count: 30
              unit: 'Second'
            }
          }
          runAfter: {
            Analyze_with_DI: [ 'Succeeded' ]
          }
        }
        Get_DI_Result: {
          type: 'Http'
          inputs: {
            method: 'GET'
            uri: '@outputs(\'Analyze_with_DI\')[\'headers\'][\'Operation-Location\']'
            authentication: {
              type: 'ManagedServiceIdentity'
              audience: 'https://cognitiveservices.azure.com'
            }
          }
          runAfter: {
            Delay_for_Analysis: [ 'Succeeded' ]
          }
        }
        Parse_DI_Content: {
          type: 'Compose'
          inputs: '@body(\'Get_DI_Result\')?[\'analyzeResult\']?[\'content\']'
          runAfter: {
            Get_DI_Result: [ 'Succeeded' ]
          }
        }
        Split_Into_Chunks: {
          type: 'Compose'
          inputs: '@split(string(outputs(\'Parse_DI_Content\')), \'\\n\\n\')'
          runAfter: {
            Parse_DI_Content: [ 'Succeeded' ]
          }
        }
        Generate_Embeddings: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: '${aiServicesEndpoint}openai/deployments/text-embedding-3-large/embeddings?api-version=2024-10-21'
            headers: {
              'Content-Type': 'application/json'
            }
            body: {
              input: '@take(outputs(\'Split_Into_Chunks\'), 16)'
            }
            authentication: {
              type: 'ManagedServiceIdentity'
              audience: 'https://cognitiveservices.azure.com'
            }
          }
          runAfter: {
            Split_Into_Chunks: [ 'Succeeded' ]
          }
        }
        Index_to_Search: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: '${searchServiceEndpoint}/indexes/law-documents-index/docs/index?api-version=2024-07-01'
            headers: {
              'Content-Type': 'application/json'
              'api-key': searchService.listAdminKeys().primaryKey
            }
            body: '@json(concat(\'{"value":[\', join(body(\'Generate_Embeddings\')?[\'data\'], \',\'), \']}\'))'
          }
          runAfter: {
            Generate_Embeddings: [ 'Succeeded' ]
          }
        }
        Move_to_Processed: {
          type: 'ApiConnection'
          inputs: {
            host: {
              connection: {
                name: '@parameters(\'$connections\')[\'azureblob\'][\'connectionId\']'
              }
            }
            method: 'post'
            path: '/v2/datasets/@{encodeURIComponent(\'${storageAccountName}\')}/copyFile'
            queries: {
              source: '@triggerBody()?[\'Path\']'
              destination: '/processed-documents/@{triggerBody()?[\'Name\']}'
              overwrite: true
            }
          }
          runAfter: {
            Index_to_Search: [ 'Succeeded' ]
          }
        }
      }
      parameters: {
        '$connections': {
          defaultValue: {}
          type: 'Object'
        }
      }
    }
    parameters: {
      '$connections': {
        value: {
          azureblob: {
            connectionId: blobConnection.id
            connectionName: 'azureblob-mi'
            connectionProperties: {
              authentication: {
                type: 'ManagedServiceIdentity'
              }
            }
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azureblob')
          }
        }
      }
    }
  }
  tags: {
    project: 'rag-indexing-lab'
    workflow: 'indexing-pipeline'
  }
}

// ── Crawl Workflow (일별 스케줄 → law.go.kr → Blob) ──
resource crawlWorkflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-crawl-${take(suffix, 8)}'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      triggers: {
        Daily_Schedule: {
          type: 'Recurrence'
          recurrence: {
            frequency: 'Day'
            interval: 1
            schedule: {
              hours: [ 6 ]
              minutes: [ 0 ]
            }
            timeZone: 'Korea Standard Time'
          }
        }
      }
      actions: {
        Fetch_Recent_Laws: {
          type: 'Http'
          inputs: {
            method: 'GET'
            uri: 'https://www.law.go.kr/DRF/lawSearch.do'
            queries: {
              OC: 'test'
              target: 'prec'
              type: 'XML'
              display: '20'
              sort: 'date'
            }
          }
          runAfter: {}
        }
        Log_Result: {
          type: 'Compose'
          inputs: {
            status: 'completed'
            timestamp: '@utcNow()'
            responseCode: '@outputs(\'Fetch_Recent_Laws\')[\'statusCode\']'
          }
          runAfter: {
            Fetch_Recent_Laws: [ 'Succeeded' ]
          }
        }
      }
      parameters: {}
    }
  }
  tags: {
    project: 'rag-indexing-lab'
    workflow: 'crawl-pipeline'
  }
}

// ── RBAC: Indexing Workflow → Storage Blob Data Contributor ──
resource blobContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, indexingWorkflow.id, storageBlobDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: indexingWorkflow.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Crawl Workflow → Storage Blob Data Contributor ──
resource crawlBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, crawlWorkflow.id, storageBlobDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: crawlWorkflow.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Indexing Workflow → Cognitive Services User ──
resource cogServicesRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, indexingWorkflow.id, cognitiveServicesUserRoleId)
  scope: resourceGroup()
  properties: {
    principalId: indexingWorkflow.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Indexing Workflow → Search Index Data Contributor ──
resource searchDataRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, indexingWorkflow.id, searchIndexDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: indexingWorkflow.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Indexing Workflow → Search Service Contributor ──
resource searchSvcRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, indexingWorkflow.id, searchServiceContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: indexingWorkflow.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

output indexingWorkflowName string = indexingWorkflow.name
output crawlWorkflowName string = crawlWorkflow.name
output indexingWorkflowPrincipalId string = indexingWorkflow.identity.principalId
