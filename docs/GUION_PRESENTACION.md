# Guion de la presentación: arquitectura, PoC y casos de uso (15–18 minutos)

Todos los datos son ficticios. Se explica primero la arquitectura con el diagrama, luego la aplicación desarrollada y luego se muestran cinco casos de uso en las apps y se aclara cuándo y cómo se cargarían 500 000 registros. No se muestra el worker ni la terminal.

**Estado de partida (ya está así hoy):** saldos **P0001 = 60,00 · P0002 = 1 434,50 · P0003 = 95,50**; el Excel de Tesorería tiene «treinta soles» en la fila 7, por lo que su último archivo está rechazado.

## Preparación (10 minutos antes, fuera de la presentación)

| Qué | Cómo |
|---|---|
| SQL Server y gateway encendidos | `Get-Service 'MSSQL$SQLEXPRESS','PBIEgwService'` → ambos `Running` |
| Worker corriendo en segundo plano | En una terminal aparte: `.venv\Scripts\python.exe onprem\worker.py --cada 5`. No se muestra; solo sirve para el caso 5 |
| Pestañas abiertas en Chrome (sesión UNI iniciada) | «Consulta de deuda», «Mis observaciones» (área 01 Tesorería) y el diagrama `docs/arquitectura_objetivo-archify.html` |
| Excel de Tesorería a mano, **cerrado** | `D:\hub-deuda-azure\datos_onprem\areas\Area01\Tesoreria_movimientos.xlsx` |
| Plan B | Las capturas de `evidencias/` y el informe `docs/INFORME_FINAL.docx` |

## Parte 1 · El problema (1 minuto)

- Diez áreas llevan su parte de la deuda en Excel, cada uno con otro formato.
- Un estado de cuenta tarda **de 10 a 30 días** y nadie se arriesga a cobrar de menos.
- Lo que se propone: pasar de semanas a minutos, **sin cambiar cómo trabaja cada área**.

## Parte 2 · La arquitectura, con el diagrama de Archify (4 minutos)

Recorra el diagrama de izquierda a derecha. En cada bloque diga qué entra y qué sale.

1. **Áreas y carpetas.** Cada área sigue con su Excel. El sistema guarda el original y una copia inmutable (evidencia de auditoría).
2. **Integración local.** Un proceso detecta el cambio, **traduce** el formato de cada área al modelo común, **limpia** (espacios, papeletas, montos, fechas) y **registra cada corrección**.
3. **Validación «todo o nada».** Se validan todas las filas. Si hay un error, se rechaza el archivo completo y se devuelve la lista de errores. *Por qué:* las moras y fraccionamientos de una fila pueden depender de otra; una carga a medias llevaría a **cobrar de menos**.
4. **SQL Server en la empresa.** Única fuente de verdad: los movimientos de las áreas más la deuda base (≈ 90 %), que viene aparte y solo se lee.
5. **Gateway de datos.** Conexión **solo saliente** hacia Microsoft: no se abre ningún puerto de entrada.
6. **Power Apps y Power BI en la nube.** Solo son la interfaz y **no guardan datos**.

**Frase de cierre del diagrama:** «Los datos sensibles nunca salen de la empresa; la nube solo muestra».

**El saldo:** deuda base − pagos − descuentos + cargos. Las anulaciones no cuentan.

## Parte 3 · La aplicación desarrollada (1–2 minutos)

Muestre las dos apps y diga para quién es cada una:

- **Consulta de deuda** (atención al ciudadano): busca por papeleta, DNI/RUC o placa y muestra el saldo consolidado, los movimientos vigentes por área y el estado de cada fuente.
- **Mis observaciones** (cada área): muestra los errores de su Excel, con fila, campo y motivo, para que los corrija ella misma.

Mencione también el tablero de gestión en Power BI como la tercera pieza, **pendiente de conectar** a la base local.

## Parte 4 · Casos de uso (5 minutos)

