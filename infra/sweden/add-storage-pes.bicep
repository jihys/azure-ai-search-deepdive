// ============================================
// Incremental add: Storage Queue/Table/File Private Endpoints
// + corresponding Private DNS Zones + VNet links
// Targets existing Sweden non-public deployment.
// ============================================

targetScope = 'resourceGroup'

param location string = resourceGroup().location
param suffix string = 'dyn6dtfu'
param vnetName string = 'vnet-ragi-dyn6dtfu'
param pepSubnetName string = 'snet-pep'
param storageAccountName string = 'stragidyn6dtfun6'

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' existing = {
  name: vnetName
}

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: storageAccountName
}

var pepSubnetId = '${vnet.id}/subnets/${pepSubnetName}'

// ── Private DNS Zones (queue / table / file) ──
resource queueDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.queue.core.windows.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource queueDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: queueDnsZone
  name: 'link-queue-${suffix}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

resource tableDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.table.core.windows.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource tableDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: tableDnsZone
  name: 'link-table-${suffix}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

resource fileDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.file.core.windows.net'
  location: 'global'
  tags: { project: 'rag-indexing-lab' }
}

resource fileDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: fileDnsZone
  name: 'link-file-${suffix}'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

// ── Private Endpoints ──
resource queuePe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-queue-ragi-${suffix}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-queue-conn'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: ['queue']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource queueDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: queuePe
  name: 'queue-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'queue'
        properties: { privateDnsZoneId: queueDnsZone.id }
      }
    ]
  }
  dependsOn: [ queueDnsLink ]
}

resource tablePe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-table-ragi-${suffix}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-table-conn'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: ['table']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource tableDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: tablePe
  name: 'table-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'table'
        properties: { privateDnsZoneId: tableDnsZone.id }
      }
    ]
  }
  dependsOn: [ tableDnsLink ]
}

resource filePe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-file-ragi-${suffix}'
  location: location
  properties: {
    subnet: { id: pepSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'pe-file-conn'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: ['file']
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

resource fileDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: filePe
  name: 'file-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'file'
        properties: { privateDnsZoneId: fileDnsZone.id }
      }
    ]
  }
  dependsOn: [ fileDnsLink ]
}

output queuePeId string = queuePe.id
output tablePeId string = tablePe.id
output filePeId string = filePe.id
