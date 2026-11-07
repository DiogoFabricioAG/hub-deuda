"""Despliega la parte de Power Platform del Hub de Deuda en el entorno
Developer mediante la API web de Dataverse, con la sesión de `az login`.

  python tools/powerplatform.py desplegar   # publicador, solución, referencias y flujos (apagados)
  python tools/powerplatform.py estado      # referencias de conexión y flujos
  python tools/powerplatform.py activar     # enciende los flujos (requiere conexiones enlazadas)

Las conexiones OAuth (SharePoint, Azure Blob, SQL, Outlook) las crea el usuario
en la solución: Power Automate no permite crearlas sin su consentimiento.
"""
import json
import subprocess
import sys
from pathlib import Path

import urllib.error
import urllib.parse
import urllib.request

ORG = "https://org2535ee74.crm2.dynamics.com"
API = f"{ORG}/api/data/v9.2"
SOLUCION = "HubDeuda"
RAIZ = Path(__file__).resolve().parents[1]
VALORES = {
    "__SITE__": "https://unipe.sharepoint.com/sites/IntegracionDeuda",
    "__STORAGE__": "sthubdeudadevdg23ne",
}
REFERENCIAS = {
    "hd_sharepoint": ("Hub Deuda - SharePoint", "shared_sharepointonline"),
    "hd_azureblob": ("Hub Deuda - Azure Blob", "shared_azureblob"),
    "hd_sql": ("Hub Deuda - Azure SQL", "shared_sql"),
    "hd_outlook": ("Hub Deuda - Outlook", "shared_office365"),
}
# Orden: el hijo primero (los padres necesitan su workflowid)
FLUJOS = ["fl_copia_area", "fl_copia_programada", "fl_cargar_ahora"]

_token = None


def token():
    global _token
    if _token is None:
        az = "az.cmd" if sys.platform == "win32" else "az"
        _token = subprocess.run([az, "account", "get-access-token", "--resource", ORG,
                                 "--query", "accessToken", "-o", "tsv"],
                                capture_output=True, text=True, check=True).stdout.strip()
    return _token


