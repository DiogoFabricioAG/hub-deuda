const fs = require('fs');
const d = require('docx');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
        BorderStyle, HeadingLevel, LevelFormat, AlignmentType, ImageRun, PageBreak } = d;
const path = require('path');
// Uso: node md_a_docx.js entrada.md salida.docx   (NODE_PATH = carpeta global de node_modules)
const [src, dst] = process.argv.slice(2);
function dimsJpg(b) {                                  // ancho y alto de un JPEG leyendo su cabecera
  let o = 2;
  while (o < b.length) {
    if (b[o] !== 0xFF) { o++; continue; }
    const m = b[o + 1], len = b.readUInt16BE(o + 2);
    if (m >= 0xC0 && m <= 0xCF && m !== 0xC4 && m !== 0xC8 && m !== 0xCC) return [b.readUInt16BE(o + 7), b.readUInt16BE(o + 5)];
    o += 2 + len;
  }
  return [800, 400];
}
const FONT = 'Calibri', W = 9638;
let lines = fs.readFileSync(src, 'utf8').replace(/\r/g, '').split('\n');

const PASOS = [
  'Las áreas guardan su Excel en una carpeta por área (con su formato actual; se conserva una copia inmutable).',
  'El worker detecta el archivo nuevo o modificado.',
  'El worker lo envía (POST) a la API de validación, que mapea, limpia, valida y decide todo o nada.',
  'La API hace una carga masiva y publica en el SQL Server único.',
  'La deuda base llega desde BDOrigen por una carga programada.',
  'Las vistas de lectura (solo lectura, por área) se exponen por el gateway de datos, que abre una conexión saliente hacia Microsoft.',
  'Power Apps y Power BI (en la nube de Microsoft) consultan por ese relay. Atención al ciudadano usa Power Apps y las jefaturas el tablero.'];

const PASOS_ONPREM = [
  'Cada área guarda su Excel en su carpeta, con su formato propio.',
  'El worker detecta el archivo nuevo o modificado (huella SHA-256) y guarda el original.',
  'El worker lo traduce al modelo común (mapeo), sanea los datos y registra cada corrección; deja una copia normalizada inmutable y escribe el manifiesto al final.',
  'El procesador valida todas las filas: publica el lote completo o lo rechaza completo con la lista de errores (todo o nada).',
  'La deuda base llega desde BDOrigen a la misma base SQL Server local.',
  'Las vistas de solo lectura se exponen por el gateway de datos, que abre una conexión saliente hacia Microsoft.',
  'Power Apps y Power BI (nube de Microsoft, solo interfaz) consultan por ese relay y no guardan datos.'];

function runs(t, base = {}) {
  t = t.replace(/\[([^\]]+)\]\((?!http)[^)]+\)/g, '$1').replace(/\[([^\]]+)\]\((http[^)]+)\)/g, '$1');
  const out = []; const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g; let last = 0, m;
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(new TextRun({ text: t.slice(last, m.index), ...base }));
    const s = m[0];
    if (s.startsWith('**')) out.push(new TextRun({ text: s.slice(2, -2), bold: true, ...base }));
    else if (s.startsWith('`')) out.push(new TextRun({ text: s.slice(1, -1), font: 'Consolas', size: 19, ...base }));
    else out.push(new TextRun({ text: s.slice(1, -1), italics: true, ...base }));
    last = m.index + s.length;
  }
  if (last < t.length) out.push(new TextRun({ text: t.slice(last), ...base }));
  return out;
}

const kids = []; const numRefs = []; let i = 0;
const bord = { style: BorderStyle.SINGLE, size: 4, color: 'C9CDE0' };
const borders = { top: bord, bottom: bord, left: bord, right: bord };

