"""Validador del libro Excel de movimientos (Anexo B de la guía, ampliado).

Devuelve filas normalizadas, errores con código, SHA-256 de los bytes y el
número de filas no vacías leídas. No escribe en SQL: la publicación la hace
repositorio_sql dentro de la transacción bloqueada.
"""
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

REGLAS_VERSION = "v1"
CONTRATO_VERSION = "1"
COLUMNAS = ["MovimientoId", "PapeletaId", "Tipo", "Monto",
            "FechaEvento", "Estado", "Referencia", "Detalle"]
# Límites del libro. En Azure quedan en 10 MiB / 50 MiB; la versión on-premise los
# amplía con variables de entorno (500 000 filas ≈ 16 MiB, ≈ 100 MiB expandido).
MAX_BYTES = int(os.environ.get("HUB_MAX_BYTES", 10 * 1024 * 1024))
MAX_EXPANDIDO = int(os.environ.get("HUB_MAX_EXPANDIDO", 50 * 1024 * 1024))
LIMA = ZoneInfo("America/Lima")


@dataclass
class Resultado:
    filas: list = field(default_factory=list)
    errores: list = field(default_factory=list)
    huella: str = ""
    filas_leidas: int = 0

    @property
    def valido(self):
        return not self.errores


def validar(datos: bytes, area: int, papeletas: set, tipo_permitido: str,
            hoy: date | None = None) -> Resultado:
    res = Resultado(huella=sha256(datos).hexdigest())
    vistos, refs = set(), set()

    def error(n, campo, codigo, mensaje):
        res.errores.append({"fila": n, "campo": campo, "codigo": codigo,
                            "mensaje": mensaje})

    if area not in range(1, 11):
        error(0, "archivo", "AREA_DESCONOCIDA", "Área desconocida")
        return res
    try:
        if len(datos) > MAX_BYTES:
            raise ValueError("Archivo mayor que 10 MiB")
        with ZipFile(BytesIO(datos)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_EXPANDIDO:
                raise ValueError("Libro expandido demasiado grande")
        wb = load_workbook(BytesIO(datos), data_only=False)
    except (ValueError, KeyError, BadZipFile, OSError) as exc:
        error(0, "archivo", "ARCHIVO_INVALIDO",
              f"No se pudo abrir el libro: {exc}"[:500])
        return res
    try:
        if "Datos" not in wb.sheetnames:
            raise KeyError("Falta la hoja Datos")
        ws = wb["Datos"]
        if "tblMovimientos" not in ws.tables:
            raise KeyError("Falta la tabla tblMovimientos")
        rango = list(ws[ws.tables["tblMovimientos"].ref])
        if [c.value for c in rango[0]] != COLUMNAS:
            error(0, "archivo", "ENCABEZADOS",
                  "Encabezados u orden distintos al contrato v1")
            return res
    except KeyError as exc:
        error(0, "archivo", "ESTRUCTURA", str(exc).strip("'\""))
        return res

    hoy = hoy or datetime.now(LIMA).date()
    permitidos = {"OBSERVACION", tipo_permitido}
    for celdas in rango[1:]:
        if all(c.value is None for c in celdas):
            continue
        res.filas_leidas += 1
        n = celdas[0].row
        inicio = len(res.errores)
        if any(c.data_type == "f" for c in celdas):
            error(n, "fila", "FORMULA", "No se admiten fórmulas en los campos del contrato")
            continue
        r = dict(zip(COLUMNAS, [c.value for c in celdas]))

        for campo, limite in [("MovimientoId", 50), ("PapeletaId", 30), ("Referencia", 100)]:
            v = r[campo]
            if not isinstance(v, str) or not v.strip():
                error(n, campo, "TEXTO_REQUERIDO",
                      "Debe ser texto no vacío (formatee la columna como Texto)")
                r[campo] = ""
            else:
                r[campo] = v.strip()
                if len(r[campo]) > limite:
                    error(n, campo, "LONGITUD", f"Máximo {limite} caracteres")
        mid = r["MovimientoId"]
        if mid and mid in vistos:
            error(n, "MovimientoId", "DUPLICADO", "Identificador duplicado en el libro")
        vistos.add(mid)
        if r["PapeletaId"] and r["PapeletaId"] not in papeletas:
            error(n, "PapeletaId", "PAPELETA_INEXISTENTE", "No existe en la base vigente")
        tipo = str(r["Tipo"] or "").strip().upper()
        estado = str(r["Estado"] or "").strip().upper()
        if tipo not in permitidos:
            error(n, "Tipo", "TIPO_NO_AUTORIZADO",
                  f"Tipo no autorizado para el área (use {' u '.join(sorted(permitidos))})")
        if estado not in {"ACTIVO", "ANULADO"}:
            error(n, "Estado", "ESTADO_INVALIDO", "Use ACTIVO o ANULADO")
        try:
            if isinstance(r["Monto"], bool) or r["Monto"] is None:
                raise ValueError()
            monto = Decimal(str(r["Monto"]).strip())
            if not monto.is_finite() or abs(monto) >= Decimal("10000000000000000"):
                raise ValueError()
            if monto != monto.quantize(Decimal("0.01")):
                raise ValueError()
            monto = monto.quantize(Decimal("0.01"))
            if tipo == "OBSERVACION" and monto != 0:
                raise ValueError()
            if tipo != "OBSERVACION" and monto <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError, TypeError):
            error(n, "Monto", "MONTO_INVALIDO",
                  "Monto incompatible: PAGO/CARGO/DESCUENTO > 0, OBSERVACION = 0, máximo 2 decimales")
            monto = Decimal("0")
        if tipo != "OBSERVACION" and estado == "ACTIVO" and r["Referencia"]:
            clave = (tipo, r["Referencia"])
            if clave in refs:
                error(n, "Referencia", "REFERENCIA_REPETIDA", "Operación económica repetida")
            refs.add(clave)
        try:
            f = r["FechaEvento"]
            if isinstance(f, datetime):
                f = f.date()
            elif isinstance(f, str):
                f = date.fromisoformat(f.strip())
            if not isinstance(f, date) or f > hoy:
                raise ValueError()
        except (ValueError, TypeError):
            error(n, "FechaEvento", "FECHA_INVALIDA", "Fecha inválida o futura (AAAA-MM-DD)")
            f = hoy
        detalle = str(r["Detalle"] or "").strip()
        if len(detalle) > 250:
            error(n, "Detalle", "LONGITUD", "Máximo 250 caracteres")
        if len(res.errores) == inicio:
            res.filas.append({
                "MovimientoId": mid, "PapeletaId": r["PapeletaId"],
                "Tipo": tipo, "Monto": monto, "FechaEvento": f,
                "Estado": estado, "Referencia": r["Referencia"],
                "Detalle": detalle or None, "FilaExcel": n})
    wb.close()
    if res.filas_leidas == 0 and not res.errores:
        error(0, "archivo", "CARGA_VACIA",
              "Libro sin filas: la inicialización requiere autorización explícita")
    return res


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    r = validar(Path(sys.argv[1]).read_bytes(), int(sys.argv[2]) if len(sys.argv) > 2 else 1,
                {"P0001", "P0002", "P0003"}, "PAGO")
    print(json.dumps({"filas_validas": len(r.filas), "filas_leidas": r.filas_leidas,
                      "errores": r.errores, "sha256": r.huella}, ensure_ascii=False, indent=2))
