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

## Alcance y límites

- Un solo área y tres papeletas; no se probó con las 10 áreas a la vez.
- No se separó el tiempo de validación del de inserción.
- Las bases de prueba (`HubDeuda_test`, `BDOrigen_test`) se recrean en cada ejecución.
