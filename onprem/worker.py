"""Worker on-premise: detecta Excel nuevos o modificados en las carpetas de las áreas.

Para cada área configurada:
  1. Si el archivo cambió (SHA-256 distinto al último procesado) lo lee.
  2. Lo traduce al contrato v1 y registra las correcciones (mapeo.py).
  3. Guarda el original en originales/ y el libro normalizado en raw/ (inmutables).
  4. Escribe el manifiesto al final, como lo haría Power Automate.
  5. Llama al mismo procesador de la Function, que valida todas las filas y
     publica el lote completo o lo rechaza completo (todo o nada).

Uso (desde la raíz del repositorio):
  python onprem/worker.py --registrar          # alta de archivos autorizados (una vez)
  python onprem/worker.py --una-vez            # un ciclo
  python onprem/worker.py --cada 60            # ciclo continuo cada 60 s
Nada sale de la empresa: solo hay carpetas locales y SQL Server local.
"""
import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for sub in ("functions", "tools", "onprem"):
    sys.path.insert(0, str(RAIZ / sub))

# Límites ampliados para libros de ~500 000 filas (deben fijarse antes de importar la validación).
os.environ.setdefault("HUB_MAX_BYTES", str(200 * 1024 * 1024))
os.environ.setdefault("HUB_MAX_EXPANDIDO", str(2048 * 1024 * 1024))

import mapeo  # noqa: E402
import procesador  # noqa: E402
import sqlconn  # noqa: E402
from almacenamiento import AlmacenLocal  # noqa: E402

log = logging.getLogger("worker")


def cargar_config(ruta=None):
    return json.loads(Path(ruta or RAIZ / "onprem" / "config_areas.json").read_text(encoding="utf-8"))


def registrar_fuentes(cfg, conectar=sqlconn.conectar):
    """Da de alta (o actualiza) el archivo autorizado de cada área configurada."""
    with conectar() as cn:
        cur = cn.cursor()
        for a in cfg["areas"]:
            cur.execute("""MERGE dbo.AreaFuente AS t USING (SELECT ? AS AreaId) s ON t.AreaId=s.AreaId
                WHEN MATCHED THEN UPDATE SET ArchivoId=?, RutaArchivo=?, Activa=1
                WHEN NOT MATCHED THEN INSERT (AreaId, ArchivoId, RutaArchivo) VALUES (?,?,?);""",
                        a["areaId"], a["archivoId"], f'{a["carpeta"]}/{a["archivo"]}',
                        a["areaId"], a["archivoId"], f'{a["carpeta"]}/{a["archivo"]}')
    return len(cfg["areas"])


def _estado(datos):
    p = Path(datos) / "estado_worker.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _guardar_estado(datos, estado):
    (Path(datos) / "estado_worker.json").write_text(json.dumps(estado, indent=1), encoding="utf-8")


