// ============================================
// Logic App (Consumption) - 크롤 스케줄러
// 매일 21:00 UTC (= 06:00 KST) 실행
// → Azure Function HTTP 트리거 호출
// → Function이 law.go.kr 크롤링 + Blob 업로드
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('호출할 Azure Function의 HTTP 트리거 URL')
param crawlFunctionUrl string

@description('수집할 법령 건수')
param crawlerLimit int = 10

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
      triggers: {
        // 매일 21:00 UTC (= 한국 06:00 KST) 실행
        Daily_Crawl_Schedule: {
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
        // Azure Function HTTP 트리거 호출
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
              triggered_by: 'logic-apps-schedule'
              trigger_time: '@{utcNow()}'
            }
            retryPolicy: {
              type: 'fixed'
              count: 3
              interval: 'PT1M'
            }
          }
          runAfter: {}
        }
        // 결과 로깅 (성공/실패 무관)
        Log_Result: {
          type: 'Compose'
          inputs: {
            timestamp: '@{utcNow()}'
            function_status: '@{outputs(\'Call_Crawl_Function\')[\'statusCode\']}'
            crawl_result: '@{body(\'Call_Crawl_Function\')}'
          }
          runAfter: {
            Call_Crawl_Function: ['Succeeded', 'Failed', 'TimedOut']
          }
        }
      }
      parameters: {}
    }
  }
  tags: {
    project: 'rag-indexing-lab'
    workflow: 'crawl-scheduler'
  }
}

output crawlWorkflowName string = crawlWorkflow.name
output crawlWorkflowId string = crawlWorkflow.id