### Caso 1 · Atención al ciudadano: consulta por placa (1 min)
En «Consulta de deuda», escriba la placa **ABC123**. Aparece **P0001 · S/ 60,00**.
**Qué decir:** «En segundos, en lugar de preguntar área por área durante semanas».

### Caso 2 · Saldo consolidado de varias áreas (1 min)
Abra **P0002 · placa XYZ789 · S/ 1 434,50**. Muestre el detalle: importe original 250,00, un pago de Tesorería y el interés de 1 234,50 de Ejecutoría Coactiva.
**Qué decir:** «Este interés vivía solo en el Excel de otra área. Ahora el saldo ya lo incluye».

### Caso 3 · Frescura de la información (30 s)
En el panel «Estado de las fuentes» señale la fecha de corte de la base y el estado de cada área (aceptada, sin cargas, o último intento rechazado).
**Qué decir:** «Quien consulta sabe qué tan actual es el dato y de qué área viene».

### Caso 4 · Un área ve su error y por qué no se publicó (1 min)
En «Mis observaciones» (01 Tesorería) pulse **Actualizar**: **Fila 7 · campo Monto · MONTO_INVALIDO**. Vuelva a «Consulta de deuda»: P0001 sigue en 60,00.
**Qué decir:** «Un solo monto ilegible rechazó todo el archivo, también las filas buenas. Es el “todo o nada”: preferimos no publicar antes que publicar un saldo equivocado».

### Caso 5 · El área corrige y el dato se actualiza (1,5 min)
1. Abra el Excel de Tesorería, cambie la celda **D7** de `treinta soles` a `30`, **guarde y cierre**.
2. Espere unos 5 segundos y pulse **Actualizar** en «Consulta de deuda»: **P0001 = 30,00** (entró el pago de 30).
3. En «Mis observaciones» pulse **Actualizar**: 0 pendientes. Marque «Mostrar también las ya subsanadas» y aparece la de la fila 7.

**Qué decir:** «El área corrigió una celda y el archivo completo se limpió, se validó y se publicó solo. La observación no se borra: queda como subsanada, es parte de la auditoría».

## Parte 5 · Cuándo llegarían 500 000 registros y cómo se cargan (3 minutos)

**Primero la aclaración:** el día a día son archivos pequeños; 500 000 filas es el **caso extremo de diseño** que pidió el profesor. Aun así, hay dos situaciones reales en que un área lo presentaría:

1. **Carga inicial o histórica.** Al incorporar un área, su Excel acumulado de años entra de una sola vez. Ocurre una vez por área.
2. **Reenvío de un libro grande.** El hub trata cada archivo como el **estado completo del área**: un libro al que le faltan filas se rechaza como borrado. Por eso, cuando un área con mucho historial guarda un cambio (aunque sea una celda), se procesa **el libro entero** otra vez.

**Cómo se carga** (sin intervención manual):

1. El área guarda su libro en su carpeta; el sistema detecta el cambio por su huella SHA-256.
2. Se **lee el libro en flujo** y se traduce al modelo común, saneando y registrando cada corrección.
3. Se **validan todas las filas**. Con un solo error se rechaza todo el archivo y se devuelve la lista completa de errores.
4. Si todo es válido, se hace la **carga masiva a una zona de paso** y se **publica en un solo movimiento** (se cambia el puntero del lote vigente). Mientras tanto, las apps siguen mostrando el saldo vigente anterior (es el diseño de la publicación atómica; no se midió con consultas durante la carga).
5. Las correcciones se guardan en SQL por tandas de 20 000 filas.

**Métricas medidas** (Excel «sucio» de 500 000 filas, 16,2 MiB, un área, laptop con i5-11400H, 15,6 GB de RAM y SQL Server Express):

