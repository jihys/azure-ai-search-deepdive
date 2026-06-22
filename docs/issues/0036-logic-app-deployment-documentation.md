# Issue 0036: Documentation & Deployment Guide

**Status:** done  
**Parent:** [PRD-logic-app-storage-private-integration.md](../prd/PRD-logic-app-storage-private-integration.md)  
**Depends on:** [0027-0035](0027-logic-app-storage-vnet-infrastructure.md)  
**Blocks:** None (final documentation)  

---

## Context

After all infrastructure, modules, and validation are complete, comprehensive documentation ensures operators can deploy, troubleshoot, and maintain the solution across all environments (sweden, korea, sweden-public). This slice creates deployment guides, architectural diagrams, and runbooks.

---

## Acceptance Criteria

- [ ] **Deployment Guide** (`infra/DEPLOYMENT.md`):
  - Prerequisites (Resource Group, RBAC roles, az CLI version)
  - Step-by-step commands for each environment
  - Parameter file customization instructions
  - Estimated deployment time (e.g., 15 minutes)
  - Rollback instructions
- [ ] **Architecture Diagram** (`docs/architecture-logic-app-storage-private.drawio` or `.md`):
  - VNet topology (subnets, NSGs, route tables)
  - Private Endpoints (Storage, AI Services, DI)
  - Logic App, Function App, AI Search VNet integration
  - Data flow arrows (crawl → Storage → indexer)
  - Security zones (private, PE, public)
- [ ] **Network Topology Diagram** (`docs/network-topology.drawio`):
  - Detailed subnet layout (IP ranges, NSG rules)
  - Private DNS Zone integration
  - Shared Private Links (SPL) connectivity
- [ ] **Troubleshooting Guide** (`infra/TROUBLESHOOTING.md`):
  - Common errors (503 Service Unavailable, DNS resolution failure, etc.)
  - Diagnostic steps for each error
  - Links to validation scripts
  - Contact/escalation path
- [ ] **FAQ** (`infra/FAQ.md`):
  - Why Private Endpoints?
  - How to add a new environment?
  - How to change IP ranges?
  - How to migrate from public to private?
- [ ] **CONTEXT.md** updated:
  - Add section on Private Endpoint / VNet integration
  - Update networking terminology (snet-pep, snet-func, snet-jump)
  - Add Shared Private Links definition
- [ ] **ADR: Network Architecture Decision** (`docs/adr/ADR-network-private-endpoints.md`):
  - Decision: Use Private Endpoints for Storage, AI Services, DI
  - Rationale: Security, compliance, cost vs. alternatives
  - Consequences: Added complexity, dependency on VNet
  - Alternatives considered: Firewall rules, IP allowlist
- [ ] **Parameter File Documentation** (`infra/PARAMETERS.md`):
  - Explain each parameter in `.bicepparam` files
  - Allowed values, defaults, constraints
  - Environment-specific overrides (korea, sweden-public)
- [ ] **Bicep Code Comments**:
  - Each module has header comment (purpose, inputs, outputs)
  - Complex logic (NSG rules, role assignments) has inline comments
  - Naming conventions documented
- [ ] **Notebook 01 Integration** (`notebooks/01-infra-deployment.ipynb`):
  - Add cell to run `validate-all.sh` post-deployment
  - Add cell to display architecture diagram
  - Add cell to explain VNet/PE setup to lab participants
- [ ] All documentation uses Korean language (as per copilot-instructions.md)
- [ ] Links to ADRs, related issues, and external docs (Azure docs) are functional

---

## Blockers

None — this is the final documentation slice.

---

## Implementation Notes

### Deliverables

1. **Create `infra/DEPLOYMENT.md`**:
   ```markdown
   # 배포 가이드 — Logic App & Storage Private Endpoint 통합
   
   ## 선행 조건
   
   - Azure Subscription (적절한 RBAC 권한)
   - Azure CLI v2.40+
   - Bicep CLI v0.13+
   - Resource Group 사전 생성
   
   ## 배포 단계
   
   ### 1. Sweden Central (메인)
   
   ```bash
   az deployment group create \
     --resource-group rg-rag-indexing-lab-swc \
     --template-file infra/sweden/main.bicep \
     --parameters @infra/sweden/parameters/prod.bicepparam
   ```
   
   예상 소요 시간: 15분
   
   ### 2. Korea Central (보조)
   
   ```bash
   az deployment group create \
     --resource-group rg-rag-indexing-lab-krc \
     --template-file infra/korea/main.bicep \
     --parameters @infra/korea/parameters/prod.bicepparam
   ```
   
   ### 3. 배포 후 검증
   
   ```bash
   bash infra/scripts/validate-all.sh rg-rag-indexing-lab-swc
   ```
   
   ## 롤백
   
   ```bash
   az deployment group delete \
     --resource-group rg-rag-indexing-lab-swc \
     --name deploy-logic-app-storage-vnet
   ```
   ```

