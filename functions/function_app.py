"""Azure Function (modelo Python v2): revisa manifiestos pendientes cada minuto.

Ajustes requeridos en la Function App (sin secretos):
  STORAGE_URL   = https://<cuenta>.blob.core.windows.net
  SQL_SERVER    = <servidor>.database.windows.net
  SQL_DATABASE  = HubDeuda
La identidad administrada necesita Storage Blob Data Reader en la cuenta de
negocio y el rol de base de datos rol_hub_integracion.
"""
import logging

import azure.functions as func

from procesador import procesar_pendientes

app = func.FunctionApp()


@app.timer_trigger(schedule="0 * * * * *", arg_name="timer",
                   run_on_startup=False, use_monitor=True)
def ingestar(timer: func.TimerRequest) -> None:
    resultados = procesar_pendientes(limite=20)
    if resultados:
        resumen = {}
        for r in resultados:
            resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
        logging.info("Manifiestos procesados: %s", resumen)
