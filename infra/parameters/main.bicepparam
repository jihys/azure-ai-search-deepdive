using '../main.bicep'

param resourceGroupName = 'rg-rag-indexing-lab-swc'
param location = 'swedencentral'
param embeddingDeploymentName = 'text-embedding-3-large'
param gpt54DeploymentName = 'gpt-5.4'
param gpt54ModelVersion = '2026-03-05'
param searchSku = 'standard'
param blobContainerName = 'raw-documents'
param jumpvmAdminUsername = 'azureadmin'
// jumpvmAdminPassword: 배포 시 --parameters jumpvmAdminPassword=<password> 로 전달
//   ex) az deployment sub create ... --parameters jumpvmAdminPassword='MyP@ss1234!'
param jumpvmAdminPassword = ''

// jihyeseo@MngEnvMCAP719772.onmicrosoft.com 의 Object ID
param jumpvmEntraUserObjectIds = ['4cb458b5-ef0c-403d-8162-c39855018986']
