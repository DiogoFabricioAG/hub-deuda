# Matriz de permisos — Hub de Deuda

Documento del paquete de aceptación (sección 14 de la guía). Refleja lo declarado en el código al **7 de noviembre de 2026**: `infra/main.bicep`, `sql/hub/004_seguridad.sql`, `sql/hub/005_permiso_notificacion.sql`, `sql/hub/900_usuarios_azure.sql.template`, `sql/origen/002_exportacion.sql`, `tools/instalar_shir.ps1`, `tools/provisionar_sharepoint.ps1`, `tools/powerplatform.py` y los flujos de `powerplatform/flows/`.

Documentos relacionados: [ARQUITECTURA.md](ARQUITECTURA.md) · [DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md) · [DECISIONES.md](DECISIONES.md) · [PRUEBAS.md](PRUEBAS.md)

**Principios aplicados**

- **Mínimo privilegio por rol de base de datos.** Ninguna identidad de servicio es `db_owner`; cada una recibe solo los objetos que usa. La regresión `tests/test_permisos.py` ejecuta el procesador con los permisos exactos de `rol_hub_integracion`.
- **Sin secretos en el código.** Azure SQL acepta solo autenticación de Entra (`azureADOnlyAuthentication: true`). La Function y ADF usan identidades administradas. El único secreto (contraseña del lector de `BDOrigen`) se genera en el PC y va directo a Key Vault.
- **El plano de control no da acceso a datos.** Ser Owner o Contributor no permite leer blobs ni secretos: por eso el Bicep asigna roles de datos explícitos (Storage Blob Data …, Key Vault Secrets User).
- **Las apps no aplican la seguridad: la aplica SQL.** Cada usuario se conecta a Azure SQL con su propia identidad de Entra; elegir otra área en la app solo produce un error de permiso (T12).

---

## 1. Identidades

| Id | Identidad | Tipo | Nombre real | Estado al 7 nov 2026 |
|---|---|---|---|---|
| I1 | Responsable del proyecto y administrador | Usuario de Entra (tenant UNI) | `diogo.abregu.g@uni.pe` | Activa |
| I2 | Identidad administrada de la Function | Identidad administrada asignada por el sistema | `func-hubdeuda-dev-dg23ne` | Activa |
| I3 | Identidad administrada de Data Factory | Identidad administrada asignada por el sistema | `adf-hubdeuda-dev-dg23ne` | Activa |
| I4 | Lector de BDOrigen | Login SQL local (usado por ADF a través del SHIR) | `hub_lector` | **Pendiente:** se crea al ejecutar `tools/instalar_shir.ps1` |
| I5 | Conexiones de Power Platform | Conexiones OAuth del entorno Developer, referenciadas por `hd_sharepoint`, `hd_azureblob`, `hd_sql`, `hd_outlook` | Creadas con la cuenta I1 | `hd_sharepoint` y `hd_azureblob` en uso; `hd_sql` y `hd_outlook` sin flujo que las use todavía |
| I6 | Correctores de las áreas 01–10 | Usuarios de Entra | — | **Pendiente:** hoy las 10 áreas están a nombre de I1 en `ConfigAreas` |
| I7 | Ventanilla (consulta de deuda) | Usuarios de Entra | — | **Pendiente** |
| I8 | Analistas de BI | Usuarios de Entra | — | **Pendiente** |
| I9 | Coordinación (edita `ConfigAreas`) | Usuario de Entra | Hoy I1 | Activa (sin restricción de edición configurada) |
| I10 | Flujo de avisos | Identidad de la conexión SQL del flujo | — | **Pendiente:** el flujo no está construido |

---

## 2. Matriz resumida (identidad × recurso)

Abreviaturas: *SBDR* = Storage Blob Data Reader; *SBDO* = Storage Blob Data Owner; *SBDC* = Storage Blob Data Contributor; *KVSU* = Key Vault Secrets User; *KVSO* = Key Vault Secrets Officer. «—» = sin acceso.

