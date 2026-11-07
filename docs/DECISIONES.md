# Registro de decisiones — Hub de Deuda

Documento del paquete de aceptación (sección 14 de la guía), que pide dejar constancia de las decisiones sobre **saldo, cortes, red y licencias**. Cada decisión indica contexto, decisión, alternativas consideradas y consecuencias, con referencias al código. Todas se registran con fecha **2026-11-07**, día en que se desplegó el hub en Azure.

Responsable del proyecto: `diogo.abregu.g@uni.pe`. Documentos relacionados: [ARQUITECTURA.md](ARQUITECTURA.md) · [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md) · [MATRIZ_PERMISOS.md](MATRIZ_PERMISOS.md) · [PRUEBAS.md](PRUEBAS.md)

## Índice

| Id | Tema | Decisión | Estado |
|---|---|---|---|
| D01 | Licencias / cuenta | Cuenta UNI con suscripción de pago por uso (no había Azure for Students) | Vigente |
| D02 | Plataforma | Región `brazilsouth` | Vigente |
| D03 | Licencias | Power Apps Developer Plan | Vigente |
| D04 | Plataforma / costo | Azure SQL serverless con oferta gratuita y autopausa | Vigente, con riesgo abierto |
| D05 | Plataforma | Azure Functions en Flex Consumption | Vigente |
| D06 | Saldo | Saldo calculado en SQL sobre libros completos por área | Vigente |
| D07 | Cortes | Cortes y orden de versiones por fecha de origen | Vigente |
| D08 | Integridad | Transacciones explícitas en la publicación | Vigente |
| D09 | Cortes | Exportación consistente en `BDOrigen` | Vigente |
| D10 | Seguridad | `UniqueId` de SharePoint como identidad del archivo autorizado | Vigente |
| D11 | Seguridad | Tabla `AreaFuente` como espejo de `ConfigAreas` | Vigente |
| D12 | Operación | Reintentos con espera exponencial | Vigente |
| D13 | Red | Firewall de Azure SQL con «Permitir servicios de Azure» | Vigente (limitación del laboratorio) |
| D14 | Cortes / red | Carga directa temporal de la base sin SHIR | **Temporal** |
| D15 | Power Platform | Apps de lienzo versionadas en `pa.yaml` | Vigente |
| D16 | Power Platform | Flujos creados vía API de Dataverse | Vigente |
| D17 | Licencias | Limitaciones de licencias de Power BI | Vigente |
| D18 | Saldo / cortes | Libro vacío rechazado con `CARGA_VACIA` | Vigente, con pendiente |

---

## D01 · Cuenta UNI y suscripción de pago por uso

**Fecha:** 2026-11-07 · **Tema:** licencias y cuenta

**Contexto.** La guía supone Azure for Students. La cuenta UNI (`diogo.abregu.g@uni.pe`, tenant UNIVERSIDAD NACIONAL DE INGENIERIA) no tenía esa suscripción disponible. SharePoint y Power Platform ya viven en el tenant UNI, y la seguridad del hub depende de que Azure SQL, las identidades administradas, SharePoint y Power Platform compartan el mismo Entra ID.

**Decisión.** Crear una suscripción de **pago por uso** iniciando sesión con la cuenta UNI, para que quede en el tenant UNI. Se fija un presupuesto mensual de **USD 20** con alertas al 50, 80 y 100 % (`budget-hubdeuda-dev` en `infra/main.bicep`).

**Alternativas consideradas.**
- *Azure for Students con una cuenta personal:* daría crédito gratuito, pero en otro tenant. Los usuarios UNI tendrían que entrar como invitados en Azure SQL y las conexiones de Power Platform cruzarían tenants.
- *Cuenta gratuita personal con USD 200:* mismo problema de tenant y vence a los 30 días.
- *Esperar a que la UNI habilite Azure for Students:* bloqueaba la implementación sin fecha.

**Consecuencias.**
- Los cargos son reales y van a la tarjeta. Estimación de [ACCESOS.md](ACCESOS.md): del orden de USD 10 al mes.
- Las alertas de presupuesto **no detienen** recursos: al terminar el curso hay que detener `tr_base_programada`, apagar los flujos y eliminar `rg-hubdeuda-dev`.
- Desaparece la restricción de regiones de Azure for Students (ver D02).

**Referencias:** `docs/ACCESOS.md`, `infra/main.bicep` (presupuesto).

---

## D02 · Región `brazilsouth`

**Fecha:** 2026-11-07 · **Tema:** plataforma

**Contexto.** Los usuarios y el PC on-premise están en Lima. El entorno Developer de Power Platform quedó en la región de Sudamérica (`org2535ee74.crm2.dynamics.com`). Todos los servicios usados tenían que estar disponibles en la región elegida: Azure SQL con oferta gratuita serverless, Functions Flex Consumption, Data Factory, Key Vault y Application Insights.

