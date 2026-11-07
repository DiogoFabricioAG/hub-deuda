"""Conexiones SQL compartidas por herramientas, pruebas y la Function.

Modos:
- Local (SQL Server Express): SQL_ODBC="Driver=...;Server=localhost\\SQLEXPRESS;Trusted_Connection=yes;..."
- Azure SQL con token Entra: SQL_SERVER y SQL_DATABASE (DefaultAzureCredential:
  `az login` en desarrollo, identidad administrada en Azure).
Nunca se guardan contraseñas en el repositorio.
"""
import os
import struct

import pyodbc

SQL_COPT_SS_ACCESS_TOKEN = 1256
DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")


def driver_odbc():
    disponibles = set(pyodbc.drivers())
    for d in DRIVERS_PREFERIDOS:
        if d in disponibles:
            return d
    raise RuntimeError("Falta ODBC Driver 17/18 for SQL Server")


def cadena_local(database="master", server=r"localhost\SQLEXPRESS"):
    return (f"Driver={{{driver_odbc()}}};Server={server};Database={database};"
            "Trusted_Connection=yes;Encrypt=no;")


def conectar(database=None, autocommit=True, timeout=30):
    """Abre una conexión. Por defecto autocommit=True: las transacciones se
    controlan con BEGIN TRAN/COMMIT explícitos en el código de publicación."""
    odbc = os.environ.get("SQL_ODBC")
    if odbc:
        cs = odbc if database is None else _reemplazar_db(odbc, database)
        return pyodbc.connect(cs, autocommit=autocommit, timeout=timeout)
    server = os.environ["SQL_SERVER"]
    db = database or os.environ["SQL_DATABASE"]
    token = _credencial().get_token("https://database.windows.net/.default").token
    raw = token.encode("utf-16-le")
    token_struct = struct.pack("<I", len(raw)) + raw
    cs = (f"Driver={{{driver_odbc()}}};Server=tcp:{server},1433;Database={db};"
          "Encrypt=yes;TrustServerCertificate=no;")
    return pyodbc.connect(cs, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct},
                          autocommit=autocommit, timeout=timeout)


_cred = None


def _credencial():
    global _cred
    if _cred is None:
        from azure.identity import DefaultAzureCredential
        _cred = DefaultAzureCredential()
    return _cred


def _reemplazar_db(cs, database):
    partes = [p for p in cs.split(";") if p and not p.lower().startswith("database=")]
    partes.append(f"Database={database}")
    return ";".join(partes) + ";"
