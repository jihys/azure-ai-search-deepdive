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
