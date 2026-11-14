"""Mapeo y saneamiento de los Excel heterogéneos de las áreas (versión on-premise).

Cada área conserva su Excel con su propio formato (otros encabezados, fechas y
montos escritos de distintas maneras). Este módulo lo traduce al contrato v1
(MovimientoId, PapeletaId, Tipo, Monto, FechaEvento, Estado, Referencia,
Detalle) y devuelve además la lista de correcciones automáticas, con el valor
original y el corregido, para poder demostrar qué se limpió.

Reglas de saneamiento (solo se corrige lo que no deja dudas):
  ESPACIOS, MAYUSCULAS, PAPELETA_FORMATO, SINONIMO, MONTO_FORMATO, FECHA_FORMATO,
  DUPLICADO_EXACTO. Lo que no se puede interpretar se deja tal cual para que el
  validador rechace el archivo completo (todo o nada) con la fila y el campo.
"""
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

from plantillas import COLUMNAS, libro

FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y", "%Y/%m/%d")


class ErrorMapeo(Exception):
    pass


def _clave(txt):
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", txt.lower()).strip()


def _texto(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _monto(v):
    """Devuelve (Decimal|None, corregido?). None = no interpretable."""
    if isinstance(v, bool) or v is None:
        return None, False
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v)), False
    s = re.sub(r"(?i)s\s*/\s*|pen|\$|\s", "", str(v))
    if not s or not re.fullmatch(r"-?[0-9.,]+", s):
        return None, False
    signo = -1 if s.startswith("-") else 1
    s = s.lstrip("-")
    if "." in s and "," in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        s = s.replace(mil, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", s) else s.replace(",", "")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")
    try:
        return signo * Decimal(s), True
    except InvalidOperation:
        return None, False


def _fecha(v):
    if isinstance(v, datetime):
        return v.date(), False
    if isinstance(v, date):
        return v, False
    if isinstance(v, str):
        s = v.strip()
        for fmt in FORMATOS_FECHA:
            try:
                return datetime.strptime(s, fmt).date(), fmt != "%Y-%m-%d"
            except ValueError:
                pass
    return None, False


def _papeleta(v):
    s = _texto(v)
    if s is None:
        return None
    s2 = re.sub(r"\s+", "", s).upper()
    g = re.fullmatch(r"P-?0*(\d{1,6})", s2)
    return f"P{int(g.group(1)):04d}" if g else s2


def encontrar_encabezado(filas_iniciales, columnas):
    """Fila (1..n) y {campo: índice} del primer encabezado que reconoce >= 5 campos."""
    alias = {campo: {_clave(a) for a in lista} for campo, lista in columnas.items()}
    for n, fila in enumerate(filas_iniciales, start=1):
        celdas = [_clave(c) for c in fila]
        idx = {}
        for campo, ops in alias.items():
            for a in ops:
                if a in celdas:
                    idx[campo] = celdas.index(a)
                    break
        if len(idx) >= 5:
            return n, idx
    raise ErrorMapeo("No se reconocen los encabezados del área; actualice el mapeo")


def normalizar(datos, cfg, area):
    """Traduce el Excel del área al contrato v1.

    cfg: {"hoja": str|None, "columnas": {campo: [alias]}, "sinonimos": {campo: {valor: valor}}}
    Devuelve (bytes_libro_contrato, correcciones, resumen) con
    correcciones = [(fila_original, campo, valor_original, valor_corregido, regla)].
    Las filas vacías y los duplicados exactos se dejan en blanco (no se eliminan)
    para que los números de fila de las observaciones coincidan con los del Excel.
    """
    wb = load_workbook(BytesIO(datos), read_only=True, data_only=True)
    ws = wb[cfg["hoja"]] if cfg.get("hoja") else wb.worksheets[0]
    filas = ws.iter_rows(values_only=True)
    primeras = []
    for fila in filas:
        primeras.append(fila)
        if len(primeras) == 10:
            break
    n_enc, idx = encontrar_encabezado(primeras, cfg["columnas"])
    opcionales = cfg.get("opcionales", ["Referencia", "Detalle"])
    faltan = [c for c in COLUMNAS if c not in idx and c not in opcionales]
    if faltan:
        raise ErrorMapeo("Faltan columnas obligatorias: " + ", ".join(faltan))
    sin = {c: {_clave(k): v for k, v in m.items()} for c, m in cfg.get("sinonimos", {}).items()}

    cuerpo = list(primeras[n_enc:])
    cuerpo.extend(filas)
    nuevas, corr, vistos = [], [], set()
    vacias = duplicadas = 0
    for k, fila in enumerate(cuerpo):
        n_orig = n_enc + 1 + k
        crudo = {c: (fila[i] if i < len(fila) else None) for c, i in idx.items()}
        if all(v is None or str(v).strip() == "" for v in crudo.values()):
            nuevas.append([None] * 8)
            vacias += 1
            continue

        def reg(campo, antes, despues, regla, _n=n_orig):
            corr.append((_n, campo, None if antes is None else str(antes)[:300],
                         None if despues is None else str(despues)[:300], regla))

        out = {}
        for campo in ("MovimientoId", "Referencia", "Detalle"):
            t = _texto(crudo.get(campo))
            if t is not None and t != t.strip():
                reg(campo, t, t.strip(), "ESPACIOS")
            out[campo] = t.strip() if t is not None else None
        pid = _papeleta(crudo.get("PapeletaId"))
        if pid != _texto(crudo.get("PapeletaId")):
            reg("PapeletaId", crudo.get("PapeletaId"), pid, "PAPELETA_FORMATO")
        out["PapeletaId"] = pid
        for campo in ("Tipo", "Estado"):
            t = _texto(crudo.get(campo))
            if t is None:
                out[campo] = None
                continue
            v = t.strip().upper()
            sub = sin.get(campo, {}).get(_clave(v))
            if sub:
                v = sub
            if v != t:
                reg(campo, t, v, "SINONIMO" if sub else "MAYUSCULAS")
            out[campo] = v
        m, corregido = _monto(crudo.get("Monto"))
        if m is None or m != m.quantize(Decimal("0.01")):
            out["Monto"] = crudo.get("Monto")          # no se redondea: lo rechaza el validador
        else:
            if corregido:
                reg("Monto", crudo.get("Monto"), m, "MONTO_FORMATO")
            out["Monto"] = float(m)
        f, corregido = _fecha(crudo.get("FechaEvento"))
        if f is None:
            out["FechaEvento"] = crudo.get("FechaEvento")
        else:
            if corregido:
                reg("FechaEvento", crudo.get("FechaEvento"), f.isoformat(), "FECHA_FORMATO")
            out["FechaEvento"] = f
        fila_n = [out.get(c) for c in COLUMNAS]
        clave = tuple(str(x) for x in fila_n)
        if clave in vistos:
            reg("MovimientoId", out["MovimientoId"], None, "DUPLICADO_EXACTO")
            nuevas.append([None] * 8)
            duplicadas += 1
            continue
        vistos.add(clave)
        nuevas.append(fila_n)
    wb.close()
    resumen = {"filas_leidas": len(cuerpo), "filas_vacias": vacias, "duplicados_exactos": duplicadas,
               "correcciones": len(corr), "encabezado_en_fila": n_enc}
    return libro(nuevas, area=area), corr, resumen
