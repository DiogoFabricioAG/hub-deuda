"""Operaciones SQL del procesamiento de lotes (bloque 10 y Anexo C).

Todas las sentencias usan parámetros (?) y nunca concatenan valores del Excel.
El control de transacción (BEGIN TRAN / COMMIT / ROLLBACK) lo hace procesador.
"""
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

ERROR_SQL = re.compile(r"\((5\d{4})\)")
ERRORES_NEGOCIO = {50103, 50104, 50105, 50106, 50107}


class ErrorTecnico(Exception):
    """Fallo reintentable: red, bloqueo, timeout, base no disponible."""


class ErrorNegocio(Exception):
    def __init__(self, numero, mensaje):
        super().__init__(mensaje)
        self.numero = numero


@dataclass
class LoteInfo:
    lote_id: str
    sha256: str
    modificado_utc: datetime
    archivo_id: str
    reglas: str


def _uuid(v):
    return str(uuid.UUID(str(v))) if v is not None else None


def numero_error_sql(exc):
    texto = " ".join(str(a) for a in getattr(exc, "args", ()))
    m = ERROR_SQL.search(texto)
    return int(m.group(1)) if m else None


# ---------- lecturas fuera de la transacción (C1) ----------

def papeletas_vigentes(cur):
    return {r[0] for r in cur.execute("SELECT PapeletaId FROM dbo.vBaseVigente")}


def contexto_area(cur, area_id):
    r = cur.execute("""SELECT a.TipoPermitido, f.ArchivoId, f.Activa
        FROM dbo.Area a LEFT JOIN dbo.AreaFuente f ON f.AreaId=a.AreaId
        WHERE a.AreaId=?""", area_id).fetchone()
    if r is None:
        return None
    return {"tipo_permitido": r[0], "archivo_autorizado": r[1],
            "fuente_activa": bool(r[2]) if r[2] is not None else False}


def estado_manifiestos(cur, nombres):
    """{nombre: (terminal, próximo intento UTC o None)} de los manifiestos ya
    vistos. Los ausentes son nuevos. 'en_espera' usa el reloj de SQL."""
    res = {}
    for i in range(0, len(nombres), 500):
        parte = nombres[i:i + 500]
        marcas = ",".join("?" * len(parte))
        for n, terminal, proximo, espera in cur.execute(
                f"""SELECT Manifiesto, Terminal, ProximoIntentoUtc,
                       CAST(CASE WHEN ProximoIntentoUtc>SYSUTCDATETIME() THEN 1 ELSE 0 END AS bit)
                    FROM dbo.ProcesoManifiesto WHERE Manifiesto IN ({marcas})""", *parte):
            res[n] = (bool(terminal), proximo if espera else None)
    return res


# ---------- dentro de la transacción (C2–C6) ----------

def bloquear(cur):
    r = cur.execute("""SET NOCOUNT ON; DECLARE @r int;
        EXEC @r=sys.sp_getapplock @Resource='PublicacionHub', @LockMode='Exclusive',
             @LockOwner='Transaction', @LockTimeout=10000;
        SELECT @r;""").fetchone()[0]
    if r < 0:
        raise ErrorTecnico(f"No se obtuvo el bloqueo PublicacionHub ({r})")


def estado_lote(cur, lote_id):
    r = cur.execute("SELECT Estado FROM dbo.Lote WHERE LoteId=?", lote_id).fetchone()
    return r[0] if r else None


def lote_vigente(cur, area_id):
    r = cur.execute("""SELECT l.LoteId, l.Sha256, l.ModificadoUtc, l.ArchivoId, l.Reglas
        FROM dbo.Area a JOIN dbo.Lote l ON l.LoteId=a.LoteVigente
        WHERE a.AreaId=?""", area_id).fetchone()
    return LoteInfo(_uuid(r[0]), r[1], r[2], r[3], r[4]) if r else None


def hash_historico(cur, area_id, archivo_id, reglas, sha, excluir):
    r = cur.execute("""SELECT TOP 1 LoteId FROM dbo.Lote
        WHERE AreaId=? AND ArchivoId=? AND Reglas=? AND Sha256=?
          AND Estado='ACEPTADO' AND LoteId<>?""",
                    area_id, archivo_id, reglas, sha, excluir).fetchone()
    return _uuid(r[0]) if r else None