| Etapa | Tiempo | Ritmo |
|---|---|---|
| Mapeo y saneamiento | 147 s | ≈ 3 400 filas/s (1 583 333 correcciones) |
| Validar todas las filas, cargar y publicar | 88 s | ≈ 5 700 filas/s |
| Registrar las correcciones en SQL | 219 s | ≈ 7 200 correcciones/s |
| **Total, Excel sucio → publicado** | **454 s (≈ 7,5 min)** | ≈ 1 100 filas/s |
| Mismo volumen con libro ya limpio (formato común) | 130 s | ≈ 3 800 filas/s |
| Libro con un error en la fila 490 000 | rechazado en 224 s | base intacta |
| Consultas con el volumen cargado | saldo de una papeleta 159 ms · detalle de 20 movimientos 7 ms | |
| Memoria máxima del proceso | 2,6 GB | |

**Qué decir:** «Un archivo de 500 000 filas desordenadas llega publicado en unos 7,5 minutos y, si trae un error, se rechaza en menos de 4 y sin tocar la base. Frente a los 10 a 30 días de hoy, es otra escala».

**Dos precios de este diseño que conviene decir con honestidad:**

- No hay carga incremental: con un libro de ese tamaño, cambiar una celda cuesta reprocesar el libro completo (≈ 7,5 min), no los 1,4 s del libro pequeño. La mejora natural es cargar solo lo que cambió.
- No se midió todavía: la carga de varias áreas grandes a la vez, el tamaño final en disco, ni Excel reales con fórmulas. El equipo necesita unos 8 GB de RAM libres, y conviene programar las cargas grandes fuera del horario de consulta.

## Parte 6 · Cierre con números y límites (1–2 minutos)

- **500 000 filas** «sucias» llegan publicadas en **7,5 minutos**; un error en la fila 490 000 rechaza todo y la base queda intacta.
- Un Excel corregido se ve en SQL en **1,4 s** (sondeo de 2 s).
- **23 pruebas automáticas** aprobadas.
- **Límites que conviene decir:** hay mapeo de 3 de las 10 áreas; los permisos por área se aplican en la app, no en SQL; Power BI está pendiente; el servidor es una laptop; falta probar con Excel reales y varias áreas a la vez.

## Preguntas probables

- **¿Por qué rechazar todo el archivo?** Porque las filas se relacionan entre sí; una carga parcial lleva a cobrar de menos.
- **¿Dónde están los datos?** En el SQL Server de la empresa; la nube solo recibe el resultado de cada consulta por el gateway.
- **¿Por qué el gateway y no ngrok?** ngrok publica una URL pública, justo lo que una entidad así no aceptaría.
- **¿Qué pasa si se apaga el gateway?** Las apps pierden la conexión; esa prueba aún no se hizo.
- **¿Y si cambian las columnas de un Excel?** Se rechaza ese archivo hasta actualizar el mapeo de su área.
- **¿Y los costos?** El conector de SQL Server es premium; Power Apps ronda USD 20 por usuario al mes (fuentes secundarias, a confirmar).

## Si algo falla en vivo

| Síntoma | Qué hacer |
|---|---|
| La app sigue mostrando 60,00 tras corregir | Pulsar **Actualizar**; si sigue igual, confirmar que el Excel se guardó y está cerrado, y esperar 5 s |
| Error de conexión en la app | Reiniciar el servicio `PBIEgwService`; mientras tanto usar las capturas de `evidencias/` |
| El lote sale rechazado al corregir | La celda D7 debe ser el número `30`, sin comillas ni texto |

## Después de la presentación: volver al estado de partida

```powershell
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'onprem'); import datos_demo; from pathlib import Path; datos_demo.area1(Path('datos_onprem'), False)"
.venv\Scripts\python.exe onprem\worker.py --una-vez
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'onprem'); import datos_demo; from pathlib import Path; datos_demo.area1(Path('datos_onprem'), True)"
.venv\Scripts\python.exe onprem\worker.py --una-vez
```

Con esto P0001 vuelve a 60,00 y el Excel vuelve a tener «treinta soles» en la fila 7.
