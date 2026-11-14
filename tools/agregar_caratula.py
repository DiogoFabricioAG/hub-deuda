"""Antepone la carátula de un .docx (la hecha en Word) a otro .docx generado por md_a_docx.js.

Toma de la carátula todo lo que va hasta su primer salto de página (incluido), conserva su
formato y su logo, y lo pone al inicio del documento base. No copia los datos de la carátula
al repositorio: se lee del archivo que se indique.

  python tools/agregar_caratula.py CARATULA.docx BASE.docx SALIDA.docx
"""
import copy
import re
import sys
import zipfile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W, "r": R}
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
WP14 = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"


def limpiar(el):
    """Quita atributos de revisión (rsid, paraId...) que no hacen falta en el destino."""
    for e in el.iter():
        for a in list(e.attrib):
            if a.startswith(("{%s}" % W14, "{%s}" % WP14)) or "rsid" in a:
                del e.attrib[a]
    for e in el.xpath(".//w:proofErr", namespaces=NS):
        e.getparent().remove(e)


def main(caratula, base, salida):
    zc = zipfile.ZipFile(caratula)
    cuerpo_c = etree.fromstring(zc.read("word/document.xml")).find("w:body", NS)
    rels_c = etree.fromstring(zc.read("word/_rels/document.xml.rels"))
    destinos = {r.get("Id"): r.get("Target") for r in rels_c}

    # Elementos de la carátula: hasta el primer salto de página, incluido.
    portada = []
    for e in cuerpo_c:
        portada.append(e)
        if e.xpath('.//w:br[@w:type="page"]', namespaces=NS):
            break
    else:
        raise SystemExit("La carátula no termina en un salto de página")

    zb = zipfile.ZipFile(base)
    doc = etree.fromstring(zb.read("word/document.xml"))
    cuerpo = doc.find("w:body", NS)
    rels = etree.fromstring(zb.read("word/_rels/document.xml.rels"))
    ids = {r.get("Id") for r in rels}
    medios = {}
    for n, rid in enumerate(sorted({b.get("{%s}embed" % R) for e in portada
                                     for b in e.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")}), 1):
        origen = "word/" + destinos[rid]
        nuevo_id = f"rIdCaratula{n}"
        assert nuevo_id not in ids
        nombre = f"media/caratula{n}" + re.search(r"\.\w+$", origen).group(0)
        medios["word/" + nombre] = zc.read(origen)
        etree.SubElement(rels, "{%s}Relationship" % REL, Id=nuevo_id,
                         Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                         Target=nombre)
        for e in portada:
            for b in e.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
                if b.get("{%s}embed" % R) == rid:
                    b.set("{%s}embed" % R, nuevo_id)

    for i, e in enumerate(portada):
        e = copy.deepcopy(e)
        limpiar(e)
        cuerpo.insert(i, e)

    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as out:
        for item in zb.infolist():
            if item.filename == "word/document.xml":
                out.writestr(item, etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True))
            elif item.filename == "word/_rels/document.xml.rels":
                out.writestr(item, etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True))
            else:
                out.writestr(item, zb.read(item.filename))
        for nombre, datos in medios.items():
            out.writestr(nombre, datos)
    print(f"Carátula agregada ({len(portada)} bloques, {len(medios)} imagen) → {salida}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
