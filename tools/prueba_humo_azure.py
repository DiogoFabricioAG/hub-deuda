"""Prueba de humo de punta a punta en Azure (datos ficticios).

1. Publica la base ficticia de BDOrigen local en Azure SQL con los mismos
   procedimientos que usa ADF (mientras el SHIR no está instalado).
2. Registra un archivo autorizado de prueba para el área 01.
3. Sube a Blob un libro de Tesorería (PAGO 30 a P0001) y luego su manifiesto,
   como lo hará Power Automate.
4. Espera a que la Function publicada procese el lote y verifica P0001 = 70.

Deja datos de prueba: limpiar con tools/reiniciar_datos_hub.py antes de cargar
las plantillas reales de SharePoint.
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
sys.path.insert(0, str(RAIZ / "tools"))

import pyodbc  # noqa: E402
from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.storage.blob import BlobServiceClient  # noqa: E402

from desplegar_sql_azure import salidas_despliegue  # noqa: E402
from plantillas import libro, mov  # noqa: E402


def main():
    out = salidas_despliegue("rg-hubdeuda-dev", "hubdeuda-infra")
    os.environ.pop("SQL_ODBC", None)
    os.environ["SQL_SERVER"] = out["sqlServer"]
    os.environ["SQL_DATABASE"] = out["sqlDatabase"]
    import sqlconn

    with sqlconn.conectar() as cn:
        cur = cn.cursor()
        if cur.execute("SELECT CargaId FROM dbo.BaseActual").fetchone()[0] is None:
            origen = pyodbc.connect(sqlconn.cadena_local("BDOrigen"), autocommit=True)
            export_id, corte, n = origen.cursor().execute("EXEC dbo.usp_CrearExportacion").fetchone()
            filas = origen.cursor().execute("""SELECT PapeletaId,TipoDoc,Documento,Placa,ImporteOriginal,Activa
                FROM dbo.DeudaExport WHERE ExportId=?""", export_id).fetchall()
            origen.close()
            carga = str(uuid.uuid4())
            cur.execute("EXEC dbo.usp_IniciarBaseCarga ?, ?, ?", carga, corte, n)
            cur.executemany("""INSERT dbo.BaseFila (CargaId,PapeletaId,TipoDoc,Documento,Placa,
                ImporteOriginal,Activa) VALUES (?,?,?,?,?,?,?)""", [(carga, *tuple(f)) for f in filas])
            cur.execute("EXEC dbo.usp_PublicarBase ?", carga)
            print(f"Base publicada en Azure SQL: {n} papeletas (CargaId {carga})")
        cur.execute("""MERGE dbo.AreaFuente AS t USING (SELECT 1 AS AreaId) AS s ON t.AreaId=s.AreaId
            WHEN MATCHED THEN UPDATE SET ArchivoId='prueba-humo', Activa=1
            WHEN NOT MATCHED THEN INSERT (AreaId,ArchivoId,RutaArchivo) VALUES (1,'prueba-humo','prueba');""")
        antes = cur.execute("SELECT Saldo FROM dbo.vDeuda WHERE PapeletaId='P0001'").fetchone()[0]
    print(f"P0001 antes: {antes}")

    lote = str(uuid.uuid4())
    ahora = datetime.now(timezone.utc)
    ruta = f"area01/{ahora:%Y/%m/%d}/{lote}.xlsx"
    blob = BlobServiceClient(out["storageUrl"], credential=DefaultAzureCredential())
    blob.get_blob_client("raw", ruta).upload_blob(
        libro([mov("TES0001", "P0001", "PAGO", 30, ref="REC001")], area=1))
    manifiesto = {"loteId": lote, "areaId": 1, "sourceFileId": "prueba-humo",
                  "sourceVersion": "humo-1", "sourceModifiedUtc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "rawContainer": "raw", "rawPath": ruta, "contractVersion": "1",
                  "flowRunId": "prueba-humo", "requestedBy": "tools/prueba_humo_azure.py"}
    blob.get_blob_client("manifests", f"{lote}.json").upload_blob(json.dumps(manifiesto).encode())
    print(f"Lote {lote} subido; esperando a la Function (timer cada minuto)...")

    t0 = time.monotonic()
    while time.monotonic() - t0 < 300:
        time.sleep(15)
        with sqlconn.conectar() as cn:
            r = cn.cursor().execute("SELECT Estado FROM dbo.Lote WHERE LoteId=?", lote).fetchone()
            if r:
                saldo = cn.cursor().execute("SELECT Saldo FROM dbo.vDeuda WHERE PapeletaId='P0001'").fetchone()[0]
                print(f"Estado del lote: {r[0]} en {time.monotonic() - t0:.0f} s; P0001 ahora: {saldo}")
                return 0 if (r[0] == "ACEPTADO" and str(saldo) == "70.00") else 1
    print("La Function no procesó el lote en 5 minutos: revisar Application Insights")
    return 2


if __name__ == "__main__":
    sys.exit(main())
