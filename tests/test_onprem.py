"""Versión on-premise: mapeo de Excel heterogéneos, saneamiento y todo o nada.

Usa el worker y el mismo procesador de la Function sobre SQL Server Express local.
"""
from pathlib import Path

import datos_demo
import mapeo
import pytest
import worker
from conftest import D


@pytest.fixture
def onprem(hub, tmp_path):
    cfg = worker.cargar_config()
    worker.registrar_fuentes(cfg)
    datos = tmp_path / "datos"
    return cfg, datos


def test_tres_areas_con_formatos_distintos_se_integran(hub, onprem):
    cfg, datos = onprem
    datos_demo.generar(datos)
    creados, resultados, corr = worker.ciclo(cfg, datos)
    assert len(creados) == 3
    estados = {r["lote"]: r["estado"] for r in resultados}
    assert set(estados.values()) == {"ACEPTADO"}, resultados
    # Área 1: pago 30 (P0001) y 50 (P0002); la fila anulada no cuenta. Área 7: descuento 10 (P0001).
    assert hub.saldo("P0001") == D("60.00")          # 100 - 30 - 10
    assert hub.saldo("P0002") == D("1434.50")        # 250 - 50 + 1234,50
    assert hub.saldo("P0003") == D("95.50")          # 80 + 15,50; el pago anulado no cuenta
    # Saneamiento: filas vacías y duplicado exacto en el área 1, corregidos y registrados.
    reglas = {r[0] for r in hub.sql("SELECT DISTINCT Regla FROM dbo.CorreccionLote")}
    assert {"PAPELETA_FORMATO", "SINONIMO", "MONTO_FORMATO", "FECHA_FORMATO", "DUPLICADO_EXACTO"} <= reglas
    assert corr > 0


def test_encabezado_en_fila_tres_y_montos_con_coma():
    datos = Path(__file__).parent / "_out" / "onprem_mapeo"
    datos_demo.generar(datos)
    cfg = {a["areaId"]: a for a in worker.cargar_config()["areas"]}
    _, corr, resumen = mapeo.normalizar((datos / "areas/Area07/AdmTributaria_descuentos.xlsx").read_bytes(), cfg[7], 7)
    assert resumen["encabezado_en_fila"] == 3
    _, corr2, _ = mapeo.normalizar((datos / "areas/Area02/Coactiva_cargos.xlsx").read_bytes(), cfg[2], 2)
    montos = {r[2]: r[3] for r in corr2 if r[1] == "Monto"}
    assert montos["S/ 1.234,50"] == "1234.50"


def test_todo_o_nada_un_error_rechaza_todo_el_archivo(hub, onprem):
    cfg, datos = onprem
    datos_demo.generar(datos)
    worker.ciclo(cfg, datos)
    saldo, n = hub.saldo("P0001"), hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0]
    # El área 1 vuelve a enviar su libro con una fila imposible de interpretar.
    datos_demo.area1(datos, con_error=True)
    creados, resultados, _ = worker.ciclo(cfg, datos)
    assert [r["estado"] for r in resultados] == ["RECHAZADO"]
    lote = resultados[0]["lote"]
    assert "MONTO_INVALIDO" in hub.codigos(lote)
    # Ninguna fila del libro (ni las buenas) entró: saldo y movimientos intactos.
    assert hub.saldo("P0001") == saldo
    assert hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0] == n


def test_sin_cambios_no_vuelve_a_encolar(hub, onprem):
    cfg, datos = onprem
    datos_demo.generar(datos)
    worker.ciclo(cfg, datos)
    creados, resultados, _ = worker.ciclo(cfg, datos)
    assert creados == [] and resultados == []
