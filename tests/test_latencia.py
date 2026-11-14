"""Latencia Excel → dato visible: cuánto tarda desde que el área guarda su Excel hasta que
el resultado (saldo corregido u observación de error) se puede leer en las vistas de SQL.

El worker corre en un hilo con un intervalo de sondeo fijo, como en producción (`--cada N`).
Mide, por intervalo: espera de detección, proceso (mapeo + validación + publicación) y total.
Deja el resumen en tests/_out/latencia.json.

  pytest tests/test_latencia.py -s
"""
import json
import threading
import time
from pathlib import Path

import datos_demo
import pytest
import worker
from conftest import D

SALIDA = Path(__file__).parent / "_out" / "latencia.json"


def esperar(condicion, limite=60.0):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limite:
        if condicion():
            return time.perf_counter()
        time.sleep(0.05)
    raise AssertionError("no apareció el dato a tiempo")


@pytest.mark.parametrize("intervalo", [2, 10])
def test_latencia_excel_a_dato_visible(hub, tmp_path, monkeypatch, intervalo):
    cfg = worker.cargar_config()
    worker.registrar_fuentes(cfg)
    datos = tmp_path / "datos"
    ciclos = []                                       # (inicio, fin, ¿hizo trabajo?)
    original = worker.ciclo

    def medido(*a, **k):
        t0 = time.perf_counter()
        r = original(*a, **k)
        ciclos.append((t0, time.perf_counter(), bool(r[0] or r[1])))
        return r

    monkeypatch.setattr(worker, "ciclo", medido)
    parar = threading.Event()

    def bucle():
        while not parar.is_set():
            worker.ciclo(cfg, datos)
            parar.wait(intervalo)

    hilo = threading.Thread(target=bucle, daemon=True)
    hilo.start()
    try:
        time.sleep(intervalo + 0.5)                   # el worker ya está en marcha y sin trabajo
        # 1) Las áreas guardan su Excel; el de Tesorería trae un error de monto.
        t0 = time.perf_counter()
        datos_demo.generar(datos, con_error=True)
        t_guardado = time.perf_counter()
        t_obs = esperar(lambda: hub.sql("SELECT COUNT(*) FROM dbo.Observacion")[0][0] > 0)
        # 2) El área corrige su Excel y lo guarda de nuevo.
        time.sleep(1.1)
        datos_demo.area1(datos, con_error=False)
        t_corr0 = time.perf_counter()
        t_vis = esperar(lambda: hub.saldo("P0001") == D("60.00"))
    finally:
        parar.set()
        hilo.join(10)

    trabajo = [c for c in ciclos if c[2]]
    primero = next(c for c in trabajo if c[0] >= t0 - 0.01)
    segundo = next(c for c in trabajo if c[0] >= t_corr0 - 0.01)
    r = {
        "intervalo_s": intervalo,
        "con_error_detectado": {"espera_s": round(primero[0] - t_guardado, 2),
                                "proceso_s": round(primero[1] - primero[0], 2),
                                "total_s": round(t_obs - t_guardado, 2)},
        "corregido_visible": {"espera_s": round(segundo[0] - t_corr0, 2),
                              "proceso_s": round(segundo[1] - segundo[0], 2),
                              "total_s": round(t_vis - t_corr0, 2)},
    }
    print(f"\n=== Latencia con sondeo cada {intervalo} s ===")
    print(f"Excel con error → observación visible: {r['con_error_detectado']}")
    print(f"Excel corregido → saldo correcto visible: {r['corregido_visible']}")
    SALIDA.parent.mkdir(exist_ok=True)
    previo = json.loads(SALIDA.read_text()) if SALIDA.exists() and intervalo != 2 else []
    SALIDA.write_text(json.dumps(previo + [r], indent=2, ensure_ascii=False), encoding="utf-8")
    assert r["corregido_visible"]["total_s"] < intervalo + 30
