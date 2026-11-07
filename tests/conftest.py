"""Entorno de pruebas del núcleo contra SQL Server Express local.

Cada prueba recrea HubDeuda_test y BDOrigen_test, aplica las migraciones,
registra los archivos autorizados de las 10 áreas y publica la base inicial
(3 papeletas, total 430.00). Requiere localhost\\SQLEXPRESS con autenticación
de Windows. No toca HubDeuda_dev ni BDOrigen.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyodbc
import pytest

# Las pruebas borran y recrean bases: una conexión reutilizada del pool ODBC
# quedaría cortada y el driver devolvería el error 4083 al "recuperarla".
pyodbc.pooling = False

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "functions"))
sys.path.insert(0, str(RAIZ / "tools"))

import aplicar_sql  # noqa: E402
import cargar_base_local  # noqa: E402
import procesador  # noqa: E402
import sqlconn  # noqa: E402
from almacenamiento import AlmacenLocal  # noqa: E402
import plantillas  # noqa: E402

HUB_DB = "HubDeuda_test"
ORIGEN_DB = "BDOrigen_test"


def _recrear(nombre):
    assert nombre.endswith("_test"), "solo se recrean bases de prueba"
    with sqlconn.conectar("master") as cn:
        cur = cn.cursor()
        cur.execute(f"""IF DB_ID('{nombre}') IS NOT NULL BEGIN
            ALTER DATABASE [{nombre}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE [{nombre}]; END""")
        cur.execute(f"CREATE DATABASE [{nombre}]")


class Hub:
    """Ayudante: carga libros como lo haría Power Automate y consulta saldos."""

    def __init__(self, raiz):
        self.almacen = AlmacenLocal(raiz)
        self.raiz = Path(raiz)
        self.reloj = datetime(2026, 11, 7, 12, 0, 0)

    def sql(self, consulta, *params):
        with sqlconn.conectar() as cn:
            return cn.cursor().execute(consulta, *params).fetchall()

    def cargar(self, area, filas=(), datos=None, modificado=None, version=None,
               archivo=None, **kw):
        """Copia el libro a raw/ y escribe el manifiesto al final (9.4–9.5)."""
        lote = str(uuid.uuid4())
        if modificado is None:
            self.reloj += timedelta(minutes=5)
            modificado = self.reloj
        datos = datos if datos is not None else plantillas.libro(filas, area=area, **kw)
        ruta = f"area{area:02d}/2026/11/07/{lote}.xlsx"
        p = self.raiz / "raw" / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
        man = {"loteId": lote, "areaId": area,
               "sourceFileId": archivo or f"file-area{area:02d}",
               "sourceVersion": version or modificado.strftime("%Y%m%d%H%M%S"),
               "sourceModifiedUtc": modificado.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "rawContainer": "raw", "rawPath": ruta, "contractVersion": "1",
               "flowRunId": "prueba", "requestedBy": "pytest"}
        m = self.raiz / "manifests" / f"{lote}.json"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(json.dumps(man), encoding="utf-8")
        return lote, datos, modificado

    def procesar(self):
        return procesador.procesar_pendientes(almacen=self.almacen)

    def estado(self, lote):
        r = self.sql("SELECT Estado FROM dbo.Lote WHERE LoteId=?", lote)
        return r[0][0] if r else None

    def saldo(self, papeleta="P0001"):
        return self.sql("SELECT Saldo FROM dbo.vDeuda WHERE PapeletaId=?", papeleta)[0][0]

    def total(self):
        return self.sql("SELECT SUM(Saldo) FROM dbo.vDeuda")[0][0]

    def codigos(self, lote):
        return {r[0] for r in self.sql("SELECT Codigo FROM dbo.Observacion WHERE LoteId=?", lote)}


@pytest.fixture
def hub(tmp_path):
    os.environ["SQL_ODBC"] = sqlconn.cadena_local(HUB_DB)
    _recrear(ORIGEN_DB)
    _recrear(HUB_DB)
    with sqlconn.conectar("master") as cn:
        cn.cursor().execute(f"ALTER DATABASE [{ORIGEN_DB}] SET ALLOW_SNAPSHOT_ISOLATION ON")
    aplicar_sql.aplicar(str(RAIZ / "sql" / "origen"), ORIGEN_DB)
    aplicar_sql.aplicar(str(RAIZ / "sql" / "hub"), HUB_DB)
    with sqlconn.conectar() as cn:
        cn.cursor().executemany(
            "INSERT dbo.AreaFuente (AreaId, ArchivoId, RutaArchivo) VALUES (?,?,?)",
            [(a, f"file-area{a:02d}", f"Entradas/Area{a:02d}/movimientos.xlsx") for a in range(1, 11)])
    cargar_base_local.cargar(HUB_DB, ORIGEN_DB)
    procesador._HOOKS.clear()
    yield Hub(tmp_path)
    procesador._HOOKS.clear()


D = Decimal
