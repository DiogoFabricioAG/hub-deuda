"""Procesamiento de manifiestos pendientes (bloque 10 y Anexo C, C1–C6).

Cada manifiesto se procesa de forma aislada: un archivo defectuoso no bloquea
a las otras áreas. Un lote se publica una sola vez; si el proceso cae antes
del commit no queda nada escrito y el siguiente intento lo completa; si cae
después, el siguiente intento reconoce el lote terminal y no cambia saldos.
"""
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import repositorio_sql as repo
import sqlconn
from almacenamiento import crear_almacen
from validacion import CONTRATO_VERSION, MAX_BYTES, REGLAS_VERSION, validar

log = logging.getLogger("hubdeuda")
RUTA_RAW = re.compile(r"^area(\d{2})/\d{4}/\d{2}/\d{2}/([0-9a-f-]{36})\.xlsx$")
ESTADOS_TERMINALES = {"ACEPTADO", "RECHAZADO", "SIN_CAMBIOS", "OBSOLETO", "CONFLICTO"}

# Puntos de inyección solo para pruebas de caída (T11).
_HOOKS = {}


def _hook(nombre):
    f = _HOOKS.get(nombre)
    if f:
        f()


class ManifiestoInvalido(Exception):
    pass


@dataclass
class Manifiesto:
    lote_id: str
    area_id: int
    source_file_id: str
    source_version: str
    source_modified_utc: datetime
    raw_path: str
    flow_run_id: str | None
    requested_by: str | None


def leer_manifiesto(nombre, datos):
    try:
        m = json.loads(datos.decode("utf-8-sig"))
        lote_id = str(uuid.UUID(m["loteId"]))
        if nombre != f"{lote_id}.json":
            raise ValueError("El nombre del manifiesto no coincide con loteId")
        area = m["areaId"]
        if not isinstance(area, int) or isinstance(area, bool) or not 1 <= area <= 10:
            raise ValueError("areaId fuera de 1..10")
        if str(m.get("contractVersion")) != CONTRATO_VERSION:
            raise ValueError("contractVersion no soportada")
        if m.get("rawContainer") != "raw":
            raise ValueError("rawContainer debe ser raw")
        ruta = m["rawPath"]
        g = RUTA_RAW.match(ruta or "")
        if not g or int(g.group(1)) != area or g.group(2) != lote_id:
            raise ValueError("rawPath no pertenece al prefijo del área o al lote")
        for campo, limite in (("sourceFileId", 200), ("sourceVersion", 120)):
            v = m.get(campo)
            if not isinstance(v, str) or not v.strip() or len(v) > limite:
                raise ValueError(f"{campo} inválido")
        mod = datetime.fromisoformat(m["sourceModifiedUtc"].replace("Z", "+00:00"))
        if mod.tzinfo is None:
            raise ValueError("sourceModifiedUtc debe incluir zona (Z)")
        mod = mod.astimezone(timezone.utc).replace(tzinfo=None)
        return Manifiesto(lote_id, area, m["sourceFileId"].strip(), m["sourceVersion"].strip(),
                          mod, ruta, (m.get("flowRunId") or None),
                          (m.get("requestedBy") or None))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, AttributeError) as exc:
        raise ManifiestoInvalido(str(exc)) from exc


def decidir(m, ctx, res, vigente, historico):
    """Devuelve (estado, observaciones) o ('PUBLICAR', [])."""
    autorizado = (ctx["archivo_autorizado"] or "").strip().lower()
    if not ctx["fuente_activa"] or autorizado != m.source_file_id.strip().lower():
        return "RECHAZADO", [_obs("ARCHIVO_NO_AUTORIZADO",
                                  "El archivo no es el autorizado para el área en ConfigAreas")]
    if vigente:
        if (vigente.sha256 == res.huella and vigente.archivo_id == m.source_file_id
                and vigente.reglas == REGLAS_VERSION):
            return "SIN_CAMBIOS", []
        if m.source_modified_utc < vigente.modificado_utc:
            return "OBSOLETO", [_obs("VERSION_ANTERIOR",
                                     "La versión del archivo es anterior a la vigente")]
        if m.source_modified_utc == vigente.modificado_utc:
            return "CONFLICTO", [_obs("MISMA_FECHA_OTRO_CONTENIDO",
                                      "Misma fecha de modificación que la vigente con contenido distinto")]
    if historico:
        return "CONFLICTO", [_obs("CONTENIDO_HISTORICO",
                                  "Contenido idéntico a una versión histórica: requiere revisión antes de restaurar")]
    if res.errores:
        return "RECHAZADO", res.errores
    return "PUBLICAR", []


def _obs(codigo, mensaje, campo="archivo"):
    return {"fila": 0, "campo": campo, "codigo": codigo, "mensaje": mensaje}


