"""Demostración en vivo de la carga de 500 000 filas, en una base aparte (HubDeuda_500k).

No toca HubDeuda_dev ni las apps: usa su propia base y su propia carpeta (datos_500k/).

  python tools/demo_500k.py preparar     # una vez: genera los Excel de 500 000 filas (≈ 2 min)
  python tools/demo_500k.py reiniciar    # deja HubDeuda_500k vacía y lista (≈ 10 s)
  python tools/demo_500k.py cargar       # EN VIVO: recibe el Excel y lo carga (≈ 7,5 min)
  python tools/demo_500k.py cargar --error   # reenvía el libro con un monto ilegible en la fila 490 000
  python tools/demo_500k.py estado       # cuenta lo cargado hasta el momento

Los Excel «sucios» llevan el formato propio del área 1 (otros encabezados, fechas como texto,
papeletas mal escritas, sinónimos): pasan por el mapeo, el saneamiento y el todo o nada.
"""
import argparse
import os
import re
import shutil
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for sub in ("functions", "tools", "onprem"):
    sys.path.insert(0, str(RAIZ / sub))

import pyodbc  # noqa: E402
from openpyxl import Workbook  # noqa: E402

pyodbc.pooling = False

BD = "HubDeuda_500k"
DATOS = RAIZ / "datos_500k"
LISTO = DATOS / "listo"
BUENO = LISTO / "Tesoreria_movimientos.xlsx"
MALO = LISTO / "Tesoreria_movimientos_con_error.xlsx"
DESTINO = DATOS / "areas" / "Area01" / "Tesoreria_movimientos.xlsx"
FILA_MALA = 490_000


def hora():
    return datetime.now().strftime("%H:%M:%S")


def decir(texto):
    print(f"[{hora()}] {texto}", flush=True)


