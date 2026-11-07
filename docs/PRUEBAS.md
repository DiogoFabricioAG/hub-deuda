# Pruebas de aceptación T01–T15 — Hub de Deuda

Documento del paquete de aceptación (sección 14 de la guía): resultados de las pruebas T01–T15. Estado al **7 de noviembre de 2026**. **Todos los datos son ficticios** (base de `BDOrigen`: P0001 = 100.00, P0002 = 250.00, P0003 = 80.00; total 430.00).

Documentos relacionados: [ARQUITECTURA.md](ARQUITECTURA.md) · [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md) · [MATRIZ_PERMISOS.md](MATRIZ_PERMISOS.md) · [DECISIONES.md](DECISIONES.md)

## Resumen

| Entorno | Resultado |
|---|---|
| **Local** (SQL Server Express + pytest) | **14/14 pruebas aprobadas**: T01–T12, casos de calidad de datos y permisos mínimos |
| **Azure** (SharePoint → Power Automate → Blob → Function → Azure SQL) | **T01, T02 y T03 aprobadas**; **T04 verificada con otro libro** (Asesoría Legal); cargo y descuento aceptados con la semilla del anexo (evidencia parcial de T06/T07). **Pendientes:** el resto de T05–T15; **T12** necesita una segunda cuenta UNI y **T13** necesita el SHIR |

---

## 1. Cómo se ejecutan

### 1.1 Local (núcleo: SQL + validador + publicación)

Requiere SQL Server Express (`localhost\SQLEXPRESS`, autenticación de Windows) y Python 3.12.

```powershell
.venv\Scripts\python -m pytest tests -q
```

- Cada prueba recrea `HubDeuda_test` y `BDOrigen_test`, aplica las migraciones, registra los archivos autorizados de las 10 áreas y publica la base inicial (3 papeletas, total 430.00) con `tools/cargar_base_local.py`, que simula `pl_base_completa`. No toca `HubDeuda_dev` ni `BDOrigen`.
- La clase `Hub` de `tests/conftest.py` hace lo mismo que `fl_copia_area`: copia el libro a `raw/` y **después** escribe el manifiesto. Luego llama al mismo `procesador.procesar_pendientes` que ejecuta la Function.
- T12 y los permisos mínimos usan usuarios de base de datos `WITHOUT LOGIN` con `EXECUTE AS USER`.

### 1.2 Azure (circuito completo)

- **Entradas:** cada área edita `Entradas/AreaNN/movimientos.xlsx` en `https://unipe.sharepoint.com/sites/IntegracionDeuda`.
- **Copia:** se dispara con `fl_copia_programada` (13:00 y 18:00, hora de Lima), con `fl_cargar_ahora` (botón «Cargar ahora») o ejecutando a mano el flujo hijo `fl_copia_area`.
- **Proceso:** la Function `func-hubdeuda-dev-dg23ne` procesa los manifiestos con un timer cada minuto.
- **Verificación:** con las consultas de la sección 5 sobre `HubDeuda` en `sql-hubdeuda-dev-dg23ne`, y con las apps ConsultaDeuda y Mis observaciones.
- **Base de deuda:** hoy se carga con `tools/cargar_base_directa_azure.py`, sin SHIR (decisión D14). La ruta definitiva es `pl_base_completa` en `adf-hubdeuda-dev-dg23ne`, a través del runtime `ir-onpremise` (`tools/ejecutar_pipeline_base.ps1`).
- **Reinicio entre corridas completas:** `tools/reiniciar_datos_hub.py --confirmo-borrar-datos-de-prueba`. Vacía **todos** los datos del hub (lotes, movimientos, observaciones, avisos y cargas de base) y los blobs de prueba; conserva el esquema y los roles. Después hay que volver a cargar la base.

---

## 2. Catálogo T01–T15

Los resultados esperados son los de la guía, tal como quedaron codificados en `tests/test_circuito.py`. Los saldos de T02–T10 suponen la secuencia en orden sobre la misma base.

