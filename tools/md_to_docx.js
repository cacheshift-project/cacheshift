// Minimal Markdown -> .docx builder for course deliverables.
// Usage: node md_to_docx.js input.md output.docx
// Supports: # title, ## H1, ### H2, #### H3, ^^ subtitle line, paragraphs with **bold** / *italic*,
// "- " bullets, "1. " numbered lists, pipe tables, "> " callout boxes, and a line "\pagebreak".
// Requires the `docx` npm package (npm install docx).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel,
  AlignmentType, WidthType, ShadingType, BorderStyle, LevelFormat, PageBreak,
  Footer, PageNumber, TabStopType,
} = require("docx");

const [, , IN, OUT, FOOTER = ""] = process.argv;
const FONT = "Arial";
const ACCENT = "CC0000";
const W = 9360; // US Letter, 1" margins

function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), ...base, bold: true }));
    else out.push(new TextRun({ text: t.slice(1, -1), ...base, italics: true }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };

function tableFrom(rows) {
  const n = rows[0].length;
  // Column widths proportional to the longest cell text, clamped.
  const plain = (t) => (t || "").replace(/\*/g, "");
  const lens = Array.from({ length: n }, (_, j) => Math.max(...rows.map((r) => Math.min(plain(r[j]).length, 60)), 4));
  // Never narrower than the longest single word in the column (about 95 twips per character + margins).
  const minW = Array.from({ length: n }, (_, j) => 200 + 95 * Math.max(...rows.map((r) => Math.max(...plain(r[j]).split(/\s+/).map((w) => w.length)))));
  const tot = lens.reduce((a, b) => a + b, 0);
  // Give every column its minimum first, then share the remaining width in proportion to content length.
  const minSum = minW.reduce((a, b) => a + b, 0);
  let widths;
  if (minSum < W) widths = minW.map((m, j) => m + Math.round(((W - minSum) * lens[j]) / tot));
  else widths = minW.map((m) => Math.round((m * W) / minSum));
  widths[n - 1] += W - widths.reduce((a, b) => a + b, 0);
  const mk = (txt, j, header) => new TableCell({
    borders, width: { size: widths[j], type: WidthType.DXA },
    shading: header ? { fill: "7F0000", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ children: runs(txt, header ? { size: 17, bold: true, color: "FFFFFF" } : { size: 17 }) })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({ cantSplit: true, tableHeader: i === 0, children: r.map((c, j) => mk(c, j, i === 0)) })),
  });
}

function callout(lines) {
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W],
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      borders: { top: { style: BorderStyle.SINGLE, size: 12, color: ACCENT }, bottom: border, left: border, right: border },
      width: { size: W, type: WidthType.DXA },
      shading: { fill: "F4F1F1", type: ShadingType.CLEAR, color: "auto" },
      margins: { top: 120, bottom: 120, left: 180, right: 180 },
      children: lines.map((t) => new Paragraph({ spacing: { after: 70 }, children: runs(t, { size: 20 }) })),
    })] })],
  });
}

const lines = fs.readFileSync(IN, "utf8").split(/\r?\n/);
const children = [];
let listInstance = 0, inList = null, i = 0;
const endList = () => { inList = null; };

while (i < lines.length) {
  const L = lines[i];
  if (/^\s*$/.test(L)) { endList(); i++; continue; }
  if (L.trim() === "\\pagebreak") { endList(); children.push(new Paragraph({ children: [new PageBreak()] })); i++; continue; }
  if (L.startsWith("# ")) {
    children.push(new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: L.slice(2), bold: true, size: 40 })] }));
    i++; continue;
  }
  if (L.startsWith("^^")) {
    children.push(new Paragraph({ spacing: { after: 80 }, children: runs(L.slice(2).trim(), { size: 20, color: "595959" }) }));
    i++; continue;
  }
  const h = L.match(/^(#{2,4}) (.*)$/);
  if (h) {
    endList();
    const lvl = { 2: HeadingLevel.HEADING_1, 3: HeadingLevel.HEADING_2, 4: HeadingLevel.HEADING_3 }[h[1].length];
    children.push(new Paragraph({ heading: lvl, keepNext: true, children: [new TextRun(h[2])] }));
    i++; continue;
  }
  if (L.startsWith("|")) {
    const rows = [];
    while (i < lines.length && lines[i].startsWith("|")) {
      const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
      i++;
    }
    children.push(tableFrom(rows), new Paragraph({ spacing: { after: 60 }, children: [] }));
    continue;
  }
  if (L.startsWith(">")) {
    const block = [];
    while (i < lines.length && lines[i].startsWith(">")) { block.push(lines[i].replace(/^>\s?/, "")); i++; }
    children.push(callout(block.filter((b) => b.trim() !== "")), new Paragraph({ spacing: { after: 60 }, children: [] }));
    continue;
  }
  const b = L.match(/^(\s*)- (.*)$/);
  if (b) {
    if (inList !== "b") { inList = "b"; }
    children.push(new Paragraph({ numbering: { reference: "bullets", level: b[1].length >= 2 ? 1 : 0 }, spacing: { after: 50 }, children: runs(b[2]) }));
    i++; continue;
  }
  const n = L.match(/^\d+\. (.*)$/);
  if (n) {
    if (inList !== "n") { inList = "n"; listInstance++; }
    children.push(new Paragraph({ numbering: { reference: "nums", level: 0, instance: listInstance }, spacing: { after: 50 }, children: runs(n[1]) }));
    i++; continue;
  }
  endList();
  // Paragraph: join soft-wrapped lines.
  const para = [L];
  i++;
  while (i < lines.length && lines[i].trim() !== "" && !/^(#|>|\||- |\d+\. |\^\^|\\pagebreak)/.test(lines[i])) { para.push(lines[i]); i++; }
  children.push(new Paragraph({ spacing: { after: 110 }, children: runs(para.join(" ")) }));
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: "7F0000" }, paragraph: { spacing: { before: 260, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: FONT, color: "262626" }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 21, bold: true, font: FONT, color: "7F0000" }, paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [
      { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 280 } } } },
      { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 950, hanging: 280 } } } },
    ] },
    { reference: "nums", levels: [
      { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 320 } } } },
    ] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      tabStops: [{ type: TabStopType.RIGHT, position: W }],
      children: [
        new TextRun({ text: FOOTER, size: 16, color: "808080" }),
        new TextRun({ text: "\tPage ", size: 16, color: "808080" }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "808080" }),
        new TextRun({ text: " of ", size: 16, color: "808080" }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: "808080" }),
      ] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT); });
