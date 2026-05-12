using '../main.bicep'

param resourceGroupName = 'rg-rag-indexing-lab-krc'
param docIntelResourceGroupName = 'rg-rag-indexing-lab-eus2'
param location = 'koreacentral'
param docIntelLocation = 'eastus2'
param embeddingDeploymentName = 'text-embedding-3-large'
param gptDeploymentName = 'gpt-5.4'
param gptModelName = 'gpt-5.4'
param gptModelVersion = '2026-03-05'
param searchSku = 'standard'
param blobContainerName = 'raw-documents'
param jumpvmAdminUsername = 'azureadmin'
// jumpvmAdminPassword: 배포 시 --parameters jumpvmAdminPassword=<password> 로 전달
//   ex) az deployment sub create ... --parameters jumpvmAdminPassword='MyP@ss1234!'
param jumpvmAdminPassword = ''
// jihyeseo@MngEnvMCAP719772.onmicrosoft.com 의 Object ID
param jumpvmEntraUserObjectIds = ['4cb458b5-ef0c-403d-8162-c39855018986']
