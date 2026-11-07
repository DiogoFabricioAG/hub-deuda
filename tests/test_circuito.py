"""Pruebas integrales T01–T12 de la guía (sección 14) sobre el núcleo local.

T13 (SHIR detenido), T14 (frescura en la app) y T15 (Excel modificado durante
la copia) dependen de ADF, Power Apps y Power Automate: se ejecutan en Azure.
"""
from datetime import date, timedelta

import pytest

import procesador
from conftest import D
from plantillas import mov


def test_t01_a_t10_secuencia(hub):
    # T01 Base: 100 + 250 + 80
    assert hub.total() == D("430.00")
    assert len(hub.sql("SELECT * FROM dbo.vDeuda")) == 3

    # T02 Pago: Tesorería paga 30 a P0001
    t02, bytes_t02, mod_t02 = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    hub.procesar()
    assert hub.estado(t02) == "ACEPTADO"
    assert hub.saldo() == D("70.00") and hub.total() == D("400.00")

    # T03 Duplicado: el mismo archivo (mismos bytes y versión) otra vez
    t03, _, _ = hub.cargar(1, datos=bytes_t02, modificado=mod_t02)
    hub.procesar()
    assert hub.estado(t03) == "SIN_CAMBIOS"
    assert hub.saldo() == D("70.00")
    assert hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0] == 1

    # T04 Error: PAGO con monto negativo → lote rechazado, saldo intacto
    t04, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001"),
                               mov("TES0002", "P0001", "PAGO", -5, ref="REC002")])
    hub.procesar()
    assert hub.estado(t04) == "RECHAZADO"
    assert "MONTO_INVALIDO" in hub.codigos(t04)
    assert hub.saldo() == D("70.00")
    assert hub.sql("SELECT COUNT(*) FROM dbo.Notificacion WHERE LoteId=? AND TipoAviso='RECHAZADO'", t04)[0][0] == 1

    # T05 Corrección: TES0001 pasa de 30 a 35 (mismo MovimientoId)
    t05, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 35, ref="REC001")])
    hub.procesar()
    assert hub.estado(t05) == "ACEPTADO"
    assert hub.saldo() == D("65.00")
    # 11.9: las observaciones del lote rechazado quedan subsanadas, no borradas
    assert hub.sql("SELECT COUNT(*) FROM dbo.Observacion WHERE LoteId=? AND SubsanadaPor=?", t04, t05)[0][0] >= 1

    # T06 Cargo: Ejecutoría Coactiva añade 15
    t06, _, _ = hub.cargar(2, [mov("EJE0001", "P0001", "CARGO", 15, ref="GAS001")])
    hub.procesar()
    assert hub.estado(t06) == "ACEPTADO" and hub.saldo() == D("80.00")

    # T07 Descuento: Administración Tributaria descuenta 10
    t07, _, _ = hub.cargar(7, [mov("ADT0001", "P0001", "DESCUENTO", 10, ref="RES001")])
    hub.procesar()
    assert hub.estado(t07) == "ACEPTADO"
    assert hub.saldo() == D("70.00") and hub.total() == D("400.00")

    # T08 Anulación: TES0001 ANULADO
    t08, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 35, estado="ANULADO", ref="REC001")])
    hub.procesar()
    assert hub.estado(t08) == "ACEPTADO"
    assert hub.saldo() == D("105.00") and hub.total() == D("435.00")

    # T09 Borrado: omitir TES0001 en el siguiente libro → rechazo por pérdida de historia
    t09, _, _ = hub.cargar(1, [mov("TES0002", "P0002", "PAGO", 5, ref="REC009")])
    hub.procesar()
    assert hub.estado(t09) == "RECHAZADO"
    assert "PUBLICACION_50107" in hub.codigos(t09)
    assert hub.saldo() == D("105.00") and hub.total() == D("435.00")

    # T10 Orden: una versión anterior no reemplaza a la vigente
    viejo = hub.reloj - timedelta(days=1)
    t10, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 99, ref="REC001")], modificado=viejo)
    hub.procesar()
    assert hub.estado(t10) == "OBSOLETO"
    assert hub.saldo() == D("105.00")
    vigente = hub.sql("SELECT LoteVigente FROM dbo.Area WHERE AreaId=1")[0][0]
    assert str(vigente).lower() == t08