| Id | Caso | Resultado esperado | Cómo se prueba en local | Cómo se prueba en Azure |
|---|---|---|---|---|
| T01 | Base | 3 papeletas en `vDeuda`; total **430.00** | `test_t01_a_t10_secuencia` | Publicar la base (hoy carga directa; definitiva con ADF) y consultar `vDeuda` |
| T02 | Pago | Tesorería paga 30 a P0001: lote `ACEPTADO`; P0001 **70.00**; total **400.00** | Ídem | Fila `TES0001 · P0001 · PAGO · 30 · REC001` en el libro del área 01; copia; consultar `Lote` y `vDeuda` |
| T03 | Duplicado | El mismo archivo otra vez: lote `SIN_CAMBIOS`; P0001 sigue en 70.00; un solo movimiento | Ídem | Dejar el libro sin cambios y esperar la siguiente copia programada (o volver a copiarlo) |
| T04 | Error | Libro con `PAGO −5`: lote `RECHAZADO`, código `MONTO_INVALIDO`, saldo intacto (70.00), aviso `RECHAZADO` en `Notificacion` | Ídem | Agregar una fila con monto inválido; revisar `Observacion` y la app Mis observaciones |
| T05 | Corrección | `TES0001` pasa de 30 a 35 con el mismo `MovimientoId`: `ACEPTADO`; P0001 **65.00**; las observaciones de T04 quedan subsanadas (`SubsanadaPor`), no borradas | Ídem | Corregir la fila y quitar la errónea; copiar |
| T06 | Cargo | Ejecutoría Coactiva (área 02) carga 15: `ACEPTADO`; P0001 **80.00** | Ídem | Fila `CARGO 15` en el libro del área 02 |
| T07 | Descuento | Administración Tributaria (área 07) descuenta 10: `ACEPTADO`; P0001 **70.00**; total **400.00** | Ídem | Fila `DESCUENTO 10` en el libro del área 07 |
| T08 | Anulación | `TES0001` pasa a `ANULADO`: `ACEPTADO`; P0001 **105.00**; total **435.00** | Ídem | Cambiar `Estado` a `ANULADO` en el libro del área 01 |
| T09 | Borrado | Un libro que omite `TES0001` se rechaza (`PUBLICACION_50107`); saldos sin cambio (105.00 / 435.00) | Ídem | Borrar la fila `TES0001` del libro del área 01 |
| T10 | Orden | Una versión anterior a la vigente queda `OBSOLETO`; el puntero del área no cambia | Ídem (manifiesto con fecha de un día antes) | Reenviar el raw de un lote anterior con un manifiesto nuevo que conserve su `sourceModifiedUtc` (script al estilo de `prueba_humo_azure.py`). Restaurar una versión en SharePoint **no** sirve: crea una versión con fecha nueva |
| T11 | Caída | Caída antes del commit: nada escrito, reintento con espera, publicación una sola vez. Caída después del commit: el reintento reconoce el lote terminal y no cambia saldos | `test_t11_caida_antes_y_despues_del_commit` (punto de inyección `antes_commit`) | Escribir un manifiesto antes que su raw: debe quedar `REINTENTO` en `ProcesoManifiesto`; al subir el raw se publica una vez. Volver a dejar un manifiesto ya terminal: no cambia nada |
| T12 | Aislamiento | El área 01 no ve las observaciones del área 02, ni la tabla `Observacion`, ni `vDeuda` (error de permiso) | `test_t12_aislamiento_por_area` | Una segunda cuenta UNI en `rol_hub_area01` abre Mis observaciones: ve su área y recibe error de permiso al elegir el área 02 |
| T13 | SHIR detenido | La carga de la base falla sin dañar nada: `BaseActual` no cambia, los saldos siguen iguales y `vEstadoFuentes` (área 0) muestra el corte anterior | No cubierta (depende de ADF). `test_base_obsoleta_o_incompleta_no_cambia_puntero` cubre que una base fallida no mueve el puntero | Detener el servicio `DIAHostService` y lanzar `pl_base_completa` desde el portal o con `createRun`. `tools/ejecutar_pipeline_base.ps1` no sirve aquí: se niega a ejecutar si el SHIR no está Online |
| T14 | Frescura | La app muestra el corte de la base y el estado de cada fuente; con la base atrasada se ve el corte anterior | No cubierta (depende de Power Apps) | Tras T13, abrir ConsultaDeuda: etiqueta «Corte de la base» y lista «Estado de las fuentes» |
| T15 | Excel modificado durante la copia | `fl_copia_area` termina con `ARCHIVO_MODIFICADO_DURANTE_LECTURA` (ETag distinto) sin escribir raw ni manifiesto; la siguiente copia toma la versión nueva | No cubierta (depende de Power Automate) | En una copia de prueba del flujo, agregar una espera entre `Meta_antes` y `Meta_despues` y editar el Excel durante ella; comprobar que no aparece un blob nuevo en `raw` ni en `manifests` |

---

## 3. Estado y evidencias

Las columnas **LoteId** y **Evidencia** se completan al adjuntar las capturas en `evidencias/` (sección 6). En T01 y T13 el identificador es el `CargaId` de `BaseCarga`.