2. **Create `infra/TROUBLESHOOTING.md`**:
   ```markdown
   # 문제 해결 가이드
   
   ## 503 Service Unavailable (Function App)
   
   **증상**: Logic App이 Function App 호출 시 503 오류
   
   **진단**:
   ```bash
   az functionapp show --name func-crawl-ragi --query 'state'
   # State가 'Stopped'이면 시작
   ```
   
   **해결**:
   1. Function App 시작: `az functionapp start ...`
   2. VNet 통합 확인: `az functionapp show ... --query 'properties.virtualNetworkSubnetId'`
   3. Managed Identity 확인: `az functionapp identity show ...`
   
   ## 403 Access Denied (Storage)
   
   **증상**: Function App이 Storage 접근 시 403 오류
   
   **원인**: RBAC 역할 미할당 또는 Storage 네트워크 규칙 불일치
   
   **진단**:
   ```bash
   bash infra/scripts/validate-rbac.sh rg-rag-indexing-lab-swc
   bash infra/scripts/validate-storage-firewall.sh rg-rag-indexing-lab-swc
   ```
   
   **해결**:
   - RBAC: `az role assignment create --assignee ... --role "Storage Blob Data Contributor" --scope ...`
   - 네트워크: Storage 네트워크 규칙 확인, snet-func 서브넷 추가
   ```

3. **Create Architecture Diagram** (`docs/architecture-logic-app-storage-private.md` or draw.io):
   - Use Mermaid for a text-based diagram or reference an existing draw.io file
   - Show: VNet, subnets, PE, Logic App, Function App, Storage, AI Search
   - Include data flow and security boundaries

4. **Create `docs/adr/ADR-network-private-endpoints.md`**:
   ```markdown
   # ADR: 프라이빗 엔드포인트 및 VNet 통합 (2026-06-22)
   
   ## 결정
   
   Azure Storage, AI Services, Document Intelligence 에 대해 프라이빗 엔드포인트(PE)를 사용하고,
   Logic App 및 Function App에 VNet 통합을 적용합니다.
   
   ## 근거
   
   1. **보안**: 공개 인터넷을 거치지 않고 프라이빗 네트워크를 통한 접근
   2. **규정 준수**: 데이터 거주 지역(데이터 센터) 내 통신
   3. **비용**: 공개 IP 대역폭 사용 제거 (PE는 VNet 내부 트래픽)
   4. **성능**: VNet 피어링, 낮은 레이턴시
   
   ## 결과
   
   ### 긍정적
   - 100% private network 접근
   - 공개 Storage URL 차단 (publicNetworkAccess=Disabled)
   - 자동 DNS 해석 (PE → 10.0.1.x)
   
   ### 부정적
   - 추가 인프라 복잡도 (VNet, NSG, PE 관리)
   - Shared Private Links (SPL) 승인 워크플로우
   - 크로스 리전 시나리오에서 추가 PE 필요 (korea의 DI)
   ```

5. **Create `infra/PARAMETERS.md`**:
   ```markdown
   # 매개변수 파일 설명
   
   ## infra/sweden/parameters/prod.bicepparam
   
   | 매개변수 | 기본값 | 설명 |
   |---------|-------|------|
   | environment | 'sweden' | 배포 환경 (sweden, korea, sweden-public) |
   | location | 'swedencentral' | Azure 지역 |
   | resourcePrefix | 'ragi' | 리소스 이름 접두사 |
   | vnetAddressPrefix | '10.0.0.0/16' | VNet CIDR 블록 |
   | allowJumpVmAdminCidrs | ['0.0.0.0/32'] | JumpVM 관리 IP (맞춤 필요) |
   
   ## 환경별 차이
   
   - **sweden**: 완전 프라이빗 (PE + VNet)
   - **korea**: Cross-Region DI (koreacentral + US DI)
   - **sweden-public**: 공개 스토리지 (테스트 환경, PE 없음)
   ```

6. **Update `CONTEXT.md`** with new networking concepts:
   ```markdown
   ## 네트워킹 용어
   
   - **VNet (`vnet-ragi`)**: 10.0.0.0/16 — Azure 프라이빗 네트워크
   - **snet-jump**: 10.0.0.0/24 — JumpVM 관리 접근
   - **snet-func**: 10.0.2.0/24 — Function App, Logic App 아웃바운드 라우팅
   - **snet-pep**: 10.0.1.0/24 — Private Endpoint NIC (Storage, AI Services, DI)
   - **PE (Private Endpoint)**: Azure 리소스의 프라이빗 네트워크 인터페이스
   - **SPL (Shared Private Link)**: AI Search가 downstream 서비스에 접근하기 위한 PE
   - **NSG (Network Security Group)**: 서브넷 레벨 방화벽
   ```

7. **Add cells to Notebook 01** (`notebooks/01-infra-deployment.ipynb`):
   - Cell: Run validation scripts and display results
   - Cell: Display architecture diagram
   - Cell: Explain VNet/PE setup to participants

### Validation

After creating documentation:
```bash
# 1. Check all markdown files exist and are readable
ls -la infra/DEPLOYMENT.md infra/TROUBLESHOOTING.md infra/PARAMETERS.md docs/adr/ADR-network-private-endpoints.md

# 2. Verify links in documentation (manual or via tooling)
grep -r '\[.*\](.*\.md)' infra/ docs/adr/ | head -20

# 3. Run deployment using guide to ensure instructions are accurate
bash infra/DEPLOYMENT.md  # (Actually run manually)
```

### Related Issues

- [0027-0035](0027-logic-app-storage-vnet-infrastructure.md) — All infrastructure slices

---

## Design Decision Rationale

Comprehensive documentation is critical for operational success. By creating deployment guides, troubleshooting runbooks, and ADRs, we enable rapid incident response, reduce onboarding time for new operators, and preserve architectural decisions for future reference.