| Identidad | Storage de negocio `sthubdeudadevdg23ne` | Storage runtime `sthubfuncdevdg23ne` | Azure SQL `HubDeuda` | Key Vault `kv-hubdeuda-dg23ne` | BDOrigen (PC) | SharePoint `IntegracionDeuda` | Power Platform (entorno Developer) |
|---|---|---|---|---|---|---|---|
| I1 Administrador | Owner (control). Datos: *SBDC* requerido por las herramientas, no declarado en Bicep (ver 3.2) | Owner (control) | Administrador Entra del servidor → `dbo` en todas las bases | Owner (control). Datos: *KVSO* requerido para guardar `bdorigen-lector`, no declarado en Bicep | `sysadmin` local (autenticación de Windows) | Propietario del sitio | Administrador del entorno y dueño de la solución `HubDeuda`, flujos, apps y conexiones |
| I2 Function | *SBDR* (cuenta completa) | *SBDO* | `rol_hub_integracion` | — | — | — | — |
| I3 Data Factory | — | — | `rol_hub_ingesta_base` | *KVSU* | Indirecto, vía I4 | — | — |
| I4 `hub_lector` | — | — | — | — (su contraseña es el secreto) | `rol_origen_lector` | — | — |
| I5 Conexiones | `hd_azureblob`: escritura en `raw` y `manifests` (identidad y método de la conexión: ver 3.2) | — | `hd_sql`: según la identidad de la conexión (I1 hoy) | — | — | `hd_sharepoint`: permisos de I1 (lee `ConfigAreas` y los libros) | Referencias de conexión de la solución |
| I6 Áreas 01–10 | — | — | `rol_hub_area01` … `rol_hub_area10` (pendiente de asignar) | — | — | Editar solo `Entradas/AreaNN` (pendiente) | App Mis observaciones; flujo «Cargar ahora» (requiere licencia) |
| I7 Ventanilla | — | — | `rol_hub_consulta` (pendiente de asignar) | — | — | — | App ConsultaDeuda (requiere licencia) |
| I8 BI | — | — | `rol_hub_bi` (pendiente de asignar) | — | — | Lectura de `Reportes` (pendiente) | — (Power BI: ver 3.9) |
| I9 Coordinación | — | — | — | — | — | Editar `ConfigAreas` (hoy I1, sin restringir a los demás) | — |
| I10 Flujo de avisos | — | — | `rol_hub_avisos` (pendiente) | — | — | — | Flujo de avisos (pendiente) |

---

## 3. Detalle por recurso

### 3.1 Suscripción y grupo de recursos `rg-hubdeuda-dev` (plano de control)

| Identidad | Rol | Ámbito | Para qué |
|---|---|---|---|
| I1 | Owner | Suscripción de pago por uso | Desplegar Bicep, asignar roles a las identidades administradas, configurar firewall, presupuesto y Data Factory |
| I2, I3 | — | — | No necesitan roles de control: solo roles de datos |

### 3.2 Storage de negocio `sthubdeudadevdg23ne` (contenedores `raw`, `manifests`, `reports`)

| Identidad | Rol | Ámbito | Para qué | Declarado en |
|---|---|---|---|---|
| I2 Function | Storage Blob Data Reader | Cuenta | Listar `manifests`, leer el manifiesto y descargar el `.xlsx` de `raw`. No puede escribir ni borrar | `main.bicep` (`funcLeeNegocio`) |
| I1 Administrador | Storage Blob Data Contributor | Cuenta | `tools/prueba_humo_azure.py` sube raw y manifiestos y `tools/reiniciar_datos_hub.py` borra los de prueba, ambos con `DefaultAzureCredential` | **No está en `main.bicep`.** Confirmar con `az role assignment list --assignee diogo.abregu.g@uni.pe --scope <id de la cuenta>` y registrar la evidencia |
| I5 `hd_azureblob` | Escritura de blobs | Cuenta | `fl_copia_area` crea `raw/areaNN/…/<LoteId>.xlsx` y `manifests/<LoteId>.json` | Conexión creada por I1 en Power Automate. Documentar si usa Entra (requiere *SBDC* para I1) o clave de acceso (la clave queda en la conexión, fuera del repositorio) |

La cuenta tiene acceso público de red habilitado porque el conector Azure Blob de Power Automate no admite cuentas detrás de firewall (comentario M07 en el Bicep). El acceso anónimo a blobs está deshabilitado y los contenedores son privados.

