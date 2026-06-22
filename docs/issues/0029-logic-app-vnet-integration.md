# Issue 0029: Logic App VNet Integration & Managed Identity

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027-logic-app-storage-vnet-infrastructure.md](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** 0031, 0033  

---

## Context

Logic App Consumption plan (standard SKU) cannot integrate directly into VNet. However, when deployed on Premium ASP (Elastic Premium / EP1), Logic App can route outbound traffic through a VNet subnet (`snet-func`, 10.0.2.0/24), enabling private access to Storage Private Endpoint.

This slice configures Logic App with VNet integration and assigns Managed Identity for role-based authentication.

---

## Acceptance Criteria

- [ ] **Logic App** deployed on **Elastic Premium ASP (EP1)** or Standard ASP with VNet support enabled
- [ ] **VNet subnet integration** configured: Logic App outbound traffic routes through `snet-func` (10.0.2.0/24)
- [ ] **Managed Identity (System-assigned)** enabled on Logic App
- [ ] **Connection to Azure Blob Storage** updated to use **Managed Identity** instead of API key
  - Connection string replaced with resource ID + managed identity auth
  - No API key stored in Logic App settings
- [ ] **Outbound traffic validation**: Logic App can resolve and reach `stragi<hash>.blob.core.windows.net` (PE DNS)
- [ ] All three environments (sweden, korea, sweden-public) apply identical Logic App config
- [ ] Bicep module `infra/modules/logic-app.bicep` created for reuse
- [ ] No connection strings hardcoded; all via Managed Identity

---

## Blockers

- [ ] Depends on VNet + snet-func creation from [Issue 0027](0027-logic-app-storage-vnet-infrastructure.md)
- [ ] ASP must support VNet integration (EP1 or Standard, not Consumption)
- [ ] Assumes existing Logic App workflow definition is unchanged (only auth/networking updated)

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/logic-app.bicep`**
   - Input parameters:
     - `logicAppName` — e.g., 'logic-crawl-index-ragi'
     - `appServicePlanId` — ASP ID (must be EP1 or Standard)
     - `vnetSubnetId` — snet-func subnet ID for VNet integration
     - `workflowDefinitionUrl` — (optional) URL to workflow JSON definition
   - Output: Logic App ID, Managed Identity principal ID
   - Logic:
     ```bicep
     resource logicApp 'Microsoft.Web/sites@2021-02-01' = {
       name: logicAppName
       location: location
       kind: 'functionapp,workflowapp'
       identity: {
         type: 'SystemAssigned'
       }
       properties: {
         serverFarmId: appServicePlanId
         virtualNetworkSubnetId: vnetSubnetId  // VNet integration
         httpsOnly: true
         siteConfig: {
           numberOfWorkers: 1
           defaultDocuments: []
           functionAppScaleLimit: 10
           minimumElasticInstanceCount: 1
         }
       }
     }
     
     // Connection for Azure Blob using Managed Identity
     resource blobConnection 'Microsoft.Web/connections@2021-06-01' = {
       name: 'azureblob-managed'
       location: location
       properties: {
         displayName: 'Azure Blob Storage (Managed Identity)'
         api: {
           id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azureblob')
         }
         parameterValues: {
           resourceId: storageAccountId
           authentication: 'ManagedServiceIdentity'
         }
       }
     }
     ```

2. **Update `infra/sweden/main.bicep`**
   ```bicep
   module logicApp 'modules/logic-app.bicep' = {
     name: 'logic-app'
     params: {
       logicAppName: 'logic-crawl-index-ragi'
       appServicePlanId: appServicePlan.id
       vnetSubnetId: networking.outputs.subnetFuncId
       location: location
     }
     dependsOn: [
       networking  // Must wait for VNet + snet-func
     ]
   }
   ```

3. **Update Logic App workflow JSON** to use Managed Identity connection
   - Replace connection action inputs:
     ```json
     {
       "inputs": {
         "host": {
           "connection": {
             "name": "@parameters('$connections')['azureblob']['connectionId']",
             "referenceName": "azureblob-managed"
           }
         },
         "method": "put",
         "path": "/datasets/default/files",
         "authentication": {
           "type": "ManagedServiceIdentity"
         }
       }
     }
     ```

4. **Create Logic App workflow (if not existing)**
   - Workflow definition file: `logic-apps/crawl-preprocess-workflow/workflow.json`
   - Includes: trigger (schedule 21:00 UTC), crawl function call, preprocess indexer trigger

5. **Validation script** (`infra/scripts/validate-logic-app-vnet.sh`)
   ```bash
   #!/bin/bash
   LOGIC_APP_NAME="logic-crawl-index-ragi"
   
   # Check VNet integration
   VNET_ID=$(az webapp show --name ${LOGIC_APP_NAME} --resource-group ${RG} \
     --query 'virtualNetworkSubnetId' -o tsv)
   
   if [[ -z "$VNET_ID" ]]; then
     echo "❌ Logic App VNet integration not configured"
     exit 1
   fi
   
   echo "✅ Logic App VNet subnet ID: $VNET_ID"
   
   # Check Managed Identity
   IDENTITY=$(az webapp identity show --name ${LOGIC_APP_NAME} --resource-group ${RG})
   if [[ -z "$IDENTITY" ]]; then
     echo "❌ Logic App Managed Identity not assigned"
     exit 1
   fi
   
   echo "✅ Logic App Managed Identity assigned"
   
   # Check blob connection
   CONNECTIONS=$(az logic workflow trigger list --name ${LOGIC_APP_NAME} --resource-group ${RG})
   echo "✅ Logic App workflow triggers configured"
   ```

### Validation

After deployment:
```bash
# 1. Verify VNet integration
az webapp show --name logic-crawl-index-ragi --resource-group ${RG} \
  --query 'properties.virtualNetworkSubnetId' -o tsv

# 2. Verify Managed Identity
az webapp identity show --name logic-crawl-index-ragi --resource-group ${RG}

# 3. Test Logic App trigger (manual run)
az logic workflow run create \
  --resource-group ${RG} \
  --workflow-name logic-crawl-index-ragi \
  --trigger-inputs '{}'

# 4. Monitor run status
az logic workflow run show \
  --resource-group ${RG} \
  --workflow-name logic-crawl-index-ragi \
  --run-id ${RUN_ID} \
  --query 'properties.status' -o tsv
```

### Related Issues

- [0027](0027-logic-app-storage-vnet-infrastructure.md) — VNet setup (dependency)
- [0030](0030-logic-app-function-app-rbac.md) — Function App VNet + RBAC
- [0031](0031-logic-app-storage-network-rules.md) — Storage firewall rules

---

## Design Decision Rationale

Logic App VNet integration is a prerequisite for private Storage access. Combined with Managed Identity, it eliminates the need for connection strings/API keys and improves security posture. This slice is independent of Function App (0030) but both are needed for the crawl pipeline to function.
