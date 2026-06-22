# Logic App & Storage Private Integration — 배포 가이드

**최종 업데이트:** 2026-06-22  
**상태:** 완료 (Issues 0027-0036)

---

## 개요

이 가이드는 Azure AI Search 랩의 법령 크롤링 파이프라인을 복구하기 위한 Logic App과 Storage 간 Private Endpoint / VNet 통합 배포 과정을 설명합니다.

### 해결하는 문제

- **503 Service Unavailable**: Storage `publicNetworkAccess=Disabled` 설정 시 Logic App / Function App이 접근 불가
- **미배포 법령 데이터**: 0개 문서 (prec-court, const-court, legis-interp, admin-appeal 인덱스 모두 공 상태)
- **VNet 통합 미완료**: Logic App과 Function App의 서브넷 구성 누락

### 해결 방법

1. **VNet 통합**: Logic App / Function App 아웃바운드 트래픽을 VNet(`snet-func`)을 통해 라우팅
2. **Private Endpoint**: Storage / AI Services / Document Intelligence에 프라이빗 접근 채널 구성
3. **Storage 네트워크 규칙**: Public 접근 차단, Private Endpoint / VNet 서브넷만 허용
4. **Managed Identity & RBAC**: API 키 제거, 역할 기반 인증으로 전환

---

## 배포 환경 및 전제 조건

### 지원 환경

- **Sweden Central** (주 배포)
- **Korea Central** (백업)
- **Sweden Central (Public)** (공개 배포)

### 필수 조건

- Azure CLI `>= 2.50.0`
- Bicep CLI `>= 0.20.0` (또는 `az bicep upgrade` 실행)
- Resource Group 생성 권한
- 구독 Owner / Contributor 역할

### 배포 전 확인 사항

```bash
# Azure 로그인
az login

# 구독 확인
az account show

# Bicep 버전 확인
az bicep version
```

---

## 배포 절차

### 1단계: 환경 선택

```bash
ENVIRONMENT="sweden"           # 또는 "korea", "sweden-public"
RESOURCE_GROUP="rg-rag-indexing-lab-swc"
LOCATION="swedencentral"
```

### 2단계: 매개변수 커스터마이징 (필요 시)

각 환경의 `.bicepparam` 파일을 검토하고 필요시 값 수정:

```bash
# Sweden
# infra/sweden/parameters/prod.bicepparam

# Korea
# infra/korea/parameters/prod.bicepparam
```

주요 매개변수:
- `suffix`: 리소스 고유성 보장 (기본값: 자동 생성)
- `vnetAddressPrefix`: VNet CIDR (기본값: 10.0.0.0/16)
- `crawlerLimit`: 일일 크롤 페이지 수 (기본값: 600)
- `jumpvmEntraUserObjectIds`: JumpVM 관리자 Entra ID 사용자 (필수)

### 3단계: 배포 실행

```bash
# Resource Group 생성 (없으면)
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Bicep 검증
az bicep build --file "infra/$ENVIRONMENT/main.bicep"

# 배포 (What-If 미리보기)
az deployment group what-if \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "infra/$ENVIRONMENT/main.bicep" \
  --parameters "infra/$ENVIRONMENT/parameters/prod.bicepparam"

# 실제 배포 (최대 20-30분)
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "infra/$ENVIRONMENT/main.bicep" \
  --parameters "infra/$ENVIRONMENT/parameters/prod.bicepparam" \
  --no-wait  # 백그라운드 배포 (선택사항)
```

### 4단계: 배포 상태 확인

```bash
# 배포 상태 조회
az deployment group list -g "$RESOURCE_GROUP" -o table

# 배포 상세 확인
az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name <deployment-name>
```

---

## 배포 후 검증

### 네트워크 검증

```bash
# VNet 및 서브넷 확인
./infra/scripts/validate-network.sh "$RESOURCE_GROUP"

# Private Endpoint DNS 해석 확인 (JumpVM에서)
nslookup stragi<hash>.blob.core.windows.net  # Private IP (10.0.1.x) 반환되어야 함
```

### Managed Identity 및 RBAC 검증