### 3.3 Storage del runtime de Functions `sthubfuncdevdg23ne`

| Identidad | Rol | Ámbito | Para qué |
|---|---|---|---|
| I2 Function | Storage Blob Data Owner | Cuenta | `AzureWebJobsStorage` por identidad (bloqueos del timer) y contenedor `deploy` del paquete de Flex Consumption |

La cuenta tiene `allowSharedKeyAccess: false`: no existen claves utilizables.

### 3.4 Azure SQL — servidor `sql-hubdeuda-dev-dg23ne`, base `HubDeuda`

**Autenticación:** solo Entra. Administrador del servidor: I1. Las identidades administradas se crean con `CREATE USER … FROM EXTERNAL PROVIDER WITH OBJECT_ID` (plantilla `900_usuarios_azure.sql.template`, aplicada por `tools/desplegar_sql_azure.py`), lo que evita que el servidor necesite el rol Directory Readers.

**Roles de base de datos (004_seguridad.sql y 005_permiso_notificacion.sql)**

| Rol | Permisos | Miembros | Para qué |
|---|---|---|---|
| `rol_hub_integracion` | `SELECT` en `Area`, `AreaFuente`, `vBaseVigente`; `SELECT, INSERT` en `Lote`, `Movimiento`, `Observacion`; `INSERT` en `Notificacion` (004) y `SELECT` en `Notificacion` (005); `SELECT, INSERT, UPDATE` en `ProcesoManifiesto`; `EXECUTE` en `usp_PublicarArea` | I2 `func-hubdeuda-dev-dg23ne` | Procesar manifiestos: leer contexto y base, registrar lotes, movimientos, observaciones y avisos, publicar con el procedimiento. El `SELECT` sobre `Notificacion` se agregó en 005 tras el error 229 de la prueba de humo en Azure |
| `rol_hub_ingesta_base` | `INSERT` en `BaseFila`; `EXECUTE` en `usp_IniciarBaseCarga`, `usp_PublicarBase`, `usp_MarcarBaseFallida` | I3 `adf-hubdeuda-dev-dg23ne` | Cargar y publicar la fotografía de la deuda base. No puede leer movimientos ni saldos |
| `rol_hub_consulta` | `SELECT` en `vDeuda`, `vEstadoFuentes`, `vMovimientoDetalle` | Pendiente (I7) | App ConsultaDeuda (11.1). Sin acceso a tablas |
| `rol_hub_area01` … `rol_hub_area10` | `SELECT` solo en `vObservacionesNN` de su área | Pendiente (I6) | App Mis observaciones (11.6). Un área no ve las observaciones de otra ni las tablas (T12) |
| `rol_hub_bi` | `SELECT` en `vDeuda`, `vEstadoFuentes`, `vMovimientoDetalle`, `vLoteCalidad`, `vObservacionCalidad`, `Area` | Pendiente (I8) | Modelo de Power BI (13). Sin tablas operativas |
| `rol_hub_avisos` | `SELECT, UPDATE` en `Notificacion`; `SELECT` en `vLoteCalidad`, `AreaFuente` | Pendiente (I10) | Flujo de avisos: tomar pendientes, marcar enviados, obtener destinatarios (12.1) |
| `dbo` (administrador Entra) | Control total | I1 | Migraciones, carga directa temporal de la base, pruebas de humo, `usp_RestaurarLoteVigente` |

Ningún rol tiene permisos sobre `CambioPuntero`, `SchemaVersion`, `BaseActual`, `BaseCarga` ni `vMovimientoVigente`: se acceden solo dentro de los procedimientos (encadenamiento de propiedad) o como `dbo`.

**Firewall del servidor:** regla `AllowAzureServices` (0.0.0.0, «Permitir servicios de Azure») y regla `PcOnPremise` con la IP pública del PC (se actualiza con `tools/actualizar_ip_pc.ps1`). Ver la decisión D13 en [DECISIONES.md](DECISIONES.md).

**Alta de usuarios pendiente (ejemplo, con valores a completar):**

