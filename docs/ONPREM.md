# Versión on-premise del Hub de Deuda

Los datos viven en SQL Server Express y en carpetas de la empresa (tu PC). La nube solo muestra: Power Apps y Power BI consultan por el **gateway de datos**, que abre una conexión saliente hacia Microsoft. Arquitectura: [arquitectura_objetivo-archify.html](arquitectura_objetivo-archify.html). Informe: [INFORME_EQUIPO.md](INFORME_EQUIPO.md).

## Estado (13 nov 2026)

| Pieza | Estado |
|---|---|
| Hub local `HubDeuda_dev` (SQL Express) con migraciones 001–006 y deuda base de `BDOrigen` (3 papeletas) | Hecho |
| Worker (`onprem/worker.py`): detecta Excel nuevos, guarda original y copia normalizada, escribe el manifiesto y llama al procesador | Hecho |
| Mapeo por área (`onprem/config_areas.json`) para 3 áreas con formatos distintos (áreas 1, 2 y 7) | Hecho |
| Saneamiento con registro de correcciones (`dbo.CorreccionLote`) | Hecho |
| Todo o nada por archivo | Hecho (mismo procesador que Azure) |
| Límites ampliados para 500 000 filas (`HUB_MAX_BYTES`, `HUB_MAX_EXPANDIDO`) | Hecho |
| Pruebas automáticas | 21 aprobadas, 2 de volumen opcionales |
| Volumen: 500 000 filas sucias por el worker | Hecho: 454 s hasta publicado, rechazo todo o nada comprobado ([PRUEBA_VOLUMEN.md](PRUEBA_VOLUMEN.md)) |
| Activar TCP/IP en SQL Express (`tools/onprem_preparar_sql.ps1`) | Hecho (puerto 1433) |
| Gateway de datos local `gw-hubdeudax`, registrado en la región del entorno (South America) | Hecho |
| Cuenta local `svc_hubdeuda` con solo lectura sobre las vistas (`tools/onprem_gateway_acceso.py`) | Hecho |
| Conexión SQL Server con gateway en Power Apps (`HubDeuda_dev localhost,1433`, autenticación Windows) | Hecho |
| Apps «Consulta de deuda» y «Mis observaciones» leyendo del SQL local por el gateway | Hecho y publicadas; evidencias del 14 nov en `evidencias/` |
| Power BI en DirectQuery vía gateway | Pendiente (usuario, en Power BI Desktop) |

## Cómo funciona

1. Cada área deja su Excel en `datos_onprem/areas/AreaNN/` (con su propio formato).
2. `worker.py` calcula la huella SHA-256. Si cambió, lo traduce al contrato v1 con `mapeo.py` y registra cada corrección (espacios, mayúsculas, formato de papeleta, sinónimos, montos «1.234,50» o «S/ 30.00», fechas dd/mm/aaaa, duplicados exactos).
3. Guarda el original en `originales/` y la copia normalizada en `raw/`, y escribe el manifiesto al final.
4. El procesador (el mismo de la Function) valida **todas** las filas y publica el lote completo o lo rechaza completo con la lista de errores (fila y campo).
5. Lo que el mapeo no puede interpretar (por ejemplo un monto «treinta soles») no se corrige: queda para que el validador rechace el archivo.

Las filas en blanco y los duplicados exactos se dejan vacíos, sin eliminarlos, para que el número de fila de cada observación coincida con el del Excel. Si el encabezado no está en la fila 1 (área 7: fila 3), las observaciones usan la numeración del libro normalizado (resta `encabezado_en_fila - 1`).

## Comandos (desde la raíz del repositorio)

```powershell
.venv\Scripts\python.exe tools\aplicar_sql.py --carpeta sql\hub --db HubDeuda_dev
.venv\Scripts\python.exe tools\cargar_base_local.py --hub HubDeuda_dev
.venv\Scripts\python.exe onprem\worker.py --registrar        # alta de archivos autorizados
.venv\Scripts\python.exe onprem\datos_demo.py                # Excel de demostración (3 áreas)
.venv\Scripts\python.exe onprem\worker.py --una-vez          # un ciclo (o --cada 60)
```

Resultado de la demostración: P0001 = 60,00, P0002 = 1 434,50 y P0003 = 95,50, con 29 correcciones registradas.

## Pasos del usuario

1. **Activar TCP/IP en SQL Express** (PowerShell como administrador):
   `.\tools\onprem_preparar_sql.ps1`. Activa TCP/IP, fija el puerto 1433 y reinicia el servicio. No abre el firewall.
2. **Instalar el gateway de datos local** (modo estándar) con la cuenta UNI y darle un nombre (por ejemplo `gw-hubdeuda`). Descarga: <https://aka.ms/on-premises-data-gateway-installer>.
3. **Dar acceso de solo lectura al servicio del gateway** (usa tu autenticación de Windows, sin contraseñas):
   `.venv\Scripts\python.exe tools\onprem_gateway_acceso.py --cuenta "NT SERVICE\PBIEgwService" --bd HubDeuda_dev`
4. En Power Apps crear la conexión de SQL Server marcando «Conectar mediante un gateway de datos local»: servidor `localhost,1433`, base `HubDeuda_dev`, autenticación Windows.

## Lecciones de la puesta en marcha

- **El gateway solo aparece en entornos de su misma región.** El entorno estaba en South America y el gateway nació en South Central US; hubo que reinstalarlo y elegir la región del entorno al registrarlo.
- **La conexión usa una cuenta de Windows con contraseña**, no la cuenta del servicio del gateway. Por eso se creó `svc_hubdeuda`, sin privilegios, con solo lectura. Su contraseña no caduca: `Set-LocalUser -Name svc_hubdeuda -PasswordNeverExpires $true`.
- **Cambiar el origen de datos de una app** se hace en Studio quitando los orígenes viejos y agregando las vistas desde la conexión nueva. Después se baja el paquete (`pac canvas download` + `unpack --layout SourceCode`) a `*_original.msapr` y se publica desde el código con `tools/publicar_apps.ps1`.
- Al reimportar la solución, cada app vuelve a pedir la autorización de la conexión (la acepta el usuario).
- Se quitaron de «Mis observaciones» el botón «Cargar ahora» y «Abrir carpeta del área», que dependían de SharePoint y Azure. La corrección se hace en el Excel local y el worker la procesa.

## Límites conocidos

- Con el gateway, todos los usuarios consultan con una sola identidad: los permisos por área se aplican en la app, no en SQL Server.
- La lectura con `openpyxl` consume unos 2,5 GB con 500 000 filas ([PRUEBA_VOLUMEN.md](PRUEBA_VOLUMEN.md)).
- Solo hay mapeo para 3 de las 10 áreas.
