// AI Search MSI → Azure AI Services (AOAI) RBAC
// Skillset 의 AzureOpenAIEmbeddingSkill (apiKey 미사용 — MSI auth) 호출 권한 부여
@description('AOAI 계정 이름 (existing reference)')
param aoaiAccountName string

@description('AI Search System-Assigned MSI principalId')
param aiSearchPrincipalId string

// Cognitive Services OpenAI User
var openAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aoaiAccountName
}

resource searchToOpenAIRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aoai.id, aiSearchPrincipalId, openAIUserRoleId)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAIUserRoleId)
    principalId: aiSearchPrincipalId
    principalType: 'ServicePrincipal'
  }
}
