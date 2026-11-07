"""La Function no debe abrir Azure SQL cuando no hay trabajo: la base serverless
solo se pausa tras 15 minutos sin conexiones, y la oferta gratuita (100 000
vCore-segundos al mes) se agotaría en unos 2 días con una consulta por minuto.
"""
import procesador
import sqlconn
from conftest import D
from plantillas import mov


class Contador:
    """Envuelve sqlconn.conectar y cuenta cuántas conexiones se abren."""

    def __init__(self):
        self.n = 0

    def __call__(self, *a, **k):
        self.n += 1
        return sqlconn.conectar(*a, **k)


def test_sin_trabajo_no_se_abre_sql(hub):
    c = Contador()
    assert procesador.procesar_pendientes(almacen=hub.almacen, conectar=c) == []
    assert c.n == 0                                    # contenedor vacío

    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    hub.procesar()
    assert hub.estado(lote) == "ACEPTADO"
    meta = dict(hub.almacen.listar_manifiestos_meta())[f"{lote}.json"]
    assert meta == {"hd_estado": "terminal", "hd_resultado": "ACEPTADO"}

    c = Contador()
    assert procesador.procesar_pendientes(almacen=hub.almacen, conectar=c) == []
    assert c.n == 0                                    # solo manifiestos terminales


def test_manifiesto_previo_sin_metadatos_se_marca_una_vez(hub):
    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    hub.procesar()
    (hub.raiz / "manifests" / "_meta" / f"{lote}.json").unlink()   # como antes del cambio

    c = Contador()
    assert procesador.procesar_pendientes(almacen=hub.almacen, conectar=c) == []
    assert c.n == 1                                    # una consulta para reconocerlo
    assert dict(hub.almacen.listar_manifiestos_meta())[f"{lote}.json"]["hd_estado"] == "terminal"
    assert hub.saldo() == D("70.00")                   # no se reprocesó

    c = Contador()
    procesador.procesar_pendientes(almacen=hub.almacen, conectar=c)
    assert c.n == 0


def test_reintento_en_espera_no_abre_sql(hub):
    def caer():
        raise RuntimeError("caída simulada")

    procesador._HOOKS["antes_commit"] = caer
    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    assert hub.procesar()[0]["estado"] == "REINTENTO"
    procesador._HOOKS.clear()
    assert "hd_proximo" in dict(hub.almacen.listar_manifiestos_meta())[f"{lote}.json"]

    c = Contador()
    assert procesador.procesar_pendientes(almacen=hub.almacen, conectar=c) == []
    assert c.n == 0                                    # espera leída del blob, sin SQL