**Decisión.** Desplegar todo `rg-hubdeuda-dev` en **`brazilsouth`** (parámetro `location` de `infra/dev.parameters.local.json`). El despliegue Bicep terminó con estado `Succeeded` el 2026-11-07, con todos los recursos en esa región.

**Alternativas consideradas.**
- *Regiones de EE. UU. (`eastus2`, `southcentralus`):* precios por unidad algo menores y catálogo más amplio, pero mayor latencia desde Lima y datos fuera de la geografía del entorno de Power Platform.
- *Región más cercana a Lima de lanzamiento reciente:* no se verificó que ofreciera todos los servicios y ofertas anteriores; se prefirió una región consolidada.

**Consecuencias.**
- Latencia menor hacia Lima que desde EE. UU., y Azure y Power Platform en la misma geografía.
- Los precios en Brasil suelen ser algo mayores que en EE. UU.; con este volumen la diferencia es marginal.
- El SHIR del PC se conecta hacia `brazilsouth` (ADF por 443 y Azure SQL por 1433).

**Referencias:** `infra/main.bicep` (`param location`), `infra/despliegue.local.log`.

---

## D03 · Power Apps Developer Plan

**Fecha:** 2026-11-07 · **Tema:** licencias

**Contexto.** Los flujos y las apps usan conectores **Premium** (SQL Server y Azure Blob) y Dataverse para la solución. Las licencias de Microsoft 365 de la UNI no incluyen conectores Premium.

**Decisión.** Usar el **Power Apps Developer Plan** gratuito de la cuenta UNI. Entorno: `https://org2535ee74.crm2.dynamics.com/`, solución `HubDeuda`, publicador `hubdeuda` (prefijo `hd`).

**Alternativas consideradas.**
- *Prueba de Power Apps Premium de 30 días:* vence antes de cerrar el curso; queda como respaldo si la UNI bloquea el autoservicio.
- *Licencias Premium por usuario:* costo mensual por persona; innecesario para un laboratorio.
- *Entorno predeterminado del tenant UNI:* no admite conectores Premium sin licencia y lo comparte toda la universidad.

**Consecuencias.**
- Solo el dueño del plan (Diogo) puede ejecutar las apps y flujos Premium. Alcanza para construir y presentar, no para un uso real por las áreas.
- Las apps no se pueden compartir con correctores ni ventanilla sin que cada uno tenga su Developer Plan o una licencia. Esto condiciona la prueba **T12** con una segunda cuenta (ver PRUEBAS.md).
- Los flujos corren con las conexiones de Diogo (ver MATRIZ_PERMISOS.md, I5).

**Referencias:** `docs/ACCESOS.md` (sección 3), `tools/powerplatform.py`.

---

## D04 · Azure SQL serverless con oferta gratuita y autopausa

**Fecha:** 2026-11-07 · **Tema:** plataforma y costo

**Contexto.** El hub necesita una base relacional con transacciones, bloqueos de aplicación (`sp_getapplock`) y autenticación de Entra, con un costo cercano a cero.

**Decisión.** Base `HubDeuda` en el servidor `sql-hubdeuda-dev-dg23ne`, SKU **`GP_S_Gen5_2`** (General Purpose serverless) con **oferta gratuita** (`useFreeLimit: true`), **autopausa al agotar el límite** (`freeLimitExhaustionBehavior: AutoPause`), retraso de autopausa de 60 minutos, mínimo de 0.5 vCore y respaldo con redundancia local. Solo autenticación de Entra.

**Alternativas consideradas.**
- *Basic (DTU 5):* unos USD 5 al mes fijos, sin pausa; menos capacidad.
- *Serverless sin oferta gratuita:* se paga cada segundo activo.
- *SQL Server en una VM:* costo y mantenimiento mayores; no aporta al objetivo del curso.
- *Comportamiento `BillOverUsage` al agotar el límite:* el hub seguiría funcionando, pero con cargos.

