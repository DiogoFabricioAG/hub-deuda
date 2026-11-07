<#
Publica los artefactos de adf/ en la Data Factory desplegada por Bicep
(runtime autohospedado, conexiones, conjuntos de datos, pipeline y disparador).
El disparador queda detenido: se activa solo tras una ejecución exitosa (8.6).

  .\tools\desplegar_adf.ps1
#>
param(
  [string]$ResourceGroup = 'rg-hubdeuda-dev',
  [string]$Deployment = 'hubdeuda-infra'
)
$ErrorActionPreference = 'Stop'
$raiz = Resolve-Path "$PSScriptRoot\.."

$o = az deployment group show -g $ResourceGroup -n $Deployment --query properties.outputs -o json | ConvertFrom-Json
$sub = az account show --query id -o tsv
$factory = $o.dataFactory.value
$kvUrl = "https://$($o.keyVault.value).vault.azure.net/"
$base = "https://management.azure.com/subscriptions/$sub/resourceGroups/$ResourceGroup/providers/Microsoft.DataFactory/factories/$factory"

$orden = @(
  @{ carpeta = 'integrationRuntime'; tipo = 'integrationRuntimes' },
  @{ carpeta = 'linkedService';      tipo = 'linkedservices' },
  @{ carpeta = 'dataset';            tipo = 'datasets' },
  @{ carpeta = 'pipeline';           tipo = 'pipelines' },
  @{ carpeta = 'trigger';            tipo = 'triggers' }
)
$tmp = Join-Path $env:TEMP 'hubdeuda-adf'
New-Item -ItemType Directory -Force $tmp | Out-Null

foreach ($paso in $orden) {
  # Key Vault antes que las conexiones que lo referencian
  $archivos = Get-ChildItem (Join-Path $raiz "adf\$($paso.carpeta)") -Filter *.json |
    Sort-Object { if ($_.BaseName -eq 'ls_keyvault') { 0 } else { 1 } }, Name
  foreach ($f in $archivos) {
    $texto = (Get-Content $f.FullName -Raw -Encoding utf8).Replace('__KV_URL__', $kvUrl).Replace('__SQL_SERVER__', $o.sqlServer.value)
    $obj = $texto | ConvertFrom-Json
    if ($paso.tipo -eq 'triggers') { $obj.properties.PSObject.Properties.Remove('runtimeState') }
    $cuerpo = Join-Path $tmp "$($f.BaseName).json"
    @{ properties = $obj.properties } | ConvertTo-Json -Depth 50 | Out-File -Encoding utf8 $cuerpo
    az rest --method put --url "$base/$($paso.tipo)/$($obj.name)?api-version=2018-06-01" --body "@$cuerpo" -o none
    if ($LASTEXITCODE -ne 0) { throw "Falló la publicación de $($obj.name)" }
    Write-Host "Publicado $($paso.tipo)/$($obj.name)"
  }
}
Remove-Item $tmp -Recurse -Force
Write-Host "Data Factory $factory lista. Los disparadores quedan detenidos hasta activarlos con ejecutar_pipeline_base.ps1 -ActivarDisparador."
