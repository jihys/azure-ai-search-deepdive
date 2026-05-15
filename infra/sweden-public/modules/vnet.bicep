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
var funcFc1SubnetName = 'snet-func-fc1'

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
      {
        // Flex Consumption (FC1) Function App 전용 서브넷
        // FC1 은 Container Apps 기반 → Microsoft.App/environments 위임 필요
        // 동일 subnet 을 EP1 plan 과 공유 불가 (ServiceAssociationLink 충돌)
        name: funcFc1SubnetName
        properties: {
          addressPrefix: '10.0.4.0/24'
          delegations: [
            {
              name: 'delegation-func-fc1'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
          ]
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Outputs ──
// NOTE: Public 변형은 Private Endpoint / Private DNS Zone 을 사용하지 않습니다.
output vnetId string = vnet.id
output vnetName string = vnet.name
output pepSubnetId string = '${vnet.id}/subnets/${pepSubnetName}'
output funcSubnetId string = '${vnet.id}/subnets/${funcSubnetName}'
output funcFc1SubnetId string = '${vnet.id}/subnets/${funcFc1SubnetName}'
output jumpSubnetId string = '${vnet.id}/subnets/${jumpSubnetName}'