**Consecuencias.**
- Cuando la base está pausada, la primera conexión tarda en reanudarla. La Function lo absorbe con reintentos (D12); ADF tiene reintentos en «Exportar origen» e «Iniciar carga»; la app puede necesitar «Actualizar».
- Si se agota la concesión mensual gratuita, la base **se pausa hasta el mes siguiente** y el hub deja de funcionar (los manifiestos quedan en reintento y no se pierden).
- **Riesgo detectado y corregido el 7 nov 2026.** La oferta gratuita da 100 000 vCore-segundos al mes; con un mínimo de 0.5 vCore se agota tras unas 55 horas encendida. La métrica `connection_successful` mostraba 1 conexión por minuto: el timer de la Function consultaba `ProcesoManifiesto` en cada ejecución porque los manifiestos nunca se borran, y la base no llegaba a pausarse (consumo de 2 días para agotar la concesión).
  - **Corrección:** la Function guarda el estado de cada manifiesto en sus **metadatos de Blob** (`hd_estado=terminal` con `hd_resultado`, o `hd_proximo` con la hora del próximo reintento) y **no abre SQL si no hay manifiestos nuevos o vencidos**. Los manifiestos se conservan para auditoría. La primera ejecución marcó los 14 manifiestos previos con una sola consulta.
  - **Permiso:** *Storage Blob Data Contributor* de la identidad de la Function solo sobre el contenedor `manifests`; en el resto de la cuenta sigue con lectura.
  - **Data Factory:** el disparador horario se reemplazó por `tr_base_programada` (12:55 y 17:55, antes de las cargas de Excel), para compartir la misma ventana de base encendida.
  - **Límite que queda:** Azure no permite bajar el retraso de autopausa de 60 minutos con `AutoPause` al agotar; cada ventana de carga mantiene la base unos 60 minutos encendida. Dos ventanas al día quedan cerca del límite mensual; vigilar `free_amount_remaining`. Alternativa si no alcanza: `BillOverUsage` con pausa de 15 minutos (consume menos, pero factura el excedente).
  - **Pruebas:** `tests/test_sin_consultas.py` verifica 0 conexiones SQL sin trabajo, el marcado de manifiestos previos y la espera de reintento leída del blob.

**Referencias:** `infra/main.bicep` (`hubDb`, `funcMarcaManifiestos`), `functions/procesador.py` (`procesar_pendientes`), `functions/almacenamiento.py`, `functions/function_app.py` (timer `0 * * * * *`), `adf/trigger/tr_base_programada.json`.

---

## D05 · Azure Functions en Flex Consumption

**Fecha:** 2026-11-07 · **Tema:** plataforma

**Contexto.** La validación y publicación de los Excel corre en Python 3.12 con `openpyxl` y `pyodbc`. Se quería un plan sin servidor, sin claves de almacenamiento y con identidad administrada.

**Decisión.** Function App Linux `func-hubdeuda-dev-dg23ne` en el plan **Flex Consumption** (`asp-hubdeuda-dev`, SKU FC1), Python 3.12, memoria de instancia de 2048 MB. `AzureWebJobsStorage` se conecta por identidad (`AzureWebJobsStorage__accountName`) y el paquete se despliega en el contenedor `deploy` con la identidad del sistema. La cuenta de runtime (`sthubfuncdevdg23ne`) va separada de la de negocio y tiene las claves compartidas deshabilitadas.

**Alternativas consideradas.**
- *Consumo clásico en Linux (Y1):* necesita una cadena de conexión con clave para el contenido. Además, Microsoft recomienda Flex Consumption para las nuevas apps Linux sin servidor.
- *Premium (EP1):* instancias siempre activas e integración de red, pero con un costo mensual fijo alto para un laboratorio.
- *Container Apps o App Service:* más configuración y costo fijo.

**Consecuencias.**
- No hay secretos: Storage y SQL se acceden por identidad administrada (ver MATRIZ_PERMISOS.md, I2).
- Sin integración con una red virtual, la Function no tiene IP de salida fija, lo que obliga a la decisión D13.
- El timer cada minuto genera unas 43 200 ejecuciones al mes. Hay que confirmar en la factura que quedan dentro de la concesión gratuita del plan, y además mantiene viva la base SQL (D04).
- El timer se ejecuta en una sola instancia, así que el máximo de 40 instancias no influye. `functionTimeout` es de 5 minutos.

**Referencias:** `infra/main.bicep` (`plan`, `func`, `runtime`), `functions/host.json`, `functions/requirements.txt`.

---

## D06 · Regla de saldo

**Fecha:** 2026-11-07 · **Tema:** saldo

**Contexto.** La guía (2.2) define el saldo como el importe original de la base más los movimientos de las áreas. Cada área entrega un libro que puede corregirse, reenviarse o llegar duplicado. Hay que impedir la doble contabilización y mantener la historia.

**Decisión.**
- `Saldo = ImporteOriginal + Σ CARGO − Σ (PAGO + DESCUENTO)`, sumando solo movimientos `ACTIVO` del **lote vigente** de cada área. `OBSERVACION` tiene monto 0 y `ANULADO` no suma.
- El saldo **no se almacena**: lo calcula la vista `dbo.vDeuda` en cada consulta, y las apps y Power BI lo leen de ahí, sin recalcularlo.
- Cada libro es la fotografía completa del área. La corrección conserva el `MovimientoId`; quitar un movimiento exige anularlo, porque omitirlo se rechaza (`PUBLICACION_50107`).
- Un saldo negativo (pago en exceso) **se muestra**, con `RequiereRevision = 1`; no se oculta ni se trunca a cero.