def api(metodo, ruta, cuerpo=None, solucion=False):
    h = {"Authorization": f"Bearer {token()}", "Accept": "application/json",
         "OData-MaxVersion": "4.0", "OData-Version": "4.0",
         "Content-Type": "application/json; charset=utf-8", "Prefer": "return=representation"}
    if solucion:
        h["MSCRM.SolutionUniqueName"] = SOLUCION
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    ruta = urllib.parse.quote(ruta, safe="/?$=&'(),@:;")
    req = urllib.request.Request(API + ruta, data=datos, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            texto = r.read().decode("utf-8")
            return json.loads(texto) if texto else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {ruta} -> {e.code}: {e.read().decode('utf-8', 'replace')[:800]}")


def uno(ruta):
    v = api("GET", ruta).get("value", [])
    return v[0] if v else None


def asegurar_solucion():
    pub = uno("/publishers?$select=publisherid&$filter=uniquename eq 'hubdeuda'")
    if not pub:
        pub = api("POST", "/publishers", {
            "uniquename": "hubdeuda", "friendlyname": "Hub de Deuda (SI806U)",
            "customizationprefix": "hd", "customizationoptionvalueprefix": 10567,
            "description": "Publicador del proyecto Hub de Deuda"})
        print("Publicador hubdeuda (prefijo hd) creado")
    sol = uno(f"/solutions?$select=solutionid&$filter=uniquename eq '{SOLUCION}'")
    if not sol:
        api("POST", "/solutions", {
            "uniquename": SOLUCION, "friendlyname": "Hub de Deuda", "version": "1.0.0.0",
            "description": "Flujos, apps, referencias de conexión del Hub de Deuda",
            "publisherid@odata.bind": f"/publishers({pub['publisherid']})"})
        print(f"Solución {SOLUCION} creada")


def asegurar_referencias():
    for logico, (nombre, conector) in REFERENCIAS.items():
        if not uno(f"/connectionreferences?$select=connectionreferenceid&$filter=connectionreferencelogicalname eq '{logico}'"):
            api("POST", "/connectionreferences", {
                "connectionreferencelogicalname": logico, "connectionreferencedisplayname": nombre,
                "connectorid": f"/providers/Microsoft.PowerApps/apis/{conector}",
                "description": "Referencia de conexión del Hub de Deuda"}, solucion=True)
            print(f"Referencia {logico} creada")


def flujo_existente(nombre):
    return uno(f"/workflows?$select=workflowid,statecode&$filter=name eq '{nombre}' and category eq 5")


def desplegar_flujos():
    ids = {}
    for nombre in FLUJOS:
        datos = json.loads((RAIZ / "powerplatform" / "flows" / f"{nombre}.json").read_text(encoding="utf-8"))
        descripcion = datos.pop("_descripcion", "")
        texto = json.dumps(datos, ensure_ascii=False)
        for k, v in VALORES.items():
            texto = texto.replace(k, v)
        if "__CHILD_ID__" in texto:
            texto = texto.replace("__CHILD_ID__", ids["fl_copia_area"])
        previo = flujo_existente(nombre)
        if previo:
            if previo["statecode"] == 1:
                api("PATCH", f"/workflows({previo['workflowid']})", {"statecode": 0, "statuscode": 1})
            api("PATCH", f"/workflows({previo['workflowid']})", {"clientdata": texto, "description": descripcion})
            ids[nombre] = previo["workflowid"]
            print(f"Flujo {nombre} actualizado ({ids[nombre]})")
        else:
            r = api("POST", "/workflows", {
                "name": nombre, "category": 5, "type": 1, "primaryentity": "none",
                "description": descripcion, "clientdata": texto}, solucion=True)
            ids[nombre] = r["workflowid"]
            print(f"Flujo {nombre} creado ({ids[nombre]})")
    return ids


def estado():
    print("Referencias de conexión:")
    for r in api("GET", "/connectionreferences?$select=connectionreferencelogicalname,connectionid&$filter=startswith(connectionreferencelogicalname,'hd_')")["value"]:
        print(f"  {r['connectionreferencelogicalname']:15} {'enlazada' if r.get('connectionid') else 'SIN CONEXIÓN'}")
    print("Flujos:")
    for n in FLUJOS:
        f = flujo_existente(n)
        print(f"  {n:22} {'no existe' if not f else ('ENCENDIDO' if f['statecode'] == 1 else 'apagado')}")


def conexiones_powerapps():
    """Conexiones del entorno por conector (API de Power Apps, sesión de az)."""
    az = "az.cmd" if sys.platform == "win32" else "az"
    tok = subprocess.run([az, "account", "get-access-token", "--resource", "https://service.powerapps.com/",
                          "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True, check=True).stdout.strip()
    entorno = "ac29d72f-46e6-e8e5-b3ae-7af14ca530ec"
    res = {}
    for _, (_, conector) in REFERENCIAS.items():
        url = (f"https://api.powerapps.com/providers/Microsoft.PowerApps/apis/{conector}/connections"
               f"?api-version=2016-11-01&$filter=" + urllib.parse.quote(f"environment eq '{entorno}'"))
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req) as r:
            for c in json.loads(r.read())["value"]:
                if any(s.get("status") == "Connected" for s in c["properties"].get("statuses", [])):
                    res.setdefault(conector, c["name"])
    return res


def enlazar():
    conex = conexiones_powerapps()
    for logico, (_, conector) in REFERENCIAS.items():
        ref = uno(f"/connectionreferences?$select=connectionreferenceid,connectionid&$filter=connectionreferencelogicalname eq '{logico}'")
        if conector not in conex:
            print(f"  {logico}: no hay conexión conectada de {conector}")
            continue
        if ref.get("connectionid") != conex[conector]:
            api("PATCH", f"/connectionreferences({ref['connectionreferenceid']})", {"connectionid": conex[conector]})
            print(f"  {logico} -> {conex[conector]}")


def activar():
    for n in FLUJOS:
        f = flujo_existente(n)
        if f and f["statecode"] != 1:
            api("PATCH", f"/workflows({f['workflowid']})", {"statecode": 1, "statuscode": 2})
            print(f"Flujo {n} encendido")
    estado()


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "estado"
    if accion == "desplegar":
        asegurar_solucion()
        asegurar_referencias()
        desplegar_flujos()
        estado()
    elif accion == "enlazar":
        enlazar()
        estado()
    elif accion == "activar":
        enlazar()
        activar()
    else:
        estado()
