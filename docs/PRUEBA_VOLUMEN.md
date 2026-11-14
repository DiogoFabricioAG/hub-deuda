# Prueba de volumen: 500 000 filas

Fecha: 13 nov 2026. Equipo: Intel i5-11400H (6 núcleos), 15,6 GB de RAM, SSD NVMe. SQL Server Express local (`localhost\SQLEXPRESS`).
Prueba: [`tests/test_volumen.py`](../tests/test_volumen.py) (se activa con `HUB_VOLUMEN=500000`). Usa el mismo procesador que la Function (`procesar_pendientes`), con un libro del contrato v1 (hoja `Datos`, tabla `tblMovimientos`) de un área.

| Medición | Resultado |
|---|---|
| Tamaño del libro de 500 000 filas | 16,1 MiB |
| Con el límite actual de 10 MiB | Rechazado completo: `ARCHIVO_INVALIDO` en 0,1 s |
| Con límites ampliados: validar, cargar y publicar | **130 s** (≈ 3 800 filas/s), 500 000 movimientos, lote ACEPTADO |
| Pico de memoria del proceso | 2 531 MiB |
| Saldo de una papeleta (`vDeuda`) | 188 ms |
| Total de todas las papeletas | 480 ms |
| Detalle de 20 movimientos de una papeleta | 12 ms |
| Libro nuevo con la fila 490 000 corrupta (PAGO negativo) | **RECHAZADO** con `MONTO_INVALIDO` en la fila 490 000; 123,6 s |
| Efecto del rechazo en la base | Ninguno: mismo total y los mismos 500 000 movimientos que antes |

## Conclusiones

- El «todo o nada» se cumple con volumen: un error en la fila 490 000 rechaza el archivo completo y no deja datos a medias.
- Con 500 000 filas el límite de 10 MiB debe ampliarse (el libro pesa 16 MiB).
- La memoria (2,5 GB) y los dos minutos vienen sobre todo de leer el Excel con `openpyxl` y de la validación fila por fila en Python, no de SQL Server. Mejora posible: lectura en modo `read_only` o conversión previa a CSV.
- Las lecturas sobre la base cargada responden en milisegundos, salvo el total global (0,5 s).

## Segunda prueba: camino real on-premise (Excel «sucio» → worker → SQL)

Fecha: 14 nov 2026. Misma máquina. Prueba: [`tests/test_volumen_worker.py`](../tests/test_volumen_worker.py) (`HUB_VOLUMEN=500000`). A diferencia de la anterior, el libro tiene el formato propio del área 1 (otros encabezados, fechas como texto dd/mm/aaaa, papeletas mal escritas, sinónimos) y pasa por el mapeo, el saneamiento y el registro de correcciones.

| Etapa | Resultado |
|---|---|
| Generar el Excel sucio | 57 s · 16,2 MiB |
| 1. Mapeo y saneamiento (`worker.encolar_cambios`) | **147 s** · 1 583 333 correcciones · pico de memoria 2 018 MiB |
| 2. Validar todas las filas, cargar y publicar | **88 s** · ACEPTADO · 500 000 movimientos · pico de memoria 2 607 MiB |
| 3. Registrar las correcciones en SQL | **219 s** · 1 583 333 filas |
| **Total Excel sucio → publicado** | **454 s (≈ 7,5 min)** |
| Saldo de una papeleta / detalle de 20 movimientos / estado de fuentes | 159 ms / 7 ms / 11 ms |
| Reenvío con «treinta soles» en la fila 490 000 | **RECHAZADO** · `MONTO_INVALIDO` en la fila 490 000 · 224 s · la base no cambia (500 000 movimientos, mismo total) |

### Hallazgo y corrección

La primera ejecución no terminó: el worker enviaba las ~1,6 M correcciones en una sola llamada `executemany` y SQL Server llevó más de 79 min de CPU sin acabar. Insertando por tandas pequeñas el ritmo es de unas 8 000 filas/s, así que ahora `guardar_correcciones` inserta de 20 000 en 20 000 (`onprem/worker.py`).

### Conclusiones

- El camino completo con 500 000 filas sucias tarda unos 7,5 min, lejos de los 10–30 días del proceso manual.
- El «todo o nada» se cumple también con el saneamiento delante: lo que no se puede interpretar rechaza el archivo completo.
- El pico de memoria es de 2,6 GB: el equipo necesita unos 8 GB de RAM libres para este volumen.
- El registro de correcciones crece mucho con datos muy sucios (3 por fila en esta prueba); conviene definir cuánto tiempo se conserva.

## Alcance y límites

- Un solo área y tres papeletas; no se probó con las 10 áreas a la vez.
- No se separó el tiempo de validación del de inserción.
- Las bases de prueba (`HubDeuda_test`, `BDOrigen_test`) se recrean en cada ejecución.