**Alternativas consideradas.**
- *Tabla de saldos actualizada en cada carga:* un reintento o una caída a mitad de proceso podría duplicar o perder ajustes.
- *Libros de novedades (solo movimientos nuevos):* un reenvío duplicaría importes y obligaría a controlar qué se cargó.
- *Calcular el saldo en Power Apps o Power BI:* dos fórmulas que pueden divergir.

**Consecuencias.**
- Reprocesar no cambia saldos: un archivo idéntico queda `SIN_CAMBIOS` (T03) y un manifiesto repetido tras el commit se reconoce como terminal (T11).
- Cambiar el puntero de un área, incluso al restaurar un lote con `usp_RestaurarLoteVigente`, actualiza el saldo al instante.
- Un área no puede «limpiar» su libro: la historia queda en `Movimiento`, `Lote` y `Observacion`.

**Referencias:** `sql/hub/002_vistas.sql` (`vDeuda`), `sql/hub/003_procedimientos.sql` (`usp_PublicarArea`), `tests/test_circuito.py` (T02–T09).

---

## D07 · Cortes y orden de versiones

**Fecha:** 2026-11-07 · **Tema:** cortes

**Contexto.** Hay dos fuentes con ritmos distintos: la base del origen local (la guía propone copia cada hora; se hace a las 12:55 y 17:55, ver D04), y los libros de las áreas, con copias a las 13:00 y 18:00 de Lima y bajo demanda. Las versiones pueden llegar desordenadas y el usuario debe saber de qué hora son los datos.

**Decisión.**
- **Base:** cada carga es una fotografía con `CorteUtc`, el momento de la exportación en el origen. `usp_PublicarBase` solo publica si el corte es **más nuevo** que el vigente (50006), si el conteo coincide (50003), si los documentos son válidos (50004) y si no faltan papeletas con movimientos vigentes (50005). Si algo falla, la carga queda `FALLIDA` y `BaseActual` no cambia.
- **Áreas:** el orden lo da `sourceModifiedUtc`, el `TimeLastModified` del archivo en SharePoint, no la hora de proceso.
  - Una versión anterior a la vigente queda `OBSOLETO` (T10).
  - Una versión con la misma fecha y otro contenido queda `CONFLICTO`.
  - Un contenido idéntico a una versión histórica también queda `CONFLICTO`, y se restaura de forma explícita con motivo (`usp_RestaurarLoteVigente`).
- **Horarios:** copia programada a las 13:00 y 18:00 (zona `SA Pacific Standard Time`), botón «Cargar ahora» y ADF a las 12:55 y 17:55. El disparador `tr_base_programada` se crea detenido y solo se activa tras una ejecución exitosa (8.6).
- **Frescura visible:** `vEstadoFuentes` expone, por área y para la base (`AreaId = 0`), la versión vigente, la última verificación y el último intento. La app ConsultaDeuda muestra el «Corte de la base».
- Las marcas de tiempo se guardan en UTC. `FechaEvento` se valida contra la fecha de Lima.

**Alternativas consideradas.**
- *Última en procesarse gana:* dos copias cercanas podrían dejar vigente la más antigua.
- *Ordenar por `UIVersionLabel` de SharePoint:* depende del historial de versiones y de restauraciones manuales.
- *Base incremental (solo cambios):* más difícil de validar por conteo y de reconstruir.

**Consecuencias.**
- Una caída del origen nunca deja una base a medias. Se sigue mostrando la última base válida con su corte (T13, T14).
- Si el SHIR no responde, el pipeline falla en «Exportar origen», antes de crear la fila en `BaseCarga`. Por eso `vEstadoFuentes` muestra el corte atrasado, pero **no** un último intento fallido de la base.
- La app muestra las horas en UTC (con la etiqueta «UTC»). Conviene evaluar convertirlas a la hora de Lima.

**Referencias:** `sql/hub/003_procedimientos.sql`, `functions/procesador.py` (`decidir`), `sql/hub/002_vistas.sql` (`vEstadoFuentes`), `powerplatform/flows/fl_copia_programada.json`, `adf/trigger/tr_base_programada.json`.

---

## D08 · Transacciones explícitas

**Fecha:** 2026-11-07 · **Tema:** integridad

