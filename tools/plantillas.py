"""Genera el libro controlado movimientos.xlsx (6.2) y libros de prueba.

  python tools/plantillas.py --salida powerplatform/plantillas   # 10 plantillas vacías

La hoja Datos contiene la tabla tblMovimientos con los 8 encabezados del
contrato, columnas de identificadores en formato Texto y validación de datos
para Tipo, Estado, Monto y FechaEvento.
"""
import argparse
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

COLUMNAS = ["MovimientoId", "PapeletaId", "Tipo", "Monto",
            "FechaEvento", "Estado", "Referencia", "Detalle"]
TIPO_AREA = {1: "PAGO", 2: "CARGO", 7: "DESCUENTO"}
FILAS_FORMATEADAS = 500


def libro(filas=(), area=1, encabezados=COLUMNAS, nombre_tabla="tblMovimientos",
          hoja="Datos", con_formula=False):
    """Devuelve bytes de un .xlsx. filas: lista de listas/tuplas en orden COLUMNAS."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(list(encabezados))
    for f in filas:
        ws.append(list(f))
    if con_formula and filas:
        ws.cell(row=2, column=4).value = "=10+20"
    ultima = max(len(filas) + 1, 2)
    for col in ("A", "B", "G", "H"):          # identificadores y textos: Texto
        for r in range(2, FILAS_FORMATEADAS + 2):
            ws[f"{col}{r}"].number_format = "@"
    for r in range(2, FILAS_FORMATEADAS + 2):
        ws[f"D{r}"].number_format = "0.00"
        ws[f"E{r}"].number_format = "yyyy-mm-dd"
    tipos = sorted({"OBSERVACION", TIPO_AREA.get(area, "OBSERVACION")})
    dv_tipo = DataValidation(type="list", formula1='"' + ",".join(tipos) + '"', allow_blank=False)
    dv_estado = DataValidation(type="list", formula1='"ACTIVO,ANULADO"', allow_blank=False)
    dv_monto = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0")
    dv_fecha = DataValidation(type="date", operator="lessThanOrEqual", formula1="TODAY()")
    for dv, col in ((dv_tipo, "C"), (dv_estado, "F"), (dv_monto, "D"), (dv_fecha, "E")):
        dv.error = "Valor fuera del contrato v1"
        dv.showErrorMessage = True
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{FILAS_FORMATEADAS + 1}")
    if nombre_tabla:
        t = Table(displayName=nombre_tabla, ref=f"A1:H{ultima}")
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)
    for i, ancho in enumerate((14, 12, 14, 10, 12, 10, 18, 40), start=1):
        ws.column_dimensions[chr(64 + i)].width = ancho
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def mov(mid, pap, tipo, monto, estado="ACTIVO", ref=None, fecha=date(2026, 11, 7), detalle=""):
    return [mid, pap, tipo, monto, fecha, estado, ref or f"REF-{mid}", detalle]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="powerplatform/plantillas")
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    for area in range(1, 11):
        p = out / f"Area{area:02d}" / "movimientos.xlsx"
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(libro(area=area))
    print(f"10 plantillas en {out}")


if __name__ == "__main__":
    main()