def test_t11_caida_antes_y_despues_del_commit(hub):
    def caer():
        raise RuntimeError("caída simulada antes del commit")

    procesador._HOOKS["antes_commit"] = caer
    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    r = hub.procesar()
    assert r[0]["estado"] == "REINTENTO"
    assert hub.estado(lote) is None                      # nada quedó escrito
    assert hub.saldo() == D("100.00")
    assert hub.sql("SELECT Intentos FROM dbo.ProcesoManifiesto WHERE LoteId=?", lote)[0][0] == 1

    # Mientras corre el backoff no se reintenta
    procesador._HOOKS.clear()
    assert hub.procesar() == []
    # Vence la espera: el siguiente intento completa la operación una sola vez
    hub.sql("UPDATE dbo.ProcesoManifiesto SET ProximoIntentoUtc=NULL "
            "OUTPUT inserted.Manifiesto WHERE LoteId=?", lote)
    hub.almacen.fijar_metadatos(f"{lote}.json", {})   # la espera también vive en el blob
    hub.procesar()
    assert hub.estado(lote) == "ACEPTADO" and hub.saldo() == D("70.00")

    # Caída después del commit: se vuelve a leer el mismo manifiesto
    r = procesador.procesar_manifiesto(f"{lote}.json", hub.almacen)
    assert r["repetido"] is True and r["estado"] == "ACEPTADO"
    assert hub.saldo() == D("70.00")
    assert hub.sql("SELECT COUNT(*) FROM dbo.Movimiento")[0][0] == 1


def test_t12_aislamiento_por_area(hub):
    lote, _, _ = hub.cargar(2, [mov("EJE0001", "P0001", "CARGO", -1, ref="X")])
    hub.procesar()
    assert hub.estado(lote) == "RECHAZADO"
    hub.sql("""CREATE USER u_area01 WITHOUT LOGIN; ALTER ROLE rol_hub_area01 ADD MEMBER u_area01;
               CREATE USER u_area02 WITHOUT LOGIN; ALTER ROLE rol_hub_area02 ADD MEMBER u_area02;
               SELECT 1""")

    def como(usuario, consulta):
        return hub.sql(f"EXECUTE AS USER='{usuario}'; {consulta}; REVERT;")

    assert len(como("u_area02", "SELECT * FROM dbo.vObservaciones02")) >= 1
    assert como("u_area01", "SELECT * FROM dbo.vObservaciones01") == []
    for prohibido in ("SELECT * FROM dbo.vObservaciones02", "SELECT * FROM dbo.Observacion",
                      "SELECT * FROM dbo.vDeuda"):
        with pytest.raises(Exception, match="(?i)permission|permiso|denied|denegad"):
            como("u_area01", prohibido)
        hub.sql("IF USER_NAME()<>'dbo' REVERT; SELECT 1")


def test_semilla_diez_areas(hub):
    """Anexo A: una fila por área sobre P0001 → saldo 75 y total 405."""
    tipos = {1: ("PAGO", 30), 2: ("CARGO", 15), 7: ("DESCUENTO", 10)}
    lotes = []
    for area in range(1, 11):
        tipo, monto = tipos.get(area, ("OBSERVACION", 0))
        lotes.append(hub.cargar(area, [mov(f"A{area:02d}-0001", "P0001", tipo, monto,
                                           ref=f"REF-A{area:02d}")])[0])
    hub.procesar()
    assert [hub.estado(l) for l in lotes] == ["ACEPTADO"] * 10
    assert hub.saldo() == D("75.00") and hub.total() == D("405.00")
    estados = hub.sql("SELECT COUNT(*) FROM dbo.vEstadoFuentes WHERE AreaId>0 AND Estado='ACEPTADO'")
    assert estados[0][0] == 10