**Contexto.** El lote, sus movimientos, la publicación, el aviso y la marca del manifiesto deben confirmarse juntos o no confirmarse (Anexo C, C2–C5). `pyodbc` con `autocommit=False` usa transacciones implícitas de ODBC, con las que `@@TRANCOUNT` dentro del procedimiento no es predecible.

**Decisión.** La conexión usa `autocommit=True` y el procesador abre y cierra la transacción con `SET XACT_ABORT ON; BEGIN TRAN` y `COMMIT`/`ROLLBACK` explícitos. Dentro de ella toma `sp_getapplock('PublicacionHub')`. `usp_PublicarArea` **exige** una transacción abierta (50101) y no abre otra.

**Alternativas consideradas.**
- *Modo implícito de ODBC (`autocommit=False`):* el procedimiento podría quedar anidado y un `ROLLBACK` interno desharía más de lo esperado.
- *Que el procedimiento abra su propia transacción:* la inserción del lote y de los movimientos quedaría fuera de la unidad atómica.

**Consecuencias.**
- Una caída antes del commit no deja nada escrito, y el siguiente intento completa la operación una sola vez (T11).
- Las publicaciones de áreas y de la base se serializan con el mismo bloqueo `PublicacionHub`.
- Toda herramienta que llame a `usp_PublicarArea` debe abrir la transacción.

**Referencias:** `functions/sqlconn.py`, `functions/procesador.py`, `README.md` (decisiones de implementación).

---

## D09 · Exportación consistente en BDOrigen

**Fecha:** 2026-11-07 · **Tema:** cortes

**Contexto.** ADF necesita el conteo, el corte y las filas de la **misma** fotografía (8.4, 8.7). Si cuenta en una consulta y copia en otra, un cambio intermedio en el origen hace fallar la validación de conteo o publica una base incoherente.

**Decisión.** `usp_CrearExportacion` copia `vDeudaExportable` a `DeudaExport` dentro de una transacción `SERIALIZABLE`, registra `ExportControl` (`ExportId`, `CorteUtc`, `Filas`) y devuelve esos datos. ADF copia solo las filas de ese `ExportId`. El lector `hub_lector` puede ejecutar el procedimiento y leer `DeudaExport`, pero no ve `DeudaOrigen`. Las exportaciones de más de 7 días se borran.

**Alternativas consideradas.**
- *Copiar directamente de `DeudaOrigen` con un conteo aparte:* conteo y copia de momentos distintos.
- *Leer con aislamiento SNAPSHOT en ADF:* la búsqueda (Lookup) y la copia (Copy) usan conexiones distintas, así que no comparten la instantánea.
- *Change Tracking o CDC:* sobredimensionado para tres papeletas y una copia completa.

**Consecuencias.**
- La base publicada siempre corresponde a un corte coherente: la comprobación de conteo de `usp_PublicarBase` (50003) solo falla por errores reales de copia.
- El origen recibe escrituras propias de la integración (tablas de exportación); la retención de 7 días acota su tamaño.
- Hay una incoherencia menor de documentación: el comentario de `001_deuda_origen.sql` dice «aislamiento SNAPSHOT», y `aplicar_sql.py --snapshot` lo habilita, pero el procedimiento usa `SERIALIZABLE`.

**Referencias:** `sql/origen/002_exportacion.sql`, `adf/pipeline/pl_base_completa.json`, `tools/cargar_base_local.py`.

---

## D10 · `UniqueId` de SharePoint como archivo autorizado

**Fecha:** 2026-11-07 · **Tema:** seguridad

**Contexto.** Hay que garantizar que cada área cargue **su** libro controlado y no otro archivo con el mismo nombre o colocado en otra carpeta.

**Decisión.** El archivo autorizado de cada área se identifica por su **`UniqueId`** de SharePoint, en minúsculas. `ConfigAreas.FileUniqueId` lo guarda y el flujo lee el libro con `GetFileById`. El manifiesto lleva `sourceFileId = UniqueId` y la Function lo compara con `AreaFuente.ArchivoId`; si no coincide, el lote se rechaza con `ARCHIVO_NO_AUTORIZADO`.

**Alternativas consideradas.**
- *Ruta del archivo:* cambia al renombrar o mover, y basta borrar y subir otro archivo con el mismo nombre para suplantarlo.
- *Id del elemento de la lista o id de Graph:* también es estable, pero es menos directo con la API REST de SharePoint que usa el flujo.

**Consecuencias.**
- Renombrar o mover el libro no rompe la carga. **Reemplazarlo** (borrar y subir) cambia el `UniqueId`, y el área queda rechazada hasta actualizar `ConfigAreas` y `AreaFuente`.
- La comparación no distingue mayúsculas: el flujo convierte a minúsculas y la Function también.

