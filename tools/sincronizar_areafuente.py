"""Copia a dbo.AreaFuente el archivo autorizado de cada área (espejo de la
lista ConfigAreas). Lee infra/sharepoint.local.json, generado por
tools/provisionar_sharepoint.ps1. Usa la sesión de `az login`.

  python tools/sincronizar_areafuente.py
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
sys.path.insert(0, str(RAIZ / "tools"))

from desplegar_sql_azure import salidas_despliegue  # noqa: E402


def main():
    cfg = json.loads((RAIZ / "infra" / "sharepoint.local.json").read_text(encoding="utf-8-sig"))
    out = salidas_despliegue("rg-hubdeuda-dev", "hubdeuda-infra")
    os.environ.pop("SQL_ODBC", None)
    os.environ["SQL_SERVER"] = out["sqlServer"]
    os.environ["SQL_DATABASE"] = out["sqlDatabase"]
    import sqlconn
    with sqlconn.conectar() as cn:
        cur = cn.cursor()
        for a in cfg["areas"]:
            cur.execute("""MERGE dbo.AreaFuente AS t
                USING (SELECT ? AS AreaId) AS s ON t.AreaId=s.AreaId
                WHEN MATCHED THEN UPDATE SET ArchivoId=?, RutaArchivo=?, Activa=1
                WHEN NOT MATCHED THEN INSERT (AreaId, ArchivoId, RutaArchivo, Activa) VALUES (?,?,?,1);""",
                        a["areaId"], a["uniqueId"], a["rutaArchivo"],
                        a["areaId"], a["uniqueId"], a["rutaArchivo"])
        n = cur.execute("SELECT COUNT(*) FROM dbo.AreaFuente WHERE Activa=1").fetchone()[0]
    print(f"AreaFuente sincronizada: {n} áreas activas")


if __name__ == "__main__":
    main()
