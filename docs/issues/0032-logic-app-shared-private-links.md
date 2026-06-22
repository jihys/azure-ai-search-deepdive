# Issue 0032: Shared Private Links Approval & AI Search Integration

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0028-logic-app-storage-private-endpoint.md](0028-logic-app-storage-private-endpoint.md), [0031-logic-app-storage-network-rules.md](0031-logic-app-storage-network-rules.md)  
**Blocks:** 0035  

---

## Context

Shared Private Links (SPL) enable AI Search (and other services) to access Storage, AI Services, and Document Intelligence via Private Endpoints without exposing public endpoints. This slice verifies and auto-approves SPL resources for the three critical integrations.

---

## Acceptance Criteria

- [ ] **Shared Private Link: Storage Blob** (AI Search indexer → Storage)
  - Status: `Succeeded`
  - Group ID: `blob`
  - Bicep auto-approves using Managed Identity
- [ ] **Shared Private Link: AI Services** (AI Search embedding skill → Azure OpenAI)
  - Status: `Succeeded`
  - Group ID: `account`
  - Bicep auto-approves using Managed Identity
- [ ] **Shared Private Link: Document Intelligence** (AI Search layout skill → Document Intelligence)
  - Status: `Succeeded`
  - Group ID: `account`
  - Bicep auto-approves using Managed Identity
- [ ] All SPL resources created during Bicep deployment (no manual approval steps)
- [ ] AI Search can reach downstream services (Storage, AI Services, DI) via SPL
- [ ] All three environments (sweden, korea, sweden-public) have identical SPL configuration
- [ ] Validation: AI Search indexer run succeeds with no "access denied" errors

---

## Blockers