**Referencias:** `powerplatform/flows/fl_copia_area.json`, `functions/procesador.py` (`decidir`), `tools/provisionar_sharepoint.ps1`.

---

## D11 · Tabla `AreaFuente`

**Fecha:** 2026-11-07 · **Tema:** seguridad

**Contexto.** La Function debe validar el archivo autorizado sin depender de SharePoint, y sin que un manifiesto mal formado o malicioso le haga confiar en el flujo.

**Decisión.** Crear `dbo.AreaFuente` como **espejo controlado** de `ConfigAreas` en SQL. La llena `tools/sincronizar_areafuente.py` a partir de `infra/sharepoint.local.json`, generado al aprovisionar SharePoint. La Function solo lee esta tabla.

**Alternativas consideradas.**
- *Que la Function lea `ConfigAreas` por Microsoft Graph:* requiere permisos de aplicación (`Sites.Selected`) con consentimiento de administrador en el tenant UNI, poco probable de obtener.
- *Confiar en el flujo:* cualquiera con escritura en `manifests` podría hacer pasar otro archivo como autorizado.

**Consecuencias.**
- Defensa en profundidad: el flujo y la Function comprueban cada uno, de forma independiente, que el archivo sea el autorizado.
- La sincronización es **manual** y puede desfasarse si se edita `ConfigAreas` sin volver a ejecutar el script.
- **Pendiente:** el script copia solo `ArchivoId`, `RutaArchivo` y `Activa`, esta última siempre en 1. `ResponsableUPN`, `DestinoAvisos` y `VersionContrato` quedan sin sincronizar, aunque el flujo de avisos los necesitará.

**Referencias:** `sql/hub/001_esquema.sql`, `tools/sincronizar_areafuente.py`, `functions/repositorio_sql.py` (`contexto_area`).

---

## D12 · Reintentos con espera exponencial

**Fecha:** 2026-11-07 · **Tema:** operación

**Contexto.** La guía (10) separa los fallos técnicos (red, bloqueo, base pausada, raw que aún no llega, base de deuda no cargada) de los resultados de negocio (archivo inválido). Un fallo técnico nunca debe registrarse como archivo inválido ni bloquear a otras áreas.

**Decisión.** `dbo.ProcesoManifiesto` lleva por manifiesto los intentos, el último error, el próximo reintento y la marca de terminal. Ante un fallo técnico (`ErrorTecnico` o cualquier excepción que no sea de negocio) se programa el siguiente intento con espera de 1, 2, 4, 8, 16 y 32 minutos, y luego cada 60 minutos. Los resultados de negocio (`ACEPTADO`, `RECHAZADO`, `SIN_CAMBIOS`, `OBSOLETO`, `CONFLICTO`, `MANIFIESTO_INVALIDO`) son terminales. Cada manifiesto se procesa aislado y hasta 20 por ejecución.

**Alternativas consideradas.**
- *Cola de Storage con mensajes envenenados:* añade un componente y otro permiso de escritura.
- *Durable Functions:* más complejidad para un flujo corto.
- *Reintentar sin espera:* martillea SQL cuando la base está pausada o sin base vigente.

**Consecuencias.**
- Sin base vigente, los lotes **esperan** en vez de rechazarse como si las papeletas no existieran.
- No hay un máximo de intentos: un fallo persistente se reintenta cada hora hasta corregirse, y queda visible en `UltimoError`.
- Ver D04: el sondeo por minuto también consulta SQL.

**Referencias:** `functions/repositorio_sql.py` (`registrar_fallo_tecnico`, `manifiestos_omitidos`), `functions/procesador.py`, `tests/test_circuito.py` (T11), `tests/test_permisos.py`.

---

## D13 · Firewall de Azure SQL con «Permitir servicios de Azure»

**Fecha:** 2026-11-07 · **Tema:** red

**Contexto.** A Azure SQL se conectan cuatro orígenes:
- la Function (Flex Consumption sin red virtual, sin IP de salida fija);
- los conectores de Power Platform, con rangos de IP amplios y cambiantes;
- ADF;
- el PC (herramientas y SHIR), con IP pública dinámica.

En el laboratorio no hay red virtual, puntos de conexión privados ni IP de salida fija. El origen local nunca debe exponerse a Internet.

**Decisión.**
- Habilitar en el firewall la regla **`AllowAzureServices`** (0.0.0.0, «Permitir servicios de Azure»), parámetro `permitirServiciosAzure = true`.
- Agregar la regla **`PcOnPremise`** con la IP pública del PC, que se actualiza con `tools/actualizar_ip_pc.ps1`.
- El SHIR solo abre conexiones **salientes**: 443 hacia ADF y 1433 hacia Azure SQL. No se abren puertos de entrada en el PC.

