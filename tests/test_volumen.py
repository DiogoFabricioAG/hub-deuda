"""Prueba de volumen: libro de 500 000 filas contra SQL Server Express local.

Lenta: solo corre si se define HUB_VOLUMEN (p. ej. 500000). Mide generación,
validación, carga y publicación, y comprueba el «todo o nada» con una fila
corrupta cerca del final.

  $env:HUB_VOLUMEN="500000"; pytest tests/test_volumen.py -s
"""
import ctypes
import os
import time
from ctypes import wintypes
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

import procesador
import validacion
from plantillas import COLUMNAS

FILAS = int(os.environ.get("HUB_VOLUMEN", "0"))
pytestmark = pytest.mark.skipif(not FILAS, reason="defina HUB_VOLUMEN para correrla")


def pico_memoria_mb():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    p = PMC()
    p.cb = ctypes.sizeof(PMC)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(p), p.cb)
    return p.PeakWorkingSetSize / 1024 / 1024


def generar(filas, fila_corrupta=None):
    """Libro con el contrato v1 (hoja Datos, tabla tblMovimientos), modo escritura."""
    from io import BytesIO
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Datos")
    ws.append(COLUMNAS)
    f = date(2026, 10, 1)
    for i in range(1, filas + 1):
        monto = Decimal("0.01") + Decimal(i % 50) / 100
        if fila_corrupta and i + 1 == fila_corrupta:
            monto = Decimal("-5.00")                  # PAGO negativo: inválido
        ws.append([f"VOL{i:07d}", f"P000{(i % 3) + 1}", "PAGO", float(monto), f, "ACTIVO",
                   f"REF{i:07d}", "Pago de prueba de volumen"])
    t = Table(displayName="tblMovimientos", ref=f"A1:H{filas + 1}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(t)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_volumen(hub, monkeypatch):
    print(f"\n=== Prueba de volumen: {FILAS:,} filas ===")
    t0 = time.perf_counter()
    datos = generar(FILAS)
    print(f"Generar el libro: {time.perf_counter() - t0:.1f} s · tamaño {len(datos) / 1024 / 1024:.1f} MiB")

    # 1. Con los límites actuales (10 MiB) el archivo se rechaza completo.
    lote0, _, _ = hub.cargar(1, datos=datos)
    t0 = time.perf_counter()
    hub.procesar()
    print(f"[límite actual 10 MiB] estado={hub.estado(lote0)} códigos={hub.codigos(lote0)} "
          f"({time.perf_counter() - t0:.1f} s)")

    # 2. Con los límites ampliados (propuesta para la versión on-premise).
    for mod in (validacion, procesador):
        monkeypatch.setattr(mod, "MAX_BYTES", 200 * 1024 * 1024, raising=False)
    monkeypatch.setattr(validacion, "MAX_EXPANDIDO", 2048 * 1024 * 1024)
    lote1, datos1, _ = hub.cargar(1, datos=datos)
    t0 = time.perf_counter()
    hub.procesar()
    seg = time.perf_counter() - t0
    estado = hub.estado(lote1)
    n = hub.sql("SELECT COUNT(*) FROM dbo.Movimiento WHERE LoteId=?", lote1)[0][0]
    print(f"[límites ampliados] estado={estado} filas={n:,} validar+cargar+publicar={seg:.1f} s "
          f"({n / seg:,.0f} filas/s) · pico de memoria {pico_memoria_mb():,.0f} MiB")
    print(f"  errores: {sorted(hub.codigos(lote1))}")
    assert estado == "ACEPTADO" and n == FILAS

    # 3. Lecturas sobre el volumen cargado.
    for nombre, sql in [("saldo de una papeleta (vDeuda)", "SELECT * FROM dbo.vDeuda WHERE PapeletaId='P0001'"),
                        ("total de todas las papeletas", "SELECT SUM(Saldo) FROM dbo.vDeuda"),
                        ("detalle de movimientos de una papeleta (20)",
                         "SELECT TOP 20 * FROM dbo.vMovimientoDetalle WHERE PapeletaId='P0002'")]:
        t0 = time.perf_counter()
        filas = hub.sql(sql)
        print(f"  lectura · {nombre}: {(time.perf_counter() - t0) * 1000:.0f} ms ({len(filas)} filas)")

    # 4. Todo o nada: fila 490 000 corrupta en un libro nuevo del mismo tamaño.
    fila_mala = min(490_000, FILAS)
    corrupto = generar(FILAS, fila_corrupta=fila_mala)
    antes = (hub.total(), hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0])
    lote2, _, _ = hub.cargar(1, datos=corrupto)
    t0 = time.perf_counter()
    hub.procesar()
    seg = time.perf_counter() - t0
    despues = (hub.total(), hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0])
    obs = hub.sql("SELECT FilaExcel, Codigo FROM dbo.Observacion WHERE LoteId=?", lote2)
    print(f"[fila {fila_mala:,} corrupta] estado={hub.estado(lote2)} observaciones={[tuple(o) for o in obs]} "
          f"({seg:.1f} s)")
    print(f"  antes: total={antes[0]} movimientos={antes[1]:,} · después: total={despues[0]} "
          f"movimientos={despues[1]:,}")
    assert hub.estado(lote2) == "RECHAZADO"
    assert antes == despues