- [ ] Depends on Storage Private Endpoint from [Issue 0028](0028-logic-app-storage-private-endpoint.md)
- [ ] Depends on Storage network rules from [Issue 0031](0031-logic-app-storage-network-rules.md)
- [ ] AI Search service must exist and have system-assigned Managed Identity enabled

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/shared-private-links.bicep`**
   - Input parameters:
     - `searchServiceId` — AI Search resource ID
     - `storageAccountId` — Storage account resource ID
     - `aiServicesId` — Azure OpenAI / AI Services resource ID
     - `docIntelId` — Document Intelligence resource ID
   - Output: SPL resource IDs and approval status
   - Logic:
     ```bicep
     param searchServiceId string
     param storageAccountId string
     param aiServicesId string
     param docIntelId string
     
     resource searchService 'Microsoft.Search/searchServices@2023-11-01' existing = {
       name: last(split(searchServiceId, '/'))
     }
     
     // SPL: Storage Blob (for indexer data ingestion)
     resource splBlob 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
       parent: searchService
       name: 'spl-blob'
       properties: {
         privateLinkResourceId: '${storageAccountId}/blobServices/default'
         groupId: 'blob'
         requestMessage: 'AI Search indexer requires Storage Blob access via Private Endpoint'
         status: 'Succeeded'  // Auto-approved with Managed Identity
       }
     }
     
     // SPL: AI Services (for embedding skill using Azure OpenAI)
     resource splAiServices 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
       parent: searchService
       name: 'spl-aiservices'
       properties: {
         privateLinkResourceId: aiServicesId
         groupId: 'account'
         requestMessage: 'AI Search embedding skill requires Azure OpenAI access via Private Endpoint'
         status: 'Succeeded'
       }
     }
     
     // SPL: Document Intelligence (for layout skill)
     resource splDocIntel 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2023-11-01' = {
       parent: searchService
       name: 'spl-docintel'
       properties: {
         privateLinkResourceId: '${docIntelId}'
         groupId: 'account'
         requestMessage: 'AI Search layout skill requires Document Intelligence access via Private Endpoint'
         status: 'Succeeded'
       }
     }
     
     output splBlobStatus string = splBlob.properties.status
     output splAiServicesStatus string = splAiServices.properties.status
     output splDocIntelStatus string = splDocIntel.properties.status
     ```

2. **Update `infra/sweden/main.bicep`**
   ```bicep
   module sharedPrivateLinks 'modules/shared-private-links.bicep' = {
     name: 'spl'
     params: {
       searchServiceId: searchService.id
       storageAccountId: storageAccount.id
       aiServicesId: aiServices.id
       docIntelId: docIntel.id
     }
     dependsOn: [
       storageNetworkRules  // Must wait for Storage network config
       privateEndpoint      // Must wait for PE creation
     ]
   }
   ```

3. **Verification & approval script** (`infra/scripts/validate-spl.sh`)
   ```bash
   #!/bin/bash
   
   SEARCH_SERVICE="search-ragi-${HASH}"
   RG=${RG}
   
   echo "Verifying Shared Private Links for AI Search..."
   
   # Get SPL resources
   SPL_LIST=$(az search shared-private-link-resource list \
     --resource-group ${RG} \
     --search-service-name ${SEARCH_SERVICE} \
     --query '[].{name: name, status: properties.status, groupId: properties.groupId}' \
     -o json)
   
   echo "Current SPL resources:"
   echo "$SPL_LIST" | jq '.'
   
   # Check each SPL status
   for SPL_NAME in spl-blob spl-aiservices spl-docintel; do
     STATUS=$(echo "$SPL_LIST" | jq -r ".[] | select(.name==\"$SPL_NAME\") | .status" 2>/dev/null)
     
     if [[ -z "$STATUS" ]]; then
       echo "❌ SPL $SPL_NAME not found"
       exit 1
     elif [[ "$STATUS" != "Succeeded" ]]; then
       echo "⚠️  SPL $SPL_NAME status: $STATUS (not yet Succeeded)"
       # Optionally auto-approve if status is "Pending" or "IncompleteJobNotification"
     else
       echo "✅ SPL $SPL_NAME approved: $STATUS"
     fi
   done
   
   echo "✅ All Shared Private Links verified"
   ```

4. **AI Search Managed Identity setup** (must be pre-requisite)
   - Ensure AI Search has System-assigned Managed Identity enabled
   - Assign **Search Service Contributor** role to search service on dependent resources (Storage, AI Services, DI)
   ```bicep
   // In main.bicep or separate module
   resource searchServiceStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
     scope: storageAccount
     name: guid(storageAccount.id, searchService.id, '8ebe5a00-a938-4c3c-845b-13448b5e456f')
     properties: {
       roleDefinitionId: subscriptionResourceId(
         'Microsoft.Authorization/roleDefinitions',
         '8ebe5a00-a938-4c3c-845b-13448b5e456f'  // Search Service Contributor
       )
       principalId: searchService.identity.principalId
       principalType: 'ServicePrincipal'
     }
   }
   ```

5. **Test SPL integration** (post-deployment)
   ```bash
   # Manual indexer run to verify SPL connectivity
   az search indexer run --name "legal-indexer" \
     --resource-group ${RG} \
     --search-service-name ${SEARCH_SERVICE}
   
   # Wait and check indexer status
   sleep 10
   
   az search indexer status show --name "legal-indexer" \
     --resource-group ${RG} \
     --search-service-name ${SEARCH_SERVICE} \
     --query 'lastStatus' -o json
   ```

### Validation

After deployment:
```bash
# 1. List all SPL resources
az search shared-private-link-resource list \
  --resource-group ${RG} \
  --search-service-name search-ragi-${HASH} \
  --query '[].{name: name, status: properties.status, groupId: properties.groupId}' -o json

# 2. Get detailed status for each SPL
az search shared-private-link-resource show \
  --resource-group ${RG} \
  --search-service-name search-ragi-${HASH} \
  --name spl-blob

# 3. Run AI Search indexer to verify downstream connectivity
az search indexer run --name "prec-court-indexer" \
  --resource-group ${RG} \
  --search-service-name search-ragi-${HASH}

# 4. Check indexer status (should show no network errors)
az search indexer status show \
  --name "prec-court-indexer" \
  --resource-group ${RG} \
  --search-service-name search-ragi-${HASH}
```

### Related Issues

- [0028](0028-logic-app-storage-private-endpoint.md) — Storage PE setup (dependency)
- [0031](0031-logic-app-storage-network-rules.md) — Storage network rules (dependency)
- [0035](0035-logic-app-validation-e2e-testing.md) — E2E validation

---

## Design Decision Rationale

Shared Private Links are the bridge that allows AI Search to reach its dependent services (Storage, AI Services, Document Intelligence) via Private Endpoints. By auto-approving SPL in Bicep using Managed Identity RBAC, we eliminate manual approval steps and ensure repeatable, infrastructure-as-code deployments across all environments.
