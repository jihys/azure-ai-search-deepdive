// ============================================
// App Service Plan (Elastic Premium EP1)
// Shared by Function Apps: crawler, preprocess, skills
// ============================================

@description('배포 리전')
param location string

@description('리소스 이름 접미사')
param suffix string

@description('App Service Plan SKU')
@allowed(['EP1', 'EP2', 'EP3'])
param planSku string = 'EP1'

var planName = 'asp-crawl-ragi-${take(suffix, 8)}'

// ── Elastic Premium Plan (Linux, EP1+) ──
// EP1: 1 vCore, 3.5GB RAM, VNet integration 지원
// EP2: 2 vCore, 7GB RAM
// EP3: 4 vCore, 14GB RAM
resource funcPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: {
    name: planSku
    tier: 'ElasticPremium'
  }
  kind: 'elastic'
  properties: {
    reserved: true   // Linux 필수
    maximumElasticWorkerCount: 5
  }
  tags: { project: 'rag-indexing-lab' }
}

@description('App Service Plan ID')
output hostingPlanId string = funcPlan.id

@description('App Service Plan Name')
output hostingPlanName string = funcPlan.name