| Id | Local (pytest) | Azure | Fecha (Azure) | LoteId / CargaId | Evidencia | Observaciones |
|---|---|---|---|---|---|---|
| T01 | Aprobada | **Aprobada:** base con 3 papeletas, total 430.00 | 2026-11-07 | (completar) | `evidencias/T01_base.png` (por adjuntar) | Se cargó **sin SHIR** con `cargar_base_directa_azure.py` (D14). Repetir con `pl_base_completa` cuando el SHIR esté instalado |
| T02 | Aprobada | **Aprobada:** pago de Tesorería de 30 → P0001 70.00, total 400.00, por el circuito SharePoint → Power Automate → Blob → Function → SQL | 2026-11-07 | (completar) | `evidencias/T02_pago.png` (por adjuntar) | — |
| T03 | Aprobada | **Aprobada:** la copia programada de las 13:00 de Lima reenvió el libro de Tesorería sin cambios → lote `SIN_CAMBIOS`, sin duplicar movimientos | 2026-11-07 | (completar) | `evidencias/T03_sin_cambios.png` (por adjuntar) | — |
| T04 | Aprobada | **Comportamiento verificado con otro libro:** libro de Asesoría Legal con `OBSERVACION` de monto 5 → `RECHAZADO`, observación en fila 3, campo `Monto`, código `MONTO_INVALIDO`; saldo de P0002 intacto | 2026-11-07 | (completar) | `evidencias/T04_rechazo.png` (por adjuntar) | El caso literal de la guía (`PAGO −5` en Tesorería) queda opcional; la regla es la misma (`MONTO_INVALIDO`) |
| T05 | Aprobada | Pendiente | — | — | — | — |
| T06 | Aprobada | Pendiente (evidencia parcial) | 2026-11-07 | (completar) | — | Cargo de 15 del área 02 aceptado con la semilla del anexo. Falta la corrida en la secuencia de la guía (P0001 = 80.00 tras T05) |
| T07 | Aprobada | Pendiente (evidencia parcial) | 2026-11-07 | (completar) | — | Descuento de 10 del área 07 aceptado: con el pago de T02 y el cargo, P0001 = **75.00** y total = **405.00** (semilla del anexo) |
| T08 | Aprobada | Pendiente | — | — | — | — |
| T09 | Aprobada | Pendiente | — | — | — | — |
| T10 | Aprobada | Pendiente | — | — | — | Necesita un manifiesto con fecha anterior (ver catálogo) |
| T11 | Aprobada | Pendiente | — | — | — | — |
| T12 | Aprobada (usuarios `WITHOUT LOGIN`) | Pendiente | — | — | — | **Necesita una segunda cuenta UNI.** Con la cuenta del administrador no sirve: es `dbo` y ve todo (MATRIZ_PERMISOS.md, P2) |
| T13 | No cubierta | Pendiente | — | — | — | **Requiere el SHIR** instalado y registrado en `ir-onpremise` |
| T14 | No cubierta | Pendiente | — | — | — | Depende de T13 y de la app ConsultaDeuda |
| T15 | No cubierta | Pendiente | — | — | — | Depende de una variante de prueba de `fl_copia_area` |

---

## 4. Pruebas complementarias

### 4.1 Locales (incluidas en las 14 aprobadas)

| Prueba (pytest) | Qué verifica | Resultado |
|---|---|---|
| `test_circuito.py::test_t01_a_t10_secuencia` | T01–T10 en secuencia | Aprobada |
| `test_circuito.py::test_t11_caida_antes_y_despues_del_commit` | T11 | Aprobada |
| `test_circuito.py::test_t12_aislamiento_por_area` | T12 | Aprobada |
| `test_circuito.py::test_semilla_diez_areas` | Semilla del Anexo A: una fila por área sobre P0001 → P0001 **75.00**, total **405.00**; 10 áreas `ACEPTADO` en `vEstadoFuentes` | Aprobada |
| `test_circuito.py::test_calidad_de_datos` | Un libro con `DUPLICADO`, `PAPELETA_INEXISTENTE`, `TIPO_NO_AUTORIZADO`, `MONTO_INVALIDO`, `REFERENCIA_REPETIDA`, `FECHA_INVALIDA` y `TEXTO_REQUERIDO` se rechaza completo; saldo intacto | Aprobada |
| `test_circuito.py::test_libros_mal_formados` (4 casos) | Encabezados en otro orden (`ENCABEZADOS`), sin tabla (`ESTRUCTURA`), hoja con otro nombre (`ESTRUCTURA`), fórmula en una celda (`FORMULA`) | 4 aprobadas |
| `test_circuito.py::test_archivo_no_autorizado_y_manifiesto_invalido` | `sourceFileId` ajeno → `ARCHIVO_NO_AUTORIZADO`; `rawPath` de otra área → `MANIFIESTO_INVALIDO` sin crear lote | Aprobada |
| `test_circuito.py::test_libro_vacio_requiere_autorizacion` | Libro sin filas → `RECHAZADO` con `CARGA_VACIA` | Aprobada |
| `test_circuito.py::test_base_obsoleta_o_incompleta_no_cambia_puntero` | Una base que omite una papeleta con movimientos se rechaza (50005), queda `FALLIDA` y `BaseActual` no cambia | Aprobada |
| `test_permisos.py::test_procesador_con_permisos_minimos` | El procesador funciona solo con `rol_hub_integracion` (regresión del error 229) | Aprobada |
| `test_permisos.py::test_fallo_tecnico_se_registra_con_permisos_minimos` | Un fallo técnico se registra en `ProcesoManifiesto` con permisos mínimos | Aprobada |