while (i < lines.length) {
  const l = lines[i];
  if (l.startsWith('```')) {                                   // bloque de código/mermaid
    let j = i + 1; while (j < lines.length && !lines[j].startsWith('```')) j++;
    if (l.includes('mermaid')) {
      kids.push(new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: 'Recorrido de un dato, de principio a fin:', bold: true })] }));
      const ref = 'n' + numRefs.length; numRefs.push(ref);
      (lines.slice(i, j).join(' ').includes('PROCESADOR') ? PASOS_ONPREM : PASOS).forEach(p => kids.push(new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60 }, children: runs(p) })));
    }
    i = j + 1; continue;
  }
  const img = l.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/);
  if (img) {                                           // imagen con pie
    const f = path.resolve(path.dirname(src), img[2]); const buf = fs.readFileSync(f); const [w, h] = dimsJpg(buf);
    const ancho = 560;
    kids.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 }, keepNext: true,
      children: [new ImageRun({ type: 'jpg', data: buf, transformation: { width: ancho, height: Math.round(ancho * h / w) },
        altText: { title: img[1], description: img[1], name: path.basename(f) } })] }));
    kids.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: img[1], italics: true, size: 18, color: '555555' })] }));
    i++; continue;
  }
  if (l.trim() === '<!-- salto -->') { kids.push(new Paragraph({ children: [new PageBreak()] })); i++; continue; }
  if (l.startsWith('# ')) kids.push(new Paragraph({ heading: HeadingLevel.TITLE, children: runs(l.slice(2)) }));
  else if (l.startsWith('## ')) kids.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: runs(l.slice(3)) }));
  else if (l.startsWith('### ')) kids.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: runs(l.slice(4)) }));
  else if (l.trim() === '---' || l.trim() === '') { /* nada */ }
  else if (l.startsWith('> ')) kids.push(new Paragraph({ spacing: { before: 80, after: 120 }, indent: { left: 360 },
      border: { left: { style: BorderStyle.SINGLE, size: 24, color: '5C2D91', space: 8 } },
      shading: { type: ShadingType.CLEAR, fill: 'F6F1FB' }, children: runs(l.slice(2), { italics: true }) }));
  else if (l.startsWith('|')) {
    const rows = []; while (i < lines.length && lines[i].startsWith('|')) { rows.push(lines[i]); i++; }
    const cells = rows.filter(r => !/^\|[\s|:-]+\|$/.test(r)).map(r => r.replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
    const n = cells[0].length;
    const wts = Array.from({ length: n }, (_, c) => Math.min(60, Math.max(8, ...cells.map(r => (r[c] || '').length))));
    const tot = wts.reduce((a, b) => a + b, 0); let cw = wts.map(x => Math.floor(x / tot * W));
    cw[n - 1] += W - cw.reduce((a, b) => a + b, 0);
    kids.push(new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cw, rows: cells.map((r, ri) =>
      new TableRow({ tableHeader: ri === 0, cantSplit: true, children: r.map((c, ci) => new TableCell({
        width: { size: cw[ci], type: WidthType.DXA }, borders,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        shading: ri === 0 ? { type: ShadingType.CLEAR, fill: 'EEF0F7' } : undefined,
        children: [new Paragraph({ children: runs(c, ri === 0 ? { bold: true, size: 20 } : { size: 20 }) })] })) })) }));
    kids.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
    continue;
  }
  else if (/^- /.test(l)) kids.push(new Paragraph({ numbering: { reference: 'bul', level: 0 }, spacing: { after: 60 }, children: runs(l.slice(2)) }));
  else if (/^\d+\. /.test(l)) {
    const ref = 'n' + numRefs.length; numRefs.push(ref);
    while (i < lines.length && /^\d+\. /.test(lines[i])) {
      kids.push(new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60 }, children: runs(lines[i].replace(/^\d+\. /, '')) })); i++;
    }
    continue;
  }
  else kids.push(new Paragraph({ spacing: { after: 120 }, children: runs(l) }));
  i++;
}

const numbering = { config: [
  { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
  ...numRefs.map(r => ({ reference: r, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] }))] };
const doc = new Document({
  title: (lines.find(x => x.startsWith('# ')) || '# Hub de Deuda').slice(2), numbering,
  styles: { default: { document: { run: { font: FONT, size: 22 } } }, paragraphStyles: [
    { id: 'Title', name: 'Title', basedOn: 'Normal', run: { font: FONT, size: 44, bold: true, color: '5C2D91' }, paragraph: { spacing: { before: 0, after: 200 }, keepNext: true } },
    { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 30, bold: true, color: '003F72' }, paragraph: { spacing: { before: 320, after: 120 }, keepNext: true, outlineLevel: 0 } },
    { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 25, bold: true }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 1 } }] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } }, children: kids }] });
Packer.toBuffer(doc).then(b => { fs.writeFileSync(dst, b); console.log('ok', b.length); });
