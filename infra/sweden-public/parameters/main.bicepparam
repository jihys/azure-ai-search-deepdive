using '../main.bicep'

// PUBLIC variant (workshop) — separate RG so it doesn't clash with the private deployment.
param resourceGroupName = 'rg-rag-indexing-lab-swc-pub'
param location = 'swedencentral'
param embeddingDeploymentName = 'text-embedding-3-large'
param gptDeploymentName = 'gpt-5.4'
param gptModelName = 'gpt-5.4'
param gptModelVersion = '2026-03-05'
param searchSku = 'standard'
param blobContainerName = 'raw-documents'

// 핸즈온 사용자(들)의 Entra ID Object ID 를 넣으면
// Storage / AI Search / OpenAI / Doc Intelligence 데이터 평면 RBAC 가 자동으로 부여됩니다.
//   az ad signed-in-user show --query id -o tsv
// 예: param userObjectIds = ['00000000-0000-0000-0000-000000000000']
param userObjectIds = []

