"""Simula localmente el pipeline pl_base_completa de Data Factory (8.4–8.5).

Mismos pasos que adf/pipeline/pl_base_completa.json:
 1. Lookup: EXEC usp_CrearExportacion en el origen (fotografía consistente).
 2. usp_IniciarBaseCarga en el hub con CargaId, CorteUtc y FilasEsperadas.
 3. Copy: DeudaExport del ExportId → BaseFila con la columna CargaId.
 4. usp_PublicarBase; si algo falla, usp_MarcarBaseFallida (puntero intacto).
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
import pyodbc  # noqa: E402

import sqlconn  # noqa: E402


def cargar(hub_db, origen_db="BDOrigen", server=r"localhost\SQLEXPRESS", carga_id=None):
    carga_id = carga_id or str(uuid.uuid4())
    origen = pyodbc.connect(sqlconn.cadena_local(origen_db, server), autocommit=True)
    oc = origen.cursor()
    export_id, corte, n = oc.execute("EXEC dbo.usp_CrearExportacion").fetchone()
    filas = oc.execute("""SELECT PapeletaId,TipoDoc,Documento,Placa,ImporteOriginal,Activa
                          FROM dbo.DeudaExport WHERE ExportId=?""", export_id).fetchall()
    origen.close()

    hub = pyodbc.connect(sqlconn.cadena_local(hub_db, server), autocommit=True)
    hc = hub.cursor()
    try:
        hc.execute("EXEC dbo.usp_IniciarBaseCarga @CargaId=?, @CorteUtc=?, @FilasEsperadas=?",
                   carga_id, corte, n)
        if filas:
            hc.fast_executemany = True
            hc.executemany("""INSERT dbo.BaseFila (CargaId,PapeletaId,TipoDoc,Documento,Placa,
                              ImporteOriginal,Activa) VALUES (?,?,?,?,?,?,?)""",
                           [(carga_id, *tuple(f)) for f in filas])
            hc.fast_executemany = False
        hc.execute("EXEC dbo.usp_PublicarBase @CargaId=?", carga_id)
        while hc.nextset():
            pass
        return carga_id, n
    except Exception as exc:
        hc.execute("EXEC dbo.usp_MarcarBaseFallida @CargaId=?, @Motivo=?", carga_id, str(exc)[:500])
        raise
    finally:
        hub.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", default="HubDeuda_dev")
    ap.add_argument("--origen", default="BDOrigen")
    a = ap.parse_args()
    cid, n = cargar(a.hub, a.origen)
    print(f"Base publicada: CargaId={cid} filas={n}")