def procesar_manifiesto(nombre, almacen, conectar=sqlconn.conectar):
    t0 = time.monotonic()
    try:
        m = leer_manifiesto(nombre, almacen.leer_manifiesto(nombre))
    except ManifiestoInvalido as exc:
        with conectar() as cn:
            repo.marcar_proceso(cn.cursor(), nombre, None, True, f"MANIFIESTO_INVALIDO: {exc}"[:1000])
        log.warning("Manifiesto inválido %s", nombre)
        return {"manifiesto": nombre, "estado": "MANIFIESTO_INVALIDO"}

    # C1: preparar fuera de la transacción
    with conectar() as cn:
        cur = cn.cursor()
        ctx = repo.contexto_area(cur, m.area_id)
        papeletas = repo.papeletas_vigentes(cur)
    if not papeletas:
        raise repo.ErrorTecnico("No hay base de deuda vigente; se reintentará")
    tam = almacen.tamano("raw", m.raw_path)
    if tam is None:
        raise repo.ErrorTecnico("El archivo raw aún no existe")
    if tam > MAX_BYTES:
        from validacion import Resultado
        res = Resultado(huella="0" * 64, errores=[_obs("ARCHIVO_INVALIDO", "Archivo mayor que 10 MiB")])
    else:
        res = validar(almacen.leer("raw", m.raw_path), m.area_id, papeletas, ctx["tipo_permitido"])

    cn = conectar()
    cur = cn.cursor()
    try:
        cur.execute("SET XACT_ABORT ON; BEGIN TRAN;")
        repo.bloquear(cur)                                      # C2
        previo = repo.estado_lote(cur, m.lote_id)               # C3
        if previo in ESTADOS_TERMINALES:
            repo.marcar_proceso(cur, nombre, m.lote_id, True)
            cur.execute("COMMIT")
            return {"manifiesto": nombre, "lote": m.lote_id, "estado": previo, "repetido": True}
        vigente = repo.lote_vigente(cur, m.area_id)
        historico = repo.hash_historico(cur, m.area_id, m.source_file_id, REGLAS_VERSION,
                                        res.huella, vigente.lote_id if vigente else m.lote_id)
        estado, obs = decidir(m, ctx, res, vigente, historico)
        if estado != "PUBLICAR":                                # C4
            _registrar_terminal(cur, nombre, m, estado, res, obs)
            cur.execute("COMMIT")
        else:                                                   # C5
            repo.insertar_lote(cur, m, "VALIDADO", res.huella, res.filas_leidas, REGLAS_VERSION)
            repo.insertar_movimientos(cur, m.lote_id, res.filas)
            repo.publicar_area(cur, m.lote_id)
            repo.insertar_notificacion(cur, m.lote_id, "ACEPTADO")
            repo.marcar_proceso(cur, nombre, m.lote_id, True)
            _hook("antes_commit")
            cur.execute("COMMIT")
            estado = "ACEPTADO"
    except repo.ErrorNegocio as exc:                            # C6
        cur.execute("IF @@TRANCOUNT>0 ROLLBACK")
        estado = _registrar_rechazo_publicacion(conectar, nombre, m, res, exc)
    except Exception:
        try:
            cur.execute("IF @@TRANCOUNT>0 ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        cn.close()
    log.info("Lote %s area=%s estado=%s filas=%s errores=%s ms=%d", m.lote_id, m.area_id,
             estado, res.filas_leidas, len(res.errores), (time.monotonic() - t0) * 1000)
    return {"manifiesto": nombre, "lote": m.lote_id, "estado": estado}


def _registrar_terminal(cur, nombre, m, estado, res, obs):
    repo.insertar_lote(cur, m, estado, res.huella, res.filas_leidas, REGLAS_VERSION)
    repo.insertar_observaciones(cur, m.lote_id, obs)
    if estado != "SIN_CAMBIOS":
        repo.insertar_notificacion(cur, m.lote_id, estado)
    repo.marcar_proceso(cur, nombre, m.lote_id, True)


def _registrar_rechazo_publicacion(conectar, nombre, m, res, exc):
    estado = "RECHAZADO"
    if exc.numero == 50104:
        estado = "OBSOLETO"
    obs = [_obs(f"PUBLICACION_{exc.numero}", _mensaje_sql(exc))]
    with conectar() as cn:
        cur = cn.cursor()
        cur.execute("SET XACT_ABORT ON; BEGIN TRAN;")
        try:
            repo.bloquear(cur)
            previo = repo.estado_lote(cur, m.lote_id)
            if previo in ESTADOS_TERMINALES:   # otro proceso ya lo terminó
                cur.execute("COMMIT")
                return previo
            _registrar_terminal(cur, nombre, m, estado, res, obs)
            cur.execute("COMMIT")
        except Exception:
            cur.execute("IF @@TRANCOUNT>0 ROLLBACK")
            raise
    return estado


def _mensaje_sql(exc):
    texto = str(exc)
    m = re.search(r"\[SQL Server\](.*?)\s*\(5\d{4}\)", texto)
    return (m.group(1) if m else "Rechazado al publicar")[:500]


def procesar_pendientes(limite=20, almacen=None, conectar=sqlconn.conectar):
    almacen = almacen or crear_almacen()
    nombres = almacen.listar_manifiestos()
    if not nombres:
        return []
    with conectar() as cn:
        omitidos = repo.manifiestos_omitidos(cn.cursor(), nombres)
    pendientes = [n for n in nombres if n not in omitidos][:limite]
    resultados = []
    for nombre in pendientes:
        try:
            resultados.append(procesar_manifiesto(nombre, almacen, conectar))
        except Exception as exc:  # fallo técnico: no es "archivo inválido"
            log.exception("Fallo técnico en %s", nombre)
            lote = nombre[:-5] if nombre.endswith(".json") else None
            try:
                lote = str(uuid.UUID(lote))
            except (TypeError, ValueError):
                lote = None
            try:
                with conectar() as cn:
                    repo.registrar_fallo_tecnico(cn.cursor(), nombre, lote,
                                                 f"{type(exc).__name__}: {exc}")
            except Exception:
                log.exception("No se pudo registrar el fallo técnico de %s", nombre)
            resultados.append({"manifiesto": nombre, "estado": "REINTENTO",
                               "error": type(exc).__name__})
    return resultados
