"""Aplica las migraciones del hub en Azure SQL y crea los usuarios de las
identidades administradas (Function y ADF) con permisos mínimos.

Requiere `az login` con la cuenta administradora Entra del servidor y que la
IP del PC esté en el firewall (regla PcOnPremise del Bicep).

  python tools/desplegar_sql_azure.py --rg rg-hubdeuda-dev --deployment hubdeuda-infra
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
sys.path.insert(0, str(RAIZ / "tools"))


def salidas_despliegue(rg, nombre):
    az = "az.cmd" if os.name == "nt" else "az"
    r = subprocess.run([az, "deployment", "group", "show", "-g", rg, "-n", nombre,
                        "--query", "properties.outputs", "-o", "json"],
                       capture_output=True, text=True, check=True)
    return {k: v["value"] for k, v in json.loads(r.stdout).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rg", default="rg-hubdeuda-dev")
    ap.add_argument("--deployment", default="hubdeuda-infra")
    a = ap.parse_args()
    out = salidas_despliegue(a.rg, a.deployment)
    os.environ.pop("SQL_ODBC", None)
    os.environ["SQL_SERVER"] = out["sqlServer"]
    os.environ["SQL_DATABASE"] = out["sqlDatabase"]

    import aplicar_sql
    import sqlconn
    aplicar_sql.aplicar(str(RAIZ / "sql" / "hub"), out["sqlDatabase"])

    plantilla = (RAIZ / "sql" / "hub" / "900_usuarios_azure.sql.template").read_text(encoding="utf-8")
    texto = (plantilla.replace("{FUNC_NAME}", out["functionApp"])
             .replace("{FUNC_OBJECT_ID}", out["functionPrincipalId"])
             .replace("{ADF_NAME}", out["dataFactory"])
             .replace("{ADF_OBJECT_ID}", out["adfPrincipalId"]))
    with sqlconn.conectar() as cn:
        cur = cn.cursor()
        for lote in aplicar_sql.lotes_sql(texto):
            cur.execute(lote)
        filas = cur.execute("""SELECT m.name, r.name FROM sys.database_role_members x
            JOIN sys.database_principals r ON r.principal_id=x.role_principal_id
            JOIN sys.database_principals m ON m.principal_id=x.member_principal_id
            WHERE r.name LIKE 'rol_hub_%'""").fetchall()
    print("Miembros de roles:", [(m, r) for m, r in filas])


if __name__ == "__main__":
    main()