```sql
CREATE USER [<upn de la cuenta del área 01>] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '<object id de Entra>';
ALTER ROLE rol_hub_area01 ADD MEMBER [<upn de la cuenta del área 01>];
```

Se recomienda usar grupos de Entra por rol (si la UNI permite crearlos) en lugar de usuarios sueltos.

### 3.5 Key Vault `kv-hubdeuda-dg23ne` (autorización RBAC)

| Identidad | Rol | Para qué | Declarado en |
|---|---|---|---|
| I3 Data Factory | Key Vault Secrets User | Leer el secreto `bdorigen-lector` para `ls_sql_origen` | `main.bicep` (`adfLeeSecretos`) |
| I1 Administrador | Key Vault Secrets Officer | `tools/instalar_shir.ps1` escribe `bdorigen-lector` con `az keyvault secret set` | **No está en `main.bicep`.** Asignar antes de instalar el SHIR y registrar la evidencia |
| I2 Function | — | No usa secretos | — |

Borrado temporal (soft delete) de 7 días.

### 3.6 BDOrigen (SQL Server Express del PC)

| Identidad | Permiso | Para qué |
|---|---|---|
| I4 `hub_lector` (login SQL) | Miembro de `rol_origen_lector`: `EXECUTE` en `usp_CrearExportacion` y `SELECT` en `DeudaExport` | ADF, vía SHIR, crea una exportación consistente y copia solo esa fotografía. No ve `DeudaOrigen` |
| I1 (Windows) | `sysadmin` de la instancia local | Crear la base, aplicar migraciones, carga directa temporal |

`tools/instalar_shir.ps1` cambia la instancia a autenticación mixta (necesaria para el login SQL) y genera una contraseña aleatoria de 32 caracteres que se guarda solo en Key Vault. El SHIR no abre puertos de entrada: inicia conexiones salientes (443 hacia ADF, 1433 hacia Azure SQL).

### 3.7 SharePoint — sitio `https://unipe.sharepoint.com/sites/IntegracionDeuda`

| Elemento | Permiso actual | Permiso objetivo (guía, sección 6) | Estado |
|---|---|---|---|
| Sitio | I1 propietario | I1 propietario; resto según su función | Hecho |
| Biblioteca `Entradas`, carpetas `Area01`–`Area10` | Heredan del sitio | Cada carpeta con herencia rota: el área NN edita solo `AreaNN`; las demás áreas sin acceso; la cuenta de los flujos con lectura | **Pendiente** |
| Lista `ConfigAreas` | Hereda del sitio | Edición solo coordinación (I9); lectura para la cuenta de los flujos | **Pendiente** |
| Biblioteca `Plantillas` | Hereda | Lectura para áreas; edición coordinación | Pendiente |
| Biblioteca `Reportes` | Hereda | Escritura del flujo de reportes; lectura para ventanilla y BI | Pendiente (flujo de reportes no construido) |
| Biblioteca `Evidencias` | Hereda | Edición del equipo del proyecto | Pendiente |

Todas las bibliotecas tienen historial de versiones (hasta 100 versiones principales). Los flujos acceden con la conexión `hd_sharepoint` de I1, por lo que no dependen de los permisos de las áreas.

### 3.8 Power Platform — entorno Developer `https://org2535ee74.crm2.dynamics.com/`

| Elemento | Permiso | Notas |
|---|---|---|
| Entorno | I1 administrador (dueño del Developer Plan) | Solo el dueño puede ejecutar lo Premium con este plan |
| Solución `HubDeuda` (publicador `hubdeuda`, prefijo `hd`) | I1 | Creada por `tools/powerplatform.py` vía API de Dataverse |
| Flujos `fl_copia_area`, `fl_copia_programada`, `fl_cargar_ahora` | Dueño I1; se ejecutan con las conexiones de I1 | `fl_cargar_ahora` solo copia si el correo del usuario que lo invoca es el `ResponsableUPN` del área en `ConfigAreas`. Hoy ese valor es I1 en las 10 áreas |
| Apps ConsultaDeuda y Mis observaciones | Dueño I1; no compartidas | Compartirlas exige licencia Premium (o Developer Plan propio) para cada usuario. El conector SQL con autenticación de Entra hace que cada usuario use su propia identidad y sus roles de SQL |
| Referencias de conexión `hd_sharepoint`, `hd_azureblob`, `hd_sql`, `hd_outlook` | Enlazadas a conexiones de I1 | Las conexiones OAuth solo las puede crear el usuario (consentimiento) |