def insertar_lote(cur, m, estado, sha, filas_leidas, reglas):
    cur.execute("""INSERT dbo.Lote (LoteId, AreaId, ArchivoId, VersionFuente, ModificadoUtc,
            Reglas, Sha256, RawPath, Estado, FilasLeidas, FlowRunId, SolicitadoPor)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                m.lote_id, m.area_id, m.source_file_id, m.source_version,
                m.source_modified_utc, reglas, sha, m.raw_path, estado, filas_leidas,
                m.flow_run_id, m.requested_by)


def insertar_observaciones(cur, lote_id, errores):
    if not errores:
        return
    cur.executemany("""INSERT dbo.Observacion (LoteId, FilaExcel, Campo, Codigo, Mensaje)
        VALUES (?,?,?,?,?)""",
                    [(lote_id, e["fila"] or None, e["campo"][:50], e["codigo"][:40],
                      e["mensaje"][:500]) for e in errores])


def insertar_movimientos(cur, lote_id, filas):
    cur.fast_executemany = True
    cur.executemany("""INSERT dbo.Movimiento (LoteId, MovimientoId, PapeletaId, Tipo, Monto,
            FechaEvento, Estado, Referencia, Detalle, FilaExcel)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [(lote_id, f["MovimientoId"], f["PapeletaId"], f["Tipo"], f["Monto"],
                      f["FechaEvento"], f["Estado"], f["Referencia"], f["Detalle"],
                      f["FilaExcel"]) for f in filas])
    cur.fast_executemany = False


def publicar_area(cur, lote_id):
    try:
        cur.execute("EXEC dbo.usp_PublicarArea @LoteId=?", lote_id)
        while cur.nextset():
            pass
    except Exception as exc:  # pyodbc.Error
        n = numero_error_sql(exc)
        if n in ERRORES_NEGOCIO:
            raise ErrorNegocio(n, str(exc)) from exc
        raise


def insertar_notificacion(cur, lote_id, tipo):
    cur.execute("""IF NOT EXISTS (SELECT 1 FROM dbo.Notificacion WHERE LoteId=? AND TipoAviso=?)
        INSERT dbo.Notificacion (LoteId, TipoAviso) VALUES (?,?)""",
                lote_id, tipo, lote_id, tipo)


def marcar_proceso(cur, manifiesto, lote_id, terminal, error=None):
    cur.execute("""MERGE dbo.ProcesoManifiesto WITH (HOLDLOCK) AS t
        USING (SELECT ? AS Manifiesto) AS s ON t.Manifiesto=s.Manifiesto
        WHEN MATCHED THEN UPDATE SET LoteId=?, Terminal=?, UltimoError=?,
             ProximoIntentoUtc=NULL, ActualizadoUtc=SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (Manifiesto, LoteId, Terminal, UltimoError)
             VALUES (?,?,?,?);""",
                manifiesto, lote_id, int(terminal), error, manifiesto, lote_id,
                int(terminal), error)


def registrar_fallo_tecnico(cur, manifiesto, lote_id, error):
    """Backoff exponencial 1, 2, 4 … hasta 60 minutos. No es terminal.
    Devuelve el próximo intento (UTC) para guardarlo también en el blob."""
    r = cur.execute("""MERGE dbo.ProcesoManifiesto WITH (HOLDLOCK) AS t
        USING (SELECT ? AS Manifiesto) AS s ON t.Manifiesto=s.Manifiesto
        WHEN MATCHED AND t.Terminal=0 THEN UPDATE SET Intentos=t.Intentos+1,
             LoteId=COALESCE(?, t.LoteId), UltimoError=?,
             ProximoIntentoUtc=DATEADD(MINUTE, CASE WHEN t.Intentos>=6 THEN 60
                               ELSE POWER(2,t.Intentos) END, SYSUTCDATETIME()),
             ActualizadoUtc=SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (Manifiesto, LoteId, Intentos, UltimoError, ProximoIntentoUtc)
             VALUES (?,?,1,?,DATEADD(MINUTE,1,SYSUTCDATETIME()))
        OUTPUT inserted.ProximoIntentoUtc;""",
                    manifiesto, lote_id, error[:1000], manifiesto, lote_id, error[:1000]).fetchone()
    return r[0] if r else None
