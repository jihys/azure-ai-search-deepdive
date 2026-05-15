// ============================================
// [HISTORICAL] Search → AOAI Shared Private Link 패치
//
// 이 패치는 이미 infra/sweden/modules/ai-search-spl.bicep 의
// 'spl-aiservices' 로 존재하는 동일 리소스입니다.
// (ai-search-spl.bicep 은 SPL Approved 재배포 충돌 방지를 위해
//  main.bicep 에서 자동 호출되지 않고, 최초 1회 수동 실행합니다.)
// ============================================
// Deploy only the missing spl-aiservices SPL
@description('AI Search 서비스 이름')
param searchServiceName string = 'search-ragi-dyn6dtfu'

@description('AI Services 리소스 ID')
param aiServicesId string

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

resource sharedPlAiServices 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2024-06-01-preview' = {
  parent: searchService
  name: 'spl-aiservices'
  properties: {
    privateLinkResourceId: aiServicesId
    groupId: 'cognitiveservices_account'
    requestMessage: 'AI Search Knowledge Agent planner needs access to AOAI'
  }
}

output id string = sharedPlAiServices.id
output status string = sharedPlAiServices.properties.status
