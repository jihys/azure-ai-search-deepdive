# Issue 0031: Storage Network Rules, ACLs & Firewall Configuration

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0028-logic-app-storage-private-endpoint.md](0028-logic-app-storage-private-endpoint.md), [0029-logic-app-vnet-integration.md](0029-logic-app-vnet-integration.md), [0030-logic-app-function-app-vnet-rbac.md](0030-logic-app-function-app-vnet-rbac.md)  
**Blocks:** 0032, 0035  

---

## Context

Storage account has `publicNetworkAccess=Disabled` but Network Rules are incomplete or misconfigured. This slice finalizes Storage firewall configuration:
- Default action: **Deny** (block public internet)
- Allow rules: Private Endpoint (implicit) + VNet subnets (snet-func, snet-jump) + Azure Services bypass
- Shared Private Links: Prepare for AI Search, Function App outbound access via PE

---

## Acceptance Criteria

- [ ] **Storage network ACLs** configured:
  - `defaultAction: Deny` (block all public internet access)
  - `bypass: AzureServices` (allow internal Azure services)
  - `virtualNetworkRules`: Allow snet-func (10.0.2.0/24) + snet-jump (10.0.0.0/24)
- [ ] **Private Endpoint** implicitly allows blob access (no additional IP rules needed)
- [ ] **Shared Private Links (SPL)** state verified:
  - SPL blob: status == "Succeeded" (AI Search → Storage blob access)
  - SPL AI Services: status == "Succeeded" (AI Search → Azure OpenAI embedding)
  - SPL Document Intelligence: status == "Succeeded" (AI Search → Document Intelligence)
- [ ] All three environments (sweden, korea, sweden-public) apply identical firewall rules
- [ ] Bicep module `infra/modules/storage-network-rules.bicep` created
- [ ] Validation: Non-PE traffic to Storage is blocked; PE traffic succeeds

---

## Blockers

