// ============================================
// Logic App (Consumption) - 크롤 + 전처리 통합 스케줄러
// 매일 21:00 UTC (= 06:00 KST)
//   1. Call_Crawl_Function_All_Sources → /api/crawl  (4-source 병렬 크롤)
//   2. Check_Crawl_Success → if status=success
//       Parallel_Preprocess_Sources → /api/preprocess × {prec, detc, expc, admrul}
//   3. Log_Pipeline_Completion
//
// Self-reference SetVariable 회피: pipelineResults 누적 변수 제거,
// 모든 결과는 마지막 Compose 액션에서 한 번에 모음.
// → Sweden/Korea 동일 정의로 재사용 가능.
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('호출할 크롤 Function HTTP 트리거 URL (/api/crawl)')
param crawlFunctionUrl string

@description('호출할 Preprocess Function HTTP 트리거 URL (/api/preprocess)')
param preprocessFunctionUrl string

@description('수집할 법령 건수 (0 = 무제한)')
param crawlerLimit int = 0

var workflowName = 'logic-crawl-ragi-${take(suffix, 8)}'

resource crawlWorkflow 'Microsoft.Logic/workflows@2019-05-01' = {
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
      parameters: {}
      triggers: {
        Daily_Schedule_Crawl_and_Preprocess: {
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
          metadata: {
            description: '06:00 KST - crawl + preprocess pipeline'
          }
        }
      }
      actions: {
        Initialize_Today_Date: {
          type: 'InitializeVariable'
          inputs: {
            variables: [
              {
                name: 'crawlDate'
                type: 'string'
                value: '@{formatDateTime(utcNow(), \'yyyy-MM-dd\')}'
              }
            ]
          }
          runAfter: {}
        }
        Call_Crawl_Function_All_Sources: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: crawlFunctionUrl
            headers: {
              'Content-Type': 'application/json'
            }
            body: {
              source: 'all'
              max_pages: crawlerLimit
              detail_workers: 5
              triggered_by: 'logic-app-crawl-preprocess'
            }
            retryPolicy: {
              type: 'fixed'
              count: 3
              interval: 'PT1M'
            }
          }
          runAfter: {
            Initialize_Today_Date: ['Succeeded']
          }
          limit: {
            timeout: 'PT2H'
          }
          metadata: {
            description: 'crawl Function - all 4 sources (prec/detc/expc/admrul)'
          }
        }
        Check_Crawl_Success: {
          type: 'If'
          expression: {
            and: [
              {
                equals: [
                  '@body(\'Call_Crawl_Function_All_Sources\')?[\'status\']'
                  'success'
                ]
              }
            ]
          }
          actions: {
            Parallel_Preprocess_Sources: {
              type: 'Scope'
              actions: {
                Preprocess_Prec: {
                  type: 'Http'
                  inputs: {
                    method: 'POST'
                    uri: preprocessFunctionUrl
                    headers: {
                      'Content-Type': 'application/json'
                    }
                    body: {
                      source: 'prec'
                      crawl_date: '@{variables(\'crawlDate\')}'
                      triggered_by: 'logic-app-crawl-preprocess'
                    }
                  }
                  limit: {
                    timeout: 'PT1H'
                  }
                  metadata: {
                    description: 'prec JSON -> JSONL'
                  }
                }
                Preprocess_Detc: {
                  type: 'Http'
                  inputs: {
                    method: 'POST'
                    uri: preprocessFunctionUrl
                    headers: {
                      'Content-Type': 'application/json'
                    }
                    body: {
                      source: 'detc'
                      crawl_date: '@{variables(\'crawlDate\')}'
                      triggered_by: 'logic-app-crawl-preprocess'
                    }
                  }
                  limit: {
                    timeout: 'PT1H'
                  }
                  metadata: {
                    description: 'detc JSON -> JSONL'
                  }
                }
                Preprocess_Expc: {
                  type: 'Http'
                  inputs: {
                    method: 'POST'
                    uri: preprocessFunctionUrl
                    headers: {
                      'Content-Type': 'application/json'
                    }
                    body: {
                      source: 'expc'
                      crawl_date: '@{variables(\'crawlDate\')}'
                      triggered_by: 'logic-app-crawl-preprocess'
                    }
                  }
                  limit: {
                    timeout: 'PT1H'
                  }
                  metadata: {
                    description: 'expc JSON -> JSONL'
                  }
                }
                Preprocess_Admrul: {
                  type: 'Http'
                  inputs: {
                    method: 'POST'
                    uri: preprocessFunctionUrl
                    headers: {
                      'Content-Type': 'application/json'
                    }
                    body: {
                      source: 'admrul'
                      crawl_date: '@{variables(\'crawlDate\')}'
                      triggered_by: 'logic-app-crawl-preprocess'
                    }
                  }
                  limit: {
                    timeout: 'PT1H'
                  }
                  metadata: {
                    description: 'admrul JSON -> JSONL'
                  }
                }
              }
              runAfter: {}
              metadata: {
                description: '4-source parallel preprocess (Integration: JSON -> JSONL)'
              }
            }
          }
          else: {
            actions: {}
          }
          runAfter: {
            Call_Crawl_Function_All_Sources: ['Succeeded']
          }
        }
        Log_Pipeline_Completion: {
          type: 'Compose'
          inputs: {
            completedAt: '@{utcNow()}'
            crawlDate: '@{variables(\'crawlDate\')}'
            crawlStatus: '@{body(\'Call_Crawl_Function_All_Sources\')?[\'status\']}'
            crawlResult: '@body(\'Call_Crawl_Function_All_Sources\')'
            preprocessResults: {
              prec: '@body(\'Preprocess_Prec\')'
              detc: '@body(\'Preprocess_Detc\')'
              expc: '@body(\'Preprocess_Expc\')'
              admrul: '@body(\'Preprocess_Admrul\')'
            }
          }
          runAfter: {
            Check_Crawl_Success: ['Succeeded', 'Failed', 'Skipped']
          }
          metadata: {
            description: 'final pipeline result log (crawl + 4-source preprocess)'
          }
        }
      }
    }
  }
  tags: {
    project: 'rag-indexing-lab'
    workflow: 'crawl-preprocess-workflow'
  }
}

output crawlWorkflowName string = crawlWorkflow.name
output crawlWorkflowId string = crawlWorkflow.id
