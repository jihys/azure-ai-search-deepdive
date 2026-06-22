# Issue 0030: Function App VNet Integration, Managed Identity & RBAC

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027-logic-app-storage-vnet-infrastructure.md](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** 0031, 0033  

---

## Context

The crawl and preprocess function apps (`func-crawl-ragi`, `func-preprocess-ragi`) currently cannot reach Storage account due to missing VNet integration and improper authentication. This slice configures Function App VNet integration, assigns Managed Identity, and establishes RBAC role assignments for Storage Blob Data access.

---

## Acceptance Criteria

- [ ] **Function App** deployed on **Elastic Premium ASP (EP1)** or Standard ASP
- [ ] **VNet subnet integration** configured: Function App outbound routes through `snet-func` (10.0.2.0/24)
- [ ] **Managed Identity (System-assigned)** enabled on both Function App resources:
  - `func-crawl-ragi`
  - `func-preprocess-ragi`
- [ ] **RBAC role assignment**: Both Function Apps assigned **Storage Blob Data Contributor** role on Storage account
  - Using Managed Identity principal ID
  - No API key/connection string in Function App settings
- [ ] **Function App settings** updated to remove hardcoded Storage keys:
  - Remove `AzureWebJobsStorage` (connection string)
  - Add `StorageAccount__accountName`, `StorageAccount__credential=managedidentity` instead
- [ ] **Runtime authentication** (Python code):
  - Replace `BlobServiceClient.from_connection_string()` with `BlobServiceClient(account_url=..., credential=ManagedIdentityCredential())`
- [ ] All three environments apply identical Function App config
- [ ] Bicep module `infra/modules/function-app.bicep` created for reuse
- [ ] Validation: Function App successfully uploads/downloads blobs to Storage PE

---

## Blockers

- [ ] Depends on VNet + snet-func creation from [Issue 0027](0027-logic-app-storage-vnet-infrastructure.md)
- [ ] Assumes existing Function App code uses environment variables (not hardcoded secrets)
- [ ] Storage account must have been created (pre-existing)

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/function-app.bicep`**
   - Input parameters:
     - `functionAppName` — e.g., 'func-crawl-ragi'
     - `appServicePlanId` — ASP ID
     - `vnetSubnetId` — snet-func subnet ID
     - `storageAccountId` — Storage account resource ID
     - `runtime` — e.g., 'python', 'dotnet'
     - `runtimeVersion` — e.g., '3.11'
   - Output: Function App ID, Managed Identity principal ID
   - Logic:
     ```bicep
     resource functionApp 'Microsoft.Web/sites@2021-02-01' = {
       name: functionAppName
       location: location
       kind: 'functionapp,linux'
       identity: {
         type: 'SystemAssigned'
       }
       properties: {
         serverFarmId: appServicePlanId
         virtualNetworkSubnetId: vnetSubnetId  // VNet integration
         httpsOnly: true
         siteConfig: {
           linuxFxVersion: 'PYTHON|3.11'
           alwaysOn: true
           functionAppScaleLimit: 10
           appSettings: [
             {
               name: 'AzureWebJobsStorage'
               value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccountName};EndpointSuffix=core.windows.net'
             }
             {
               name: 'FUNCTIONS_EXTENSION_VERSION'
               value: '~4'
             }
             {
               name: 'FUNCTIONS_WORKER_RUNTIME'
               value: 'python'
             }
             {
               name: 'StorageAccount__accountName'
               value: storageAccountName
             }
             {
               name: 'StorageAccount__credential'
               value: 'managedidentity'
             }
           ]
         }
       }
     }
     
     // RBAC: Function App → Storage Blob Data Contributor
     resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
       scope: storageAccount
       name: guid(storageAccount.id, functionApp.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
       properties: {
         roleDefinitionId: subscriptionResourceId(
           'Microsoft.Authorization/roleDefinitions',
           'ba92f5b4-2d11-453d-a403-e96b0029c9fe'  // Storage Blob Data Contributor
         )
         principalId: functionApp.identity.principalId
         principalType: 'ServicePrincipal'
       }
     }
     ```

2. **Update `src/` Function App code** to use Managed Identity
   ```python
   # Before (hardcoded connection string):
   from azure.storage.blob import BlobServiceClient
   blob_client = BlobServiceClient.from_connection_string(os.getenv('AzureWebJobsStorage'))
   
   # After (Managed Identity):
   from azure.storage.blob import BlobServiceClient
   from azure.identity import ManagedIdentityCredential
   
   credential = ManagedIdentityCredential()
   account_name = os.getenv('StorageAccount__accountName')
   blob_client = BlobServiceClient(
       account_url=f'https://{account_name}.blob.core.windows.net',
       credential=credential
   )
   ```

3. **Update `infra/sweden/main.bicep`**
   ```bicep
   module funcCrawl 'modules/function-app.bicep' = {
     name: 'func-crawl'
     params: {
       functionAppName: 'func-crawl-ragi'
       appServicePlanId: appServicePlan.id
       vnetSubnetId: networking.outputs.subnetFuncId
       storageAccountId: storageAccount.id
       runtime: 'python'
       runtimeVersion: '3.11'
       location: location
     }
     dependsOn: [ networking ]
   }
   
   module funcPreprocess 'modules/function-app.bicep' = {
     name: 'func-preprocess'
     params: {
       functionAppName: 'func-preprocess-ragi'
       appServicePlanId: appServicePlan.id
       vnetSubnetId: networking.outputs.subnetFuncId
       storageAccountId: storageAccount.id
       runtime: 'python'
       runtimeVersion: '3.11'
       location: location
     }
     dependsOn: [ networking ]
   }
   ```

4. **Create verification script** (`infra/scripts/validate-function-app-vnet.sh`)
   ```bash
   #!/bin/bash
   
   for FUNC_NAME in func-crawl-ragi func-preprocess-ragi; do
     # Check VNet integration
     VNET_ID=$(az functionapp show --name ${FUNC_NAME} --resource-group ${RG} \
       --query 'virtualNetworkSubnetId' -o tsv)
     
     if [[ -z "$VNET_ID" ]]; then
       echo "❌ ${FUNC_NAME} VNet integration not configured"
       exit 1
     fi
     
     echo "✅ ${FUNC_NAME} VNet subnet: $VNET_ID"
     
     # Check Managed Identity
     IDENTITY=$(az functionapp identity show --name ${FUNC_NAME} --resource-group ${RG} \
       --query 'principalId' -o tsv)
     
     if [[ -z "$IDENTITY" ]]; then
       echo "❌ ${FUNC_NAME} Managed Identity not assigned"
       exit 1
     fi
     
     echo "✅ ${FUNC_NAME} Managed Identity: $IDENTITY"
     
     # Check RBAC role assignment
     ROLE=$(az role assignment list --assignee ${IDENTITY} --scope ${STORAGE_ID} \
       --query "[?roleDefinitionName=='Storage Blob Data Contributor']" -o tsv)
     
     if [[ -z "$ROLE" ]]; then
       echo "❌ ${FUNC_NAME} Storage Blob Data Contributor role not assigned"
       exit 1
     fi
     
     echo "✅ ${FUNC_NAME} Storage Blob Data Contributor role assigned"
   done
   ```

5. **Function App deployment** (in Notebook 01)
   ```bash
   az deployment group create \
     --name deploy-function-app \
     --resource-group ${RG} \
     --template-file infra/sweden/main.bicep \
     --parameters @infra/sweden/parameters/prod.bicepparam
   ```

### Validation

After deployment:
```bash
# 1. Verify VNet integration
az functionapp show --name func-crawl-ragi --resource-group ${RG} \
  --query 'properties.virtualNetworkSubnetId' -o tsv

