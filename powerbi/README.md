# Tablero Power BI · Hub de Deuda

> **Datos ficticios de laboratorio (SI806U).**

Proyecto de Power BI Desktop (PBIP) guardado como texto: el modelo semántico en
**TMDL** y el informe en **PBIR**. Lee las vistas de Azure SQL en modo
**Import** (guía 13.1) y tiene tres páginas: **Resumen**, **Integración** y
**Calidad** (guía 13.4).

```
powerbi/
├── HubDeuda.pbip                      ← abrir este archivo
├── HubDeuda.SemanticModel/
│   ├── definition.pbism
│   ├── .platform
│   └── definition/
│       ├── database.tmdl
│       ├── model.tmdl
│       ├── expressions.tmdl           ← parámetros ServidorSQL y BaseSQL
│       ├── relationships.tmdl
│       └── tables/                    ← Area, vDeuda, vMovimientoDetalle,
│                                        vEstadoFuentes, vLoteCalidad, vObservacionCalidad
└── HubDeuda.Report/
    ├── definition.pbir                ← byPath ../HubDeuda.SemanticModel
    ├── .platform
    └── definition/
        ├── report.json, version.json
        └── pages/ (pages.json, Resumen/, Integracion/, Calidad/ con sus visuals/)
```

## 1. Requisitos

| Requisito | Detalle |
|---|---|
| Power BI Desktop | Versión **2026** (la actual). El informe declara esquemas PBIR de enero de 2026 (`report` 3.1.0, `visualContainer` 2.5.0). Una versión anterior puede negarse a abrirlo. |
| Acceso a la base | Tu cuenta UNI necesita lectura en `HubDeuda`. Si eres el administrador Entra del servidor (quien desplegó `infra/main.bicep`), ya lo tienes. Si no, un administrador ejecuta: `CREATE USER [persona@uni.edu.pe] FROM EXTERNAL PROVIDER; ALTER ROLE rol_hub_bi ADD MEMBER [persona@uni.edu.pe];` (el rol `rol_hub_bi` de `sql/hub/004_seguridad.sql` solo lee estas vistas y `dbo.Area`). |
| Firewall de Azure SQL | Desktop se conecta desde tu PC: su IP pública debe estar en la regla `PcOnPremise`. Si cambió, ejecuta `.\tools\actualizar_ip_pc.ps1`. |

## 2. Abrir el proyecto

1. Power BI Desktop → **Archivo → Abrir** → `D:\hub-deuda-azure\powerbi\HubDeuda.pbip`.
   También puedes abrir `HubDeuda.Report\definition.pbir`.
2. Si Desktop indica que el formato no está habilitado, actívalo en **Archivo → Opciones y configuración → Opciones → Características en versión preliminar**:
   - «Opción de guardado de proyectos de Power BI (.pbip)» (*Power BI Project (.pbip) save option*)
   - «Almacenar el modelo semántico con el formato TMDL» (*Store semantic model using TMDL format*)
   - «Almacenar informes con el formato de metadatos mejorado (PBIR)» (*Store reports using enhanced metadata format (PBIR)*)

   Reinicia Desktop y vuelve a abrir el archivo. En las versiones recientes estas opciones ya no son preliminares y no aparecen.
3. El proyecto **no trae datos**: no se versiona `cache.abf`. Hasta la primera actualización, los visuales salen vacíos o con aviso de error.

## 3. Autenticarse y actualizar

1. **Inicio → Actualizar**. Desktop pide credenciales para `sql-hubdeuda-dev-dg23ne.database.windows.net;HubDeuda`.
2. Elige **Cuenta Microsoft** (*Microsoft account*) → **Iniciar sesión** → cuenta UNI (`...@uni.edu.pe`) → **Conectar**.
   El servidor solo acepta Microsoft Entra: las opciones «Base de datos» (usuario SQL) y «Windows» no funcionan.
3. Si pide nivel de privacidad, elige **Organizacional**.
4. Para cambiar o borrar la credencial: **Archivo → Opciones y configuración → Configuración de origen de datos → Editar permisos / Borrar permisos**.
5. Para apuntar a otro servidor o base: **Inicio → Transformar datos → Editar parámetros** (`ServidorSQL`, `BaseSQL`) y vuelve a actualizar.
6. **Guardar** (Ctrl+S) mantiene el formato PBIP. El `.gitignore` de la raíz ya excluye `**/.pbi/cache.abf` y `**/.pbi/localSettings.json`.

## 4. Publicar

1. **Inicio → Publicar** → **Mi área de trabajo**. Con licencia gratuita es el único destino: sirve para demostrar, no para compartir. Un área de trabajo compartida requiere Pro, PPU o una prueba de Fabric (ver `docs/ACCESOS.md`, 4.2).
2. En Power BI Service: **Mi área de trabajo** → modelo semántico **HubDeuda** → **Configuración** → **Credenciales del origen de datos** → **Editar credenciales** → método **OAuth2** → cuenta UNI.
   No hace falta gateway porque Azure SQL está en la nube. El servicio entra por la regla de firewall `AllowAzureServices` (parámetro `permitirServiciosAzure` del Bicep).
3. Opcional: **Actualización programada** (en capacidad compartida, hasta 8 por día).

## 5. Modelo semántico

Origen M: `Sql.Database(ServidorSQL, BaseSQL)` con navegación a `dbo.<vista>` y `Table.SelectColumns`. La selección se pliega a SQL, así que **la columna `Documento` de `vDeuda` nunca sale de la base**: solo se importa `DocumentoEnmascarado`. La fecha y hora automática está desactivada.

