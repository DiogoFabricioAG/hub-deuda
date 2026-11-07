# Hub de Deuda — implementación Azure + Power Platform

Implementación de la *Guía de implementación de la integración de datos* (SI806U, UNI) a partir del informe `ENTREGRABLE FINAL.docx`. Integra la deuda base de un SQL Server local con los Excel de diez áreas y publica una deuda consolidada en Azure SQL. **Todos los datos son ficticios.**

- **Documento técnico** (cómo está construido, paso a paso, pendientes y enlaces): [docs/DOCUMENTO_TECNICO.md](docs/DOCUMENTO_TECNICO.md)
- **Casos de uso** (CU01–CU11 y cómo se implementa cada uno): [docs/CASOS_DE_USO.md](docs/CASOS_DE_USO.md)
- Accesos y licencias necesarios: [docs/ACCESOS.md](docs/ACCESOS.md)
- Arquitectura (PC, nube de Microsoft y VPS): [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)
- Diccionario de datos, permisos, decisiones y pruebas: [docs/DICCIONARIO_DATOS.md](docs/DICCIONARIO_DATOS.md), [docs/MATRIZ_PERMISOS.md](docs/MATRIZ_PERMISOS.md), [docs/DECISIONES.md](docs/DECISIONES.md), [docs/PRUEBAS.md](docs/PRUEBAS.md)

## Estructura

| Carpeta | Contenido | Estado |
|---|---|---|
| `sql/hub` | Migraciones del hub: esquema, vistas, procedimientos de publicación, roles | Probado en SQL Express |
| `sql/origen` | Base on-premise simulada `BDOrigen` | Probado en SQL Express |
| `functions` | Azure Function Python v2: validador, persistencia idempotente, timer | Probado localmente |
| `tests` | Pruebas T01–T12, calidad y permisos mínimos (pytest) | 14/14 aprobadas |
| `tools` | Migraciones, carga base local (simula ADF), generador de plantillas | — |
| `powerplatform/plantillas` | 10 libros `movimientos.xlsx` (tabla `tblMovimientos`) | Generados |
| `infra`, `adf`, `powerplatform`, `powerbi` | Bicep, pipeline ADF, solución Power Platform, modelo Power BI | Pendiente de accesos |

## Probar el núcleo en local

Requiere SQL Server Express (`localhost\SQLEXPRESS`, autenticación de Windows) y Python 3.12.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r functions\requirements.txt pytest
.venv\Scripts\python -m pytest tests -q
```

Las pruebas recrean `HubDeuda_test` y `BDOrigen_test` en cada caso. Para una base de desarrollo persistente:

```powershell
.venv\Scripts\python tools\aplicar_sql.py --carpeta sql\origen --db BDOrigen --crear --snapshot
.venv\Scripts\python tools\aplicar_sql.py --carpeta sql\hub --db HubDeuda_dev --crear
.venv\Scripts\python tools\cargar_base_local.py --hub HubDeuda_dev
```

## Decisiones de implementación (además de la guía)

- **Transacciones explícitas:** la conexión usa `autocommit=True` con `BEGIN TRAN`/`COMMIT` explícitos, en lugar del modo implícito de ODBC, para que `usp_PublicarArea` vea `@@TRANCOUNT=1` sin transacciones anidadas.
- **Archivo autorizado:** `dbo.AreaFuente` es el espejo controlado de `ConfigAreas`. Un manifiesto cuyo `sourceFileId` no coincide se rechaza con `ARCHIVO_NO_AUTORIZADO`.
- **Reintentos:** `dbo.ProcesoManifiesto` lleva intentos, último error y próximo reintento, con espera exponencial de 1 a 60 minutos. Un fallo técnico nunca se registra como archivo inválido.
- **Observaciones corregidas:** cuando se acepta un lote nuevo del área, sus observaciones anteriores se marcan `SubsanadaPor`; no se borran.
- **Base no cargada:** sin base vigente, el lote espera; no se rechaza como si las papeletas no existieran.