# 2. Verify Managed Identity
az functionapp identity show --name func-crawl-ragi --resource-group ${RG}

# 3. Verify RBAC role
PRINCIPAL_ID=$(az functionapp identity show --name func-crawl-ragi --resource-group ${RG} \
  --query 'principalId' -o tsv)

az role assignment list --assignee ${PRINCIPAL_ID} --scope $(az storage account show \
  --name stragi${HASH} --resource-group ${RG} --query 'id' -o tsv)

# 4. Test blob access (from Function App context)
az functionapp command invoke --name func-crawl-ragi --resource-group ${RG} \
  --command 'python -c "from azure.storage.blob import BlobServiceClient; from azure.identity import ManagedIdentityCredential; client = BlobServiceClient(...); print(list(client.list_containers()))"'
```

### Related Issues

- [0027](0027-logic-app-storage-vnet-infrastructure.md) — VNet setup (dependency)
- [0029](0029-logic-app-vnet-integration.md) — Logic App VNet (parallel)
- [0031](0031-logic-app-storage-network-rules.md) — Storage firewall rules

---

## Design Decision Rationale

Function App VNet integration is a critical prerequisite for the crawling pipeline to access Storage. By combining VNet routing with Managed Identity RBAC, we eliminate secrets management and enable automatic credential renewal. This slice is independent of Logic App (0029) but both must succeed for the E2E pipeline to function.