| Tabla | Rol | Notas |
|---|---|---|
| `Area` | Dimensión (AreaId 1..10) | `Nombre` se ordena por `AreaId` |
| `vDeuda` | Hechos de deuda | Una fila por `PapeletaId`. Importes en decimal fijo |
| `vMovimientoDetalle` | Movimientos vigentes | Muchos→uno con `Area` y con `vDeuda` (`PapeletaId`) |
| `vEstadoFuentes` | Frescura por fuente | **Sin relación**: `AreaId 0` (base local) no existe en `Area` y crearía una fila en blanco |
| `vLoteCalidad` | Lotes (carga) | Muchos→uno con `Area`. Columna añadida `FechaCreadoUtc` = fecha UTC de `CreadoUtc` |
| `vObservacionCalidad` | Observaciones (carga) | Muchos→uno con `Area`. **No** se relaciona con `vDeuda` (multiplicaría importes) ni con `vLoteCalidad` (dos caminos desde `Area` serían ambiguos) |

Todas las relaciones filtran en una sola dirección, de la dimensión a los hechos.

**Medidas.** Las de deuda están en la carpeta «Métricas de deuda»; las de carga, en «Métricas de carga».

| Medida | Tabla | Fórmula |
|---|---|---|
| `SaldoTotal` | vDeuda | `SUM(vDeuda[Saldo])` |
| `Papeletas` | vDeuda | `DISTINCTCOUNT(vDeuda[PapeletaId])` |
| `ImporteOriginalTotal`, `MovimientosNetos` | vDeuda | `SUM` de `ImporteOriginal` / `Movimientos` |
| `PapeletasRequierenRevision` | vDeuda | papeletas con `RequiereRevision = TRUE` (saldo negativo) |
| `CorteBaseUtc` | vDeuda | `MAX(vDeuda[CorteUtc])` |
| `CantidadMovimientos`, `MontoMovimientos` | vMovimientoDetalle | `COUNTROWS` / `SUM(Monto)` |
| `Lotes` | vLoteCalidad | `COUNTROWS(vLoteCalidad)` |
| `LotesAceptados`, `LotesRechazados` | vLoteCalidad | `COUNTROWS` con `Estado = "ACEPTADO"` / `"RECHAZADO"` (0 si no hay) |
| `PorcentajeFilasObservadas` | vLoteCalidad | `DIVIDE(SUM(FilasConError), SUM(FilasLeidas))`: filas distintas con error, no errores |
| `Observaciones`, `ObservacionesPendientes` | vObservacionCalidad | `COUNTROWS`; pendientes = `Subsanada = FALSE` |
| `AreasConCargaVigente` | Area | áreas con `LoteVigente` no vacío |

## 6. Páginas

Cada página muestra el texto «Datos ficticios de laboratorio (SI806U)». Las fechas no se convierten a la hora de Lima: son **UTC** y los títulos lo indican.

- **Resumen**: tarjetas de saldo total, papeletas, papeletas con saldo negativo y corte de la base (UTC). Tabla de papeletas con documento enmascarado, importe, movimientos y saldo. Barras de saldo por papeleta.
- **Integración**: tarjetas de áreas con carga vigente, lotes, aceptados y movimientos vigentes. Tabla del estado de cada fuente (base y 10 áreas) con fecha de corte, publicación, última verificación, último intento y último estado, en UTC. Barras de lotes por área y estado, y de movimientos vigentes por área y tipo.
- **Calidad**: segmentador de área. Tarjetas de lotes rechazados, % de filas observadas, observaciones pendientes y observaciones totales. Barras de observaciones por código y por campo. Tabla de lotes. Líneas de evolución diaria de lotes y de observaciones por fecha UTC de `CreadoUtc`.

## 7. Limitaciones y puntos a verificar

- **Generado como texto, sin abrirlo en Desktop.** Todos los JSON se validaron contra los esquemas oficiales de Microsoft (`$schema`). También se comprobó que cada tabla, columna y medida usada en los visuales y en el DAX existe en el TMDL. El TMDL no se pudo validar con el analizador oficial. Al primer guardado, Desktop reescribirá algunos archivos: agrega `diagramLayout.json`, archivos de cultura y el tema base en `StaticResources`, y puede subir las versiones de esquema. Es normal.
- **Tema base.** `report.json` usa el tema integrado `CY25SU12` (`SharedResources`) sin copiar su archivo, como en el ejemplo oficial de la API REST de Fabric. Si Desktop no encuentra el tema, haz esto: crea un informe en blanco, guárdalo como PBIP, copia su carpeta `StaticResources\SharedResources` a `HubDeuda.Report\` y usa los bloques `themeCollection` y `resourcePackages` de su `report.json`.
- **Tarjetas.** Se usa la tarjeta nueva (`cardVisual`); Microsoft marca la tarjeta clásica (`card`) como obsoleta.
- **Diseño.** Las posiciones y tamaños (lienzo de 1280×720) se fijaron a mano; conviene revisarlos al abrir el informe.
- **Sin seguridad por filas (RLS).** Quien vea el modelo publicado ve todas las papeletas, siempre con el documento enmascarado. En «Mi área de trabajo» solo lo ves tú.
- **Licencia gratuita.** No permite compartir, crear apps ni usar áreas de trabajo compartidas.
- La conexión desde Desktop depende de que la IP del PC esté en el firewall de Azure SQL; la del servicio depende de `AllowAzureServices`.
