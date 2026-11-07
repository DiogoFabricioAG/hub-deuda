"""Acceso a los contenedores raw y manifests.

En Azure usa Blob Storage con DefaultAzureCredential (identidad administrada
de la Function: lectura en la cuenta y escritura de metadatos en manifests).
En pruebas locales usa una carpeta con la misma estructura: <raiz>/raw/... y
<raiz>/manifests/... (los metadatos van en <raiz>/manifests/_meta/).

Los metadatos del manifiesto (hd_estado, hd_proximo) permiten que la Function
descarte lo ya procesado o en espera SIN consultar Azure SQL, para que la base
serverless pueda pausarse cuando no hay trabajo.
"""
import json
import os
from pathlib import Path, PurePosixPath


class AlmacenLocal:
    def __init__(self, raiz):
        self.raiz = Path(raiz)

    def listar_manifiestos(self):
        return [n for n, _ in self.listar_manifiestos_meta()]

    def listar_manifiestos_meta(self):
        carpeta = self.raiz / "manifests"
        if not carpeta.exists():
            return []
        res = []
        for p in sorted(carpeta.glob("*.json")):
            meta = carpeta / "_meta" / p.name
            res.append((p.name, json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}))
        return res

    def fijar_metadatos(self, nombre, meta):
        p = self.raiz / "manifests" / "_meta" / _seguro(nombre)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(meta), encoding="utf-8")

    def leer_manifiesto(self, nombre):
        return (self.raiz / "manifests" / _seguro(nombre)).read_bytes()

    def tamano(self, contenedor, ruta):
        p = self.raiz / contenedor / _seguro(ruta)
        return p.stat().st_size if p.exists() else None

    def leer(self, contenedor, ruta):
        return (self.raiz / contenedor / _seguro(ruta)).read_bytes()


class AlmacenBlob:
    def __init__(self, url):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        self.svc = BlobServiceClient(url, credential=DefaultAzureCredential())

    def listar_manifiestos(self):
        return [n for n, _ in self.listar_manifiestos_meta()]

    def listar_manifiestos_meta(self):
        c = self.svc.get_container_client("manifests")
        return sorted((b.name, dict(b.metadata or {})) for b in c.list_blobs(include=["metadata"])
                      if b.name.endswith(".json"))

    def fijar_metadatos(self, nombre, meta):
        self.svc.get_blob_client("manifests", nombre).set_blob_metadata(meta)

    def leer_manifiesto(self, nombre):
        return self.svc.get_blob_client("manifests", nombre).download_blob().readall()

    def tamano(self, contenedor, ruta):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return self.svc.get_blob_client(contenedor, ruta).get_blob_properties().size
        except ResourceNotFoundError:
            return None

    def leer(self, contenedor, ruta):
        return self.svc.get_blob_client(contenedor, ruta).download_blob().readall()


def crear_almacen():
    if os.environ.get("LOCAL_STORAGE_DIR"):
        return AlmacenLocal(os.environ["LOCAL_STORAGE_DIR"])
    return AlmacenBlob(os.environ["STORAGE_URL"])


def _seguro(ruta):
    p = PurePosixPath(ruta)
    if p.is_absolute() or ".." in p.parts or "\\" in ruta:
        raise ValueError("Ruta no permitida")
    return str(p)
