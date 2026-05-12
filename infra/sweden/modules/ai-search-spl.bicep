// ============================================
// AI Search Shared Private Links (초회 배포 전용)
// SPL은 Approved 상태가 된 후 재배포 시 ARM이 "conflicting update" 오류를 냅니다.
// 이 모듈은 main.bicep에서 호출하지 않고, 최초 환경 구성 시에만 직접 실행합니다:
//
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file infra/sweden/modules/ai-search-spl.bicep \
//     --parameters searchServiceName=<name> \
//                  storageAccountId=<id> \
//                  aiServicesId=<id> \
//                  docIntelligenceId=<id>
// ============================================

@description('AI Search 서비스 이름')
param searchServiceName string

@description('Storage Account 리소스 ID')
param storageAccountId string

@description('AI Services 리소스 ID')
param aiServicesId string

@description('Document Intelligence 리소스 ID')
param docIntelligenceId string

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

// ── Shared Private Link: AI Search → Storage Blob ──
resource sharedPlStorage 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2024-06-01-preview' = {
  parent: searchService
  name: 'spl-blob'
  properties: {
    privateLinkResourceId: storageAccountId
    groupId: 'blob'
    requestMessage: 'AI Search indexer needs read access to blob storage'
  }
}

// ── Shared Private Link: AI Search → AI Services ──
// AIServices kind의 올바른 groupId: 'cognitiveservices_account'
resource sharedPlAiServices 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2024-06-01-preview' = {
  parent: searchService
  name: 'spl-aiservices'
  properties: {
    privateLinkResourceId: aiServicesId
    groupId: 'cognitiveservices_account'
    requestMessage: 'AI Search skillset needs access to AI Services for embeddings'
  }
}

// ── Shared Private Link: AI Search → Document Intelligence ──
resource sharedPlDocIntel 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2024-06-01-preview' = {
  parent: searchService
  name: 'spl-docintel'
  properties: {
    privateLinkResourceId: docIntelligenceId
    groupId: 'cognitiveservices_account'
    requestMessage: 'AI Search skillset needs access to Document Intelligence for layout analysis'
  }
}

output splBlobId string = sharedPlStorage.id
output splAiServicesId string = sharedPlAiServices.id
output splDocIntelId string = sharedPlDocIntel.id
