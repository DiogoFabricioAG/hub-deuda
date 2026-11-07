// Hub de Deuda — infraestructura de Azure (sección 5 de la guía).
// Despliegue: az deployment group create -g rg-hubdeuda-dev -f infra/main.bicep -p infra/dev.bicepparam
// Sin secretos: Entra ID para SQL, identidades administradas para Function y ADF.

@description('Región permitida por la suscripción (Azure for Students limita regiones).')
param location string = resourceGroup().location
@description('Sufijo único corto (minúsculas/números) para nombres globales.')
@minLength(3)
@maxLength(8)
param sufijo string
@description('UPN del administrador Entra de Azure SQL (tu cuenta UNI).')
param sqlAdminLogin string
@description('Object ID en Entra del administrador de SQL.')
param sqlAdminObjectId string
@description('IP pública del PC que ejecuta el SHIR y las pruebas (regla de firewall SQL).')
param ipPc string = ''
@description('Permitir servicios de Azure en el firewall SQL (necesario para Functions sin VNet y conectores de Power Platform en el laboratorio).')
param permitirServiciosAzure bool = true
@description('Correo para alertas de presupuesto.')
param correoAlertas string
@description('Presupuesto mensual en USD.')
param presupuestoUsd int = 20
param fechaInicioPresupuesto string = '2026-11-01'

var tags = { proyecto: 'hubdeuda', entorno: 'dev', responsable: sqlAdminLogin }
var stNegocio = 'sthubdeudadev${sufijo}'
var stFunc = 'sthubfuncdev${sufijo}'

// ---------- Monitoreo ----------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-hubdeuda-dev'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}
resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-hubdeuda-dev'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: law.id }
}

// ---------- Storage de negocio: raw, manifests, reports (5.6) ----------
resource negocio 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stNegocio
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    isHnsEnabled: false
    // El conector Azure Blob de Power Automate no admite cuentas tras firewall (M07).
    publicNetworkAccess: 'Enabled'
  }
}
resource negocioBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: negocio
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: { enabled: true, days: 14 }
    containerDeleteRetentionPolicy: { enabled: true, days: 14 }
  }
}
resource contenedores 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for c in ['raw', 'manifests', 'reports']: {
  parent: negocioBlob
  name: c
  properties: { publicAccess: 'None' }
}]

// ---------- Storage del runtime de Functions (separado del raw) ----------
resource runtime 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stFunc
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false
  }
}
resource runtimeBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: runtime
  name: 'default'
}
resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: runtimeBlob
  name: 'deploy'
  properties: { publicAccess: 'None' }
}

// ---------- Azure SQL: solo autenticación Entra, oferta gratuita serverless ----------
resource sql 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'sql-hubdeuda-dev-${sufijo}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      login: sqlAdminLogin
      sid: sqlAdminObjectId
      tenantId: subscription().tenantId
      principalType: 'User'
      azureADOnlyAuthentication: true
    }
  }
}
resource hubDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sql
  name: 'HubDeuda'
  location: location
  tags: tags
  sku: { name: 'GP_S_Gen5_2', tier: 'GeneralPurpose' }
  properties: {
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    // Con oferta gratuita y freeLimitExhaustionBehavior=AutoPause, Azure solo
    // admite el valor por defecto (60 min). La oferta da 100 000 vCore-segundos
    // al mes (~55 h a 0.5 vCore): la Function no abre SQL sin trabajo para que
    // la pausa ocurra.
    autoPauseDelay: 60
    minCapacity: json('0.5')
    requestedBackupStorageRedundancy: 'Local'
  }
}
resource fwAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (permitirServiciosAzure) {
  parent: sql
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}
resource fwPc 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (!empty(ipPc)) {
  parent: sql
  name: 'PcOnPremise'
  properties: { startIpAddress: ipPc, endIpAddress: ipPc }
}

// ---------- Key Vault con RBAC (5.7) ----------
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-hubdeuda-${sufijo}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ---------- Function App Linux, Python, Flex Consumption ----------
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'asp-hubdeuda-dev'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}
resource func 'Microsoft.Web/sites@2024-04-01' = {
  name: 'func-hubdeuda-dev-${sufijo}'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: runtime.name }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appi.properties.ConnectionString }
        { name: 'STORAGE_URL', value: negocio.properties.primaryEndpoints.blob }
        { name: 'SQL_SERVER', value: sql.properties.fullyQualifiedDomainName }
        { name: 'SQL_DATABASE', value: hubDb.name }
      ]
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${runtime.properties.primaryEndpoints.blob}deploy'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      scaleAndConcurrency: { maximumInstanceCount: 40, instanceMemoryMB: 2048 }
      runtime: { name: 'python', version: '3.12' }
    }
  }
  dependsOn: [ deployContainer ]
}

// ---------- Data Factory con identidad administrada ----------
resource adf 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: 'adf-hubdeuda-dev-${sufijo}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

// ---------- Roles de datos (Contributor no concede acceso a datos) ----------
var rolBlobReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'   // Storage Blob Data Reader
var rolBlobOwner = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'    // Storage Blob Data Owner
var rolBlobContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
var rolKvSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User

resource funcLeeNegocio 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: negocio
  name: guid(negocio.id, func.id, rolBlobReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolBlobReader)
    principalId: func.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
// Escritura SOLO en el contenedor manifests: la Function marca en los metadatos
// del manifiesto su estado (terminal / próximo reintento) para no consultar SQL.
resource funcMarcaManifiestos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: contenedores[1]
  name: guid(contenedores[1].id, func.id, rolBlobContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolBlobContributor)
    principalId: func.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource funcRuntime 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: runtime
  name: guid(runtime.id, func.id, rolBlobOwner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolBlobOwner)
    principalId: func.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource adfLeeSecretos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, adf.id, rolKvSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolKvSecretsUser)
    principalId: adf.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------- Presupuesto con alertas 50/80/100 % (5.5) ----------
resource presupuesto 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-hubdeuda-dev'
  properties: {
    category: 'Cost'
    amount: presupuestoUsd
    timeGrain: 'Monthly'
    timePeriod: { startDate: fechaInicioPresupuesto }
    notifications: {
      al50: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 50, contactEmails: [ correoAlertas ] }
      al80: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 80, contactEmails: [ correoAlertas ] }
      al100: { enabled: true, operator: 'GreaterThanOrEqualTo', threshold: 100, contactEmails: [ correoAlertas ] }
    }
  }
}

output storageNegocio string = negocio.name
output storageUrl string = negocio.properties.primaryEndpoints.blob
output sqlServer string = sql.properties.fullyQualifiedDomainName
output sqlDatabase string = hubDb.name
output functionApp string = func.name
output functionPrincipalId string = func.identity.principalId
output dataFactory string = adf.name
output adfPrincipalId string = adf.identity.principalId
output keyVault string = kv.name
