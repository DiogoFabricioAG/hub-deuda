"""Vacía los datos (no el esquema) del hub en Azure SQL para repetir pruebas
desde cero (la guía pide reiniciar el conjunto entre corridas de T01–T08).
También borra de Blob solo los manifiestos/raw generados por pruebas
(flowRunId "prueba-humo" o "pytest"), para que la Function no los reprocese.

  python tools/reiniciar_datos_hub.py --confirmo-borrar-datos-de-prueba
"""
import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
sys.path.insert(0, str(RAIZ / "tools"))

from desplegar_sql_azure import salidas_despliegue  # noqa: E402

RUNS_DE_PRUEBA = {"prueba-humo", "pytest"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirmo-borrar-datos-de-prueba", action="store_true", required=True)
    ap.parse_args()
    out = salidas_despliegue("rg-hubdeuda-dev", "hubdeuda-infra")

    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient
    svc = BlobServiceClient(out["storageUrl"], credential=DefaultAzureCredential())
    mc = svc.get_container_client("manifests")
    borrados = 0
    for b in list(mc.list_blobs()):
        m = json.loads(mc.download_blob(b.name).readall())
        if m.get("flowRunId") in RUNS_DE_PRUEBA:
            mc.delete_blob(b.name)
            try:
                svc.get_blob_client("raw", m["rawPath"]).delete_blob()
            except Exception:
                pass
            borrados += 1
    print(f"Blobs de prueba borrados: {borrados} manifiestos con su raw")

    os.environ.pop("SQL_ODBC", None)
    os.environ["SQL_SERVER"] = out["sqlServer"]
    os.environ["SQL_DATABASE"] = out["sqlDatabase"]
    import sqlconn
    with sqlconn.conectar() as cn:
        cur = cn.cursor()
        cur.execute("""SET XACT_ABORT ON; BEGIN TRAN;
            DELETE dbo.Notificacion; DELETE dbo.Observacion; DELETE dbo.Movimiento;
            DELETE dbo.ProcesoManifiesto; DELETE dbo.CambioPuntero;
            UPDATE dbo.Area SET LoteVigente=NULL; DELETE dbo.Lote;
            UPDATE dbo.BaseActual SET CargaId=NULL; DELETE dbo.BaseFila; DELETE dbo.BaseCarga;
            DELETE dbo.AreaFuente WHERE ArchivoId='prueba-humo';
            COMMIT;""")
        n = cur.execute("SELECT COUNT(*) FROM dbo.Lote").fetchone()[0]
    print(f"Datos del hub vaciados (lotes restantes: {n}); el esquema y los roles se conservan")


if __name__ == "__main__":
    main()