**Alternativas consideradas.**
- *Red virtual con punto de conexión privado para SQL e integración de red de la Function:* es lo correcto en producción, pero suma costo y complejidad, y los conectores de Power Platform no llegarían sin una puerta de enlace de datos o una red virtual de Power Platform.
- *Reglas por rangos de IP de Power Platform y Functions:* decenas de rangos que cambian y que el firewall de Azure SQL no admite como etiquetas de servicio.

**Consecuencias.**
- La regla admite conexiones de red desde **cualquier** servicio de Azure, incluso de otros clientes. La protección queda en la autenticación solo con Entra, TLS 1.2 y los roles de mínimo privilegio (MATRIZ_PERMISOS.md).
- La IP del PC cambia; si las herramientas o el SHIR fallan con un error de firewall, hay que ejecutar `tools/actualizar_ip_pc.ps1`.
- El Storage de negocio también queda con acceso público de red, porque el conector Azure Blob no admite cuentas detrás de firewall (M07).

**Referencias:** `infra/main.bicep` (`fwAzure`, `fwPc`), `tools/actualizar_ip_pc.ps1`, `adf/linkedService/ls_sql_origen.json`.

---

## D14 · Carga directa temporal de la base sin SHIR

**Fecha:** 2026-11-07 · **Tema:** cortes y red · **Estado:** temporal

**Contexto.** La instalación del SHIR requiere:
- descargar el instalador oficial;
- ejecutar `tools/instalar_shir.ps1` como administrador;
- cambiar SQL Express a autenticación mixta.

Mientras tanto, la Function rechazaría o dejaría en espera todos los lotes, porque no habría base vigente.

**Decisión.** Publicar la base ficticia de `BDOrigen` en Azure SQL con `tools/cargar_base_directa_azure.py`. El script usa **los mismos procedimientos** que ADF (`usp_CrearExportacion` → `usp_IniciarBaseCarga` → `BaseFila` → `usp_PublicarBase`, y `usp_MarcarBaseFallida` si falla), pero se conecta desde el PC con la cuenta del administrador, sin pasar por el SHIR.

**Alternativas consideradas.**
- *Esperar al SHIR:* bloqueaba las pruebas T01–T04 del circuito SharePoint → Function.
- *Insertar la base a mano en SQL:* se saltaría las validaciones de publicación.

**Consecuencias.**
- La prueba **T01** en Azure (3 papeletas, total 430.00) se hizo por esta vía; **no** demuestra la ruta on-premise (la guía lo advierte en 8.6).
- Cuando ADF cargue la base, su corte será posterior y la reemplazará sin conflicto.
- **T13** (SHIR detenido) y la activación de `tr_base_programada` siguen pendientes de instalar el SHIR.

**Referencias:** `tools/cargar_base_directa_azure.py`, `tools/instalar_shir.ps1`, `tools/ejecutar_pipeline_base.ps1`.

---

## D15 · Apps de lienzo versionadas en `pa.yaml`

**Fecha:** 2026-11-07 · **Tema:** Power Platform

**Contexto.** La guía pide entregar la solución de Power Platform. Una app de lienzo editada solo en Power Apps Studio es un binario (`.msapp`) que no se puede revisar en Git.

**Decisión.** Mantener las apps **ConsultaDeuda** y **Mis observaciones** como código fuente `pa.yaml` (`powerplatform/apps/<App>/Src/`). `tools/publicar_apps.ps1` empaqueta cada app con `pac canvas pack`, exporta la solución `HubDeuda`, reemplaza los `.msapp` dentro del zip, la vuelve a importar y publica. Se conservan los originales (`*_original.msapr`).

**Alternativas consideradas.**
- *Editar solo en Studio y exportar la solución:* sin diferencias legibles.
- *Integración de Git de Power Platform:* en vista previa y dependiente de la configuración del entorno.

**Consecuencias.**
- Los cambios de pantalla se revisan como texto y quedan en el repositorio.
- Microsoft indica que el YAML de las apps de lienzo sirve para revisar y para ediciones menores (vista previa). Lo que se cambie en Studio debe volver al `pa.yaml`, o se pierde en la siguiente publicación.
- El zip de la solución exportada no se versiona (`tests/_out/` está ignorado): para el paquete de entrega hay que exportarlo aparte.

**Referencias:** `powerplatform/apps/*/Src/*.pa.yaml`, `tools/publicar_apps.ps1`.

---

## D16 · Flujos creados vía API de Dataverse

**Fecha:** 2026-11-07 · **Tema:** Power Platform

**Contexto.** Los flujos `fl_copia_area`, `fl_copia_programada` y `fl_cargar_ahora` tenían que quedar versionados y desplegarse de forma repetible dentro de la solución. Las conexiones OAuth no pueden crearse sin el consentimiento del usuario.

