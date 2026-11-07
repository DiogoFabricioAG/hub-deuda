<#
Ejecuta pl_base_completa en Data Factory, espera el resultado y muestra el
detalle de cada actividad (8.6: primero una ejecución manual exitosa).

  .\tools\ejecutar_pipeline_base.ps1
  .\tools\ejecutar_pipeline_base.ps1 -ActivarDisparador   # tras una ejecución exitosa
#>
param(
  [string]$ResourceGroup = 'rg-hubdeuda-dev',
  [string]$Factory = 'adf-hubdeuda-dev-dg23ne',
  [switch]$ActivarDisparador
)
$ErrorActionPreference = 'Stop'
$sub = az account show --query id -o tsv
$base = "https://management.azure.com/subscriptions/$sub/resourceGroups/$ResourceGroup/providers/Microsoft.DataFactory/factories/$Factory"
$api = 'api-version=2018-06-01'

$ir = az rest --method post --url "$base/integrationRuntimes/ir-onpremise/getStatus?$api" --query "properties.state" -o tsv
Write-Host "Runtime ir-onpremise: $ir"
if ($ir -ne 'Online') { throw 'El SHIR no está Online: revise el servicio DIAHostService en el PC' }

$run = az rest --method post --url "$base/pipelines/pl_base_completa/createRun?$api" --query runId -o tsv
Write-Host "Ejecución iniciada: $run"
do {
  Start-Sleep -Seconds 10
  $estado = az rest --method get --url "$base/pipelineruns/${run}?$api" --query status -o tsv
  Write-Host "  estado: $estado"
} while ($estado -in 'Queued', 'InProgress', 'Canceling')

$hasta = (Get-Date).ToUniversalTime().AddMinutes(5).ToString('o')
$desde = (Get-Date).ToUniversalTime().AddHours(-1).ToString('o')
$cuerpo = New-TemporaryFile
[IO.File]::WriteAllText($cuerpo.FullName, (@{ lastUpdatedAfter = $desde; lastUpdatedBefore = $hasta } | ConvertTo-Json))
az rest --method post --url "$base/pipelineruns/$run/queryActivityruns?$api" --body "@$($cuerpo.FullName)" `
  --query "value[].{actividad:activityName, estado:status, segundos:durationInMs, error:error.message}" -o table
Remove-Item $cuerpo.FullName

if ($estado -eq 'Succeeded' -and $ActivarDisparador) {
  az rest --method post --url "$base/triggers/tr_base_programada/start?$api" -o none
  Write-Host 'Disparador tr_base_programada ACTIVADO (12:55 y 17:55, hora de Lima).'
}
Write-Host "Resultado: $estado (RunId $run = CargaId en dbo.BaseCarga)"

