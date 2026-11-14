"""Da al servicio del gateway de datos acceso de SOLO LECTURA a las vistas del hub local.

Usa la autenticación de Windows del usuario que lo ejecuta (debe ser administrador de SQL
Server). No usa ni guarda contraseñas.

  python tools/onprem_gateway_acceso.py --cuenta "NT SERVICE\\PBIEgwService" --bd HubDeuda_dev

La cuenta por defecto es la del servicio del gateway estándar. Si al instalarlo se eligió
otra cuenta, indíquela con --cuenta (DOMINIO\\usuario).
"""
import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
import os  # noqa: E402

import sqlconn  # noqa: E402

GO = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuenta", default=r"NT SERVICE\PBIEgwService")
    ap.add_argument("--bd", default="HubDeuda_dev")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_ .\\$-]{3,128}", a.cuenta) or not re.fullmatch(r"\w{1,100}", a.bd):
        raise SystemExit("Cuenta o base con caracteres no permitidos")
    os.environ["SQL_ODBC"] = sqlconn.cadena_local("master")
    texto = (RAIZ / "sql" / "onprem" / "gateway_acceso.sql").read_text(encoding="utf-8")
    texto = texto.replace("{CUENTA}", a.cuenta).replace("{BD}", a.bd)
    with sqlconn.conectar("master", autocommit=True) as cn:
        cur = cn.cursor()
        for lote in (b.strip() for b in GO.split(texto)):
            if lote:
                cur.execute(lote)
                while cur.nextset():
                    pass
    print(f"Listo: {a.cuenta} tiene solo lectura sobre las vistas de {a.bd}.")


if __name__ == "__main__":
    main()