def test_calidad_de_datos(hub):
    futuro = date.today() + timedelta(days=30)
    filas = [
        mov("TES0001", "P0001", "PAGO", 30, ref="R1"),
        mov("TES0001", "P0001", "PAGO", 10, ref="R2"),          # MovimientoId duplicado
        mov("TES0003", "P9999", "PAGO", 10, ref="R3"),          # papeleta inexistente
        mov("TES0004", "P0001", "CARGO", 10, ref="R4"),         # tipo de otra área
        mov("TES0005", "P0001", "PAGO", 10.123, ref="R5"),      # 3 decimales
        mov("TES0006", "P0001", "PAGO", 10, ref="R1"),          # referencia económica repetida
        mov("TES0007", "P0001", "PAGO", 10, ref="R7", fecha=futuro),
        mov("TES0008", "P0001", "OBSERVACION", 5, ref="R8"),    # observación con monto
        [8001, "P0001", "PAGO", 10, date(2026, 11, 1), "ACTIVO", "R9", ""],  # id numérico
    ]
    lote, _, _ = hub.cargar(1, filas)
    hub.procesar()
    assert hub.estado(lote) == "RECHAZADO"
    assert {"DUPLICADO", "PAPELETA_INEXISTENTE", "TIPO_NO_AUTORIZADO", "MONTO_INVALIDO",
            "REFERENCIA_REPETIDA", "FECHA_INVALIDA", "TEXTO_REQUERIDO"} <= hub.codigos(lote)
    assert hub.saldo() == D("100.00")


@pytest.mark.parametrize("variante,codigo", [
    ({"encabezados": ["PapeletaId", "MovimientoId", "Tipo", "Monto", "FechaEvento",
                      "Estado", "Referencia", "Detalle"]}, "ENCABEZADOS"),
    ({"nombre_tabla": None}, "ESTRUCTURA"),
    ({"hoja": "Hoja1"}, "ESTRUCTURA"),
    ({"con_formula": True}, "FORMULA"),
])
def test_libros_mal_formados(hub, variante, codigo):
    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="R1")], **variante)
    hub.procesar()
    assert hub.estado(lote) == "RECHAZADO"
    assert codigo in hub.codigos(lote)


def test_archivo_no_autorizado_y_manifiesto_invalido(hub):
    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="R1")],
                            archivo="otro-archivo")
    hub.procesar()
    assert hub.estado(lote) == "RECHAZADO"
    assert hub.codigos(lote) == {"ARCHIVO_NO_AUTORIZADO"}

    # rawPath de otra área: el manifiesto se descarta sin crear lote
    import json
    lote2, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="R1")])
    m = hub.raiz / "manifests" / f"{lote2}.json"
    d = json.loads(m.read_text(encoding="utf-8"))
    d["rawPath"] = d["rawPath"].replace("area01", "area02")
    m.write_text(json.dumps(d), encoding="utf-8")
    r = hub.procesar()
    assert {x["estado"] for x in r} == {"MANIFIESTO_INVALIDO"}
    assert hub.estado(lote2) is None and hub.saldo() == D("100.00")


def test_libro_vacio_requiere_autorizacion(hub):
    lote, _, _ = hub.cargar(1, [])
    hub.procesar()
    assert hub.estado(lote) == "RECHAZADO" and "CARGA_VACIA" in hub.codigos(lote)


def test_base_obsoleta_o_incompleta_no_cambia_puntero(hub):
    import cargar_base_local
    import conftest
    antes = hub.sql("SELECT CargaId FROM dbo.BaseActual")[0][0]
    # Una base que omite una papeleta con movimientos vigentes se rechaza (50005)
    hub.cargar(1, [mov("TES0001", "P0003", "PAGO", 10, ref="R1")])
    hub.procesar()
    import pyodbc
    cn = pyodbc.connect(conftest.sqlconn.cadena_local(conftest.ORIGEN_DB), autocommit=True)
    cn.cursor().execute("DELETE FROM dbo.DeudaOrigen WHERE PapeletaId='P0003'")
    cn.close()
    with pytest.raises(Exception, match="50005"):
        cargar_base_local.cargar(conftest.HUB_DB, conftest.ORIGEN_DB)
    assert hub.sql("SELECT CargaId FROM dbo.BaseActual")[0][0] == antes
    assert hub.sql("SELECT COUNT(*) FROM dbo.BaseCarga WHERE Estado='FALLIDA'")[0][0] == 1
