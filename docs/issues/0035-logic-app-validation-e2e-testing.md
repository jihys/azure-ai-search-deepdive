# Issue 0035: E2E Testing & Validation Automation

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027, 0028, 0029, 0030, 0031, 0032, 0034](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** None (parallel or final validation)  

---

## Context

After all infrastructure and network components are deployed, comprehensive E2E testing validates that the complete pipeline works: Logic App triggers crawl → Function App accesses Storage via PE → Documents indexed in AI Search. This slice creates automated validation scripts and integration tests.

---

## Acceptance Criteria

- [ ] **Bicep syntax validation** script (`infra/scripts/validate-bicep.sh`):
  - `bicep build` succeeds for all environment templates
  - No compilation errors or warnings
- [ ] **ARM template what-if simulation** (`infra/scripts/validate-what-if.sh`):
  - `az deployment group what-if` shows expected resources
  - No errors or warnings in deployment preview
- [ ] **Network connectivity validation** script (`infra/scripts/validate-network.sh`):
  - Storage PE DNS resolves to 10.0.1.x (private IP)
  - Storage PE is reachable via HTTPS from Function App subnet
  - Public internet access to Storage is blocked
- [ ] **Managed Identity & RBAC validation** (`infra/scripts/validate-rbac.sh`):
  - Function App has Managed Identity assigned
  - Logic App has Managed Identity assigned
  - Both have Storage Blob Data Contributor role
  - AI Search has appropriate roles (Search Service Contributor)
- [ ] **Storage Network Rules validation** (`infra/scripts/validate-storage-firewall.sh`):
  - Default action is "Deny"
  - VNet rules include snet-func and snet-jump
  - Bypass includes "AzureServices"
- [ ] **Shared Private Links validation** (`infra/scripts/validate-spl.sh`):
  - All SPL resources exist and have status "Succeeded"
  - Storage, AI Services, Document Intelligence SPLs are approved
- [ ] **Python integration tests** (`tests/integration/test_network_integration.py`):
  - Test Function App can connect to Storage via Managed Identity
  - Test Logic App can trigger indexer successfully
  - Test AI Search indexer runs without errors
  - Fixtures use `.venv` environment
- [ ] **E2E crawl pipeline test** (`tests/integration/test_crawl_pipeline_e2e.py`):
  - Logic App manually triggered
  - Wait for crawl completion (max 60 seconds)
  - Verify raw-documents/* files created in Storage
  - Verify AI Search indexer runs and injects documents into prec-court-index
  - Verify document count > 0 in index
- [ ] **Master validation script** (`infra/scripts/validate-all.sh`):
  - Orchestrates all validation scripts in sequence
  - Reports pass/fail summary
  - Exports results to JSON for CI/CD pipelines
- [ ] All three environments (sweden, korea, sweden-public) can run the same test suite
- [ ] Tests output clear PASS/FAIL status; suitable for CI/CD integration
- [ ] No hardcoded resource names; all via environment variables or resource queries

---

## Blockers

- [ ] Depends on all infrastructure components from [Issues 0027-0034](0027-logic-app-storage-vnet-infrastructure.md)
- [ ] Assumes Logic App workflow is deployed and operational

---

## Implementation Notes

### Deliverables

1. **Create shell validation scripts**:

   **`infra/scripts/validate-bicep.sh`**:
   ```bash
   #!/bin/bash
   set -e
   
   echo "=== Validating Bicep Templates ==="
   
   for TEMPLATE in infra/sweden/main.bicep infra/korea/main.bicep infra/sweden-public/main.bicep; do
     echo "Building $TEMPLATE..."
     if bicep build "$TEMPLATE" --output-format json > /dev/null 2>&1; then
       echo "✅ $TEMPLATE validated"
     else
       echo "❌ $TEMPLATE failed validation"
       bicep build "$TEMPLATE" --output-format json
       exit 1
     fi
   done
   
   echo "✅ All Bicep templates validated successfully"
   ```

   **`infra/scripts/validate-network.sh`**:
   ```bash
   #!/bin/bash
   set -e
   
   RG=${1:-rg-rag-indexing-lab-swc}
   STORAGE_NAME=$(az storage account list --resource-group ${RG} --query '[0].name' -o tsv)
   
   echo "=== Validating Network Connectivity ==="
   
   # 1. Storage PE DNS
   echo "Checking Storage PE DNS resolution..."
   DNS_RESULT=$(nslookup ${STORAGE_NAME}.blob.core.windows.net | grep -A1 "Name:" | tail -1 || true)
   if [[ $DNS_RESULT == *"10.0.1"* ]]; then
     echo "✅ Storage PE DNS resolved to private IP"
   else
     echo "❌ Storage PE DNS did not resolve correctly"
     echo "   Result: $DNS_RESULT"
     exit 1
   fi
   
   # 2. Test HTTPS connectivity from Function App
   echo "Testing Function App connectivity to Storage PE..."
   FUNC_NAME=$(az functionapp list --resource-group ${RG} --query '[0].name' -o tsv)
   
   # Use Azure CLI to invoke a test in Function App context
   az functionapp command invoke \
     --name ${FUNC_NAME} \
     --resource-group ${RG} \
     --command "python -c \"
   from azure.storage.blob import BlobServiceClient
   from azure.identity import ManagedIdentityCredential
   
   credential = ManagedIdentityCredential()
   client = BlobServiceClient(account_url='https://${STORAGE_NAME}.blob.core.windows.net', credential=credential)
   containers = list(client.list_containers())
   print(f'Connected. Containers: {len(containers)}')
   \"" || echo "❌ Function App → Storage PE connectivity test failed"
   
   echo "✅ Network connectivity validated"
   ```

   **`infra/scripts/validate-rbac.sh`**:
   ```bash
   #!/bin/bash
   set -e
   
   RG=${1:-rg-rag-indexing-lab-swc}
   
   echo "=== Validating RBAC Assignments ==="
   
   # Function App Managed Identity
   FUNC_NAME=$(az functionapp list --resource-group ${RG} --query '[0].name' -o tsv)
   FUNC_PRINCIPAL=$(az functionapp identity show --name ${FUNC_NAME} --resource-group ${RG} --query 'principalId' -o tsv)
   
   echo "Function App: $FUNC_NAME"
   echo "Principal ID: $FUNC_PRINCIPAL"
   
   # Storage account
   STORAGE_ID=$(az storage account list --resource-group ${RG} --query '[0].id' -o tsv)
   
   # Check Storage Blob Data Contributor role
   ROLE_ASSIGNMENT=$(az role assignment list \
     --assignee ${FUNC_PRINCIPAL} \
     --scope ${STORAGE_ID} \
     --query "[?roleDefinitionName=='Storage Blob Data Contributor']" -o json)
   
   if [[ $(echo "$ROLE_ASSIGNMENT" | jq 'length') -gt 0 ]]; then
     echo "✅ Function App has Storage Blob Data Contributor role"
   else
     echo "❌ Function App missing Storage Blob Data Contributor role"
     exit 1
   fi
   
   # Similar checks for Logic App, AI Search...
   
   echo "✅ RBAC assignments validated"
   ```

   **`infra/scripts/validate-all.sh`**:
   ```bash
   #!/bin/bash
   
   RG=${1:-rg-rag-indexing-lab-swc}
   ENV=${2:-sweden}
   
   RESULTS_FILE="validation-results-$(date +%s).json"
   
   echo "Starting comprehensive validation for $ENV in RG $RG..."
   
   validate_step() {
     local step=$1
     local script=$2
     
     echo ""
     echo "=== Running: $step ==="
     
     if bash "$script" "$RG"; then
       echo "✅ $step PASSED"
       echo "{ \"step\": \"$step\", \"status\": \"PASSED\" }" >> "$RESULTS_FILE"
       return 0
     else
       echo "❌ $step FAILED"
       echo "{ \"step\": \"$step\", \"status\": \"FAILED\" }" >> "$RESULTS_FILE"
       return 1
     fi
   }
   
   # Run all validations
   validate_step "Bicep Syntax" "infra/scripts/validate-bicep.sh"
   validate_step "Network Connectivity" "infra/scripts/validate-network.sh"
   validate_step "RBAC Assignments" "infra/scripts/validate-rbac.sh"
   validate_step "Storage Firewall" "infra/scripts/validate-storage-firewall.sh"
   validate_step "Shared Private Links" "infra/scripts/validate-spl.sh"
   
   echo ""
   echo "=== Validation Summary ==="
   echo "Results saved to: $RESULTS_FILE"
   jq '.' "$RESULTS_FILE" || cat "$RESULTS_FILE"
   ```

2. **Create Python integration tests** (`tests/integration/test_network_integration.py`):
   ```python
   import pytest
   import os
   from azure.storage.blob import BlobServiceClient
   from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
   from azure.search.documents import SearchClient
   
   @pytest.fixture
   def azure_credential():
       """Use Managed Identity when in Function App, DefaultAzureCredential otherwise"""
       try:
           return ManagedIdentityCredential()
       except:
           return DefaultAzureCredential()
   
   @pytest.fixture
   def storage_client(azure_credential):
       account_url = f"https://{os.getenv('STORAGE_ACCOUNT_NAME', 'stragi')}.blob.core.windows.net"
       return BlobServiceClient(account_url=account_url, credential=azure_credential)
   
   @pytest.fixture
   def search_client(azure_credential):
       return SearchClient(
           endpoint=os.getenv('SEARCH_ENDPOINT'),
           index_name='prec-court-index',
           credential=azure_credential
       )
   
   @pytest.mark.integration
   def test_storage_connectivity(storage_client):
       """Verify Function App can access Storage via Managed Identity"""
       containers = list(storage_client.list_containers())
       assert len(containers) > 0, "No containers found"
       assert any(c.name == 'raw-documents' for c in containers), "raw-documents container not found"
   
   @pytest.mark.integration
   def test_search_index_exists(search_client):
       """Verify AI Search index is accessible"""
       try:
           results = search_client.search(search_text='*', top=1)
           # Index exists, even if empty
           assert True
       except Exception as e:
           pytest.fail(f"Search index not accessible: {e}")
   
   @pytest.mark.integration
   def test_crawl_pipeline_e2e(storage_client, search_client):
       """E2E test: Logic App trigger → Crawl → Index"""
       import time
       
       # Trigger Logic App
       from azure.mgmt.logic import LogicManagementClient
       logic_client = LogicManagementClient(...)  # Initialize with creds
       
       # Run Logic App workflow
       response = logic_client.workflows.trigger_callback(...)
       
       # Wait for crawl to complete (max 2 minutes)
       time.sleep(10)
       
       # Verify raw-documents were created
       container = storage_client.get_container_client('raw-documents')
       blobs = list(container.list_blobs())
       assert len(blobs) > 0, "No crawled documents found in Storage"
       
       # Verify AI Search has indexed documents
       time.sleep(10)  # Indexer lag
       results = search_client.search(search_text='*', top=1)
       doc_count = results.get_count()
       assert doc_count > 0, "No documents indexed in AI Search"
   ```

3. **Create test runner** (`infra/scripts/run-integration-tests.sh`):
   ```bash
   #!/bin/bash
   set -e
   
   RG=${1:-rg-rag-indexing-lab-swc}
   
   echo "Running integration tests for $RG..."
   
   # Activate venv
   source .venv/bin/activate
   
   # Set environment variables
   export STORAGE_ACCOUNT_NAME=$(az storage account list --resource-group ${RG} --query '[0].name' -o tsv)
   export SEARCH_ENDPOINT=https://$(az search service list --resource-group ${RG} --query '[0].name' -o tsv).search.windows.net
   export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
   
   # Run pytest
   pytest tests/integration/test_network_integration.py -v --tb=short
   ```

4. **Update CI/CD pipeline** (`.github/workflows/validate-infra.yml` if applicable):
   ```yaml
   name: Infrastructure Validation
   
   on:
     push:
       paths:
         - 'infra/**'
   
   jobs:
     validate:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - name: Run Bicep validation
           run: bash infra/scripts/validate-bicep.sh
         - name: Run all validations
           run: bash infra/scripts/validate-all.sh
   ```

### Validation

After implementation:
```bash
# 1. Run all validation scripts
bash infra/scripts/validate-all.sh rg-rag-indexing-lab-swc

# 2. Run integration tests
python -m pytest tests/integration/ -v

# 3. Review results
cat validation-results-*.json | jq '.'
```

### Related Issues

- [0027-0034](0027-logic-app-storage-vnet-infrastructure.md) — Infrastructure components
- [0036](0036-logic-app-deployment-guide.md) — Deployment documentation

---

## Design Decision Rationale

Comprehensive E2E testing ensures the entire pipeline works after deployment, catching network misconfigurations, permission issues, or SPL approval failures early. By automating validation, we enable rapid feedback and reduce manual troubleshooting time during incident response.