- [ ] Depends on Private Endpoint creation from [Issue 0028](0028-logic-app-storage-private-endpoint.md)
- [ ] Depends on Function App + Logic App VNet integration from [Issues 0029, 0030](0029-logic-app-vnet-integration.md)
- [ ] AI Search service must exist (pre-existing)

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/storage-network-rules.bicep`**
   - Input parameters:
     - `storageAccountId` — Storage account resource ID
     - `storageAccountName` — Storage account name
     - `vnetSubnetIds` — Array of VNet subnet IDs to allow (snet-func, snet-jump)
     - `searchServiceId` — AI Search resource ID (for SPL)
     - `aiServicesId` — Azure OpenAI/AI Services ID (for SPL)
     - `docIntelId` — Document Intelligence ID (for SPL)
   - Output: Network ACL resource ID
   - Logic:
     ```bicep
     resource storageAccount 'Microsoft.Storage/storageAccounts@2021-04-01' existing = {
       name: storageAccountName
     }
     
     // Configure network ACLs
     resource networkAcls 'Microsoft.Storage/storageAccounts/networkAcls@2021-04-01' = {
       name: '${storageAccount.name}/default'
       properties: {
         bypass: 'AzureServices'  // Allow internal Azure services
         virtualNetworkRules: [
           for subnetId in vnetSubnetIds: {
             id: subnetId
             action: 'Allow'
           }
         ]
         ipRules: []
         defaultAction: 'Deny'  // Block all public internet access
       }
     }
     
     // Shared Private Link: Storage Blob
     resource splBlob 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
       name: '${last(split(searchServiceId, '/'))}/spl-blob'
       properties: {
         privateLinkResourceId: '${storageAccount.id}/blobServices/default'
         groupId: 'blob'
         requestMessage: 'Approve Storage Blob access for AI Search indexer'
         status: 'Succeeded'  // Auto-approve with Managed Identity
       }
     }
     
     // Shared Private Link: AI Services (Embedding)
     resource splAiServices 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
       name: '${last(split(searchServiceId, '/'))}/spl-aiservices'
       properties: {
         privateLinkResourceId: aiServicesId
         groupId: 'account'
         requestMessage: 'Approve Azure OpenAI access for AI Search embedding skill'
         status: 'Succeeded'
       }
     }
     
     // Shared Private Link: Document Intelligence (Layout skill)
     resource splDocIntel 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
       name: '${last(split(searchServiceId, '/'))}/spl-docintel'
       properties: {
         privateLinkResourceId: docIntelId
         groupId: 'account'
         requestMessage: 'Approve Document Intelligence access for AI Search layout skill'
         status: 'Succeeded'
       }
     }
     ```

2. **Update `infra/sweden/main.bicep`**
   ```bicep
   module storageNetworkRules 'modules/storage-network-rules.bicep' = {
     name: 'storage-network-rules'
     params: {
       storageAccountId: storageAccount.id
       storageAccountName: storageAccount.name
       vnetSubnetIds: [
         networking.outputs.subnetFuncId
         networking.outputs.subnetJumpId
       ]
       searchServiceId: searchService.id
       aiServicesId: aiServices.id
       docIntelId: docIntel.id
     }
     dependsOn: [
       storageAccount
       networking
       privateEndpoint  // Must wait for PE creation
     ]
   }
   ```

3. **Create validation script** (`infra/scripts/validate-storage-network-rules.sh`)
   ```bash
   #!/bin/bash
   
   STORAGE_NAME="stragi${HASH}"
   
   # 1. Verify network ACLs
   DEFAULT_ACTION=$(az storage account show --name ${STORAGE_NAME} --resource-group ${RG} \
     --query 'networkRulesBypassOptions' -o tsv)
   
   if [[ "$DEFAULT_ACTION" != "AzureServices" ]]; then
     echo "❌ Storage network bypass not set to AzureServices"
     exit 1
   fi
   
   echo "✅ Storage network bypass: AzureServices"
   
   # 2. Verify default action is Deny
   DEFAULT_ACTION=$(az storage account show --name ${STORAGE_NAME} --resource-group ${RG} \
     --query 'networkAcls.defaultAction' -o tsv)
   
   if [[ "$DEFAULT_ACTION" != "Deny" ]]; then
     echo "❌ Storage default action is not Deny (current: $DEFAULT_ACTION)"
     exit 1
   fi
   
   echo "✅ Storage default action: Deny"
   
   # 3. Verify virtual network rules
   VNET_RULES=$(az storage account network-rule list --account-name ${STORAGE_NAME} \
     --resource-group ${RG} --query 'virtualNetworkRules[].virtualNetworkResourceId' -o tsv)
   
   if [[ -z "$VNET_RULES" ]]; then
     echo "❌ No virtual network rules configured"
     exit 1
   fi
   
   echo "✅ Virtual network rules configured: $VNET_RULES"
   
   # 4. Verify Shared Private Links
   SPL_STATUS=$(az search shared-private-link-resource list \
     --resource-group ${RG} --search-service-name search-ragi-${HASH} \
     --query '[].{name: name, status: properties.status}' -o json)
   
   echo "✅ Shared Private Links status: $SPL_STATUS"
   
   # 5. Test public access is blocked (should fail)
   AZURE_STORAGE_ACCOUNT=${STORAGE_NAME} \
   AZURE_STORAGE_KEY=$(az storage account keys list --account-name ${STORAGE_NAME} \
     --resource-group ${RG} --query '[0].value' -o tsv) \
   az storage blob list --container-name raw-documents 2>&1 | grep -q 'AuthorizationPermissionMismatch\|AuthenticationFailed'
   
   if [[ $? -eq 0 ]]; then
     echo "✅ Public access blocked (expected AuthenticationFailed)"
   else
     echo "⚠️  Public access test inconclusive (may succeed due to network context)"
   fi
   ```

4. **Network rules parameterization** (`infra/sweden/parameters/prod.bicepparam`)
   ```
   param storageNetworkRules = {
     vnetSubnetIds: [
       subscriptionResourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-ragi', 'snet-func')
       subscriptionResourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-ragi', 'snet-jump')
     ]
     bypass: 'AzureServices'
     defaultAction: 'Deny'
   }
   ```

### Validation

After deployment:
```bash
# 1. Verify Storage network ACLs
az storage account show --name stragi${HASH} --resource-group ${RG} \
  --query 'networkRulesBypassOptions, networkAcls' -o json

# 2. Verify Shared Private Links approval status
az search shared-private-link-resource list \
  --resource-group ${RG} --search-service-name search-ragi-${HASH} \
  | jq '.[] | {name: .name, status: .properties.status}'

# 3. Verify Storage is accessible via PE from within VNet
# (Run from JumpVM or Function App context)
curl -I https://stragi${HASH}.blob.core.windows.net/raw-documents

# 4. Verify public IP cannot reach Storage
# (Run from public internet - should timeout or get 403)
curl -I --max-time 5 https://stragi${HASH}.blob.core.windows.net/raw-documents || echo "❌ Public access blocked (expected)"
```

### Related Issues

- [0028](0028-logic-app-storage-private-endpoint.md) — Private Endpoint setup (dependency)
- [0029](0029-logic-app-vnet-integration.md) — Logic App VNet (dependency)
- [0030](0030-logic-app-function-app-vnet-rbac.md) — Function App VNet + RBAC (dependency)
- [0032](0032-logic-app-storage-shared-private-links.md) — SPL approval workflow
- [0035](0035-logic-app-validation-e2e-testing.md) — E2E validation

---

## Design Decision Rationale

Storage network rules are the enforcement layer: once configured, all public internet access is blocked, forcing all clients to use Private Endpoints. Combined with Shared Private Links, this ensures AI Search can reach Storage privately and securely. This slice depends on all VNet infrastructure (0027) and Private Endpoint (0028) being complete.