def generar_sucio(destino, filas, fila_mala=None):
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Datos")
    ws.append(["N° Recibo", "Papeleta", "Concepto", "Importe", "Fecha de pago", "Situación",
               "Referencia", "Observación"])
    d = date(2026, 10, 1)
    for i in range(1, filas + 1):
        papeleta = (" p-1 ", "P0002", "P3")[i % 3]
        fecha = d.strftime("%d/%m/%Y") if i % 2 else d
        importe = "treinta soles" if fila_mala and i + 1 == fila_mala else round(0.01 + (i % 50) / 100, 2)
        ws.append([f"R-{i:07d}", papeleta, "Abono", importe, fecha, "Vigente", f"REC{i:07d}",
                   "Pago de prueba de volumen"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


def preparar(filas):
    t0 = time.perf_counter()
    decir(f"Generando el Excel sucio de {filas:,} filas…")
    generar_sucio(BUENO, filas)
    decir(f"  listo: {BUENO.name} · {BUENO.stat().st_size / 1048576:.1f} MiB")
    decir(f"Generando la versión con un monto ilegible en la fila {FILA_MALA:,}…")
    generar_sucio(MALO, filas, fila_mala=min(FILA_MALA, filas))
    decir(f"Todo preparado en {time.perf_counter() - t0:.0f} s. Siguiente: reiniciar")


def _entorno(base=BD):
    import sqlconn
    os.environ["SQL_ODBC"] = sqlconn.cadena_local(base)
    return sqlconn


def reiniciar():
    assert re.fullmatch(r"HubDeuda_500k", BD)          # solo esta base se borra
    sqlconn = _entorno("master")
    import aplicar_sql
    import cargar_base_local
    import worker
    decir(f"Recreando {BD}…")
    with sqlconn.conectar("master") as cn:
        cur = cn.cursor()
        cur.execute(f"""IF DB_ID('{BD}') IS NOT NULL BEGIN
            ALTER DATABASE [{BD}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{BD}]; END""")
    aplicar_sql.crear_bd(BD)
    aplicar_sql.aplicar(str(RAIZ / "sql" / "hub"), BD)
    cid, n = cargar_base_local.cargar(BD)
    decir(f"Deuda base publicada ({n} papeletas)")
    _entorno()
    worker.registrar_fuentes(worker.cargar_config())
    for sub in ("areas", "originales", "raw", "manifests", "correcciones"):
        shutil.rmtree(DATOS / sub, ignore_errors=True)
    (DATOS / "estado_worker.json").unlink(missing_ok=True)
    decir("Listo: base vacía, archivos autorizados registrados y carpeta limpia")


def conteos():
    sqlconn = _entorno()
    with sqlconn.conectar(BD) as cn:
        c = cn.cursor()
        mov = c.execute("SELECT COUNT(*) FROM dbo.Movimiento").fetchone()[0]
        corr = c.execute("SELECT COUNT(*) FROM dbo.CorreccionLote").fetchone()[0]
        lotes = [tuple(r) for r in c.execute("SELECT Estado, COUNT(*) FROM dbo.Lote GROUP BY Estado")]
        saldos = [(r[0], r[1]) for r in c.execute("SELECT PapeletaId, Saldo FROM dbo.vDeuda ORDER BY 1")]
    return mov, corr, lotes, saldos


def estado():
    mov, corr, lotes, saldos = conteos()
    decir(f"Movimientos: {mov:,} · correcciones: {corr:,} · lotes: {lotes}")
    for p, s in saldos:
        decir(f"  {p}: saldo {s:,.2f}")


def cargar(con_error):
    if not BUENO.exists():
        raise SystemExit("Falta el Excel: ejecute primero «preparar»")
    _entorno()
    import worker
    from almacenamiento import AlmacenLocal
    import procesador

    cfg = worker.cargar_config()
    origen = MALO if con_error else BUENO
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    t_ini = time.perf_counter()
    stop = threading.Event()

    def latido():
        while not stop.wait(20):
            print(f"[{hora()}]   … sigue trabajando ({time.perf_counter() - t_ini:.0f} s)", flush=True)
    threading.Thread(target=latido, daemon=True).start()

    decir(f"El área 01 guarda su Excel ({origen.stat().st_size / 1048576:.1f} MiB) en su carpeta")
    shutil.copyfile(origen, DESTINO)
    time.sleep(1.1)
    datos = DATOS

    decir("1/3 El worker lo detecta, lo traduce al modelo común y sanea los datos…")
    t = time.perf_counter()
    creados = worker.encolar_cambios(cfg, datos)
    r = creados[0]
    decir(f"    listo en {time.perf_counter() - t:.0f} s: {r['filas_leidas']:,} filas leídas · "
          f"{r['correcciones']:,} correcciones")

    decir("2/3 El validador revisa TODAS las filas y publica el lote (todo o nada)…")
    t = time.perf_counter()
    res = procesador.procesar_pendientes(almacen=AlmacenLocal(datos))
    t2 = time.perf_counter() - t
    estado_lote = res[0]["estado"]
    decir(f"    listo en {t2:.0f} s: lote {estado_lote}")
    if estado_lote == "ACEPTADO":
        mov, _, _, saldos = conteos()
        decir(f"    >>> PUBLICADO a los {time.perf_counter() - t_ini:.0f} s: {mov:,} movimientos en la base")
    else:
        sqlconn = _entorno()
        with sqlconn.conectar(BD) as cn:
            obs = cn.cursor().execute(
                "SELECT FilaExcel, Campo, Codigo FROM dbo.Observacion WHERE LoteId=?", res[0]["lote"]).fetchall()
        decir(f"    >>> RECHAZADO a los {time.perf_counter() - t_ini:.0f} s: "
              f"{[tuple(o) for o in obs]} · la base no cambió")

    decir("3/3 Registrando cada corrección hecha por el saneamiento…")
    t = time.perf_counter()
    n = worker.guardar_correcciones(datos)
    decir(f"    listo en {time.perf_counter() - t:.0f} s: {n:,} correcciones guardadas")
    stop.set()
    decir(f"TOTAL: {time.perf_counter() - t_ini:.0f} s")
    estado()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["preparar", "reiniciar", "cargar", "estado"])
    ap.add_argument("--filas", type=int, default=500_000)
    ap.add_argument("--error", action="store_true")
    a = ap.parse_args()
    {"preparar": lambda: preparar(a.filas), "reiniciar": reiniciar,
     "cargar": lambda: cargar(a.error), "estado": estado}[a.accion]()


if __name__ == "__main__":
    main()