**Decisión.** Guardar la definición de cada flujo como JSON en `powerplatform/flows/`, con los marcadores `__SITE__`, `__STORAGE__` y `__CHILD_ID__`. Desplegarla con `tools/powerplatform.py`, que usa la **API web de Dataverse** con el token de `az login` y hace lo siguiente:
- crea el publicador y la solución;
- crea las referencias de conexión `hd_*`;
- crea o actualiza los flujos (entidad `workflows`, categoría 5) apagados, primero el hijo para obtener su id;
- después de que el usuario crea las conexiones, las enlaza (`enlazar`) y enciende los flujos (`activar`).

**Alternativas consideradas.**
- *Construir los flujos a mano en el portal:* no son repetibles ni revisables.
- *`pac solution pack`/`import` de una solución desempaquetada:* más archivos generados y menos control sobre cada flujo.
- *Logic Apps en Azure:* otro servicio, otro costo, y no es lo que pide la guía.

**Consecuencias.**
- El repositorio es la fuente de verdad. Un cambio hecho en el portal debe llevarse de vuelta al JSON, o se sobrescribe en el siguiente despliegue.
- Los flujos corren con las conexiones de quien las creó (Diogo).
- El flujo de avisos y `fl_reporte_deuda` todavía no existen. Las referencias `hd_sql` y `hd_outlook` están creadas, pero nada las usa aún.
- `fl_cargar_ahora` (botón «Cargar ahora») está desplegado, pero ninguna de las dos apps lo invoca todavía.

**Referencias:** `tools/powerplatform.py`, `powerplatform/flows/*.json`.

---

## D17 · Limitaciones de licencias de Power BI

**Fecha:** 2026-11-07 · **Tema:** licencias

**Contexto.** La guía (13) pide un tablero con las páginas Resumen, Integración y Calidad. La cuenta UNI tiene licencia gratuita de Power BI.

**Decisión.** Construir el modelo en **Power BI Desktop** sobre las vistas autorizadas (`rol_hub_bi`: `vDeuda`, `vEstadoFuentes`, `vMovimientoDetalle`, `vLoteCalidad`, `vObservacionCalidad`, `Area`) y publicarlo en **«Mi área de trabajo»** para la demostración. Si se necesita compartirlo, usar una prueba de Pro, PPU o Fabric.

**Alternativas consideradas.**
- *Licencia Pro o PPU:* costo por usuario.
- *Publicar en la web («Publish to web»):* expone los datos públicamente; descartado aunque sean ficticios, por ser mala práctica.
- *Informes en Power Apps en lugar de Power BI:* no cumple la sección 13.

**Consecuencias.**
- El tablero se puede mostrar, pero no compartir con otros usuarios con licencia gratuita.
- Azure SQL es un origen en la nube: no hace falta puerta de enlace de datos.
- **Pendiente:** el modelo de Power BI aún no está en el repositorio (no existe la carpeta `powerbi/`).

**Referencias:** `docs/ACCESOS.md` (sección 4), `sql/hub/004_seguridad.sql` (`rol_hub_bi`).

---

## D18 · Libro vacío rechazado con `CARGA_VACIA`

**Fecha:** 2026-11-07 · **Tema:** saldo y cortes

**Contexto.** La guía establece que un libro vacío no puede publicarse sin autorización explícita, porque podría borrar en silencio la contribución de un área.

**Decisión.** El validador rechaza todo libro sin filas con `CARGA_VACIA`, y `usp_PublicarArea` repite el control (`PUBLICACION_50105`, «Lote vacio no autorizado»).

**Alternativas consideradas.**
- *Aceptar el libro vacío como «sin movimientos»:* un error de copia o de plantilla dejaría a un área sin movimientos sin que nadie lo note.

**Consecuencias.**
- En Azure, las 9 áreas con plantillas vacías quedaron `RECHAZADO` con `CARGA_VACIA` en la copia programada, el comportamiento esperado.
- Cada copia programada (13:00 y 18:00) crea un nuevo lote rechazado y un aviso `RECHAZADO` por cada área que siga vacía: ruido en `Lote`, `Observacion`, `Notificacion` y en el tablero de calidad.
- **Pendiente:** no hay un mecanismo de «autorización explícita». No existe una columna, un procedimiento ni una marca en `ConfigAreas` para autorizar una inicialización vacía. Opciones: desactivar en `ConfigAreas` las áreas sin datos hasta su primera carga, o agregar una autorización auditada.

**Referencias:** `functions/validacion.py`, `sql/hub/003_procedimientos.sql`, `tests/test_circuito.py::test_libro_vacio_requiere_autorizacion`.
