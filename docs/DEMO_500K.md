# Demostración en vivo: carga de 500 000 filas

Se hace en una base aparte, **`HubDeuda_500k`**, con su propia carpeta (`datos_500k/`). No toca `HubDeuda_dev` ni las apps de Power Apps. El script es `tools/demo_500k.py`.

**Estado actual (ya preparado):** los Excel de 500 000 filas están generados en `datos_500k\listo\` y la base `HubDeuda_500k` está vacía, con la deuda base y los archivos autorizados registrados.

## Tiempos medidos en el ensayo (14 nov, laptop i5-11400H, 15,6 GB de RAM)

| Momento | Carga buena | Carga con error en la fila 490 000 |
|---|---|---|
| Mapeo y saneamiento | 122 s | 129 s |
| Validar todas las filas | 81 s | 72 s |
| **Resultado visible en la base** | **205 s (≈ 3,4 min): 500 000 movimientos, ACEPTADO** | **202 s: RECHAZADO, `MONTO_INVALIDO` en la fila 490 000, base intacta** |
| Registrar las 1 583 333 correcciones | 223 s | 221 s |
| **Total** | **428 s (≈ 7,1 min)** | 423 s |

Preparar los Excel (una sola vez) tarda unos 2 min. Reiniciar la base tarda unos 10 s.

## Pasos de la demostración

**Antes (el día anterior y 10 minutos antes)**

1. Cierre lo que no necesite (Word, Chrome pesado): el proceso llega a 2,6 GB de memoria.
2. Si ya corrió la demostración una vez, deje la base vacía: `.venv\Scripts\python.exe tools\demo_500k.py reiniciar`.
3. Abra SSMS conectado a `localhost\SQLEXPRESS` y deje a mano las consultas de abajo.
4. Abra una terminal en `D:\hub-deuda-azure` (sin ejecutar nada todavía).

**En vivo**

1. En SSMS ejecute la consulta de movimientos: da **0**. «La base está vacía».
2. En la terminal:
   ```powershell
   .venv\Scripts\python.exe tools\demo_500k.py cargar
   ```
   Cada paso se anuncia en pantalla con la hora y un aviso cada 20 s.
3. Mientras corre (unos 3,4 minutos hasta que se publica), explique la arquitectura con el diagrama: qué hace el worker, qué hace el validador y por qué «todo o nada».
4. Cuando aparezca `>>> PUBLICADO` vuelva a SSMS: **500 000 movimientos** y un lote `ACEPTADO`.
5. Los 3 minutos siguientes el sistema termina de guardar el registro de correcciones; puede mostrar cómo sube el conteo.
6. (Opcional, 3,4 minutos hasta el rechazo) El caso del error:
   ```powershell
   .venv\Scripts\python.exe tools\demo_500k.py cargar --error
   ```
   Termina en `>>> RECHAZADO ... (490000, 'Monto', 'MONTO_INVALIDO') · la base no cambió`. En SSMS el conteo sigue en 500 000.
7. Para repetir: `reiniciar` y vuelve a empezar.

## Consultas para SSMS

```sql
USE HubDeuda_500k;

SELECT COUNT(*) AS Movimientos FROM dbo.Movimiento;
SELECT Estado, COUNT(*) AS Lotes FROM dbo.Lote GROUP BY Estado;
SELECT COUNT(*) AS Correcciones FROM dbo.CorreccionLote;
SELECT Regla, COUNT(*) AS Veces FROM dbo.CorreccionLote GROUP BY Regla ORDER BY 2 DESC;
SELECT FilaExcel, Campo, Codigo FROM dbo.Observacion;
```

## Detalles a tener en cuenta

- **No muestre los saldos de esta base.** El libro sintético lleva 500 000 pagos pequeños y los saldos de P0001 a P0003 salen negativos (≈ −42 000). Es normal en una prueba de volumen. Muestre el conteo de movimientos.
- **Las apps no ven esta base:** el gateway apunta a `HubDeuda_dev`. La demostración se hace con la terminal y SSMS.
- **El rechazo también registra correcciones** (otras 1,58 M): el saneamiento ya ocurrió antes de que la validación detectara el error. Por eso, tras cargar y luego rechazar, la tabla tiene 3,2 M de filas.
- Si el equipo está lento, avise al profesor de antemano: la carga completa son unos 7 minutos y el saldo se ve a los 3,4.
- Los Excel se generan con papeletas sucias (` p-1 `, `P3`), fechas como texto y sinónimos, a propósito, para mostrar el mapeo y el saneamiento.
