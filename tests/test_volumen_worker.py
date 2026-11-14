"""Volumen por el camino real on-premise: Excel «sucio» de 500 000 filas → worker → SQL local.

Lenta: solo corre si se define HUB_VOLUMEN. A diferencia de test_volumen.py (que usa un libro ya
en contrato v1), aquí el libro tiene el formato propio del área 1 (otros encabezados, fechas como
texto, sinónimos, papeletas mal escritas) y pasa por el mapeo, el saneamiento y el registro de
correcciones, igual que en producción.

  $env:HUB_VOLUMEN="500000"; pytest tests/test_volumen_worker.py -s
"""
import ctypes
import os
import time
from ctypes import wintypes
from datetime import date

import pytest
from openpyxl import Workbook

import procesador
import validacion
import worker
from almacenamiento import AlmacenLocal

FILAS = int(os.environ.get("HUB_VOLUMEN", "0"))
pytestmark = pytest.mark.skipif(not FILAS, reason="defina HUB_VOLUMEN para correrla")


def pico_mb():
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


def generar_sucio(destino, filas, fila_mala=None):
    """Libro del área 1 con su formato propio y suciedad realista."""
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Datos")
    ws.append(["N° Recibo", "Papeleta", "Concepto", "Importe", "Fecha de pago", "Situación",
               "Referencia", "Observación"])
    d = date(2026, 10, 1)
    for i in range(1, filas + 1):
        papeleta = (" p-1 ", "P0002", "P3")[i % 3]                       # 2 de 3 necesitan normalizarse
        fecha = d.strftime("%d/%m/%Y") if i % 2 else d                   # mitad texto dd/mm/aaaa
        importe = "treinta soles" if fila_mala and i + 1 == fila_mala else round(0.01 + (i % 50) / 100, 2)
        ws.append([f"R-{i:07d}", papeleta, "Abono", importe, fecha, "Vigente", f"REC{i:07d}",
                   "Pago de prueba de volumen"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


def test_volumen_por_el_worker(hub, tmp_path, monkeypatch):
    for mod in (validacion, procesador):
        monkeypatch.setattr(mod, "MAX_BYTES", 200 * 1024 * 1024, raising=False)
    monkeypatch.setattr(validacion, "MAX_EXPANDIDO", 2048 * 1024 * 1024)
    cfg = worker.cargar_config()
    worker.registrar_fuentes(cfg)
    datos = tmp_path / "datos"
    origen = datos / "areas" / "Area01" / "Tesoreria_movimientos.xlsx"
    print(f"\n=== Volumen por el worker: {FILAS:,} filas ===")

    t0 = time.perf_counter()
    generar_sucio(origen, FILAS)
    print(f"Generar el Excel sucio: {time.perf_counter() - t0:.0f} s · {origen.stat().st_size / 1048576:.1f} MiB")

    # Etapa 1: detectar, mapear, sanear y dejar raw + manifiesto
    t0 = time.perf_counter()
    creados = worker.encolar_cambios(cfg, datos)
    t_mapeo = time.perf_counter() - t0
    r = creados[0]
    print(f"[1] Mapeo y saneamiento: {t_mapeo:.0f} s · filas={r['filas_leidas']:,} · "
          f"correcciones={r['correcciones']:,} · pico de memoria {pico_mb():,.0f} MiB")

    # Etapa 2: validar todas las filas, cargar y publicar
    t0 = time.perf_counter()
    res = procesador.procesar_pendientes(almacen=AlmacenLocal(datos))
    t_proc = time.perf_counter() - t0
    estado = res[0]["estado"]
    n = hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0]
    print(f"[2] Validar + cargar + publicar: {t_proc:.0f} s · estado={estado} · movimientos={n:,} · "
          f"pico de memoria {pico_mb():,.0f} MiB")

    # Etapa 3: registro de correcciones en SQL
    t0 = time.perf_counter()
    guardadas = worker.guardar_correcciones(datos)
    t_corr = time.perf_counter() - t0
    print(f"[3] Registrar correcciones en SQL: {t_corr:.0f} s · {guardadas:,} filas")
    print(f"TOTAL Excel sucio → publicado: {t_mapeo + t_proc + t_corr:.0f} s")
    assert estado == "ACEPTADO" and n == FILAS

    # Lecturas con el volumen cargado
    for nombre, sql in [("saldo de una papeleta", "SELECT * FROM dbo.vDeuda WHERE PapeletaId='P0001'"),
                        ("detalle de 20 movimientos", "SELECT TOP 20 * FROM dbo.vMovimientoDetalle WHERE PapeletaId='P0002'"),
                        ("estado de las fuentes", "SELECT * FROM dbo.vEstadoFuentes")]:
        t0 = time.perf_counter()
        hub.sql(sql)
        print(f"  lectura · {nombre}: {(time.perf_counter() - t0) * 1000:.0f} ms")

    # Todo o nada: el área reenvía su libro con un monto ilegible en la fila 490 000
    antes = (hub.total(), hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0])
    time.sleep(1.1)                                   # nueva fecha de modificación del archivo
    generar_sucio(origen, FILAS, fila_mala=min(490_000, FILAS))
    t0 = time.perf_counter()
    creados = worker.encolar_cambios(cfg, datos)
    res = procesador.procesar_pendientes(almacen=AlmacenLocal(datos))
    seg = time.perf_counter() - t0
    lote = res[0]["lote"]
    obs = hub.sql("SELECT FilaExcel, Codigo FROM dbo.Observacion WHERE LoteId=?", lote)
    despues = (hub.total(), hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0])
    print(f"[fila {min(490_000, FILAS):,} ilegible] estado={res[0]['estado']} observaciones={[tuple(o) for o in obs]} "
          f"({seg:.0f} s) · antes={antes[1]:,} movimientos, después={despues[1]:,} · total igual: {antes[0] == despues[0]}")
    assert res[0]["estado"] == "RECHAZADO" and antes == despues
