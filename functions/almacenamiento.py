"""Acceso a los contenedores raw y manifests.

En Azure usa Blob Storage con DefaultAzureCredential (identidad administrada
de la Function con rol Storage Blob Data Reader). En pruebas locales usa una
carpeta con la misma estructura: <raiz>/raw/... y <raiz>/manifests/...
"""
import os
from pathlib import Path, PurePosixPath


class AlmacenLocal:
    def __init__(self, raiz):
        self.raiz = Path(raiz)

    def listar_manifiestos(self):
        carpeta = self.raiz / "manifests"
        if not carpeta.exists():
            return []
        return sorted(p.name for p in carpeta.glob("*.json"))

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
        c = self.svc.get_container_client("manifests")
        return sorted(b.name for b in c.list_blobs() if b.name.endswith(".json"))

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
