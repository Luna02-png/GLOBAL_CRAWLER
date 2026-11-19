// Clipboard helpers. TSV comes from the backend exporter (single tested implementation);
// an HTML table is added alongside so Google Sheets pastes multi-line cells reliably.

export function parseTsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += c;
    } else if (c === '"' && cell === "") q = true;
    else if (c === "\t") { row.push(cell); cell = ""; }
    else if (c === "\r") { /* skip */ }
    else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");

export function tsvToHtml(tsv: string): string {
  const grid = parseTsv(tsv);
  return "<table>" + grid.map(r => "<tr>" + r.map(c => `<td>${esc(c)}</td>`).join("") + "</tr>").join("") + "</table>";
}

export async function copyTsv(tsv: string): Promise<void> {
  try {
    if ("ClipboardItem" in window && navigator.clipboard?.write) {
      await navigator.clipboard.write([new ClipboardItem({
        "text/plain": new Blob([tsv], { type: "text/plain" }),
        "text/html": new Blob([tsvToHtml(tsv)], { type: "text/html" }),
      })]);
      return;
    }
    await navigator.clipboard.writeText(tsv);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = tsv;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}
