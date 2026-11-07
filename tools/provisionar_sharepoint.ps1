<#
Crea el sitio IntegracionDeuda y su estructura (sección 6 de la guía) con la
CLI for Microsoft 365. Requiere haber ejecutado `m365 setup` y `m365 login`
con la cuenta UNI. Es repetible: lo que ya existe no se vuelve a crear.

  .\tools\provisionar_sharepoint.ps1
  .\tools\provisionar_sharepoint.ps1 -TipoSitio CommunicationSite   # si la UNI no permite crear grupos M365

Salida: infra\sharepoint.local.json con la URL del sitio y el UniqueId de
cada movimientos.xlsx, que tools\sincronizar_areafuente.py copia a dbo.AreaFuente.
#>
param(
  [string]$Alias = 'IntegracionDeuda',
  [ValidateSet('TeamSite', 'CommunicationSite')] [string]$TipoSitio = 'TeamSite',
  [string]$Plantillas = "$PSScriptRoot\..\powerplatform\plantillas"
)
$ErrorActionPreference = 'Stop'

function M365Json([string[]]$argumentos) {
  $salida = & m365 @argumentos --output json 2>&1
  if ($LASTEXITCODE -ne 0) { throw "m365 $($argumentos -join ' ') falló: $salida" }
  if ($salida) { return ($salida | Out-String | ConvertFrom-Json) }
}

$areas = [ordered]@{
  1 = 'Tesorería'; 2 = 'Ejecutoría Coactiva'; 3 = 'Asesoría Legal'; 4 = 'Fiscalización'
  5 = 'Atención al Ciudadano'; 6 = 'Recaudación'; 7 = 'Administración Tributaria'
  8 = 'Contabilidad'; 9 = 'Tránsito'; 10 = 'Archivo Central'
}

$estado = M365Json @('status')
if (-not $estado.connectedAs) { throw 'No hay sesión: ejecute m365 setup y m365 login con la cuenta UNI.' }
Write-Host "Sesión: $($estado.connectedAs)"

$raiz = M365Json @('request', '--url', 'https://graph.microsoft.com/v1.0/sites/root?$select=webUrl', '--method', 'get')
$tenantUrl = ([uri]$raiz.webUrl).GetLeftPart([UriPartial]::Authority)
$siteUrl = "$tenantUrl/sites/$Alias"
$sitePath = "/sites/$Alias"

# 6.1 Sitio
$existe = $true
try { M365Json @('spo', 'web', 'get', '--url', $siteUrl) | Out-Null } catch { $existe = $false }
if (-not $existe) {
  Write-Host "Creando $TipoSitio $siteUrl ..."
  if ($TipoSitio -eq 'TeamSite') {
    M365Json @('spo', 'site', 'add', '--type', 'TeamSite', '--title', $Alias, '--alias', $Alias,
      '--description', 'Hub de Deuda: entradas de las áreas, plantillas, reportes y evidencias (datos ficticios)') | Out-Null
  } else {
    M365Json @('spo', 'site', 'add', '--type', 'CommunicationSite', '--title', $Alias, '--url', $siteUrl,
      '--description', 'Hub de Deuda: entradas de las áreas, plantillas, reportes y evidencias (datos ficticios)') | Out-Null
  }
}

# Bibliotecas con historial de versiones
$listas = (M365Json @('spo', 'list', 'list', '--webUrl', $siteUrl)).Title
foreach ($b in 'Entradas', 'Plantillas', 'Reportes', 'Evidencias') {
  if ($listas -notcontains $b) {
    M365Json @('spo', 'list', 'add', '--webUrl', $siteUrl, '--title', $b, '--baseTemplate', 'DocumentLibrary',
      '--enableVersioning', 'true', '--majorVersionLimit', '100') | Out-Null
    Write-Host "Biblioteca $b creada"
  }
}

