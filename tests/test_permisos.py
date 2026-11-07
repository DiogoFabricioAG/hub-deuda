"""El procesador debe funcionar solo con los permisos de rol_hub_integracion
(los de la identidad administrada de la Function en Azure), no como dbo.
Regresión del error 229 sobre dbo.Notificacion detectado en la prueba de humo.
"""
import procesador
import sqlconn
from conftest import D
from plantillas import mov


def _crear_usuario(hub):
    hub.sql("""CREATE USER u_func WITHOUT LOGIN;
               ALTER ROLE rol_hub_integracion ADD MEMBER u_func; SELECT 1""")


def conectar_como_funcion(database=None, **kw):
    cn = sqlconn.conectar(database, **kw)
    cn.cursor().execute("EXECUTE AS USER = 'u_func'")
    return cn


def test_procesador_con_permisos_minimos(hub):
    _crear_usuario(hub)
    ok, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    malo, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001"),
                                mov("TES0002", "P0001", "PAGO", -1, ref="REC002")])
    r = procesador.procesar_pendientes(almacen=hub.almacen, conectar=conectar_como_funcion)
    assert {x["estado"] for x in r} == {"ACEPTADO", "RECHAZADO"}, r
    assert hub.estado(ok) == "ACEPTADO" and hub.estado(malo) == "RECHAZADO"
    assert hub.saldo() == D("70.00")
    # Reintento del mismo manifiesto ya terminal
    r = procesador.procesar_manifiesto(f"{ok}.json", hub.almacen, conectar_como_funcion)
    assert r["repetido"] is True


def test_fallo_tecnico_se_registra_con_permisos_minimos(hub):
    _crear_usuario(hub)

    def caer():
        raise RuntimeError("caída simulada")

    procesador._HOOKS["antes_commit"] = caer
    lote, _, _ = hub.cargar(1, [mov("TES0001", "P0001", "PAGO", 30, ref="REC001")])
    r = procesador.procesar_pendientes(almacen=hub.almacen, conectar=conectar_como_funcion)
    assert r[0]["estado"] == "REINTENTO"
    assert hub.sql("SELECT Intentos FROM dbo.ProcesoManifiesto WHERE LoteId=?", lote)[0][0] == 1
