"""Genera Excel «sucios» de tres áreas con formatos distintos (datos ficticios).

Cada área tiene sus propios encabezados y escribe fechas y montos a su manera:
  Área 1 Tesorería: encabezados en la fila 1, montos como «S/ 30.00», fechas dd/mm/aaaa.
  Área 2 Coactiva: otros encabezados, montos con coma decimal («15,50»), tipo «Recargo».
  Área 7 Adm. Tributaria: título en las filas 1–2 y encabezados en la fila 3.
Incluye filas en blanco, espacios sobrantes y un duplicado exacto para que el
saneamiento tenga algo que corregir.

  python onprem/datos_demo.py [--datos datos_onprem] [--con-error]
"""
import argparse
import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "onprem"))


def _guardar(filas, ruta):
    wb = Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)


def area1(datos, con_error=False):
    filas = [
        ["N° Recibo", "Papeleta", "Concepto", "Importe", "Fecha de pago", "Situación", "Referencia", "Observación"],
        ["R-001", " p-1 ", "abono", "S/ 30.00", "07/11/2026", "Vigente", "REC001", "Pago parcial"],
        ["R-002", "P0002", "Pago", "50,00", date(2026, 11, 8), "vigente", "REC002", None],
        [None] * 8,
        ["R-002", "P0002", "Pago", "50,00", date(2026, 11, 8), "vigente", "REC002", None],   # duplicado exacto
        ["R-003 ", "P3", "Cancelación", 20, "2026-11-09", "ANULADA", "REC003", "Anulado por error"],
    ]
    if con_error:
        filas.append(["R-004", "P0001", "Pago", "treinta soles", "10/11/2026", "Vigente", "REC004", None])
    _guardar(filas, datos / "areas" / "Area01" / "Tesoreria_movimientos.xlsx")


def area2(datos, con_error=False):
    filas = [
        ["ID", "Nro Papeleta", "Tipo mov", "Monto (S/)", "Fecha", "Estado", "Operación", "Glosa"],
        ["C-100", "P0003", "Recargo", "15,50", "05/11/2026", "Activo", "OP-9", "Recargo por mora"],
        ["C-101", "p0002", "Interés", "S/ 1.234,50", "06/11/2026", "Vigente", "OP-10", "Interés acumulado"],
    ]
    if con_error:
        filas.append(["C-102", "P0002", "Mora", -5, "07/11/2026", "Activo", "OP-11", None])
    _guardar(filas, datos / "areas" / "Area02" / "Coactiva_cargos.xlsx")


def area7(datos, con_error=False):
    filas = [
        ["Descuentos aprobados", None, None, None, None, None, None, None],
        [None] * 8,
        ["Cod", "Papeleta ID", "Clase", "Descuento aplicado", "Fecha resolución", "Estado", "Resolución", "Motivo"],
        ["D-1", "P0001", "Rebaja", "10,00", "01.11.2026", "Vigente", "RES-77", "Pronto pago"],
    ]
    _guardar(filas, datos / "areas" / "Area07" / "AdmTributaria_descuentos.xlsx")


def generar(datos, con_error=False):
    datos = Path(datos)
    area1(datos, con_error)
    area2(datos, con_error)
    area7(datos, con_error)
    return datos


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(RAIZ / "datos_onprem"))
    ap.add_argument("--con-error", action="store_true")
    a = ap.parse_args()
    print("Excel de demostración en", generar(a.datos, a.con_error))