### 4.2 En Azure

| Prueba | Resultado | Fecha |
|---|---|---|
| Prueba de humo `tools/prueba_humo_azure.py` (sube raw y manifiesto sin pasar por Power Automate) | Detectó el error 229 (falta `SELECT` sobre `Notificacion` para `rol_hub_integracion`); se corrigió con la migración `005_permiso_notificacion.sql` y la regresión `test_permisos.py` | 2026-11-07 |
| Semilla del anexo, parcial | Cargo de 15 (área 02) y descuento de 10 (área 07) aceptados → P0001 75.00, total 405.00 | 2026-11-07 |
| Botón «Cargar ahora» (CU04) | Tesorería desde «Mis observaciones» → RECIBIDO, lote `02ff35c9` ACEPTADO en menos de 1 minuto, sin observaciones; P0001 sigue en 75.00 y total 355.00 (incluye `TES0002`, PAGO 50 a P0002). Evidencia `evidencias/2026-11-07_app-observaciones-cargar-ahora-RECIBIDO.jpg` | 2026-11-07 |
| Libro vacío | Las 9 áreas con plantillas vacías quedaron `RECHAZADO` con `CARGA_VACIA`. Es el comportamiento esperado por la regla de la guía (un libro vacío requiere autorización) | 2026-11-07 |

---

## 5. Consultas de verificación

Ejecutar en `HubDeuda` con la cuenta administradora y adjuntar la salida como evidencia.

```sql
-- Saldos y total (T01–T09, semilla)
SELECT PapeletaId, ImporteOriginal, Movimientos, Saldo, RequiereRevision, CorteUtc
FROM dbo.vDeuda ORDER BY PapeletaId;
SELECT COUNT(*) AS Papeletas, SUM(Saldo) AS Total FROM dbo.vDeuda;

-- Últimos lotes con su estado (LoteId para la tabla de la sección 3)
SELECT TOP (20) LoteId, AreaId, Estado, FilasLeidas, ModificadoUtc, CreadoUtc, PublicadoUtc, SolicitadoPor
FROM dbo.Lote ORDER BY CreadoUtc DESC;

-- Observaciones de un lote (T04, T09)
SELECT FilaExcel, Campo, Codigo, Mensaje, SubsanadaPor
FROM dbo.Observacion WHERE LoteId = '<LoteId>';

-- Sin duplicados (T03, T11): movimientos vigentes
SELECT AreaId, COUNT(*) AS Movimientos FROM dbo.vMovimientoVigente GROUP BY AreaId;

-- Frescura (T13, T14)
SELECT AreaId, Nombre, Estado, ModificadoUtc, UltimaVerificacionUtc, UltimoIntentoUtc, UltimoEstado
FROM dbo.vEstadoFuentes ORDER BY AreaId;

-- Cargas de la base (T01, T13)
SELECT CargaId, CorteUtc, Estado, FilasEsperadas, PublicadaUtc, Motivo
FROM dbo.BaseCarga ORDER BY CreadaUtc DESC;

-- Avisos (T04) y reintentos (T11)
SELECT LoteId, TipoAviso, Estado, CreadaUtc FROM dbo.Notificacion ORDER BY CreadaUtc DESC;
SELECT Manifiesto, Intentos, UltimoError, ProximoIntentoUtc, Terminal
FROM dbo.ProcesoManifiesto WHERE Terminal = 0;
```

---

## 6. Convención de evidencias

- **Carpeta:** `evidencias/` en la raíz del repositorio, con copia en la biblioteca **Evidencias** del sitio `IntegracionDeuda`.
- **Nombre:** `TNN_<tema>[_<n>].png`, por ejemplo `T02_pago.png` y `T02_pago_2.png`.
- **Contenido mínimo por prueba:**
  1. el libro de Excel o la acción que dispara la prueba;
  2. la ejecución del flujo o pipeline;
  3. la salida de la consulta SQL de la sección 5, con `LoteId` o `CargaId`;
  4. si aplica, la pantalla de la app.
- **No capturar** claves, cadenas de conexión, tokens, IP públicas ni correos personales. Los datos de negocio son ficticios.
