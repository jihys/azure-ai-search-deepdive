# Issue 0028: Storage Private Endpoint & Private DNS Integration

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027-logic-app-storage-vnet-infrastructure.md](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** 0031, 0032  

---

## Context

Storage account has `publicNetworkAccess=Disabled` but Private Endpoint is partially misconfigured. This slice ensures the Storage PE is fully set up with Private DNS Zone integration, allowing Function App and Logic App to resolve `stragi<hash>.blob.core.windows.net` to 10.0.1.x (private subnet).

---

## Acceptance Criteria

- [ ] **Private Endpoint `pe-blob-ragi`** (if missing) created on `snet-pep` (10.0.1.0/24)
- [ ] **Private Endpoint Network Interface (NIC)** configured with static IP in snet-pep range (e.g., 10.0.1.4)
- [ ] **Private DNS Zone `privatelink.blob.core.windows.net`** exists
- [ ] **Private DNS Zone virtual network link** established: VNet `vnet-ragi` linked to the DNS zone with `registrationEnabled=false`
- [ ] **A record** in Private DNS Zone resolving `stragi<hash>` → PE NIC private IP (10.0.1.4)
- [ ] DNS resolution test passes: `nslookup stragi<hash>.blob.core.windows.net` returns 10.0.1.x (not public IP)
- [ ] All three environments (sweden, korea, sweden-public) have identical Private DNS setup
- [ ] Bicep module `infra/modules/private-endpoint.bicep` created for reuse
- [ ] No hardcoded PE IP addresses; all derived from NIC properties

---

## Blockers

- [ ] Depends on VNet + snet-pep creation from [Issue 0027](0027-logic-app-storage-vnet-infrastructure.md)
- [ ] Storage account must exist with `publicNetworkAccess=Disabled` (pre-existing, assumed)

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/private-endpoint.bicep`**
   - Input parameters:
     - `storageAccountId` — Full resource ID of Storage account
     - `privateLinkSubnetId` — snet-pep subnet ID
     - `vnetId` — VNet ID
     - `privateDnsZoneName` — e.g., 'privatelink.blob.core.windows.net'
   - Output: PE resource ID, NIC private IP
   - Logic:
     ```bicep
     resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2021-05-01' = {
       name: 'pe-blob-ragi'
       location: location
       properties: {
         subnet: { id: privateLinkSubnetId }
         privateLinkServiceConnections: [
           {
             name: 'blob-connection'
             properties: {
               privateLinkServiceId: storageAccountId
               groupIds: ['blob']
             }
           }
         ]
       }
     }
     
     resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing = {
       name: privateDnsZoneName
     }
     
     resource privateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
       parent: privateDnsZone
       name: 'vnet-link'
       location: 'global'
       properties: {
         registrationEnabled: false
         virtualNetwork: { id: vnetId }
       }
     }
     
     resource dnsARecord 'Microsoft.Network/privateDnsZones/A@2020-06-01' = {
       parent: privateDnsZone
       name: storageAccountName
       properties: {
         aRecords: [
           {
             ipv4Address: storagePrivateEndpoint.properties.networkInterfaces[0].properties.ipConfigurations[0].properties.privateIPAddress
           }
         ]
         ttl: 3600
       }
     }
     ```

2. **Update `infra/sweden/main.bicep`**
   ```bicep
   module privateEndpoint 'modules/private-endpoint.bicep' = {
     name: 'storage-pe'
     params: {
       storageAccountId: storageAccount.id
       privateLinkSubnetId: networking.outputs.subnetPepId
       vnetId: networking.outputs.vnetId
       privateDnsZoneName: 'privatelink.blob.core.windows.net'
       location: location
     }
   }
   ```

3. **Verification script** (`infra/scripts/validate-pe-dns.sh`)
   ```bash
   #!/bin/bash
   STORAGE_NAME="stragi${HASH}"
   EXPECTED_IP_PREFIX="10.0.1"
   
   DNS_RESULT=$(nslookup ${STORAGE_NAME}.blob.core.windows.net | grep -A1 "Name:" | tail -1)
   if [[ $DNS_RESULT == *"$EXPECTED_IP_PREFIX"* ]]; then
     echo "✅ Private Endpoint DNS resolution succeeded: $DNS_RESULT"
   else
     echo "❌ Private Endpoint DNS resolution failed: $DNS_RESULT"
     exit 1
   fi
   ```

4. **Bicep deployment command** (in Notebook 01 or docs/DEPLOYMENT.md)
   ```bash
   az deployment group create \
     --name deploy-storage-pe \
     --resource-group ${RG} \
     --template-file infra/sweden/main.bicep \
     --parameters @infra/sweden/parameters/prod.bicepparam
   ```

### Validation

After deployment, manually verify:
```bash
# 1. Private Endpoint exists
az network private-endpoint show --resource-group ${RG} --name pe-blob-ragi

# 2. DNS A record in Private DNS Zone
az network private-dns record-set a show \
  --resource-group ${RG} \
  --zone-name privatelink.blob.core.windows.net \
  --name stragi${HASH}

# 3. DNS resolution from inside VNet
nslookup stragi${HASH}.blob.core.windows.net  # Should return 10.0.1.x

# 4. VNet link to Private DNS Zone
az network private-dns zone virtual-network-link show \
  --resource-group ${RG} \
  --zone-name privatelink.blob.core.windows.net \
  --name vnet-link
```

### Related Issues

- [0027](0027-logic-app-storage-vnet-infrastructure.md) — VNet creation (dependency)
- [0031](0031-logic-app-storage-network-rules.md) — Storage firewall configuration
- [0032](0032-logic-app-storage-shared-private-links.md) — AI Search SPL approval

---

## Design Decision Rationale

Separating PE setup from network rules (0031) and SPL approval (0032) allows each layer to be tested independently. Private Endpoint + DNS must work before downstream services (Logic App, Function App, AI Search) can use it.
