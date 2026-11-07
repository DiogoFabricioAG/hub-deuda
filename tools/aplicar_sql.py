"""Aplica migraciones SQL numeradas y registra cuáles ya se aplicaron.

Uso:
  python tools/aplicar_sql.py --carpeta sql/hub --db HubDeuda_dev [--crear]
  python tools/aplicar_sql.py --carpeta sql/origen --db BDOrigen --crear

Sin SQL_ODBC/SQL_SERVER definidos usa el SQL Server Express local con
autenticación de Windows. Un script ya aplicado cuyo contenido cambió se
reporta como error: las migraciones publicadas no se editan, se agrega otra.
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
import sqlconn  # noqa: E402

GO = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)


def lotes_sql(texto):
    return [b.strip() for b in GO.split(texto) if b.strip()]


def asegurar_local():
    if not os.environ.get("SQL_ODBC") and not os.environ.get("SQL_SERVER"):
        os.environ["SQL_ODBC"] = sqlconn.cadena_local()


def crear_bd(nombre, snapshot=False):
    if not re.fullmatch(r"[A-Za-z0-9_]{1,100}", nombre):
        raise SystemExit("Nombre de base inválido")
    with sqlconn.conectar("master") as cn:
        cur = cn.cursor()
        if cur.execute("SELECT DB_ID(?)", nombre).fetchone()[0] is None:
            cur.execute(f"CREATE DATABASE [{nombre}]")
            print(f"Base creada: {nombre}")
        if snapshot:
            cur.execute(f"ALTER DATABASE [{nombre}] SET ALLOW_SNAPSHOT_ISOLATION ON")


def aplicar(carpeta, db):
    scripts = sorted(p for p in Path(carpeta).glob("[0-8]*.sql"))
    with sqlconn.conectar(db) as cn:
        cur = cn.cursor()
        cur.execute("""IF OBJECT_ID('dbo.SchemaVersion') IS NULL
            CREATE TABLE dbo.SchemaVersion (Script nvarchar(200) PRIMARY KEY,
              Sha256 char(64) NOT NULL,
              AplicadoUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME())""")
        hechos = {r[0]: r[1] for r in cur.execute("SELECT Script, Sha256 FROM dbo.SchemaVersion")}
        for p in scripts:
            texto = p.read_text(encoding="utf-8")
            h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
            clave = f"{Path(carpeta).name}/{p.name}"
            if clave in hechos:
                if hechos[clave] != h:
                    raise SystemExit(f"{clave} cambió después de aplicarse; cree una migración nueva")
                continue
            cur.execute("SET XACT_ABORT ON; BEGIN TRAN;")
            try:
                for lote in lotes_sql(texto):
                    cur.execute(lote)
                    while cur.nextset():
                        pass
                cur.execute("INSERT dbo.SchemaVersion (Script, Sha256) VALUES (?, ?)", clave, h)
                cur.execute("COMMIT")
            except Exception:
                cur.execute("IF @@TRANCOUNT>0 ROLLBACK")
                raise
            print(f"Aplicado {clave}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--crear", action="store_true", help="crear la base si no existe (solo local)")
    ap.add_argument("--snapshot", action="store_true", help="habilitar SNAPSHOT (origen)")
    a = ap.parse_args()
    asegurar_local()
    if a.crear:
        crear_bd(a.db, a.snapshot)
    aplicar(a.carpeta, a.db)


if __name__ == "__main__":
    main()