def encolar_cambios(cfg, datos):
    """Detecta archivos nuevos o modificados y escribe raw + manifiesto. Devuelve los lotes creados."""
    datos = Path(datos)
    estado = _estado(datos)
    creados = []
    for a in cfg["areas"]:
        origen = datos / "areas" / a["carpeta"] / a["archivo"]
        if not origen.exists():
            continue
        contenido = origen.read_bytes()
        huella = sha256(contenido).hexdigest()
        if estado.get(str(a["areaId"])) == huella:
            continue
        lote = str(uuid.uuid4())
        ahora = datetime.now(timezone.utc)
        modificado = datetime.fromtimestamp(origen.stat().st_mtime, timezone.utc).replace(microsecond=0)
        previa = estado.get(f"mod_{a['areaId']}")
        if previa and modificado <= datetime.fromisoformat(previa):     # dos guardados en el mismo segundo
            modificado = datetime.fromisoformat(previa) + timedelta(seconds=1)
        resumen, correcciones = {}, []
        try:
            raw_bytes, correcciones, resumen = mapeo.normalizar(contenido, a, a["areaId"])
        except Exception as exc:  # encabezados irreconocibles, libro ilegible, etc.
            log.warning("Área %s: no se pudo mapear (%s); se envía el original para que lo rechace "
                        "el validador", a["areaId"], exc)
            raw_bytes = contenido
        (datos / "originales" / a["carpeta"]).mkdir(parents=True, exist_ok=True)
        (datos / "originales" / a["carpeta"] / f"{lote}_original.xlsx").write_bytes(contenido)
        ruta = f'area{a["areaId"]:02d}/{ahora:%Y/%m/%d}/{lote}.xlsx'
        destino = datos / "raw" / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(raw_bytes)
        if correcciones:
            c = datos / "correcciones"
            c.mkdir(exist_ok=True)
            (c / f"{lote}.json").write_text(json.dumps(correcciones, ensure_ascii=False), encoding="utf-8")
        manifiesto = {"loteId": lote, "areaId": a["areaId"], "sourceFileId": a["archivoId"],
                      "sourceVersion": huella[:16],
                      "sourceModifiedUtc": modificado.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "rawContainer": "raw", "rawPath": ruta, "contractVersion": "1",
                      "flowRunId": "worker-onprem", "requestedBy": "worker"}
        m = datos / "manifests" / f"{lote}.json"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(json.dumps(manifiesto), encoding="utf-8")          # el manifiesto va al final
        estado[str(a["areaId"])] = huella
        estado[f"mod_{a['areaId']}"] = modificado.isoformat()
        _guardar_estado(datos, estado)
        creados.append({"lote": lote, "area": a["areaId"], **resumen})
    return creados


def guardar_correcciones(datos, conectar=sqlconn.conectar):
    """Inserta las correcciones de los lotes ya registrados en SQL (reintenta los demás después)."""
    carpeta = Path(datos) / "correcciones"
    if not carpeta.exists():
        return 0
    total = 0
    for p in sorted(carpeta.glob("*.json")):
        lote = p.stem
        with conectar() as cn:
            cur = cn.cursor()
            if cur.execute("SELECT 1 FROM dbo.Lote WHERE LoteId=?", lote).fetchone() is None:
                continue
            filas = json.loads(p.read_text(encoding="utf-8"))
            cur.fast_executemany = True
            # Por tandas: una sola llamada con cientos de miles de filas degrada SQL Server.
            for i in range(0, len(filas), 20_000):
                cur.executemany("""INSERT dbo.CorreccionLote (LoteId, FilaOriginal, Campo, ValorOriginal,
                                   ValorCorregido, Regla) VALUES (?,?,?,?,?,?)""",
                                [(lote, f[0], f[1][:50], f[2], f[3], f[4]) for f in filas[i:i + 20_000]])
            total += len(filas)
        p.unlink()
    return total


def ciclo(cfg, datos, conectar=sqlconn.conectar):
    creados = encolar_cambios(cfg, datos)
    resultados = procesador.procesar_pendientes(almacen=AlmacenLocal(datos), conectar=conectar) \
        if (Path(datos) / "manifests").exists() else []
    corregidas = guardar_correcciones(datos, conectar)
    return creados, resultados, corregidas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--datos", default=str(RAIZ / "datos_onprem"))
    ap.add_argument("--hub", default="HubDeuda_dev")
    ap.add_argument("--registrar", action="store_true")
    ap.add_argument("--una-vez", action="store_true")
    ap.add_argument("--cada", type=int, default=0, help="segundos entre ciclos")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not os.environ.get("SQL_ODBC") and not os.environ.get("SQL_SERVER"):
        os.environ["SQL_ODBC"] = sqlconn.cadena_local(a.hub)
    cfg = cargar_config(a.config)
    if a.registrar:
        print(f"Archivos autorizados registrados: {registrar_fuentes(cfg)}")
        return
    while True:
        creados, resultados, corr = ciclo(cfg, a.datos)
        for c in creados:
            log.info("Lote %s (área %s) encolado: %s", c["lote"][:8], c["area"], {k: v for k, v in c.items() if k not in ("lote", "area")})
        for r in resultados:
            log.info("Resultado: %s", r)
        if corr:
            log.info("Correcciones registradas: %s", corr)
        if a.una_vez or not a.cada:
            break
        time.sleep(a.cada)


if __name__ == "__main__":
    main()
