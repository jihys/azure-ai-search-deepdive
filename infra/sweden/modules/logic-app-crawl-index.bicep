// ============================================
// Logic App (Consumption) - 크롤 + 인덱싱 파이프라인
// 1단계: 매일 21:00 UTC (= 06:00 KST) 크롤 Function 호출
// 2단계: 크롤 성공 시 AI Search Indexer 실행 트리거
//        (basic + verbalized 두 인덱서 모두 트리거)
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('호출할 Azure Function의 HTTP 트리거 URL (크롤)')
param crawlFunctionUrl string

@description('수집할 법령 건수')
param crawlerLimit int = 10

@description('AI Search 서비스 엔드포인트 (예: https://xxx.search.windows.net)')
param searchEndpoint string

@description('멀티모달 Basic Indexer 이름')
param basicIndexerName string = 'st-multimodal-basic-indexer'

@description('멀티모달 Verbalized Indexer 이름')
param verbalizedIndexerName string = 'st-multimodal-verbalized-indexer'

@description('Law 텍스트 Indexer 이름')
param lawIndexerName string = 'law-blob-indexer'

var workflowName = 'logic-crawl-index-ragi-${take(suffix, 8)}'

resource crawlIndexWorkflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: workflowName
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
        Daily_Pipeline_Schedule: {
          type: 'Recurrence'
          recurrence: {
            frequency: 'Day'
            interval: 1
            schedule: {
              hours: ['21']
              minutes: [0]
            }
            timeZone: 'UTC'
          }
        }
      }
      actions: {
        // ── Step 1: 크롤링 Function 호출 ──
        Call_Crawl_Function: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: crawlFunctionUrl
            headers: {
              'Content-Type': 'application/json'
            }
            body: {
              limit: crawlerLimit
              triggered_by: 'logic-apps-pipeline'
              trigger_time: '@{utcNow()}'
            }
            retryPolicy: {
              type: 'fixed'
              count: 3
              interval: 'PT1M'
            }
            authentication: {
              type: 'ManagedServiceIdentity'
            }
          }
          runAfter: {}
        }

        // ── Step 2: 크롤 결과 확인 (신규 데이터 유무) ──
        Check_New_Data: {
          type: 'If'
          expression: {
            and: [
              {
                greater: [
                  '@body(\'Call_Crawl_Function\')?[\'total_uploaded\']'
                  0
                ]
              }
            ]
          }
          runAfter: {
            Call_Crawl_Function: ['Succeeded']
          }
          actions: {
            // ── Step 3a: Law 텍스트 인덱서 트리거 ──
            Run_Law_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '${searchEndpoint}/indexers/${lawIndexerName}/run?api-version=2024-11-01-preview'
                headers: {
                  'Content-Type': 'application/json'
                }
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {}
            }
            // ── Step 3b: 멀티모달 Basic 인덱서 트리거 ──
            Run_Basic_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '${searchEndpoint}/indexers/${basicIndexerName}/run?api-version=2024-11-01-preview'
                headers: {
                  'Content-Type': 'application/json'
                }
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {
                Run_Law_Indexer: ['Succeeded', 'Failed']
              }
            }
            // ── Step 3c: 멀티모달 Verbalized 인덱서 트리거 ──
            Run_Verbalized_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '${searchEndpoint}/indexers/${verbalizedIndexerName}/run?api-version=2024-11-01-preview'
                headers: {
                  'Content-Type': 'application/json'
                }
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {
                Run_Basic_Indexer: ['Succeeded', 'Failed']
              }
            }
          }
          else: {
            actions: {
              // 신규 데이터 없음 → 인덱서 실행 안 함
              Skip_Indexing: {
                type: 'Compose'
                inputs: {
                  message: 'No new data uploaded. Skipping indexer execution.'
                  timestamp: '@{utcNow()}'
                }
              }
            }
          }
        }

        // ── Step 4: 결과 로깅 ──
        Log_Pipeline_Result: {
          type: 'Compose'
          inputs: {
            timestamp: '@{utcNow()}'
            crawl_status: '@{outputs(\'Call_Crawl_Function\')[\'statusCode\']}'
            crawl_result: '@{body(\'Call_Crawl_Function\')}'
            indexing_triggered: '@{equals(outputs(\'Check_New_Data\')?[\'status\'], \'Succeeded\')}'
          }
          runAfter: {
            Check_New_Data: ['Succeeded', 'Failed', 'Skipped']
          }
        }
      }
      parameters: {}
    }
  }
  tags: {
    project: 'rag-indexing-lab'
    workflow: 'crawl-index-pipeline'
  }
}

output workflowName string = crawlIndexWorkflow.name
output workflowId string = crawlIndexWorkflow.id
output workflowPrincipalId string = crawlIndexWorkflow.identity.principalId
