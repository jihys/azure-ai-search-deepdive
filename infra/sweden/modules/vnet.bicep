// ============================================
// Virtual Network + Private DNS Zones
// Sweden Central - Private Networking
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

var vnetName = 'vnet-ragi-${take(suffix, 8)}'
var nsgName = 'nsg-pep-ragi-${take(suffix, 8)}'
var jumpSubnetName = 'snet-jump'
var pepSubnetName = 'snet-pep'
var funcSubnetName = 'snet-func'

// ── NSG (Private Endpoint 서브넷용) ──
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: []
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Virtual Network ──
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    subnets: [
      {
        // JumpVM 서브넷 - AI Search 등 Private Endpoint에 접근하기 위한 관리자 VM
        name: jumpSubnetName
        properties: {
          addressPrefix: '10.0.3.0/24'
        }
      }
      {
        name: pepSubnetName
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: { id: nsg.id }
          // Private Endpoint에서 필수: 네트워크 정책 비활성화
          privateEndpointNetworkPolicies: 'Disabled'
          privateLinkServiceNetworkPolicies: 'Disabled'
        }
      }
      {
        // Azure Functions VNet Integration 전용 서브넷 (아웃바운드)
        // EP1 Plan이 Storage PE에 접근하기 위한 아웃바운드 경로
        name: funcSubnetName
        properties: {
          addressPrefix: '10.0.2.0/24'
          delegations: [
            {
              name: 'delegation-func'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Private DNS Zone: Storage Blob ──
resource blobDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.core.windows.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource blobDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: blobDnsZone
  name: 'link-blob-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private DNS Zone: AI Search ──
resource searchDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.search.windows.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource searchDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: searchDnsZone
  name: 'link-search-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private DNS Zone: Cognitive Services (Doc Intelligence + AI Services) ──
resource cogServicesDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource cogServicesDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: cogServicesDnsZone
  name: 'link-cog-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private DNS Zone: OpenAI (AIServices kind에서도 openai 엔드포인트 사용) ──
resource openaiDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource openaiDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: openaiDnsZone
  name: 'link-openai-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private DNS Zone: Azure ML (AI Foundry Hub) ──
resource azuremlDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.api.azureml.ms'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource azuremlDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: azuremlDnsZone
  name: 'link-azureml-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private DNS Zone: Azure ML Notebooks ──
resource notebooksDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.notebooks.azure.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource notebooksDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: notebooksDnsZone
  name: 'link-notebooks-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private DNS Zone: Key Vault ──
resource vaultDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource vaultDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: vaultDnsZone
  name: 'link-vault-${take(suffix, 8)}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Outputs ──
output vnetId string = vnet.id
output vnetName string = vnet.name
output pepSubnetId string = '${vnet.id}/subnets/${pepSubnetName}'
output funcSubnetId string = '${vnet.id}/subnets/${funcSubnetName}'
output jumpSubnetId string = '${vnet.id}/subnets/${jumpSubnetName}'
output blobDnsZoneId string = blobDnsZone.id
output searchDnsZoneId string = searchDnsZone.id
output cogServicesDnsZoneId string = cogServicesDnsZone.id
output openaiDnsZoneId string = openaiDnsZone.id
output azuremlDnsZoneId string = azuremlDnsZone.id
output notebooksDnsZoneId string = notebooksDnsZone.id
output vaultDnsZoneId string = vaultDnsZone.id
