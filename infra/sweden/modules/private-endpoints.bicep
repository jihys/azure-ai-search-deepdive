// ============================================
// Private Endpoints - 모든 서비스 인바운드 프라이빗 접근
// Storage / AI Search / AI Services / Doc Intelligence
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('Private Endpoint가 배치될 Subnet ID')
param pepSubnetId string

@description('Storage Account 리소스 ID')
param storageAccountId string

@description('AI Search 서비스 리소스 ID')
param searchServiceId string

@description('AI Services 계정 리소스 ID (OpenAI)')
param aiServicesId string

@description('Document Intelligence 리소스 ID')
param docIntelligenceId string

@description('AI Foundry Hub 리소스 ID')
param hubId string

@description('Key Vault 리소스 ID')
param keyVaultId string

@description('Blob Private DNS Zone ID')
param blobDnsZoneId string

@description('AI Search Private DNS Zone ID')
param searchDnsZoneId string

@description('Cognitive Services Private DNS Zone ID')
param cogServicesDnsZoneId string

@description('OpenAI Private DNS Zone ID')
param openaiDnsZoneId string

@description('Azure ML Private DNS Zone ID')
param azuremlDnsZoneId string

@description('Azure ML Notebooks Private DNS Zone ID')
param notebooksDnsZoneId string

@description('Key Vault Private DNS Zone ID')
param vaultDnsZoneId string

@description('Foundry Agent Service (services.ai.azure.com) Private DNS Zone ID')
param servicesAiDnsZoneId string

// ── Storage Blob Private Endpoint ──
resource storageBlobPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-blob-ragi-${take(suffix, 8)}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-blob-conn'
        properties: {
          privateLinkServiceId: storageAccountId
          groupIds: ['blob']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource storageBlobDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: storageBlobPe
  name: 'blob-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: { privateDnsZoneId: blobDnsZoneId }
      }
    ]
  }
}

// ── AI Search Private Endpoint ──
resource searchPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-search-ragi-${take(suffix, 8)}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-search-conn'
        properties: {
          privateLinkServiceId: searchServiceId
          groupIds: ['searchService']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource searchDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: searchPe
  name: 'search-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'search'
        properties: { privateDnsZoneId: searchDnsZoneId }
      }
    ]
  }
}

// ── AI Services (OpenAI) Private Endpoint ──
// kind=AIServices → cognitiveservices + openai 두 DNS 존 등록
resource aiServicesPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-aiservices-ragi-${take(suffix, 8)}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-aiservices-conn'
        properties: {
          privateLinkServiceId: aiServicesId
          groupIds: ['account']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource aiServicesDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: aiServicesPe
  name: 'aiservices-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices'
        properties: { privateDnsZoneId: cogServicesDnsZoneId }
      }
      {
        name: 'openai'
        properties: { privateDnsZoneId: openaiDnsZoneId }
      }
      {
        name: 'services-ai'
        properties: { privateDnsZoneId: servicesAiDnsZoneId }
      }
    ]
  }
}

// ── Document Intelligence Private Endpoint ──
resource docIntelPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-docintel-ragi-${take(suffix, 8)}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-docintel-conn'
        properties: {
          privateLinkServiceId: docIntelligenceId
          groupIds: ['account']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource docIntelDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: docIntelPe
  name: 'docintel-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices'
        properties: { privateDnsZoneId: cogServicesDnsZoneId }
      }
    ]
  }
}

// ── AI Foundry Hub Private Endpoint ──
resource hubPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-hub-ragi-${take(suffix, 8)}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-hub-conn'
        properties: {
          privateLinkServiceId: hubId
          groupIds: ['amlworkspace']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource hubDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: hubPe
  name: 'hub-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'azureml'
        properties: { privateDnsZoneId: azuremlDnsZoneId }
      }
      {
        name: 'notebooks'
        properties: { privateDnsZoneId: notebooksDnsZoneId }
      }
    ]
  }
}

// ── Key Vault Private Endpoint ──
resource kvPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-kv-ragi-${take(suffix, 8)}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-kv-conn'
        properties: {
          privateLinkServiceId: keyVaultId
          groupIds: ['vault']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource kvDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: kvPe
  name: 'kv-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'vaultcore'
        properties: { privateDnsZoneId: vaultDnsZoneId }
      }
    ]
  }
}

// ── Outputs ──
output storagePeId string = storageBlobPe.id
output searchPeId string = searchPe.id
output aiServicesPeId string = aiServicesPe.id
output docIntelPeId string = docIntelPe.id
output hubPeId string = hubPe.id
output kvPeId string = kvPe.id
