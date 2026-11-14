<#
.SYNOPSIS
  Activa TCP/IP en SQL Server Express (instancia SQLEXPRESS) para que el gateway de datos pueda conectarse.

.DESCRIPTION
  Ejecutar COMO ADMINISTRADOR en PowerShell. Hace solo esto:
    1. Activa el protocolo TCP/IP de la instancia SQLEXPRESS.
    2. Fija el puerto estático 1433 (quita el puerto dinámico).
    3. Reinicia el servicio MSSQL$SQLEXPRESS.
  No abre ningún puerto en el firewall: el gateway corre en este mismo equipo y se conecta por
  localhost,1433. SQL Server sigue sin ser accesible desde la red ni desde internet.

  Después, en la conexión del gateway use el servidor:  localhost,1433

.PARAMETER Instancia
  Identificador de la instancia en el registro (por defecto MSSQL16.SQLEXPRESS = SQL Server 2022 Express).
#>
param([string]$Instancia = "MSSQL16.SQLEXPRESS")

$ErrorActionPreference = "Stop"
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) { throw "Ejecute este script como administrador." }

$base = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$Instancia\MSSQLServer\SuperSocketNetLib\Tcp"
if (-not (Test-Path $base)) { throw "No se encontró la instancia '$Instancia' en el registro: $base" }

Write-Host "TCP/IP actual: Enabled =" (Get-ItemProperty $base).Enabled
Set-ItemProperty -Path $base -Name Enabled -Value 1
$ipAll = Join-Path $base "IPAll"
Set-ItemProperty -Path $ipAll -Name TcpDynamicPorts -Value ""
Set-ItemProperty -Path $ipAll -Name TcpPort -Value "1433"

Write-Host "Reiniciando el servicio MSSQL`$SQLEXPRESS..."
Restart-Service -Name 'MSSQL$SQLEXPRESS' -Force
Start-Sleep -Seconds 5
Get-Service -Name 'MSSQL$SQLEXPRESS' | Format-Table Name, Status -AutoSize

$escucha = Get-NetTCPConnection -LocalPort 1433 -State Listen -ErrorAction SilentlyContinue
if ($escucha) { Write-Host "OK: SQL Server escucha en el puerto 1433 (servidor para el gateway: localhost,1433)." }
else { Write-Warning "No se ve el puerto 1433 en escucha; revise el registro del servicio." }