```bash
# Function App MI 확인
az functionapp identity show \
  --resource-group "$RESOURCE_GROUP" \
  --name "func-crawl-ragi-<suffix>"

# Role Assignment 확인
az role assignment list \
  --scope "/subscriptions/<subscription>/resourceGroups/$RESOURCE_GROUP" \
  --assignee "<function-app-principal-id>"
```

### Logic App 및 인덱싱 파이프라인 검증

```bash
# Logic App 수동 트리거 (테스트)
az logic workflow run create \
  --resource-group "$RESOURCE_GROUP" \
  --workflow-name "logic-crawl-ragi-<suffix>" \
  --trigger-name "Daily_Schedule_Crawl_and_Preprocess"

# 크롤 결과 확인 (Storage에 raw-documents 생성되었는지)
az storage blob list \
  --account-name "stragi<hash>" \
  --container-name "raw-documents" \
  --auth-mode login

# AI Search 인덱스 문서 수 확인
az search documents count \
  --index-name "prec-court-index" \
  --search-service-name "search-ragi-<suffix>" \
  --resource-group "$RESOURCE_GROUP"
```

---

## 롤백 절차

배포 후 문제 발생 시:

### 전체 롤백 (리소스 그룹 삭제)

```bash
# 주의: 모든 리소스가 영구 삭제됨
az group delete \
  --name "$RESOURCE_GROUP" \
  --yes --no-wait
```

### 선택적 롤백 (특정 리소스)

```bash
# Logic App 삭제 (VNet 통합 재설정)
az logic workflow delete \
  --resource-group "$RESOURCE_GROUP" \
  --workflow-name "logic-crawl-ragi-<suffix>"

# Function App 삭제
az functionapp delete \
  --resource-group "$RESOURCE_GROUP" \
  --name "func-crawl-ragi-<suffix>"

# Private Endpoint 삭제 (DNS 정리 필요)
az network private-endpoint delete \
  --resource-group "$RESOURCE_GROUP" \
  --name "pe-blob-ragi-<suffix>"
```

---

## 환경 간 일관성

모든 환경(sweden, korea, sweden-public)은 동일한 Bicep 모듈을 사용합니다:
- `infra/modules/networking.bicep` — VNet 및 서브넷
- `infra/modules/private-endpoint.bicep` — Private Endpoint
- `infra/modules/logic-app.bicep` — Logic App
- `infra/modules/function-app.bicep` — Function App
- `infra/modules/storage-network-rules.bicep` — Storage 방화벽
- `infra/modules/shared-private-links.bicep` — Shared Private Links

각 환경은 `.bicepparam` 파일로 환경별 차이(지역, CIDR)를 관리합니다.

---

## 문제 해결

### 503 Service Unavailable

**증상**: Function App에서 Storage 접근 불가

**확인 사항**:
1. Storage `publicNetworkAccess` 확인: `Disabled` 여야 함
2. Private Endpoint DNS 해석 확인: `nslookup` 테스트
3. Function App VNet 통합 확인: `az functionapp config appsettings list`
4. NSG 규칙 확인: 인바운드/아웃바운드 포트 443 (HTTPS) 허용 여부

**해결**:
```bash
# Private Endpoint 상태 확인
az network private-endpoint show \
  --resource-group "$RESOURCE_GROUP" \
  --name "pe-blob-ragi-<suffix>"

# Storage 네트워크 규칙 확인
az storage account network-rule list \
  --account-name "stragi<hash>"
```

### 크롤 실패 (0건 데이터)

**원인**: Logic App이 Function App을 호출하지 못하거나 Function App이 Storage에 접근 불가

**해결**:
```bash
# Logic App 실행 이력 확인
az logic workflow run list \
  --resource-group "$RESOURCE_GROUP" \
  --workflow-name "logic-crawl-ragi-<suffix>"

# Function App 로그 스트리밍
az functionapp log tail \
  --resource-group "$RESOURCE_GROUP" \
  --name "func-crawl-ragi-<suffix>"
```

---

## 지원 및 문의

이슈 발생 시:
1. [문제 해결 가이드](TROUBLESHOOTING.md) 참조
2. [FAQ](FAQ.md) 확인
3. GitHub Issue 제출: https://github.com/jihys/azure-ai-search-deepdive/issues
