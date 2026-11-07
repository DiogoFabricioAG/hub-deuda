"""Publica la base ficticia de BDOrigen (SQL Express local) en Azure SQL con
los mismos procedimientos que usa Data Factory, SIN pasar por el SHIR.

Solo para demostración mientras el SHIR no esté instalado: no prueba la ruta
on-premise (la guía lo advierte en 8.6). Cuando ADF cargue la base, su corte
será posterior y reemplazará a esta carga sin conflicto.

  python tools/cargar_base_directa_azure.py
"""
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
sys.path.insert(0, str(RAIZ / "tools"))

import pyodbc  # noqa: E402

from desplegar_sql_azure import salidas_despliegue  # noqa: E402


def main():
    out = salidas_despliegue("rg-hubdeuda-dev", "hubdeuda-infra")
    os.environ.pop("SQL_ODBC", None)
    os.environ["SQL_SERVER"] = out["sqlServer"]
    os.environ["SQL_DATABASE"] = out["sqlDatabase"]
    import sqlconn
    origen = pyodbc.connect(sqlconn.cadena_local("BDOrigen"), autocommit=True)
    oc = origen.cursor()
    export_id, corte, n = oc.execute("EXEC dbo.usp_CrearExportacion").fetchone()
    filas = oc.execute("""SELECT PapeletaId,TipoDoc,Documento,Placa,ImporteOriginal,Activa
        FROM dbo.DeudaExport WHERE ExportId=?""", export_id).fetchall()
    origen.close()
    carga = str(uuid.uuid4())
    with sqlconn.conectar() as cn:
        cur = cn.cursor()
        try:
            cur.execute("EXEC dbo.usp_IniciarBaseCarga ?, ?, ?", carga, corte, n)
            cur.executemany("""INSERT dbo.BaseFila (CargaId,PapeletaId,TipoDoc,Documento,Placa,
                ImporteOriginal,Activa) VALUES (?,?,?,?,?,?,?)""", [(carga, *tuple(f)) for f in filas])
            cur.execute("EXEC dbo.usp_PublicarBase ?", carga)
        except Exception as exc:
            cur.execute("EXEC dbo.usp_MarcarBaseFallida ?, ?", carga, str(exc)[:500])
            raise
        total = cur.execute("SELECT COUNT(*), SUM(ImporteOriginal) FROM dbo.vBaseVigente").fetchone()
    print(f"Base publicada en Azure SQL (carga directa, sin SHIR): {total[0]} papeletas, total {total[1]}")


if __name__ == "__main__":
    main()
