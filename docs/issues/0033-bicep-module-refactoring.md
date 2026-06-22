# Issue 0033: Bicep Module Extraction & Refactoring

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027, 0028, 0029, 0030, 0031, 0032](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** 0036  

---

## Context

Current Bicep files in `infra/sweden/` and `infra/korea/` contain duplicate or divergent logic for networking, private endpoints, and RBAC. This slice consolidates common patterns into reusable modules, ensuring consistency and maintainability across all three environments (sweden, korea, sweden-public).

---

## Acceptance Criteria

- [ ] **Module directory structure** created:
  ```
  infra/modules/
  ├── networking.bicep              # VNet, subnets, NSG
  ├── private-endpoint.bicep        # PE + Private DNS
  ├── logic-app.bicep               # Logic App + VNet + Managed Identity
  ├── function-app.bicep            # Function App + VNet + RBAC
  ├── storage-network-rules.bicep   # Storage firewall + SPL setup
  └── shared-private-links.bicep    # AI Search SPL approval
  ```
- [ ] **All modules have**:
  - Type-hinted parameters (no `any` type)
  - Descriptive output declarations
  - Inline documentation comments explaining each resource
  - No hardcoded region/SKU/naming; all parameterized
- [ ] **`infra/sweden/main.bicep`** simplified to:
  - Load parameters from `.bicepparam`
  - Call 6 modules in dependency order
  - Pass outputs between modules
  - ~50-100 lines (vs. current 500+ lines with inlined logic)
- [ ] **`infra/korea/main.bicep`** imports same modules, differs only in parameters (korea-specific DI location)
- [ ] **`infra/sweden-public/main.bicep`** imports same modules, differs only in parameters (no VNet PE setup)
- [ ] **Module interdependencies documented**:
  - networking.bicep (no dependencies)
  - private-endpoint.bicep (depends: networking output)
  - logic-app.bicep (depends: networking output)
  - function-app.bicep (depends: networking output)
  - storage-network-rules.bicep (depends: private-endpoint, logic-app, function-app outputs)
  - shared-private-links.bicep (depends: storage-network-rules output)
- [ ] **No `add-storage-pes.bicep` duplication** — all logic merged into modules
- [ ] **Git cleanup**: Remove or archive old `add-storage-pes.bicep` if no longer used
- [ ] All three environments deployable via single `az deployment group create` command

---

## Blockers

None — this is a refactoring slice depending on other modules being completed.

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/` directory** (if not exists) and add six `.bicep` module files as described in Issues 0027-0032

2. **Refactor `infra/sweden/main.bicep`** to use modules:
   ```bicep
   metadata name = 'Azure AI Search Lab - Sweden Central (Private)'
   metadata version = '1.0.0'
   
   param environment string = 'sweden'
   param location string = 'swedencentral'
   param resourcePrefix string = 'ragi'
   param vnetAddressPrefix string = '10.0.0.0/16'
   
   // Module: Networking
   module networking 'modules/networking.bicep' = {
     name: 'networking'
     params: {
       environment: environment
       vnetAddressPrefix: vnetAddressPrefix
       location: location
     }
   }
   
   // Module: Storage Private Endpoint
   module privateEndpoint 'modules/private-endpoint.bicep' = {
     name: 'storage-pe'
     params: {
       storageAccountId: storageAccount.id
       privateLinkSubnetId: networking.outputs.subnetPepId
       vnetId: networking.outputs.vnetId
       privateDnsZoneName: 'privatelink.blob.core.windows.net'
       location: location
     }
     dependsOn: [networking]
   }
   
   // Module: Logic App
   module logicApp 'modules/logic-app.bicep' = {
     name: 'logic-app'
     params: {
       logicAppName: 'logic-crawl-index-${resourcePrefix}'
       appServicePlanId: appServicePlan.id
       vnetSubnetId: networking.outputs.subnetFuncId
       storageAccountId: storageAccount.id
       location: location
     }
     dependsOn: [networking]
   }
   
   // Module: Function Apps
   module funcCrawl 'modules/function-app.bicep' = {
     name: 'func-crawl'
     params: {
       functionAppName: 'func-crawl-${resourcePrefix}'
       appServicePlanId: appServicePlan.id
       vnetSubnetId: networking.outputs.subnetFuncId
       storageAccountId: storageAccount.id
       runtime: 'python'
       runtimeVersion: '3.11'
       location: location
     }
     dependsOn: [networking]
   }
   
   // Module: Storage Network Rules
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
       privateEndpoint
       logicApp
       funcCrawl
     ]
   }
   
   // Module: Shared Private Links
   module sharedPrivateLinks 'modules/shared-private-links.bicep' = {
     name: 'spl'
     params: {
       searchServiceId: searchService.id
       storageAccountId: storageAccount.id
       aiServicesId: aiServices.id
       docIntelId: docIntel.id
     }
     dependsOn: [storageNetworkRules]
   }
   
   // Outputs
   output vnetId string = networking.outputs.vnetId
   output storageAccountId string = storageAccount.id
   output searchServiceId string = searchService.id
   ```

3. **Simplify `infra/korea/main.bicep`** — identical to sweden but with korea-specific parameters:
   ```bicep
   metadata name = 'Azure AI Search Lab - Korea Central (Private + Cross-Region DI)'
   metadata version = '1.0.0'
   
   param environment string = 'korea'
   param location string = 'koreacentral'
   param diLocation string = 'eastus2'  // Document Intelligence (Korea has no DI)
   
   // Import same modules as sweden, but with korea parameters
   // All module calls remain identical; only parameter values differ
   ```

4. **Create parameter files** for each environment:

   **`infra/sweden/parameters/prod.bicepparam`**:
   ```
   using '../main.bicep'
   
   param environment = 'sweden'
   param location = 'swedencentral'
   param resourcePrefix = 'ragi'
   param vnetAddressPrefix = '10.0.0.0/16'
   ```

   **`infra/korea/parameters/prod.bicepparam`**:
   ```
   using '../main.bicep'
   
   param environment = 'korea'
   param location = 'koreacentral'
   param diLocation = 'eastus2'
   param resourcePrefix = 'ragi-korea'
   param vnetAddressPrefix = '10.0.0.0/16'
   ```

   **`infra/sweden-public/parameters/prod.bicepparam`**:
   ```
   using '../main.bicep'
   
   param environment = 'sweden-public'
   param location = 'swedencentral'
   param resourcePrefix = 'ragi-public'
   param vnetAddressPrefix = '10.0.0.0/16'
   param deployPrivateEndpoint = false
   param deployVNetIntegration = false
   ```

5. **Consolidate or remove duplicate files**:
   - If `infra/sweden/add-storage-pes.bicep` exists and is now merged into `modules/`, archive it:
     ```bash
     git mv infra/sweden/add-storage-pes.bicep infra/_archived/add-storage-pes.bicep.bak
     ```

6. **Add module documentation** (`infra/modules/README.md`):
   ```markdown
   # Bicep Modules for Azure AI Search Lab
   
   ## Modules
   
   - **networking.bicep** — VNet, subnets, NSG setup
   - **private-endpoint.bicep** — Storage PE + Private DNS
   - **logic-app.bicep** — Logic App VNet integration + Managed Identity
   - **function-app.bicep** — Function App VNet integration + RBAC
   - **storage-network-rules.bicep** — Storage firewall + SPL setup
   - **shared-private-links.bicep** — AI Search SPL approval
   
   ## Usage
   
   All modules are imported by `main.bicep` in each environment:
   - `infra/sweden/main.bicep`
   - `infra/korea/main.bicep`
   - `infra/sweden-public/main.bicep`
   
   Deploy using:
   ```bash
   az deployment group create \
     --resource-group ${RG} \
     --template-file infra/sweden/main.bicep \
     --parameters @infra/sweden/parameters/prod.bicepparam
   ```
   ```

### Validation

After refactoring:
```bash
# 1. Validate syntax
bicep build infra/sweden/main.bicep
bicep build infra/korea/main.bicep
bicep build infra/sweden-public/main.bicep

# 2. Preview deployment (what-if)
az deployment group what-if \
  --resource-group ${RG} \
  --template-file infra/sweden/main.bicep \
  --parameters @infra/sweden/parameters/prod.bicepparam | head -50

# 3. Verify module imports
grep -r 'module.*bicep' infra/sweden/main.bicep
# Should list all 6 modules
```

### Related Issues

- [0027-0032](0027-logic-app-storage-vnet-infrastructure.md) — Module implementations
- [0036](0036-logic-app-deployment-guide.md) — Deployment documentation

---

## Design Decision Rationale

Extracting common Bicep logic into reusable modules achieves **infrastructure consistency** and **maintainability**. By centralizing networking, PE, and RBAC patterns, future changes (e.g., adding a new environment or SKU) require only parameter file edits, not template rewrites. This also reduces merge conflicts and makes code reviews easier.