### 3.9 Power BI

| Identidad | Permiso | Notas |
|---|---|---|
| I1 | Licencia gratuita: publicar en «Mi área de trabajo» | Sirve para demostrar, no para compartir |
| I8 BI | `rol_hub_bi` en SQL + licencia Pro/PPU o capacidad Fabric para ver un informe compartido | Pendiente; ver la decisión D17 |

---

## 4. Pendientes

| # | Pendiente | Prueba o sección afectada | Acción |
|---|---|---|---|
| P1 | **Permisos por carpeta de área en SharePoint** (`Entradas/Area01`–`Area10`) y edición de `ConfigAreas` solo para coordinación | Sección 6 de la guía; aislamiento de áreas | Romper herencia de cada carpeta y asignar el grupo o usuario del área con «Editar»; `ConfigAreas` con «Editar» solo para coordinación |
| P2 | **Prueba T12 en Azure con una segunda cuenta UNI** | T12 | Dar de alta la cuenta de otro integrante en `rol_hub_area01` (y otra en `rol_hub_area02`), compartirle la app Mis observaciones y comprobar que ve solo su vista. Con I1 no sirve: es `dbo` y ve todo. Localmente T12 ya pasa con usuarios `WITHOUT LOGIN` |
| P3 | Asignar miembros a `rol_hub_consulta`, `rol_hub_areaNN`, `rol_hub_bi`, `rol_hub_avisos` | 11.1, 11.6, 12.1, 13 | `CREATE USER … WITH OBJECT_ID` + `ALTER ROLE` (sección 3.4) |
| P4 | Reemplazar `ResponsableUPN` y `DestinoAvisos` de `ConfigAreas` por los responsables reales y llevarlos a `AreaFuente` | «Cargar ahora», avisos | Editar la lista; ampliar `tools/sincronizar_areafuente.py`, que hoy copia solo `ArchivoId`, `RutaArchivo` y `Activa` |
| P5 | Confirmar y documentar los roles de datos de I1 que no declara el Bicep (*SBDC* en el storage de negocio, *KVSO* en Key Vault) y el método de autenticación de `hd_azureblob` | Trazabilidad | `az role assignment list` y captura de la conexión |
| P6 | Crear `hub_lector` y su secreto al instalar el SHIR | T13 | `tools/instalar_shir.ps1` |
| P7 | Verificar en la primera ejecución de `pl_base_completa` que `INSERT` sobre `BaseFila` basta para la actividad Copy | T01 vía ADF, T13 | Si falla por permisos de metadatos, agregar una migración `006` con el permiso mínimo que pida el error (no editar 004) |
| P8 | Al cerrar el curso: quitar miembros de roles, desactivar disparadores y eliminar `rg-hubdeuda-dev` | Costos | Ver [ACCESOS.md](ACCESOS.md), sección 6 |

---

## 5. Cómo verificar

**Miembros de roles en Azure SQL** (como administrador Entra):

```sql
SELECT r.name AS rol, m.name AS miembro
FROM sys.database_role_members x
JOIN sys.database_principals r ON r.principal_id = x.role_principal_id
JOIN sys.database_principals m ON m.principal_id = x.member_principal_id
WHERE r.name LIKE 'rol_hub_%'
ORDER BY r.name, m.name;
```

**Permisos efectivos de un rol** (ejemplo con un usuario de prueba sin login, como en `tests/test_circuito.py::test_t12_aislamiento_por_area`):

```sql
EXECUTE AS USER = 'u_area01';
SELECT * FROM fn_my_permissions(NULL, 'DATABASE');
SELECT COUNT(*) FROM dbo.vObservaciones01;   -- permitido
SELECT COUNT(*) FROM dbo.vObservaciones02;   -- debe fallar con error de permiso
REVERT;
```

**Roles de Azure** (con `az login`):

```powershell
az role assignment list --resource-group rg-hubdeuda-dev --all -o table
```
