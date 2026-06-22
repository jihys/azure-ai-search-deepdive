# Issue 0027: VNet Infrastructure — Networking Layer

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** None  
**Blocks:** 0028, 0029, 0030  

---

## Context

The legal document crawling pipeline (Scenario A) is completely blocked due to Storage `publicNetworkAccess=Disabled` but missing VNet integration for Logic App and Function App. This slice establishes the foundational networking layer (VNet, subnets, NSG) needed for private endpoint access.

---

## Acceptance Criteria

- [ ] **VNet `vnet-ragi`** (10.0.0.0/16) exists in all environments (sweden, korea, sweden-public)
- [ ] **Three subnets** created:
  - `snet-jump` (10.0.0.0/24) — JumpVM for management
  - `snet-func` (10.0.2.0/24) — Function App + Logic App outbound VNet integration
  - `snet-pep` (10.0.1.0/24) — Private Endpoint network interface subnet
- [ ] **NSG `nsg-pep`** attached to `snet-pep` with default-Deny inbound + allow rules for snet-func/snet-jump (443)
- [ ] **NSG `nsg-func`** attached to `snet-func` with allow-all outbound (ephemeral ports for Storage, AI Search)
- [ ] **Route table `rt-func`** for `snet-func` configured with default route (0.0.0.0/0 → Internet) or user-defined routes per environment
- [ ] Bicep module `infra/modules/networking.bicep` created with reusable VNet + subnet + NSG logic
- [ ] All three environments (sweden, korea, sweden-public) deploy identical VNet topology via parameterized Bicep
- [ ] **No hardcoded IP ranges**; all CIDR blocks declared as parameters in `.bicepparam` files

---

## Blockers

None — this is the foundational slice.

---

## Implementation Notes

### Deliverables

1. **Create `infra/modules/networking.bicep`**
   - Input parameters: `environment`, `vnetAddressPrefix`, `subnets[]`, `location`
   - Output: VNet ID, subnet IDs (jump, func, pep), NSG resource IDs
   - NSG rules:
     - `snet-pep` inbound: Allow 443 from snet-func (10.0.2.0/24), snet-jump (10.0.0.0/24), Deny all other
     - `snet-func` outbound: Allow 443 to Internet (ephemeral dest ports), Allow AzureServices
     - No inbound traffic into snet-func from public internet

2. **Update `infra/sweden/main.bicep`**
   ```bicep
   module networking 'modules/networking.bicep' = {
     name: 'networking'
     params: {
       environment: 'sweden'
       vnetAddressPrefix: '10.0.0.0/16'
       subnets: [
         { name: 'snet-jump', addressPrefix: '10.0.0.0/24' }
         { name: 'snet-func', addressPrefix: '10.0.2.0/24' }
         { name: 'snet-pep', addressPrefix: '10.0.1.0/24' }
       ]
       location: location
     }
   }
   ```

3. **Create/update `infra/sweden/parameters/prod.bicepparam`**
   ```
   using './main.bicep'
   
   param environment = 'sweden'
   param location = 'swedencentral'
   param vnetAddressPrefix = '10.0.0.0/16'
   param subnets = [
     { name: 'snet-jump', addressPrefix: '10.0.0.0/24' }
     { name: 'snet-func', addressPrefix: '10.0.2.0/24' }
     { name: 'snet-pep', addressPrefix: '10.0.1.0/24' }
   ]
   ```

4. **Replicate for `infra/korea/` and `infra/sweden-public/`** with environment-specific parameters:
   - korea: location='koreacentral', same CIDR ranges
   - sweden-public: location='swedencentral', same CIDR ranges

### Validation

Run after deployment:
```bash
# Verify VNet exists
az network vnet show --resource-group ${RG} --name vnet-ragi

# Verify subnets
az network vnet subnet list --resource-group ${RG} --vnet-name vnet-ragi

# Verify NSG rules on snet-pep
az network nsg rule list --resource-group ${RG} --nsg-name nsg-pep | jq '.[] | {name, access, sourceAddressPrefix, destinationAddressPrefix}'
```

### Related Files

- [storage-network-rules.md](../adr/storage-network-rules.md) — Network ACL strategy for Storage
- [AGENTS.md](../../AGENTS.md) — Bicep conventions and type hints

---

## Design Decision Rationale

This slice follows **tracer-bullet vertical slicing** — it delivers a complete networking foundation without requiring downstream slices to succeed. Future slices (0028, 0029, 0030) will attach Private Endpoints and enable VNet integration for compute resources, but the network topology itself is self-contained and testable.
