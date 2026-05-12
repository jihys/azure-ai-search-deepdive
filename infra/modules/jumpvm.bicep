// ============================================
// JumpVM - 관리자용 Windows VM
// AI Search / Storage 등 Private Endpoint 리소스 접근 전용
// publicNetworkAccess=Disabled 된 서비스에 VNet 내부에서 접근
//
// 접근 방법: RDP → pip-jump-ragi-<suffix> (포트 3389)
// ※ 운영 환경에서는 소스 IP를 제한하거나 Azure Bastion 사용 권장
// Entra ID 로그인: AADLoginForWindows 확장 + RBAC (Virtual Machine User Login)
// ============================================

@description('배포 리전')
param location string

@description('JumpVM 서브넷 ID (snet-jumpvm)')
param jumpvmSubnetId string

@description('VM 관리자 계정명')
param adminUsername string

@description('VM 관리자 비밀번호')
@secure()
param adminPassword string

@description('VM 크기')
param vmSize string = 'Standard_B2s_v2'

@description('Windows 이미지 Publisher')
param osPublisher string = 'MicrosoftWindowsDesktop'

@description('Windows 이미지 Offer')
param osOffer string = 'windows-11'

@description('Windows 이미지 SKU')
param osSku string = 'win11-24h2-pro'

@description('Entra ID 로그인을 허용할 사용자 Object ID 목록')
param entraUserObjectIds array = []

@description('JumpVM 이름')
param vmName string = 'jumpvmragi01'

@description('JumpVM NIC 이름')
param nicName string = 'jumpvmragi01VMNic'

@description('JumpVM Public IP 이름')
param pipName string = 'jumpvmragi01PublicIP'

@description('JumpVM NSG 이름')
param nsgName string = 'jumpvmragi01NSG'

// ── NSG (JumpVM NIC용) - RDP 인바운드 허용 ──
resource jumpvmNsg 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowRDP'
        properties: {
          priority: 300
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '3389'
          description: 'JumpVM RDP 접근 - 운영 환경에서는 소스 IP를 제한하세요'
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Public IP (RDP 접속용) ──
resource publicIp 'Microsoft.Network/publicIPAddresses@2024-01-01' = {
  name: pipName
  location: location
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── NIC ──
resource nic 'Microsoft.Network/networkInterfaces@2024-01-01' = {
  name: nicName
  location: location
  properties: {
    networkSecurityGroup: {
      id: jumpvmNsg.id
    }
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: { id: jumpvmSubnetId }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: { id: publicIp.id }
        }
      }
    ]
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── Windows VM ──
resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: vmName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        publisher: osPublisher
        offer: osOffer
        sku: osSku
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        deleteOption: 'Delete'
      }
    }
    osProfile: {
      computerName: 'jumpvm'
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: {
        enableAutomaticUpdates: true
        patchSettings: {
          patchMode: 'AutomaticByOS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        { id: nic.id }
      ]
    }
  }
  tags: { project: 'rag-indexing-lab' }
}

// ── VM Extension: AADLoginForWindows ──
// Entra ID (Azure AD) 계정으로 RDP 로그인 가능하도록 설정
resource aadLoginExtension 'Microsoft.Compute/virtualMachines/extensions@2024-03-01' = {
  parent: vm
  name: 'AADLoginForWindows'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.ActiveDirectory'
    type: 'AADLoginForWindows'
    typeHandlerVersion: '2.0'
    autoUpgradeMinorVersion: true
    settings: {
      mdmId: ''
    }
  }
}

// ── VM Extension: 개발 도구 자동 설치 (Chocolatey) ──
// 설치 항목:
// 1) Visual Studio Code
// 2) Git
// 3) Git CLI (GitHub CLI: gh)
// 4) Azure CLI
// 5) Git Bash (Git 설치에 포함)
resource devToolsExtension 'Microsoft.Compute/virtualMachines/extensions@2024-03-01' = {
  parent: vm
  name: 'InstallDevTools'
  location: location
  properties: {
    publisher: 'Microsoft.Compute'
    type: 'CustomScriptExtension'
    typeHandlerVersion: '1.10'
    autoUpgradeMinorVersion: true
    protectedSettings: {
      commandToExecute: 'powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; if (-not (Get-Command choco -ErrorAction SilentlyContinue)) { Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = 3072; iwr https://community.chocolatey.org/install.ps1 -UseBasicParsing | iex }; choco feature enable -n=allowGlobalConfirmation; choco install -y vscode git git.install gh azure-cli"'
    }
  }
  dependsOn: [
    aadLoginExtension
  ]
}

// ── RBAC: Entra ID 사용자 → Virtual Machine User Login ──
// 이 역할이 있어야 RDP 시 Entra ID 인증이 허용됨
// (Administrator 권한이 필요하면 Virtual Machine Administrator Login 역할 사용)
var vmUserLoginRoleId = 'fb879df8-f326-4884-b1cf-06f3ad86be52'  // Virtual Machine User Login
resource entraUserVmLogin 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for objectId in entraUserObjectIds: {
  name: guid(vm.id, objectId, vmUserLoginRoleId)
  scope: vm
  properties: {
    principalId: objectId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', vmUserLoginRoleId)
    principalType: 'User'
  }
}]

output vmName string = vm.name
output publicIpAddress string = publicIp.properties.ipAddress
output privateIpAddress string = nic.properties.ipConfigurations[0].properties.privateIPAddress
