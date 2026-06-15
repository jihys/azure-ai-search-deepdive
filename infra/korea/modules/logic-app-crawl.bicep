// ============================================
// Logic App (Consumption) — Durable Functions Orchestrator 호출 + 폴링
//
// 흐름:
//   1. Daily 06:00 KST 스케줄 (또는 수동 트리거)
//   2. Start_Orchestration (HTTP POST /api/orchestrators/crawl_preprocess)
//        → 202 Accepted + statusQueryGetUri (즉시 반환, 타임아웃 무관)
//   3. Until_Completed (Until loop) — statusQueryGetUri 폴링 (30s 간격, 최대 4시간)
//        → runtimeStatus in [Completed, Failed, Terminated, Canceled] 시 종료
//   4. Log_Pipeline_Completion — 최종 output 저장
//
// 장점 (Method B):
//   - HTTP 11분 타임아웃 회피 (Durable 비동기 패턴)
//   - 크롤 → 전처리 순서 보장 (orchestrator 내부에서 처리)
//   - 4 source × N 배치 fan-out (Consumption 자동 스케일)
//   - 중복 제거: existing seqs + listing dedup + preprocess idempotency
//
// Sweden/Korea 동일 정의 — 두 리전 모두 적용 가능.
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Durable Functions HTTP starter URL (예: https://func-app/api/orchestrators/crawl_preprocess)')
param orchestratorUrl string

@description('수집할 법령 페이지 수 (0 = 무제한)')
param crawlerLimit int = 0

@description('상세 페이지 병렬 워커 수 (단일 Activity 내) — Consumption 자동 스케일과 결합되어 동시성 ↑')
param detailWorkers int = 20

@description('폴링 간격 (초)')
param pollIntervalSeconds int = 30

@description('최대 폴링 대기 시간 (ISO 8601 duration)')
param pollMaxDuration string = 'PT4H'

@description('최대 폴링 횟수 (Until loop 안전 상한)')
param pollMaxIterations int = 480

@description('AI Search endpoint (예: https://search-ragi-xxxx.search.windows.net)')
param searchEndpoint string

@description('AI Search Service 리소스 ID (RBAC용)')
param searchServiceId string

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
      parameters: {
        searchEndpoint: {
          type: 'String'
          defaultValue: searchEndpoint
        }
      }
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
            description: '06:00 KST - Durable orchestrator (crawl + preprocess)'
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
        Start_Orchestration: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: orchestratorUrl
            headers: {
              'Content-Type': 'application/json'
            }
            body: {
              source: 'all'
              max_pages: crawlerLimit
              detail_workers: detailWorkers
              triggered_by: 'logic-app-durable'
              // crawl_date 는 오늘 날짜 폴더에 raw json 을 저장하는 용도로만 쓰임.
              // preprocess 호출 시 orchestrator 내부에서 항상 "all" 로 강제하여
              // 모든 날짜의 raw-documents 가 processed-documents 와 일치하도록 보장됨.
              crawl_date: '@{variables(\'crawlDate\')}'
              skip_preprocess: false
            }
            retryPolicy: {
              type: 'fixed'
              count: 3
              interval: 'PT30S'
            }
          }
          // Logic App 은 202 응답을 자동 폴링하므로, Durable starter 가 반환하는
          // {statusQueryGetUri,...} 메타를 바로 받기 위해 async 패턴 비활성화
          operationOptions: 'DisableAsyncPattern'
          runAfter: {
            Initialize_Today_Date: ['Succeeded']
          }
          metadata: {
            description: 'Durable Functions HTTP starter — returns 202 + statusQueryGetUri (async polling disabled)'
          }
        }
        Initialize_Status_Url: {
          type: 'InitializeVariable'
          inputs: {
            variables: [
              {
                name: 'statusUrl'
                type: 'string'
                value: '@{body(\'Start_Orchestration\')?[\'statusQueryGetUri\']}'
              }
            ]
          }
          runAfter: {
            Start_Orchestration: ['Succeeded']
          }
        }
        Initialize_Status_Body: {
          type: 'InitializeVariable'
          inputs: {
            variables: [
              {
                name: 'orchestrationStatus'
                type: 'object'
                value: {
                  runtimeStatus: 'Pending'
                }
              }
            ]
          }
          runAfter: {
            Initialize_Status_Url: ['Succeeded']
          }
        }
        Until_Completed: {
          type: 'Until'
          expression: '@contains(createArray(\'Completed\',\'Failed\',\'Terminated\',\'Canceled\'), variables(\'orchestrationStatus\')?[\'runtimeStatus\'])'
          limit: {
            count: pollMaxIterations
            timeout: pollMaxDuration
          }
          actions: {
            Wait_Poll_Interval: {
              type: 'Wait'
              inputs: {
                interval: {
                  count: pollIntervalSeconds
                  unit: 'Second'
                }
              }
              runAfter: {}
            }
            Get_Orchestration_Status: {
              type: 'Http'
              inputs: {
                method: 'GET'
                uri: '@variables(\'statusUrl\')'
              }
              runAfter: {
                Wait_Poll_Interval: ['Succeeded']
              }
            }
            Update_Status: {
              type: 'SetVariable'
              inputs: {
                name: 'orchestrationStatus'
                value: '@body(\'Get_Orchestration_Status\')'
              }
              runAfter: {
                Get_Orchestration_Status: ['Succeeded']
              }
            }
          }
          runAfter: {
            Initialize_Status_Body: ['Succeeded']
          }
        }
        Log_Pipeline_Completion: {
          type: 'Compose'
          inputs: {
            completedAt: '@{utcNow()}'
            crawlDate: '@{variables(\'crawlDate\')}'
            runtimeStatus: '@{variables(\'orchestrationStatus\')?[\'runtimeStatus\']}'
            instanceId: '@{variables(\'orchestrationStatus\')?[\'instanceId\']}'
            createdTime: '@{variables(\'orchestrationStatus\')?[\'createdTime\']}'
            lastUpdatedTime: '@{variables(\'orchestrationStatus\')?[\'lastUpdatedTime\']}'
            output: '@variables(\'orchestrationStatus\')?[\'output\']'
          }
          runAfter: {
            Until_Completed: ['Succeeded']
          }
          metadata: {
            description: 'final pipeline result (Durable orchestrator output)'
          }
        }
        Check_Final_Status: {
          type: 'If'
          expression: {
            not: {
              equals: [
                '@variables(\'orchestrationStatus\')?[\'runtimeStatus\']'
                'Completed'
              ]
            }
          }
          actions: {
            Terminate_With_Failure: {
              type: 'Terminate'
              inputs: {
                runStatus: 'Failed'
                runError: {
                  code: 'OrchestrationFailed'
                  message: 'Durable orchestration ended with non-Completed status: @{variables(\'orchestrationStatus\')?[\'runtimeStatus\']}'
                }
              }
              runAfter: {}
            }
          }
          runAfter: {
            Log_Pipeline_Completion: ['Succeeded']
          }
        }
        // Step 2: 4개 법률 인덱서 Fire-and-forget 실행 (Managed Identity 인증)
        Run_Indexers_FireAndForget: {
          type: 'Scope'
          actions: {
            Run_Prec_Court_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '@{parameters(\'searchEndpoint\')}/indexers/prec-court-indexer/run?api-version=2024-11-01-preview'
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {}
            }
            Run_Const_Court_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '@{parameters(\'searchEndpoint\')}/indexers/const-court-indexer/run?api-version=2024-11-01-preview'
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {}
            }
            Run_Legis_Interp_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '@{parameters(\'searchEndpoint\')}/indexers/legis-interp-indexer/run?api-version=2024-11-01-preview'
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {}
            }
            Run_Admin_Appeal_Indexer: {
              type: 'Http'
              inputs: {
                method: 'POST'
                uri: '@{parameters(\'searchEndpoint\')}/indexers/admin-appeal-indexer/run?api-version=2024-11-01-preview'
                authentication: {
                  type: 'ManagedServiceIdentity'
                  audience: 'https://search.azure.com'
                }
              }
              runAfter: {}
            }
          }
          runAfter: {
            Check_Final_Status: ['Succeeded']
          }
          metadata: {
            description: 'Step 2: Fire-and-forget — 4개 법률 인덱서 실행 (MI 인증, 완료 대기 없음)'
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

// ── RBAC: Logic App → AI Search Service Contributor (Indexer Run 호출용) ──
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
resource logicAppSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchServiceId, crawlWorkflow.id, searchServiceContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: crawlWorkflow.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
    principalType: 'ServicePrincipal'
  }
}

output crawlWorkflowName string = crawlWorkflow.name
output crawlWorkflowId string = crawlWorkflow.id
output crawlWorkflowPrincipalId string = crawlWorkflow.identity.principalId
