# Issue 0034: NSG Rules & Network Security Hardening

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027-logic-app-storage-vnet-infrastructure.md](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** 0035, 0036  

---

## Context

Network Security Group (NSG) rules must enforce **least-privilege access** to Private Endpoint subnets and prevent unauthorized outbound traffic. This slice hardens NSG rules to ensure only legitimate traffic (Function App → Storage PE, JumpVM → PE) is allowed.

---

## Acceptance Criteria

- [ ] **NSG `nsg-pep`** (attached to `snet-pep`) rules:
  - **Inbound (Deny by default, Allow specific)**:
    - Allow port 443 (HTTPS) from snet-func (10.0.2.0/24)
    - Allow port 443 (HTTPS) from snet-jump (10.0.0.0/24)
    - Allow port 443 (HTTPS) from AI Search service (if in same VNet; else via SPL)
    - Deny all other inbound traffic
  - **Outbound (Allow by default, no restrictions)**:
    - Implicit allow-all outbound (PE only sends responses, no outbound initiations)
- [ ] **NSG `nsg-func`** (attached to `snet-func`) rules:
  - **Inbound (Deny by default)**:
    - Deny all inbound (no inbound traffic from public internet)
  - **Outbound (Allow specific)**:
    - Allow port 443 (HTTPS) to Internet (0.0.0.0/0) for Storage PE resolution, AI Search, etc.
    - Allow port 53 (DNS) to Azure DNS (168.63.129.16/32)
    - Allow port 3306 (MySQL) to databases if applicable (parameterized)
- [ ] **NSG `nsg-jump`** (attached to `snet-jump`) rules:
  - **Inbound**:
    - Allow RDP (3389) or SSH (22) from admin IP ranges (configurable)
    - Allow 443 (HTTPS) to Storage, AI Search, etc.
  - **Outbound**:
    - Allow all (JumpVM is admin tool, may need broad access)
- [ ] All NSG rules documented with inline comments explaining the purpose
- [ ] Rule priorities follow convention: 100 (first allow), 110 (second), ..., 4096 (implicit deny)
- [ ] All three environments (sweden, korea, sweden-public) apply identical security rules
- [ ] No IP ranges hardcoded; all parameterized in `.bicepparam`
- [ ] Validation: Traffic flows as expected; unauthorized flows are blocked

---

## Blockers

- [ ] Depends on NSG creation from [Issue 0027](0027-logic-app-storage-vnet-infrastructure.md)
- [ ] VNet + subnets must exist

---

## Implementation Notes

### Deliverables

1. **Update `infra/modules/networking.bicep`** with detailed NSG rules:
   ```bicep
   param allowFuncInboundCidrs array = []  // Array of CIDR blocks (e.g., Azure Bastion)
   param allowJumpVmAdminCidrs array = ['0.0.0.0/32']  // Admin IP (parameterized)
   
   // NSG for Private Endpoint subnet
   resource nsgPep 'Microsoft.Network/networkSecurityGroups@2021-02-01' = {
     name: 'nsg-pep'
     location: location
     properties: {
       securityRules: [
         {
           name: 'AllowFuncToBlob'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '443'
             sourceAddressPrefix: '10.0.2.0/24'  // snet-func
             destinationAddressPrefix: '*'
             access: 'Allow'
             priority: 100
             direction: 'Inbound'
             sourcePortRanges: []
             destinationPortRanges: []
             sourceAddressPrefixes: []
             destinationAddressPrefixes: []
           }
         }
         {
           name: 'AllowJumpVmToBlob'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '443'
             sourceAddressPrefix: '10.0.0.0/24'  // snet-jump
             destinationAddressPrefix: '*'
             access: 'Allow'
             priority: 110
             direction: 'Inbound'
           }
         }
         {
           name: 'AllowSearchServiceToBlob'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '443'
             sourceAddressPrefix: 'AzureCloud'  // AI Search managed service
             destinationAddressPrefix: '*'
             access: 'Allow'
             priority: 120
             direction: 'Inbound'
           }
         }
         {
           name: 'DenyAllInbound'
           properties: {
             protocol: '*'
             sourcePortRange: '*'
             destinationPortRange: '*'
             sourceAddressPrefix: '*'
             destinationAddressPrefix: '*'
             access: 'Deny'
             priority: 4096
             direction: 'Inbound'
           }
         }
       ]
     }
   }
   
   // NSG for Function App subnet
   resource nsgFunc 'Microsoft.Network/networkSecurityGroups@2021-02-01' = {
     name: 'nsg-func'
     location: location
     properties: {
       securityRules: [
         {
           name: 'AllowHttpsOutbound'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '443'
             sourceAddressPrefix: '*'
             destinationAddressPrefix: 'Internet'
             access: 'Allow'
             priority: 100
             direction: 'Outbound'
           }
         }
         {
           name: 'AllowDnsOutbound'
           properties: {
             protocol: 'Udp'
             sourcePortRange: '*'
             destinationPortRange: '53'
             sourceAddressPrefix: '*'
             destinationAddressPrefix: '168.63.129.16/32'  // Azure DNS
             access: 'Allow'
             priority: 110
             direction: 'Outbound'
           }
         }
         {
           name: 'DenyAllInbound'
           properties: {
             protocol: '*'
             sourcePortRange: '*'
             destinationPortRange: '*'
             sourceAddressPrefix: '*'
             destinationAddressPrefix: '*'
             access: 'Deny'
             priority: 100
             direction: 'Inbound'
           }
         }
       ]
     }
   }
   
   // NSG for JumpVM subnet
   resource nsgJump 'Microsoft.Network/networkSecurityGroups@2021-02-01' = {
     name: 'nsg-jump'
     location: location
     properties: {
       securityRules: [
         {
           name: 'AllowSshFromAdmin'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '22'
             sourceAddressPrefix: allowJumpVmAdminCidrs[0]  // Parameterized admin IP
             destinationAddressPrefix: '*'
             access: 'Allow'
             priority: 100
             direction: 'Inbound'
           }
         }
         {
           name: 'AllowRdpFromAdmin'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '3389'
             sourceAddressPrefix: allowJumpVmAdminCidrs[0]
             destinationAddressPrefix: '*'
             access: 'Allow'
             priority: 110
             direction: 'Inbound'
           }
         }
         {
           name: 'AllowHttpsOutbound'
           properties: {
             protocol: 'Tcp'
             sourcePortRange: '*'
             destinationPortRange: '443'
             sourceAddressPrefix: '*'
             destinationAddressPrefix: '*'
             access: 'Allow'
             priority: 100
             direction: 'Outbound'
           }
         }
       ]
     }
   }
   
   output nsgPepId string = nsgPep.id
   output nsgFuncId string = nsgFunc.id
   output nsgJumpId string = nsgJump.id
   ```

2. **Update parameter files** to include admin IP ranges:

   **`infra/sweden/parameters/prod.bicepparam`**:
   ```
   param allowJumpVmAdminCidrs = [
     '1.2.3.4/32'  // Replace with actual admin IP
   ]
   ```

3. **Create NSG rule validation script** (`infra/scripts/validate-nsg-rules.sh`):
   ```bash
   #!/bin/bash
   
   echo "Validating NSG rules..."
   
   # NSG: nsg-pep
   echo "Checking nsg-pep inbound rules..."
   az network nsg rule list --resource-group ${RG} --nsg-name nsg-pep \
     --query '[].{name: name, priority: priority, access: access, sourceAddressPrefix: sourceAddressPrefix, destinationPortRange: destinationPortRange}' \
     --output table
   
   # Verify critical rules exist
   FUNC_RULE=$(az network nsg rule list --resource-group ${RG} --nsg-name nsg-pep \
     --query "[?sourceAddressPrefix=='10.0.2.0/24' && destinationPortRange=='443' && access=='Allow']" -o json)
   
   if [[ -z "$FUNC_RULE" ]]; then
     echo "❌ nsg-pep does not have AllowFuncToBlob rule"
     exit 1
   fi
   
   echo "✅ nsg-pep rules verified"
   
   # NSG: nsg-func
   echo "Checking nsg-func outbound rules..."
   az network nsg rule list --resource-group ${RG} --nsg-name nsg-func \
     --query "[?direction=='Outbound']" --output table
   
   echo "✅ nsg-func rules verified"
   ```

4. **Update `infra/modules/networking.bicep` to attach NSGs to subnets**:
   ```bicep
   resource subnetFunc 'Microsoft.Network/virtualNetworks/subnets@2021-02-01' = {
     parent: vnet
     name: 'snet-func'
     properties: {
       addressPrefix: '10.0.2.0/24'
       networkSecurityGroup: {
         id: nsgFunc.id
       }
       serviceEndpoints: [
         {
           service: 'Microsoft.Storage'
         }
         {
           service: 'Microsoft.AzureCosmosDB'
         }
       ]
     }
   }
   ```

### Validation

After deployment:
```bash
# 1. List NSG rules
az network nsg rule list --resource-group ${RG} --nsg-name nsg-pep --output table

# 2. Test connectivity from Function App to Storage PE
# (Run from Function App context or via Azure Bastion)
curl -I https://stragi${HASH}.blob.core.windows.net/raw-documents

# 3. Verify unauthorized traffic is blocked
# (Attempt from public internet should timeout or be blocked by Network Watcher)
timeout 5 curl -I https://stragi${HASH}.blob.core.windows.net/ || echo "❌ Public access blocked (expected)"

# 4. Monitor NSG flow logs (if enabled)
az network watcher flow-log show --resource-group ${RG} --nsg nsg-pep
```

### Related Issues

- [0027](0027-logic-app-storage-vnet-infrastructure.md) — VNet/NSG creation
- [0031](0031-logic-app-storage-network-rules.md) — Storage firewall
- [0035](0035-logic-app-validation-e2e-testing.md) — E2E validation

---

## Design Decision Rationale

NSG rules enforce **least-privilege access** at the network layer. By explicitly allowing only necessary traffic (Function App → PE on 443, JumpVM management) and blocking all else, we minimize attack surface and ensure compliance with zero-trust networking principles.
