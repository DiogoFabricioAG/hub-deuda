#Requires -RunAsAdministrator
<#
Prepara el PC como origen on-premise para Data Factory (secciones 5.4 y 8.1–8.2).
EJECUTAR UNO MISMO en PowerShell "como administrador", desde D:\hub-deuda-azure:

  .\tools\instalar_shir.ps1 -Msi "C:\ruta\IntegrationRuntime_x.y.msi"

Qué hace (cada paso se puede revisar antes de ejecutar):
 1. Instala el Self-hosted Integration Runtime (SHIR) desde el MSI oficial de Microsoft.
 2. Obtiene la clave de registro del runtime ir-onpremise con tu sesión de `az login`
    y registra este PC como nodo. La clave no se muestra ni se guarda en disco.
 3. CAMBIA la autenticación de SQL Server Express a modo mixto (Windows + SQL) y
    reinicia el servicio MSSQL$SQLEXPRESS. Es una configuración de seguridad de tu
    equipo: solo ejecútalo si estás de acuerdo.
 4. Crea el login de solo lectura hub_lector (contraseña aleatoria de 32 caracteres)
    con permiso únicamente para usp_CrearExportacion y DeudaExport en BDOrigen, y
    guarda la contraseña directamente en Key Vault (secreto bdorigen-lector).
#>
param(
  [Parameter(Mandatory)] [string]$Msi,
  [string]$ResourceGroup = 'rg-hubdeuda-dev',
  [string]$Factory = 'adf-hubdeuda-dev-dg23ne',
  [string]$KeyVault = 'kv-hubdeuda-dg23ne',
  [string]$Instancia = 'SQLEXPRESS'
)
$ErrorActionPreference = 'Stop'

az account show -o none 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Sin sesión de Azure: ejecute az login --tenant 1eba443f-23e5-4534-90d1-0976aabe86ac' }
$sub = az account show --query id -o tsv
$ir = "https://management.azure.com/subscriptions/$sub/resourceGroups/$ResourceGroup/providers/Microsoft.DataFactory/factories/$Factory/integrationRuntimes/ir-onpremise"

# 1. Instalar SHIR
if (-not (Get-Service DIAHostService -ErrorAction SilentlyContinue)) {
  if (-not (Test-Path $Msi)) { throw "No existe el MSI: $Msi" }
  Write-Host '1/4 Instalando Self-hosted Integration Runtime...'
  $p = Start-Process msiexec.exe -ArgumentList "/i `"$Msi`" /quiet /norestart" -Wait -PassThru
  if ($p.ExitCode -notin 0, 3010) { throw "msiexec terminó con código $($p.ExitCode)" }
} else { Write-Host '1/4 SHIR ya instalado' }

# 2. Registrar el nodo
$dmgcmd = Get-ChildItem 'C:\Program Files\Microsoft Integration Runtime' -Recurse -Filter dmgcmd.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $dmgcmd) { throw 'No se encontró dmgcmd.exe tras la instalación' }
$estado = az rest --method post --url "$ir/getStatus?api-version=2018-06-01" --query "properties.nodes[].nodeName" -o tsv 2>$null
if ($estado -notcontains $env:COMPUTERNAME) {
  Write-Host '2/4 Registrando este PC en ir-onpremise...'
  $clave = az rest --method post --url "$ir/listAuthKeys?api-version=2018-06-01" --query authKey1 -o tsv
  & $dmgcmd.FullName -RegisterNewNode $clave $env:COMPUTERNAME | Out-Null
  Remove-Variable clave
} else { Write-Host '2/4 Nodo ya registrado' }

# 3. Modo mixto en SQL Express (cambio de seguridad local)
$clave = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server' |
  Where-Object { $_.PSChildName -like "MSSQL*.$Instancia" } | Select-Object -First 1
$reg = Join-Path $clave.PSPath 'MSSQLServer'
if ((Get-ItemProperty $reg).LoginMode -ne 2) {
  Write-Host '3/4 Activando autenticación mixta en SQL Express y reiniciando el servicio...'
  Set-ItemProperty $reg -Name LoginMode -Value 2
  Restart-Service "MSSQL`$$Instancia" -Force
  Start-Sleep -Seconds 5
} else { Write-Host '3/4 SQL Express ya está en modo mixto' }

# 4. Login de solo lectura y secreto en Key Vault
Add-Type -AssemblyName System.Web
$pwd = [System.Web.Security.Membership]::GeneratePassword(32, 6)
$sql = @"
IF SUSER_ID('hub_lector') IS NULL
  CREATE LOGIN hub_lector WITH PASSWORD = N'$($pwd.Replace("'","''"))', CHECK_POLICY = ON, DEFAULT_DATABASE = BDOrigen;
ELSE
  ALTER LOGIN hub_lector WITH PASSWORD = N'$($pwd.Replace("'","''"))';
USE BDOrigen;
IF DATABASE_PRINCIPAL_ID('hub_lector') IS NULL CREATE USER hub_lector FOR LOGIN hub_lector;
ALTER ROLE rol_origen_lector ADD MEMBER hub_lector;
"@
$cn = New-Object System.Data.SqlClient.SqlConnection "Server=localhost\$Instancia;Database=master;Integrated Security=True"
$cn.Open(); $cmd = $cn.CreateCommand(); $cmd.CommandText = $sql; [void]$cmd.ExecuteNonQuery(); $cn.Close()
$tmp = New-TemporaryFile
try {
  [IO.File]::WriteAllText($tmp.FullName, $pwd)
  az keyvault secret set --vault-name $KeyVault --name bdorigen-lector --file $tmp.FullName -o none
} finally { Remove-Item $tmp.FullName -Force; Remove-Variable pwd }
Write-Host '4/4 Login hub_lector listo; contraseña guardada en Key Vault (bdorigen-lector)'

Write-Host "`nEstado del runtime:"
az rest --method post --url "$ir/getStatus?api-version=2018-06-01" --query "{estado:properties.state, nodos:properties.nodes[].{nombre:nodeName, estado:status}}" -o json