# Carpetas Area01..Area10 y libro controlado de cada área
$salida = [ordered]@{ siteUrl = $siteUrl; biblioteca = 'Entradas'; areas = @() }
foreach ($id in $areas.Keys) {
  $carpeta = 'Area{0:D2}' -f $id
  try { M365Json @('spo', 'folder', 'get', '--webUrl', $siteUrl, '--url', "$sitePath/Entradas/$carpeta") | Out-Null }
  catch { M365Json @('spo', 'folder', 'add', '--webUrl', $siteUrl, '--parentFolderUrl', "$sitePath/Entradas", '--name', $carpeta) | Out-Null }
  $rutaArchivo = "$sitePath/Entradas/$carpeta/movimientos.xlsx"
  $archivo = $null
  try { $archivo = M365Json @('spo', 'file', 'get', '--webUrl', $siteUrl, '--url', $rutaArchivo) } catch {}
  if (-not $archivo) {
    $local = Join-Path $Plantillas "$carpeta\movimientos.xlsx"
    M365Json @('spo', 'file', 'add', '--webUrl', $siteUrl, '--folder', "Entradas/$carpeta", '--path', $local) | Out-Null
    $archivo = M365Json @('spo', 'file', 'get', '--webUrl', $siteUrl, '--url', $rutaArchivo)
  }
  $salida.areas += [ordered]@{ areaId = $id; nombre = $areas[$id]; rutaArchivo = $rutaArchivo; uniqueId = "$($archivo.UniqueId)".ToLower() }
  Write-Host ("{0} -> {1}" -f $carpeta, $archivo.UniqueId)
}

# Plantilla maestra controlada
try { M365Json @('spo', 'file', 'get', '--webUrl', $siteUrl, '--url', "$sitePath/Plantillas/movimientos_maestra.xlsx") | Out-Null }
catch {
  $tmp = Join-Path $env:TEMP 'movimientos_maestra.xlsx'
  Copy-Item (Join-Path $Plantillas 'Area03\movimientos.xlsx') $tmp -Force
  M365Json @('spo', 'file', 'add', '--webUrl', $siteUrl, '--folder', 'Plantillas', '--path', $tmp) | Out-Null
}

# 6.3 Lista ConfigAreas (edición solo coordinación)
if ($listas -notcontains 'ConfigAreas') {
  M365Json @('spo', 'list', 'add', '--webUrl', $siteUrl, '--title', 'ConfigAreas', '--baseTemplate', 'GenericList') | Out-Null
  $campos = @(
    '<Field Type="Number" DisplayName="AreaId" Name="AreaId" Required="TRUE" Decimals="0" Min="1" Max="10" />',
    '<Field Type="Text" DisplayName="NombreArea" Name="NombreArea" Required="TRUE" />',
    '<Field Type="Text" DisplayName="RutaArchivo" Name="RutaArchivo" Required="TRUE" />',
    '<Field Type="Text" DisplayName="FileUniqueId" Name="FileUniqueId" Required="TRUE" />',
    '<Field Type="Boolean" DisplayName="Activa" Name="Activa"><Default>1</Default></Field>',
    '<Field Type="Text" DisplayName="ResponsableUPN" Name="ResponsableUPN" />',
    '<Field Type="Text" DisplayName="VersionContrato" Name="VersionContrato"><Default>1</Default></Field>',
    '<Field Type="Text" DisplayName="DestinoAvisos" Name="DestinoAvisos" />'
  )
  foreach ($x in $campos) { M365Json @('spo', 'field', 'add', '--webUrl', $siteUrl, '--listTitle', 'ConfigAreas', '--xml', $x) | Out-Null }
}
$items = M365Json @('spo', 'listitem', 'list', '--webUrl', $siteUrl, '--listTitle', 'ConfigAreas', '--fields', 'AreaId')
foreach ($a in $salida.areas) {
  if (-not ($items | Where-Object { [int]$_.AreaId -eq $a.areaId })) {
    M365Json @('spo', 'listitem', 'add', '--webUrl', $siteUrl, '--listTitle', 'ConfigAreas',
      '--Title', $a.nombre, '--AreaId', "$($a.areaId)", '--NombreArea', $a.nombre, '--RutaArchivo', $a.rutaArchivo,
      '--FileUniqueId', $a.uniqueId, '--Activa', 'true', '--VersionContrato', '1', '--ResponsableUPN', $estado.connectedAs,
      '--DestinoAvisos', $estado.connectedAs) | Out-Null
  }
}

$destino = Join-Path $PSScriptRoot '..\infra\sharepoint.local.json'
$salida | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 $destino
Write-Host "Listo. Configuración en $destino"
