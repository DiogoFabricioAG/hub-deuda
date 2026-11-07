<#
Actualiza la regla de firewall PcOnPremise de Azure SQL con la IP pública
actual del PC (cambia al reiniciar el router o el equipo). La necesitan las
herramientas locales y el SHIR, que escribe en Azure SQL por el puerto 1433.

  .\tools\actualizar_ip_pc.ps1
#>
param(
  [string]$ResourceGroup = 'rg-hubdeuda-dev',
  [string]$Servidor = 'sql-hubdeuda-dev-dg23ne'
)
$ErrorActionPreference = 'Stop'
$ip = (Invoke-RestMethod 'https://api.ipify.org?format=json' -TimeoutSec 15).ip
$actual = az sql server firewall-rule show -g $ResourceGroup -s $Servidor -n PcOnPremise --query startIpAddress -o tsv 2>$null
if ($actual -eq $ip) { Write-Host "La regla PcOnPremise ya tiene la IP actual ($ip)"; return }
az sql server firewall-rule update -g $ResourceGroup -s $Servidor -n PcOnPremise --start-ip-address $ip --end-ip-address $ip -o none
Write-Host "Regla PcOnPremise actualizada: $actual -> $ip (puede tardar hasta 5 minutos en aplicarse)"
