<#
Publica las apps de lienzo desde su código (powerplatform/apps/<App>/Src/*.pa.yaml):
 1. Empaqueta cada app con `pac canvas pack`.
 2. Exporta la solución HubDeuda (no administrada).
 3. Reemplaza dentro del .zip el .msapp de cada app por el empaquetado.
 4. Importa la solución y publica las personalizaciones.
Las apps deben estar ya agregadas a la solución y cerradas en Studio.

  .\tools\publicar_apps.ps1
#>
param(
  [hashtable]$Apps = @{ 'Consulta de deuda' = 'ConsultaDeuda'; 'Mis observaciones' = 'MisObservaciones' },
  [string]$Solucion = 'HubDeuda'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$env:DOTNET_ROOT = "$env:USERPROFILE\.dotnet"
$pac = "$env:USERPROFILE\.dotnet\tools\pac.exe"
$raiz = Resolve-Path "$PSScriptRoot\.."
$tmp = Join-Path $raiz 'tests\_out\publicar'
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $tmp | Out-Null

foreach ($carpeta in $Apps.Values) {
  & $pac canvas pack --sources (Join-Path $raiz "powerplatform\apps\$carpeta") --msapp (Join-Path $tmp "$carpeta.msapp") | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "No se pudo empaquetar $carpeta" }
}

$zip = Join-Path $tmp "$Solucion.zip"
& $pac solution export --name $Solucion --path $zip --overwrite | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Falló la exportación de la solución' }
# Se reemplazan solo las entradas .msapp dentro de una copia del zip exportado:
# volver a comprimir la carpeta con .NET Framework escribe rutas con '\' y
# Dataverse no encuentra Workflows/*.json al importar.
$nuevo = Join-Path $tmp "$Solucion-apps.zip"
Copy-Item $zip $nuevo
$archivo = [System.IO.Compression.ZipFile]::Open($nuevo, 'Update')
try {
  $lector = New-Object IO.StreamReader($archivo.GetEntry('customizations.xml').Open(), [Text.Encoding]::UTF8)
  [xml]$cust = $lector.ReadToEnd(); $lector.Dispose()
  foreach ($app in $cust.ImportExportXml.CanvasApps.CanvasApp) {
    $carpeta = $Apps[$app.DisplayName]
    if (-not $carpeta) { continue }
    $nombre = $app.DocumentUri.TrimStart('/')
    $archivo.GetEntry($nombre).Delete()
    $entrada = $archivo.CreateEntry($nombre)
    $destino = $entrada.Open()
    $bytes = [IO.File]::ReadAllBytes((Join-Path $tmp "$carpeta.msapp"))
    $destino.Write($bytes, 0, $bytes.Length); $destino.Dispose()
    Write-Host "Reemplazado $($app.DisplayName) -> $nombre"
  }
} finally { $archivo.Dispose() }
& $pac solution import --path $nuevo --publish-changes
if ($LASTEXITCODE -ne 0) { throw 'Falló la importación de la solución' }
Write-Host 'Apps publicadas desde código.'
