# Diccionario de datos — Hub de Deuda

Documento del paquete de aceptación (sección 14 de la guía). Describe los datos tal como están construidos en el repositorio al **7 de noviembre de 2026**: contrato del libro Excel **v1** (`CONTRATO_VERSION = "1"`), reglas de validación **v1** (`REGLAS_VERSION = "v1"`), migraciones `sql/hub/001`–`005` y `sql/origen/001`–`002`. **Todos los datos son ficticios.**

Fuentes en el código: `functions/validacion.py`, `functions/procesador.py`, `functions/repositorio_sql.py`, `powerplatform/flows/fl_copia_area.json`, `tools/plantillas.py`, `tools/provisionar_sharepoint.ps1`, `sql/hub/*.sql`, `sql/origen/*.sql`.

Documentos relacionados: [ARQUITECTURA.md](ARQUITECTURA.md) · [MATRIZ_PERMISOS.md](MATRIZ_PERMISOS.md) · [DECISIONES.md](DECISIONES.md) · [PRUEBAS.md](PRUEBAS.md)

**Contenido**

1. [Libro Excel de cada área (contrato v1)](#1-libro-excel-de-cada-área-contrato-v1)
2. [Campos que agrega la integración](#2-campos-que-agrega-la-integración)
3. [Manifiesto JSON y rutas de Blob](#3-manifiesto-json-y-rutas-de-blob)
4. [Base HubDeuda (Azure SQL): tablas](#4-base-hubdeuda-azure-sql-tablas)
5. [Base HubDeuda: vistas](#5-base-hubdeuda-vistas)
6. [Base HubDeuda: procedimientos](#6-base-hubdeuda-procedimientos)
7. [Base de origen BDOrigen (SQL Server Express)](#7-base-de-origen-bdorigen-sql-server-express)
8. [Estados](#8-estados)
9. [Códigos de observación](#9-códigos-de-observación)
10. [Lista ConfigAreas (SharePoint)](#10-lista-configareas-sharepoint)

---

## 1. Libro Excel de cada área (contrato v1)

### 1.1 Ubicación y estructura

| Elemento | Valor |
|---|---|
| Ubicación | Sitio `https://unipe.sharepoint.com/sites/IntegracionDeuda` › biblioteca **Entradas** › carpeta `Area01` … `Area10` › `movimientos.xlsx` |
| Plantilla | Generada por `tools/plantillas.py` (copias en `powerplatform/plantillas/AreaNN/movimientos.xlsx`; maestra en la biblioteca **Plantillas** como `movimientos_maestra.xlsx`) |
| Hoja | `Datos` (nombre exacto) |
| Tabla de Excel | `tblMovimientos` (nombre exacto) |
| Encabezados | Exactamente 8, en este orden: `MovimientoId`, `PapeletaId`, `Tipo`, `Monto`, `FechaEvento`, `Estado`, `Referencia`, `Detalle` |
| Formato preparado | Columnas A, B, G y H con formato **Texto**; D con `0.00`; E con `yyyy-mm-dd`; listas de validación para `Tipo` (OBSERVACION + tipo del área) y `Estado`; `Monto` decimal ≥ 0; `FechaEvento` ≤ `TODAY()`. 500 filas preformateadas |

**Reglas del archivo completo** (si fallan, el lote se rechaza con una sola observación de archivo, `FilaExcel` nulo):

| Regla | Código |
|---|---|
| El área del manifiesto debe estar entre 1 y 10 | `AREA_DESCONOCIDA` |
| Archivo de 10 MiB como máximo; contenido descomprimido de 50 MiB como máximo; debe ser un .xlsx válido | `ARCHIVO_INVALIDO` |
| Debe existir la hoja `Datos` y, dentro de ella, la tabla `tblMovimientos` | `ESTRUCTURA` |
| La primera fila de la tabla debe tener los 8 encabezados exactos y en orden | `ENCABEZADOS` |
| Debe haber al menos una fila no vacía (la inicialización con libro vacío requiere autorización explícita) | `CARGA_VACIA` |

**Reglas de lectura de filas**

- Solo se leen las filas **dentro del rango de la tabla** `tblMovimientos`. Una fila escrita debajo de la tabla, fuera de su rango, no se lee.
- Las filas con las 8 celdas vacías se ignoran y no cuentan en `FilasLeidas`.
- Si **cualquier** celda de la fila contiene una fórmula, la fila se rechaza con `FORMULA` y no se evalúan sus demás campos.
- Basta un error en cualquier fila para rechazar **todo** el lote: no hay publicación parcial.

### 1.2 Campos del contrato

| # | Campo | Tipo esperado en Excel | Obligatorio | Regla de validación (validacion.py) | Código si falla | Ejemplo |
|---|---|---|---|---|---|---|
| 1 | `MovimientoId` | Texto (no número) | Sí | Texto no vacío tras recortar espacios; máximo 50 caracteres; único dentro del libro. Es la identidad estable del movimiento entre versiones: el mismo id con otros valores es una **corrección** y omitir un id ya publicado está prohibido (`PUBLICACION_50107`) | `TEXTO_REQUERIDO`, `LONGITUD`, `DUPLICADO` | `TES0001` |
| 2 | `PapeletaId` | Texto | Sí | Texto no vacío; máximo 30 caracteres; debe existir en la base de deuda vigente (`vBaseVigente`). La comparación es exacta (`p0001` ≠ `P0001`) | `TEXTO_REQUERIDO`, `LONGITUD`, `PAPELETA_INEXISTENTE` | `P0001` |
| 3 | `Tipo` | Texto de la lista | Sí | Se recorta y pasa a mayúsculas. Solo se admite `OBSERVACION` o el `TipoPermitido` del área (tabla 1.3) | `TIPO_NO_AUTORIZADO` | `PAGO` (área 01) |
| 4 | `Monto` | Número decimal | Sí | Número finito, valor absoluto < 10^16, **máximo 2 decimales**. `PAGO`, `CARGO` y `DESCUENTO` > 0; `OBSERVACION` = 0. Vacío o booleano no es válido. Se guarda redondeado a 0.01 | `MONTO_INVALIDO` | `30.00` |
| 5 | `FechaEvento` | Fecha de Excel o texto `AAAA-MM-DD` | Sí | Fecha válida y **no futura** respecto de la fecha actual en Lima (`America/Lima`). Si es fecha y hora, se toma solo la fecha | `FECHA_INVALIDA` | `2026-11-07` |
| 6 | `Estado` | Texto de la lista | Sí | Se recorta y pasa a mayúsculas: `ACTIVO` o `ANULADO`. Anular es la forma de quitar un movimiento sin borrar su historia | `ESTADO_INVALIDO` | `ACTIVO` |
| 7 | `Referencia` | Texto | Sí | Texto no vacío; máximo 100 caracteres. En movimientos económicos (`Tipo` ≠ OBSERVACION) y `ACTIVO`, el par (`Tipo`, `Referencia`) no puede repetirse en el libro (misma operación cargada dos veces) | `TEXTO_REQUERIDO`, `LONGITUD`, `REFERENCIA_REPETIDA` | `REC001` |
| 8 | `Detalle` | Texto | No | Máximo 250 caracteres. Vacío se guarda como `NULL` | `LONGITUD` | `Pago en ventanilla` |

### 1.3 Tipo permitido por área (`dbo.Area`)

| AreaId | Área | `TipoPermitido` | Efecto en el saldo |
|---|---|---|---|
| 1 | Tesorería | PAGO | Resta |
| 2 | Ejecutoría Coactiva | CARGO | Suma |
| 3 | Asesoría Legal | OBSERVACION | Ninguno (monto 0) |
| 4 | Fiscalización | OBSERVACION | Ninguno |
| 5 | Atención al Ciudadano | OBSERVACION | Ninguno |
| 6 | Recaudación | OBSERVACION | Ninguno |
| 7 | Administración Tributaria | DESCUENTO | Resta |
| 8 | Contabilidad | OBSERVACION | Ninguno |
| 9 | Tránsito | OBSERVACION | Ninguno |
| 10 | Archivo Central | OBSERVACION | Ninguno |

Todas las áreas pueden registrar además `OBSERVACION` con monto 0.

### 1.4 Semántica de versión

Cada libro es la **fotografía completa** de los movimientos del área, no un archivo de novedades. El lote aceptado más reciente reemplaza al anterior (`Area.LoteVigente`). Por eso:

- Corregir = cambiar la fila conservando el `MovimientoId`.
- Quitar = marcar `Estado = ANULADO`. Borrar la fila de un movimiento ya publicado provoca el rechazo `PUBLICACION_50107`.
- Volver a enviar el mismo archivo no duplica nada: el lote queda `SIN_CAMBIOS`.

---

## 2. Campos que agrega la integración

Además de los 8 campos del contrato, la integración agrega o normaliza estos datos:

| Campo | Dónde se guarda | Origen | Descripción |
|---|---|---|---|
| `LoteId` | `Lote`, `Movimiento`, `Observacion`, `Notificacion` | Flujo `fl_copia_area` (`guid()`) | Identificador único de cada copia del libro. Nombra el archivo en `raw` y el manifiesto |
| `AreaId` | `Lote` | Manifiesto | Área 1–10 |
| `ArchivoId` | `Lote` | Manifiesto `sourceFileId` | `UniqueId` de SharePoint del libro, en minúsculas |
| `VersionFuente` | `Lote` | Manifiesto `sourceVersion` | ETag del archivo en SharePoint al momento de la copia |
| `ModificadoUtc` | `Lote` | Manifiesto `sourceModifiedUtc` | `TimeLastModified` del archivo en SharePoint, convertido a UTC sin zona. Ordena las versiones |
| `Reglas` | `Lote` | Function (`REGLAS_VERSION`) | Versión de reglas con que se validó (`v1`) |
| `Sha256` | `Lote` | Function | Huella SHA-256 de los bytes del .xlsx. Detecta archivos idénticos (`SIN_CAMBIOS`) |
| `RawPath` | `Lote` | Manifiesto `rawPath` | Ruta del original en el contenedor `raw` |
| `Estado` | `Lote` | Function | Resultado del lote (sección 8.1) |
| `FilasLeidas` | `Lote` | Function | Filas no vacías dentro de la tabla. Debe coincidir con las filas insertadas en `Movimiento` |
| `FlowRunId` | `Lote` | Manifiesto `flowRunId` | Nombre de la ejecución de Power Automate (trazabilidad) |
| `SolicitadoPor` | `Lote` | Manifiesto `requestedBy` | `fl_copia_programada` o el correo de quien pulsó «Cargar ahora» |
| `CreadoUtc` / `PublicadoUtc` | `Lote` | SQL (`SYSUTCDATETIME()`) | Registro del lote y momento de publicación |
| `FilaExcel` | `Movimiento`, `Observacion` | Function | Número de fila en la hoja `Datos` (la fila 1 es el encabezado). En observaciones de archivo es `NULL` |
| Normalización | `Movimiento` | Function | Textos recortados; `Tipo` y `Estado` en mayúsculas; `Monto` redondeado a 2 decimales; `FechaEvento` como `date`; `Detalle` vacío → `NULL` |

---

## 3. Manifiesto JSON y rutas de Blob

### 3.1 Contenedores de la cuenta de negocio (`sthubdeudadevdg23ne`)

| Contenedor | Ruta | Escribe | Lee |
|---|---|---|---|
| `raw` | `areaNN/AAAA/MM/DD/<LoteId>.xlsx` (NN = área con dos dígitos; fecha UTC de la copia) | `fl_copia_area` | Function |
| `manifests` | `<LoteId>.json` | `fl_copia_area`, **después** de escribir el raw | Function |
| `reports` | Reservado para los PDF de `fl_reporte_deuda` | (flujo pendiente) | — |

El manifiesto es la señal de que el raw está completo: el flujo lo escribe solo si la copia del Excel terminó bien. Los manifiestos **no se borran** tras procesarse; el control de qué ya se procesó vive en `dbo.ProcesoManifiesto`.

### 3.2 Campos del manifiesto (`procesador.leer_manifiesto`)

| Campo | Tipo JSON | Obligatorio | Regla que aplica la Function | Valor que escribe `fl_copia_area` |
|---|---|---|---|---|
| `loteId` | string (GUID) | Sí | GUID válido; el nombre del blob debe ser exactamente `<loteId>.json` | `guid()` del flujo |
| `areaId` | number (entero) | Sí | Entero 1–10 (no booleano) | `int(AreaId)` recibido |
| `sourceFileId` | string | Sí | No vacío, máximo 200 caracteres. Debe coincidir (sin distinguir mayúsculas) con `AreaFuente.ArchivoId` del área y la fuente debe estar `Activa`; si no, lote `RECHAZADO` con `ARCHIVO_NO_AUTORIZADO` | `toLower(UniqueId)` leído después de la copia |
| `sourceVersion` | string | Sí | No vacío, máximo 120 caracteres | `ETag` del archivo |
| `sourceModifiedUtc` | string ISO 8601 | Sí | Debe incluir zona (`Z` u offset); se convierte a UTC | `TimeLastModified` |
| `rawContainer` | string | Sí | Exactamente `raw` | `raw` |
| `rawPath` | string | Sí | Debe cumplir `^area(\d{2})/\d{4}/\d{2}/\d{2}/<GUID>\.xlsx$`, con el área igual a `areaId` y el GUID igual a `loteId` | `areaNN/AAAA/MM/DD/<LoteId>.xlsx` |
| `contractVersion` | string | Sí | Igual a `"1"` | `"1"` |
| `flowRunId` | string | No | Texto libre | `workflow().run.name` |
| `requestedBy` | string | No | Texto libre | `fl_copia_programada` o correo del solicitante |

Se acepta UTF-8 con o sin BOM. Un manifiesto que no cumple estas reglas **no crea lote**: queda marcado como terminal en `dbo.ProcesoManifiesto` con `UltimoError = 'MANIFIESTO_INVALIDO: …'`.

### 3.3 Ejemplo (valores ficticios)

```json
{
  "loteId": "11111111-2222-4333-8444-555555555555",
  "areaId": 1,
  "sourceFileId": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
  "sourceVersion": "\"{AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE},3\"",
  "sourceModifiedUtc": "2026-11-07T17:58:12Z",
  "rawContainer": "raw",
  "rawPath": "area01/2026/11/07/11111111-2222-4333-8444-555555555555.xlsx",
  "contractVersion": "1",
  "flowRunId": "08584000000000000000000000000CU00",
  "requestedBy": "fl_copia_programada"
}
```

---

## 4. Base HubDeuda (Azure SQL): tablas

Servidor `sql-hubdeuda-dev-dg23ne.database.windows.net`, base `HubDeuda`. Las tablas guardan **versiones históricas**; los punteros vigentes (`Area.LoteVigente`, `BaseActual.CargaId`) solo se cambian mediante procedimientos.

### 4.1 `dbo.Area` — catálogo de áreas y puntero de versión vigente

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `AreaId` | tinyint | No | PK; `CHECK 1..10` | Identificador del área |
| `Nombre` | nvarchar(80) | No | — | Nombre del área |
| `TipoPermitido` | varchar(12) | No | `PAGO`, `CARGO`, `DESCUENTO`, `OBSERVACION` | Tipo económico que puede registrar (además de OBSERVACION) |
| `LoteVigente` | uniqueidentifier | Sí | FK → `Lote.LoteId` | Lote aceptado vigente del área; `NULL` si nunca se aceptó uno |

Semilla: 10 filas (tabla 1.3).

### 4.2 `dbo.AreaFuente` — archivo autorizado por área

Espejo controlado de la lista `ConfigAreas` de SharePoint. Lo llena `tools/sincronizar_areafuente.py`.

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `AreaId` | tinyint | No | PK; FK → `Area` | Área |
| `ArchivoId` | nvarchar(200) | No | — | `UniqueId` de SharePoint del `movimientos.xlsx` autorizado (minúsculas) |
| `RutaArchivo` | nvarchar(400) | No | — | Ruta relativa al servidor, p. ej. `/sites/IntegracionDeuda/Entradas/Area01/movimientos.xlsx` |
| `Activa` | bit | No | `1` | Si es 0, todo manifiesto del área se rechaza con `ARCHIVO_NO_AUTORIZADO` |
| `ResponsableUPN` | nvarchar(200) | Sí | — | Responsable del área (lo usará el flujo de avisos) |
| `DestinoAvisos` | nvarchar(200) | Sí | — | Correo o canal de avisos |
| `VersionContrato` | varchar(10) | No | `'1'` | Versión del contrato del libro |

### 4.3 `dbo.BaseCarga` — cada fotografía de la deuda base

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `CargaId` | uniqueidentifier | No | PK | En ADF es el `RunId` del pipeline |
| `CorteUtc` | datetime2 | No | — | Momento de la exportación en el origen |
| `Estado` | varchar(20) | No | `RECIBIDA`, `ACEPTADA`, `FALLIDA` | Ver 8.2 |
| `FilasEsperadas` | int | No | — | Filas que informó el origen; se compara con lo copiado |
| `CreadaUtc` | datetime2 | No | `SYSUTCDATETIME()` | Registro de la carga |
| `PublicadaUtc` | datetime2 | Sí | — | Momento en que pasó a ser la base vigente |
| `Motivo` | nvarchar(500) | Sí | — | Motivo del fallo |

### 4.4 `dbo.BaseFila` — filas de cada fotografía

| Columna | Tipo | Nulo | Restricción | Descripción |
|---|---|---|---|---|
| `CargaId` | uniqueidentifier | No | PK (1/2); FK → `BaseCarga` | Carga a la que pertenece |
| `PapeletaId` | varchar(30) | No | PK (2/2) | Papeleta |
| `TipoDoc` | varchar(3) | No | `DNI`, `RUC` | Tipo de documento |
| `Documento` | varchar(11) | No | Solo dígitos; 8 (DNI) u 11 (RUC), validado al publicar (50004) | Documento del deudor |
| `Placa` | varchar(10) | Sí | — | Placa del vehículo |
| `ImporteOriginal` | decimal(18,2) | No | `>= 0` | Importe de la papeleta en el origen |
| `Activa` | bit | No | — | Si la deuda sigue activa en el origen |

Índices: `IX_BaseFila_Documento (CargaId, Documento)`, `IX_BaseFila_Placa (CargaId, Placa)`.

### 4.5 `dbo.BaseActual` — puntero de la base vigente

| Columna | Tipo | Nulo | Restricción | Descripción |
|---|---|---|---|---|
| `Id` | tinyint | No | PK; `CHECK (Id = 1)` | Fila única |
| `CargaId` | uniqueidentifier | Sí | FK → `BaseCarga` | Carga vigente; `NULL` antes de la primera publicación |

### 4.6 `dbo.Lote` — cada copia de un libro de área

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `LoteId` | uniqueidentifier | No | PK | Del manifiesto |
| `AreaId` | tinyint | No | FK → `Area` | Área |
| `ArchivoId` | nvarchar(200) | No | — | `sourceFileId` |
| `VersionFuente` | nvarchar(120) | No | — | `sourceVersion` (ETag) |
| `ModificadoUtc` | datetime2 | No | — | `sourceModifiedUtc` en UTC |
| `Reglas` | varchar(10) | No | — | Versión de reglas (`v1`) |
| `Sha256` | char(64) | No | — | Huella del archivo (`0…0` si superó 10 MiB y no se leyó) |
| `RawPath` | nvarchar(1000) | No | — | Ruta en `raw` |
| `Estado` | varchar(20) | No | `RECIBIDO`, `VALIDADO`, `ACEPTADO`, `RECHAZADO`, `SIN_CAMBIOS`, `OBSOLETO`, `CONFLICTO` | Ver 8.1 |
| `FilasLeidas` | int | No | — | Filas no vacías leídas |
| `FlowRunId` | nvarchar(200) | Sí | — | Ejecución de Power Automate |
| `SolicitadoPor` | nvarchar(200) | Sí | — | Quién pidió la carga |
| `CreadoUtc` | datetime2 | No | `SYSUTCDATETIME()` | Registro del lote |
| `PublicadoUtc` | datetime2 | Sí | — | Solo en lotes `ACEPTADO` |

Índice: `IX_Lote_Area (AreaId, ModificadoUtc)`.

### 4.7 `dbo.Movimiento` — filas válidas de los lotes publicados

Solo se insertan movimientos de lotes que se publican; un lote rechazado no deja filas aquí.

| Columna | Tipo | Nulo | Restricción | Descripción |
|---|---|---|---|---|
| `LoteId` | uniqueidentifier | No | PK (1/2); FK → `Lote` | Lote |
| `MovimientoId` | varchar(50) | No | PK (2/2) | Del Excel |
| `PapeletaId` | varchar(30) | No | Existencia validada al publicar (50106); sin FK porque la base cambia de versión | Del Excel |
| `Tipo` | varchar(12) | No | `PAGO`, `CARGO`, `DESCUENTO`, `OBSERVACION` | Del Excel |
| `Monto` | decimal(18,2) | No | `OBSERVACION` → 0; otros → > 0 | Del Excel |
| `FechaEvento` | date | No | — | Del Excel |
| `Estado` | varchar(8) | No | `ACTIVO`, `ANULADO` | Del Excel |
| `Referencia` | nvarchar(100) | No | — | Del Excel |
| `Detalle` | nvarchar(250) | Sí | — | Del Excel |
| `FilaExcel` | int | No | — | Fila de origen |

Índice: `IX_Mov_Papeleta (PapeletaId)`.

### 4.8 `dbo.Observacion` — errores de validación o de publicación

| Columna | Tipo | Nulo | Restricción | Descripción |
|---|---|---|---|---|
| `ObservacionId` | bigint | No | PK `IDENTITY` | Identificador |
| `LoteId` | uniqueidentifier | No | FK → `Lote` | Lote observado |
| `FilaExcel` | int | Sí | — | Fila del error; `NULL` = observación de archivo |
| `Campo` | nvarchar(50) | No | — | Campo del contrato, `fila` o `archivo` |
| `Codigo` | varchar(40) | No | — | Código de la sección 9 |
| `Mensaje` | nvarchar(500) | No | — | Texto para el área |
| `SubsanadaPor` | uniqueidentifier | Sí | FK → `Lote` | Lote aceptado posterior del área que la subsana (11.9: corregido ≠ oculto; no se borra) |

Índice: `IX_Obs_Lote (LoteId)`.

### 4.9 `dbo.Notificacion` — cola de avisos (12.1)

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `NotificacionId` | bigint | No | PK `IDENTITY` | Identificador |
| `LoteId` | uniqueidentifier | No | FK → `Lote`; `UNIQUE (LoteId, TipoAviso)` | Lote del aviso (un aviso por lote y tipo) |
| `TipoAviso` | varchar(20) | No | — | `ACEPTADO`, `RECHAZADO`, `OBSOLETO` o `CONFLICTO` (no se avisa `SIN_CAMBIOS`) |
| `Estado` | varchar(12) | No | `PENDIENTE` (defecto), `ENVIADO`, `EN_REVISION` | Ver 8.3 |
| `Intentos` | int | No | `0` | Intentos de envío |
| `MensajeId` | nvarchar(200) | Sí | — | Id del mensaje enviado (Outlook/Teams) |
| `CreadaUtc` | datetime2 | No | `SYSUTCDATETIME()` | Alta del aviso |
| `EnviadaUtc` | datetime2 | Sí | — | Envío |

### 4.10 `dbo.ProcesoManifiesto` — control operativo de manifiestos

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `Manifiesto` | nvarchar(300) | No | PK | Nombre del blob (`<LoteId>.json`) |
| `LoteId` | uniqueidentifier | Sí | — | Lote, si se pudo leer |
| `Intentos` | int | No | `0` | Fallos técnicos acumulados |
| `UltimoError` | nvarchar(1000) | Sí | — | Último error técnico o `MANIFIESTO_INVALIDO: …` |
| `ProximoIntentoUtc` | datetime2 | Sí | — | Espera exponencial: 1, 2, 4, 8, 16, 32 y luego 60 minutos |
| `Terminal` | bit | No | `0` | 1 = ya tiene resultado de negocio; no se vuelve a procesar |
| `ActualizadoUtc` | datetime2 | No | `SYSUTCDATETIME()` | Última actualización |

### 4.11 `dbo.CambioPuntero` — auditoría de restauraciones (15.4)

Definida en `003_procedimientos.sql`.

| Columna | Tipo | Nulo | Restricción / valor por defecto | Descripción |
|---|---|---|---|---|
| `CambioId` | bigint | No | PK `IDENTITY` | Identificador |
| `AreaId` | tinyint | No | FK → `Area` | Área |
| `Anterior` | uniqueidentifier | Sí | — | Lote vigente antes del cambio |
| `Nuevo` | uniqueidentifier | No | — | Lote restaurado |
| `Motivo` | nvarchar(500) | No | Al menos 10 caracteres (validado en el procedimiento) | Justificación |
| `Usuario` | sysname | No | `ORIGINAL_LOGIN()` | Quién restauró |
| `FechaUtc` | datetime2 | No | `SYSUTCDATETIME()` | Cuándo |

### 4.12 `dbo.SchemaVersion` — migraciones aplicadas

La crea `tools/aplicar_sql.py`, no los scripts.

| Columna | Tipo | Nulo | Descripción |
|---|---|---|---|
| `Script` | nvarchar(200) | No | PK, p. ej. `hub/004_seguridad.sql` |
| `Sha256` | char(64) | No | Huella del script; si cambia después de aplicado, la herramienta se detiene |
| `AplicadoUtc` | datetime2 | No | Momento de aplicación |

---

## 5. Base HubDeuda: vistas

| Vista | Propósito | Columnas | Consumidores (rol) |
|---|---|---|---|
| `vMovimientoVigente` | Movimientos de los lotes vigentes de cada área | `AreaId, LoteId, MovimientoId, PapeletaId, Tipo, Monto, FechaEvento, Estado, Referencia, Detalle, FilaExcel` | Uso interno de otras vistas y procedimientos (sin permiso directo a roles) |
| `vBaseVigente` | Filas de la base de deuda vigente con su corte | `CargaId, PapeletaId, TipoDoc, Documento, Placa, ImporteOriginal, Activa, CorteUtc` | Function (`rol_hub_integracion`) |
| `vDeuda` | **Saldo consolidado** por papeleta: `Saldo = ImporteOriginal + Σ CARGO − Σ (PAGO + DESCUENTO)` de movimientos `ACTIVO` vigentes. Puede ser negativo (pago en exceso): se muestra y se marca | `PapeletaId, TipoDoc, Documento, DocumentoEnmascarado` (2 primeros + `*` + 2 últimos), `Placa, ImporteOriginal, Movimientos` (decimal 18,2), `Saldo` (decimal 18,2), `RequiereRevision` (bit, 1 si saldo < 0), `Activa, CorteUtc` | App ConsultaDeuda (`rol_hub_consulta`), Power BI (`rol_hub_bi`) |
| `vMovimientoDetalle` | Detalle de movimientos vigentes por papeleta con nombre de área y fecha de publicación (pantalla de detalle y reporte PDF) | `PapeletaId, AreaId, Area, MovimientoId, Tipo, Monto, Estado, FechaEvento, Referencia, LoteId, PublicadoUtc` | `rol_hub_consulta`, `rol_hub_bi` |
| `vEstadoFuentes` | Frescura por fuente. Una fila por área (1–10) y una para la base (`AreaId = 0`, «Base de deuda (origen local)») | `AreaId, Nombre, LoteId` (en la base: `CargaId`), `ModificadoUtc` (en la base: `CorteUtc`), `PublicadoUtc, Estado` (del lote o carga vigente), `UltimaVerificacionUtc` (último lote `ACEPTADO` o `SIN_CAMBIOS`; en la base, `PublicadaUtc`), `UltimoIntentoUtc, UltimoEstado` (último lote o carga, cualquiera sea su estado) | `rol_hub_consulta`, `rol_hub_bi` |
| `vLoteCalidad` | Métricas por lote para Power BI y avisos | `LoteId, AreaId, Area, Estado, FilasLeidas, CreadoUtc, PublicadoUtc, SegundosPublicacion` (int), `Errores` (observaciones del lote), `FilasConError` (filas distintas con error) | `rol_hub_bi`, `rol_hub_avisos` |
| `vObservacionCalidad` | Observaciones con área y marca de subsanada (Power BI) | `ObservacionId, LoteId, AreaId, FilaExcel, Campo, Codigo, CreadoUtc, Subsanada` (bit) | `rol_hub_bi` |
| `vObservaciones01` … `vObservaciones10` | Observaciones de **un solo** área (11.6). Se generan en `004_seguridad.sql` | `ObservacionId, LoteId, FilaExcel, Campo, Codigo, Mensaje, EstadoLote, CreadoUtc, VersionFuente, Subsanada` (bit), `SubsanadaPor` | App Mis observaciones; cada `rol_hub_areaNN` solo ve la suya |

Nota de privacidad: `vDeuda` expone `Documento` completo además de `DocumentoEnmascarado`. La app muestra solo el enmascarado, pero busca por el documento completo; quien tenga `rol_hub_consulta` o `rol_hub_bi` puede leer el documento sin máscara.

---

## 6. Base HubDeuda: procedimientos

| Procedimiento | Lo llama | Qué hace | Errores que lanza |
|---|---|---|---|
| `usp_IniciarBaseCarga @CargaId, @CorteUtc, @FilasEsperadas` | ADF (actividad «Iniciar carga») | Registra la carga en `RECIBIDA` antes de copiar. Idempotente por `CargaId` | 50010 si la carga ya terminó |
| `usp_PublicarBase @CargaId` | ADF («Publicar base») | En transacción con `sp_getapplock('PublicacionHub')`: valida conteo, documentos, que no se omitan papeletas con movimientos y que el corte sea más nuevo; cambia `BaseActual` y marca `ACEPTADA` | 50001–50006 (sección 9.4) |
| `usp_MarcarBaseFallida @CargaId, @Motivo` | ADF (ramas de error) | Marca `FALLIDA` sin tocar el puntero | — |
| `usp_PublicarArea @LoteId` | Function, dentro de su transacción | Valida el lote `VALIDADO` y lo publica: mueve `Area.LoteVigente`, marca `ACEPTADO` y subsana observaciones anteriores del área | 50101–50107 (sección 9.3) |
| `usp_RestaurarLoteVigente @AreaId, @LoteId, @Motivo` | Administrador (manual) | Vuelve a poner como vigente un lote `ACEPTADO` del área, con motivo auditado en `CambioPuntero` | 50201–50204 |

---

## 7. Base de origen BDOrigen (SQL Server Express)

Instancia `localhost\SQLEXPRESS` del PC (on-premise simulado). Scripts `sql/origen/001_deuda_origen.sql` y `002_exportacion.sql`.

| Objeto | Tipo | Columnas / firma | Propósito |
|---|---|---|---|
| `dbo.DeudaOrigen` | Tabla | `PapeletaId` varchar(30) PK, `TipoDoc` varchar(3) (`DNI`/`RUC`), `Documento` varchar(11), `Placa` varchar(10) NULL, `ImporteOriginal` decimal(18,2) ≥ 0, `Activa` bit, `FechaModificacion` datetime2 | Tabla operativa del sistema de origen |
| `dbo.vDeudaExportable` | Vista | `PapeletaId, TipoDoc, Documento, Placa, ImporteOriginal, Activa` | Columnas que se pueden exportar |
| `dbo.ExportControl` | Tabla | `ExportId` uniqueidentifier PK, `CorteUtc` datetime2, `Filas` int, `CreadoUtc` datetime2 | Cabecera de cada exportación (conteo y corte) |
| `dbo.DeudaExport` | Tabla | `ExportId` FK, `PapeletaId`, `TipoDoc`, `Documento`, `Placa`, `ImporteOriginal`, `Activa`; PK (`ExportId`, `PapeletaId`) | Fotografía que copia ADF |
| `dbo.usp_CrearExportacion` | Procedimiento | Devuelve `ExportId, CorteUtc, FilasEsperadas` | Copia `vDeudaExportable` a `DeudaExport` en una transacción `SERIALIZABLE` (conteo, corte y filas de la misma fotografía) y borra exportaciones de más de 7 días |
| `rol_origen_lector` | Rol | `EXECUTE` en `usp_CrearExportacion`, `SELECT` en `DeudaExport` | Lo usa el login `hub_lector` del SHIR; no ve `DeudaOrigen` |

Semilla ficticia (Anexo A):

| PapeletaId | TipoDoc | Documento | Placa | ImporteOriginal | Activa |
|---|---|---|---|---|---|
| P0001 | DNI | 00000001 | ABC123 | 100.00 | 1 |
| P0002 | RUC | 20000000001 | XYZ789 | 250.00 | 1 |
| P0003 | DNI | 00000002 | DEF456 | 80.00 | 1 |

Total base: **430.00**.

---

## 8. Estados

### 8.1 Estados de `Lote`

| Estado | Terminal | Cuándo | Efecto en saldos | Aviso |
|---|---|---|---|---|
| `RECIBIDO` | — | Permitido por el `CHECK`, pero **el código no lo escribe**. El flujo devuelve «RECIBIDO» a la app como respuesta, no como fila en SQL | — | — |
| `VALIDADO` | No | Estado transitorio dentro de la transacción de publicación, antes de `usp_PublicarArea`. Nunca queda confirmado: termina en `ACEPTADO` o se revierte | — | — |
| `ACEPTADO` | Sí | Lote sin errores publicado; pasa a ser el vigente del área | Cambian según el nuevo libro | `ACEPTADO` |
| `RECHAZADO` | Sí | Errores de validación, archivo no autorizado o rechazo del procedimiento de publicación | Ninguno | `RECHAZADO` |
| `SIN_CAMBIOS` | Sí | Mismo SHA-256, mismo archivo y mismas reglas que el vigente | Ninguno | No se avisa |
| `OBSOLETO` | Sí | `sourceModifiedUtc` anterior al del vigente (`VERSION_ANTERIOR`) o `PUBLICACION_50104` | Ninguno | `OBSOLETO` |
| `CONFLICTO` | Sí | Misma fecha que el vigente con otro contenido, o contenido idéntico a una versión aceptada histórica | Ninguno | `CONFLICTO` |

### 8.2 Estados de `BaseCarga`

| Estado | Cuándo | Puntero `BaseActual` |
|---|---|---|
| `RECIBIDA` | `usp_IniciarBaseCarga` registró la carga; la copia está en curso | Sin cambio |
| `ACEPTADA` | `usp_PublicarBase` validó y publicó | Apunta a esta carga |
| `FALLIDA` | Falló la copia o la publicación (`usp_MarcarBaseFallida`) | Sin cambio: sigue la base anterior |

Si el SHIR o el origen no responden, el pipeline falla en «Exportar origen», **antes** de registrar la carga: no se crea fila en `BaseCarga` y `vEstadoFuentes` sigue mostrando el corte anterior.

### 8.3 Estados de `Notificacion`

| Estado | Significado |
|---|---|
| `PENDIENTE` | Creada por la Function; el flujo de avisos aún no la envía |
| `ENVIADO` | Aviso enviado (`MensajeId`, `EnviadaUtc`) |
| `EN_REVISION` | No se pudo enviar tras varios intentos; requiere revisión manual |

El flujo de avisos que consume esta cola aún no está construido.

### 8.4 Resultados del procesador que no son estados de `Lote`

| Resultado | Dónde queda | Significado |
|---|---|---|
| `MANIFIESTO_INVALIDO` | `ProcesoManifiesto` (`Terminal = 1`, `UltimoError`) | El JSON no cumple la sección 3.2; no se crea lote |
| `REINTENTO` | `ProcesoManifiesto` (`Intentos`, `ProximoIntentoUtc`) | Fallo técnico (sin base vigente, raw aún inexistente, bloqueo, red, SQL no disponible). No es terminal y nunca se registra como archivo inválido |

---

## 9. Códigos de observación

### 9.1 Emitidos por el validador (`functions/validacion.py`)

| Código | Nivel | Campo | Causa | Mensaje (resumen) |
|---|---|---|---|---|
| `AREA_DESCONOCIDA` | Archivo | `archivo` | Área fuera de 1–10 | Área desconocida |
| `ARCHIVO_INVALIDO` | Archivo | `archivo` | No es un .xlsx legible, > 10 MiB o > 50 MiB descomprimido (el límite de 10 MiB también lo aplica el procesador antes de descargar) | No se pudo abrir el libro |
| `ESTRUCTURA` | Archivo | `archivo` | Falta la hoja `Datos` o la tabla `tblMovimientos` | Falta la hoja/tabla |
| `ENCABEZADOS` | Archivo | `archivo` | Encabezados distintos o en otro orden | Encabezados u orden distintos al contrato v1 |
| `CARGA_VACIA` | Archivo | `archivo` | Ninguna fila no vacía | La inicialización requiere autorización explícita |
| `FORMULA` | Fila | `fila` | Alguna celda de la fila es fórmula | No se admiten fórmulas |
| `TEXTO_REQUERIDO` | Fila | `MovimientoId`, `PapeletaId`, `Referencia` | Vacío o no es texto (p. ej. número) | Debe ser texto no vacío |
| `LONGITUD` | Fila | `MovimientoId` (50), `PapeletaId` (30), `Referencia` (100), `Detalle` (250) | Excede el máximo | Máximo N caracteres |
| `DUPLICADO` | Fila | `MovimientoId` | Id repetido en el libro | Identificador duplicado |
| `PAPELETA_INEXISTENTE` | Fila | `PapeletaId` | No existe en la base vigente | No existe en la base vigente |
| `TIPO_NO_AUTORIZADO` | Fila | `Tipo` | Tipo distinto de OBSERVACION y del tipo del área | Tipo no autorizado para el área |
| `ESTADO_INVALIDO` | Fila | `Estado` | Distinto de ACTIVO/ANULADO | Use ACTIVO o ANULADO |
| `MONTO_INVALIDO` | Fila | `Monto` | No numérico, > 2 decimales, ≤ 0 en tipos económicos o ≠ 0 en OBSERVACION | PAGO/CARGO/DESCUENTO > 0, OBSERVACION = 0 |
| `REFERENCIA_REPETIDA` | Fila | `Referencia` | Mismo (`Tipo`, `Referencia`) en dos movimientos económicos activos | Operación económica repetida |
| `FECHA_INVALIDA` | Fila | `FechaEvento` | Fecha ilegible o futura (hora de Lima) | Fecha inválida o futura |

### 9.2 Emitidos por la decisión del procesador (`functions/procesador.py`)

Son observaciones de archivo (`FilaExcel` nulo, `Campo = archivo`).

| Código | Estado del lote | Causa |
|---|---|---|
| `ARCHIVO_NO_AUTORIZADO` | `RECHAZADO` | `sourceFileId` distinto de `AreaFuente.ArchivoId` o fuente inactiva |
| `VERSION_ANTERIOR` | `OBSOLETO` | `sourceModifiedUtc` anterior al lote vigente |
| `MISMA_FECHA_OTRO_CONTENIDO` | `CONFLICTO` | Misma fecha de modificación que el vigente, contenido distinto |
| `CONTENIDO_HISTORICO` | `CONFLICTO` | Contenido idéntico a una versión aceptada anterior (requiere revisión; se restaura con `usp_RestaurarLoteVigente`) |

### 9.3 Emitidos al publicar (`PUBLICACION_501xx`)

Cuando `usp_PublicarArea` rechaza el lote, la Function revierte la transacción y registra el lote con **una** observación `PUBLICACION_<número>` y el mensaje de SQL. Son controles de defensa en profundidad: la mayoría ya los cubre el validador.

| Código | Mensaje de SQL | Estado del lote | Cuándo ocurre |
|---|---|---|---|
| `PUBLICACION_50103` | Lote no validado | `RECHAZADO` | El lote no está en `VALIDADO` |
| `PUBLICACION_50104` | Version obsoleta | `OBSOLETO` | Mientras se procesaba, se publicó una versión igual o más nueva del área |
| `PUBLICACION_50105` | Lote con observaciones / Lote vacio no autorizado / Lote incompleto / Tipo no autorizado para el area | `RECHAZADO` | Cuatro comprobaciones comparten el número: observaciones registradas, cero movimientos, `Movimiento` ≠ `FilasLeidas`, tipo ajeno al área |
| `PUBLICACION_50106` | Papeleta inexistente | `RECHAZADO` | La base cambió entre la validación y la publicación y ya no incluye una papeleta |
| `PUBLICACION_50107` | No se permite omitir movimientos anteriores | `RECHAZADO` | El libro nuevo omite un `MovimientoId` del lote vigente (prueba T09). Para quitarlo hay que anularlo |

Los errores `50101` (se requiere transacción) y `50102` (no se obtuvo bloqueo) **no** generan observación: son fallos técnicos y el manifiesto se reintenta con espera exponencial.

### 9.4 Errores de procedimientos que no generan observación

| Número | Procedimiento | Mensaje | Tratamiento |
|---|---|---|---|
| 50001 | `usp_PublicarBase` | No se obtuvo bloqueo | ADF marca `FALLIDA`; se conserva la base anterior |
| 50002 | `usp_PublicarBase` | Carga ausente o vacía | Ídem |
| 50003 | `usp_PublicarBase` | Conteo de origen y destino distinto | Ídem |
| 50004 | `usp_PublicarBase` | Documento inválido (no numérico, o longitud ≠ 8 DNI / 11 RUC) | Ídem |
| 50005 | `usp_PublicarBase` | La base omite deudas con movimientos | Ídem |
| 50006 | `usp_PublicarBase` | Corte obsoleto (no más nuevo que el vigente) | Ídem |
| 50010 | `usp_IniciarBaseCarga` | La carga ya terminó; no se reutiliza su `CargaId` | Falla la actividad |
| 50201–50204 | `usp_RestaurarLoteVigente` | Motivo corto, sin bloqueo, lote no aceptado del área, papeletas fuera de la base vigente | El administrador corrige y repite |

---

## 10. Lista ConfigAreas (SharePoint)

Creada por `tools/provisionar_sharepoint.ps1` en el sitio `IntegracionDeuda`. Es la configuración que leen los flujos; `dbo.AreaFuente` es su espejo en SQL.

| Columna | Tipo SharePoint | Obligatoria | Uso | Espejo en `AreaFuente` |
|---|---|---|---|---|
| `Title` | Texto | Sí | Nombre visible del área | — |
| `AreaId` | Número (0 decimales, 1–10) | Sí | Clave del área | `AreaId` |
| `NombreArea` | Texto | Sí | Nombre del área | — |
| `RutaArchivo` | Texto | Sí | Ruta del libro autorizado | `RutaArchivo` |
| `FileUniqueId` | Texto | Sí | `UniqueId` del libro; el flujo lo usa para leerlo con `GetFileById` | `ArchivoId` |
| `Activa` | Sí/No (defecto Sí) | No | Solo las áreas activas se copian | `Activa` (el script de sincronización hoy fuerza `1`) |
| `ResponsableUPN` | Texto | No | `fl_cargar_ahora` solo permite «Cargar ahora» a esta cuenta | No se sincroniza (queda `NULL`) |
| `VersionContrato` | Texto (defecto `1`) | No | Versión del contrato | No se sincroniza (queda el defecto `'1'`) |
| `DestinoAvisos` | Texto | No | Destino de avisos | No se sincroniza (queda `NULL`) |

Hoy las 10 áreas tienen como `ResponsableUPN` y `DestinoAvisos` la cuenta del responsable del proyecto (`diogo.abregu.g@uni.pe`), porque el script usa la cuenta con sesión iniciada. Hay que reemplazarlas por los responsables reales de cada área.
