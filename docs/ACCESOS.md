# Accesos necesarios — Hub de Deuda

Configuración elegida: **suscripción de Azure de pago por uso creada con la cuenta UNI** (`diogo.abregu.g@uni.pe`, tenant UNIVERSIDAD NACIONAL DE INGENIERIA), **Power Apps Developer Plan**, **guía completa** y el **PC de Diogo como servidor on-premise**. La cuenta UNI no tenía suscripción de Azure for Students (7 nov 2026).

> **Regla:** no se comparten contraseñas, claves ni tokens por chat. Tú inicias sesión en tu PC (navegador o código de dispositivo) y las herramientas usan esa sesión. Los secretos generados por los servicios, como la clave del SHIR o la contraseña del lector de BDOrigen, van directo a Key Vault o al instalador. Nunca se guardan en el repositorio.

## 1. Azure (cuenta UNI)

| # | Quién | Acción | Para qué |
|---|---|---|---|
| 1.1 | Tú | Crear la suscripción (cuenta gratuita con USD 200 que luego pasa a pago por uso, o pago por uso directo) **iniciando sesión con la cuenta UNI**, para que quede en el mismo tenant que SharePoint y Power Platform | Suscripción del proyecto |
| 1.2 | Tú | Confirmar que eres **Owner** de la suscripción (es el valor predeterminado) | Asignar roles a las identidades de Functions y ADF |
| 1.3 | Tú | Ejecutar `az login` en tu terminal, una vez instalada Azure CLI | Acceso programático a Azure |
| 1.4 | Yo | Revisar regiones permitidas (Azure for Students las limita por política) y registrar proveedores: Sql, Storage, Web, DataFactory, KeyVault, Insights | Elegir región válida |
| 1.5 | Yo | Desplegar con Bicep: `rg-hubdeuda-dev`, dos Storage, Azure SQL (oferta gratuita serverless), Function App, Data Factory, Key Vault y Application Insights | Infraestructura de la guía |
| 1.6 | Yo | Presupuesto con alertas al 50/80/100 % | Control del crédito |

**Riesgos del tenant UNI que se comprueban en la primera hora:**
- Si los estudiantes no pueden crear grupos ni usuarios de Entra, uso tu cuenta y las identidades administradas. Los usuarios SQL de las identidades se crean con `WITH OBJECT_ID`, sin permisos de directorio.
- La prueba **T12** (el área 01 no ve los errores del área 02) necesita **dos identidades distintas**: la cuenta UNI de otro integrante, o usuarios contenidos de SQL solo para esa prueba.

## 2. Microsoft 365 UNI (SharePoint)

| # | Quién | Acción | Para qué |
|---|---|---|---|
| 2.1 | Tú | Comprobar que puedes crear un **sitio de equipo** (o un equipo de Teams). Si la UNI lo bloquea, pedir a TI o al docente que cree `IntegracionDeuda` y te haga propietario | Bibliotecas Entradas/Plantillas/Reportes/Evidencias |
| 2.2 | Tú | Ejecutar `m365 login` (CLI for Microsoft 365) | Acceso programático a SharePoint |
| 2.3 | Yo | Crear carpetas Area01–Area10, la lista `ConfigAreas`, el historial de versiones y subir las 10 plantillas `movimientos.xlsx` | Sección 6 de la guía |

## 3. Power Platform (Developer Plan)

| # | Quién | Acción | Para qué |
|---|---|---|---|
| 3.1 | Tú | Registrarte en el **Power Apps Developer Plan** con la cuenta UNI | Entorno con Dataverse y conectores Premium (SQL Server, Azure Blob) |
| 3.2 | Tú | Ejecutar `pac auth create` (Power Platform CLI) | Importar la solución `HubDeuda` |
| 3.3 | Tú | **Autorizar las conexiones** con un clic cada una: SharePoint, Azure Blob, SQL Server, Outlook/Teams y Word Online. Microsoft no permite crear conexiones OAuth sin el usuario | Que los flujos y apps funcionen |
| 3.4 | Yo | Construir la solución: flujos `fl_copia_programada`, `fl_cargar_area`, avisos y `fl_reporte_deuda`; apps `ConsultaDeuda` y `MisObservaciones`; variables de entorno y referencias de conexión | Secciones 9, 11 y 12 |

**Limitación:** con el Developer Plan solo tú puedes ejecutar las apps y flujos Premium. Alcanza para construir y presentar, pero cada integrante que quiera usarlas necesita su propio Developer Plan o una licencia. Si la UNI bloquea el registro de autoservicio, la alternativa es la prueba de 30 días de Power Apps Premium.

## 4. Power BI

| # | Quién | Acción | Para qué |
|---|---|---|---|
| 4.1 | Tú | Instalar **Power BI Desktop** (gratuito) | Abrir y publicar el modelo |
| 4.2 | — | Publicar en un workspace compartido requiere Pro, PPU o prueba de Fabric. Con licencia gratuita solo se publica en "Mi área de trabajo": sirve para demostrar, no para compartir | Sección 13 |

## 5. Tu PC como servidor on-premise

| # | Quién | Acción | Para qué |
|---|---|---|---|
| 5.1 | ✔ | SQL Server Express (`localhost\SQLEXPRESS`) ya está instalado y corriendo | Base `BDOrigen` |
| 5.2 | Tú | Autorizar la instalación de Azure CLI, Azure Functions Core Tools v4, Power Platform CLI (herramienta dotnet), CLI for Microsoft 365 (npm) y ODBC Driver 18 | Desplegar y probar |
| 5.3 | Tú | Autorizar después la descarga e instalación del **Self-hosted Integration Runtime** (instalador oficial de Microsoft) | Que ADF lea BDOrigen |
| 5.4 | Tú | Mantener el PC encendido y sin suspensión durante las pruebas de ADF | El SHIR solo trabaja con el PC activo |
| 5.5 | Yo | Crear `BDOrigen` con las 3 deudas ficticias y un login de solo lectura. La contraseña se genera y va directa a Key Vault | Sección 8 |

## 6. Costo estimado (pago por uso: cargos reales a la tarjeta)

Estimación orientativa, por verificar con la calculadora de Azure en la región que se use: Azure SQL con oferta gratuita USD 0; Storage < USD 1; Functions USD ~0; Data Factory con disparador horario y SHIR USD 3–6; Key Vault y Application Insights USD 0–2. **Total: del orden de USD 10 al mes.** Las alertas de presupuesto no detienen recursos: al terminar el curso hay que apagar los disparadores y eliminar el grupo de recursos.

## 7. Orden de trabajo

1. **Tú:** activar Azure for Students y el Developer Plan; instalar Power BI Desktop.
2. **Yo:** instalar las CLI con tu permiso.
3. **Tú:** `az login`, `m365 login` y `pac auth create`.
4. **Yo:** infraestructura, SQL, Functions, ADF + SHIR, SharePoint, solución de Power Platform y Power BI.
5. **Tú:** autorizar las conexiones en Power Automate.
6. **Yo:** pruebas T01–T15 con evidencias en `evidencias/`.

Mientras tanto, el núcleo (SQL + validador + publicación idempotente) se construye y prueba contra el SQL Server local, sin depender de las cuentas.
