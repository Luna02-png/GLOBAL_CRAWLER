import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ColDef, GridApi, ModuleRegistry, themeQuartz } from "ag-grid-community";
import { api, Row } from "../api";
import { copyTsv } from "../clipboard";

ModuleRegistry.registerModules([AllCommunityModule]);

export type Col = { key: string; label: string; kind?: "url" | "image" | "score" | "status" | "text" | "pct" | "growth"; width?: number; hide?: boolean; pinned?: "left" };

const STATUS_CLASS: Record<string, string> = {
  "HOT NOW": "st-hot", "RISING FAST": "st-rise", "UPCOMING HYPE": "st-up", "STABLE DEMAND": "st-stable", "DECLINING": "st-down",
  "INSUFFICIENT DATA": "st-na", "OFFICIALLY CONFIRMED": "st-rise", "RETAILER LISTED": "st-rise", "REPORTED / EXPECTED": "st-up",
  RUMORED: "st-warn", LEAKED: "st-warn", DELAYED: "st-down", CANCELLED: "st-down", RELEASED: "st-stable", BREAKOUT: "st-hot",
  ACCELERATING: "st-rise", "EARLY RISING": "st-up", "NEW SIGNAL": "st-stable", MAINSTREAM: "st-stable", SATURATED: "st-na",
  "COOLING DOWN": "st-down", HIGH: "st-rise", MEDIUM: "st-up", LOW: "st-warn", UNVERIFIED: "st-na", VERIFIED: "st-rise",
  TITLE_MATCH: "st-up", SAVED: "st-rise", DUPLICATE_UPDATED: "st-up", NEED_TITLE: "st-warn", NO_PRODUCT: "st-warn", ERROR: "st-down", NEEDS_REVIEW: "st-warn", NOT_FOUND: "st-down", NOT_CHECKED: "st-na", FAILED: "st-down",
};

export function StatusChip({ v }: { v?: string | null }) {
  if (!v) return <span className="muted">—</span>;
  const k = Object.keys(STATUS_CLASS).find(s => v.startsWith(s));
  return <span className={"chip " + (k ? STATUS_CLASS[k] : "st-na")}>{v}</span>;
}

function UrlCell({ value }: { value?: string }) {
  if (!value) return <span className="muted">—</span>;
  return <span className="urlcell"><a href={value} target="_blank" rel="noreferrer noopener" title="Open in new tab">↗</a> <span className="urltext">{value}</span></span>;
}

function ImageCell({ value }: { value?: string }) {
  if (!value) return <span className="muted">—</span>;
  return <span className="urlcell"><img src={value} alt="" className="thumb" referrerPolicy="no-referrer" onError={e => ((e.target as HTMLImageElement).style.display = "none")} /> <span className="urltext">{value}</span></span>;
}

function localTsv(grid: (string | number | null | undefined)[][]): string {
  const f = (v: any) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[\t\n\r"]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return grid.map(r => r.map(f).join("\t")).join("\r\n") + "\r\n";
}

type Props = {
  rows: Row[];
  cols: Col[];
  dataset: "research" | "upcoming" | "early" | "opportunities";
  filters?: Record<string, any>;
  onOpen?: (r: Row) => void;
  actions?: (r: Row) => JSX.Element;
  toolbar?: (sel: Row[], refresh: () => void) => JSX.Element;
  height?: number | string;
  storageKey?: string;
};

export default function Grid({ rows, cols, dataset, filters, onOpen, actions, toolbar, height = "calc(100vh - 230px)", storageKey }: Props) {
  const ref = useRef<AgGridReact>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  // ---- Excel-like range selection (AG Grid Community has none): drag with the mouse, Shift+click to extend, Ctrl+C to copy
  type Cell = { r: number; c: number };
  const anchor = useRef<Cell | null>(null);
  const focus = useRef<Cell | null>(null);
  const dragging = useRef(false);
  const colOrder = useRef<string[]>([]);
  const [rangeInfo, setRangeInfo] = useState("");
  const [quick, setQuick] = useState("");
  const [sel, setSel] = useState<Row[]>([]);
  const [msg, setMsg] = useState("");
  const [headers, setHeaders] = useState(true);
  const [imageMode, setImageMode] = useState<"url" | "formula">("url");
  const [scope, setScope] = useState<"selected" | "filtered" | "all">("filtered");
  const [showCols, setShowCols] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem("cols:" + (storageKey || dataset)) || "null") ?? cols.filter(c => c.hide).map(c => c.key)); }
    catch { return new Set(cols.filter(c => c.hide).map(c => c.key)); }
  });

  const inRange = (r: number | null, colId: string) => {
    if (r === null || !anchor.current || !focus.current) return false;
    const c = colOrder.current.indexOf(colId);
    if (c < 0) return false;
    const [r1, r2] = [anchor.current.r, focus.current.r].sort((a, b) => a - b);
    const [c1, c2] = [anchor.current.c, focus.current.c].sort((a, b) => a - b);
    return r >= r1 && r <= r2 && c >= c1 && c <= c2;
  };
  const colDefs = useMemo<ColDef[]>(() => {
    const defs: ColDef[] = cols.map(c => {
      const d: ColDef = { field: c.key, headerName: c.label, hide: hidden.has(c.key), width: c.width || (c.kind === "url" || c.kind === "image" ? 260 : 140),
        filter: c.kind === "score" || c.kind === "pct" || c.kind === "growth" ? "agNumberColumnFilter" : "agTextColumnFilter", pinned: c.pinned,
        tooltipValueGetter: p => (p.value == null ? "" : String(p.value)),
        cellClassRules: { "cell-sel": p => inRange(p.node.rowIndex, p.column.getColId()) } };
      if (c.key === "product_name") d.cellRenderer = (p: any) => <span>{p.value}{p.data?.is_fixture && <span className="tag demo">DEMO</span>}{p.data?.needs_review && <span className="tag">review</span>}</span>;
      if (c.kind === "url") d.cellRenderer = UrlCell;
      if (c.kind === "image") d.cellRenderer = ImageCell;
      if (c.kind === "status") d.cellRenderer = (p: any) => <StatusChip v={p.value} />;
      if (c.kind === "score") d.valueFormatter = p => (p.value == null ? "—" : Number(p.value).toFixed(0));
      if (c.kind === "pct") d.valueFormatter = p => (p.value == null ? "—" : `${p.value}%`);
      if (c.kind === "growth") d.valueFormatter = p => (p.value == null ? "—" : `${p.value >= 0 ? "+" : ""}${Math.round(p.value * 100)}%`);
      return d;
    });
    if (actions || onOpen) {
      defs.push({ headerName: "Actions", colId: "__actions", pinned: "right", width: 330, sortable: false, filter: false,
        cellRenderer: (p: any) => <span className="rowact">{onOpen && <button className="mini" onClick={() => onOpen(p.data)}>Details</button>}{actions?.(p.data)}</span> });
    }
    return defs;
  }, [cols, hidden, actions, onOpen]);

  const apiRef = () => ref.current?.api as GridApi | undefined;
  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 3500); };
  const visibleKeys = () => (apiRef()?.getAllDisplayedColumns() || []).map(c => c.getColId()).filter(k => !k.startsWith("__") && k !== "ag-Grid-SelectionColumn");
  const rowIds = (s: typeof scope) => {
    const g = apiRef();
    if (!g) return [];
    if (s === "selected") return g.getSelectedRows().map(r => r.row_id);
    const ids: string[] = [];
    if (s === "filtered") g.forEachNodeAfterFilterAndSort(n => n.data && ids.push(n.data.row_id));
    else g.forEachNode(n => n.data && ids.push(n.data.row_id));
    return ids;
  };

  const copyScope = useCallback(async (s: typeof scope, withHeaders = headers) => {
    const ids = rowIds(s);
    if (!ids.length) return flash(s === "selected" ? "Select rows first (checkbox column)." : "No rows to copy.");
    const tsv = await api.post<string>("/api/export", { format: "tsv", dataset, row_ids: ids, columns: visibleKeys(), headers: withHeaders, image_mode: imageMode, filters });
    await copyTsv(tsv);
    flash(`Copied ${ids.length} row(s) × ${visibleKeys().length} column(s). Paste into Google Sheets with Ctrl+V.`);
  }, [headers, imageMode, dataset, filters]);

  const syncCols = () => { colOrder.current = (apiRef()?.getAllDisplayedColumns() || []).map(c => c.getColId()).filter(k => !k.startsWith("__") && k !== "ag-Grid-SelectionColumn"); };
  const repaint = () => {
    apiRef()?.refreshCells({ force: true });
    if (anchor.current && focus.current) {
      const rows = Math.abs(anchor.current.r - focus.current.r) + 1, cs = Math.abs(anchor.current.c - focus.current.c) + 1;
      setRangeInfo(rows * cs > 1 ? `${rows} dòng × ${cs} cột đang chọn — Ctrl+C để copy` : "");
    } else setRangeInfo("");
  };
  const cellAt = (e: any): Cell | null => {
    const c = colOrder.current.indexOf(e.column.getColId());
    return c < 0 || e.rowIndex == null ? null : { r: e.rowIndex, c };
  };
  const rangeGrid = (): (string | number | null)[][] | null => {
    const g = apiRef();
    if (!g || !anchor.current || !focus.current) return null;
    const [r1, r2] = [anchor.current.r, focus.current.r].sort((a, b) => a - b);
    const [c1, c2] = [anchor.current.c, focus.current.c].sort((a, b) => a - b);
    const keys = colOrder.current.slice(c1, c2 + 1);
    const out: (string | number | null)[][] = [];
    for (let r = r1; r <= r2; r++) {
      const d = g.getDisplayedRowAtIndex(r)?.data;
      if (d) out.push(keys.map(k => d[k] ?? null));
    }
    return out;
  };
  const copyRange = async () => {
    const grid = rangeGrid();
    if (!grid) return false;
    await copyTsv(localTsv(grid));
    flash(`Đã copy ${grid.length} dòng × ${grid[0]?.length || 0} cột. Dán vào Google Sheets bằng Ctrl+V.`);
    return true;
  };
  useEffect(() => {
    const up = () => { dragging.current = false; };
    const key = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "c") return;
      if (!wrapRef.current?.contains(document.activeElement) && !wrapRef.current?.matches(":hover")) return;
      if (window.getSelection()?.toString() || !anchor.current) return;
      e.preventDefault();
      copyRange();
    };
    document.addEventListener("mouseup", up);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mouseup", up); document.removeEventListener("keydown", key); };
  }, []);

  const copyCells = async () => {
    if (anchor.current && focus.current && await copyRange()) return;
    const g = apiRef();
    const fc = g?.getFocusedCell();
    if (!g || !fc) return flash("Click a cell first.");
    const key = fc.column.getColId();
    const selected = g.getSelectedRows();
    const values = selected.length ? selected.map(r => [r[key]]) : [[g.getDisplayedRowAtIndex(fc.rowIndex)?.data?.[key]]];
    await copyTsv(localTsv(values));
    flash(`Copied ${values.length} cell(s) from “${fc.column.getColDef().headerName}”.`);
  };

  const exportFile = (format: "csv" | "xlsx") => api.exportFile({ format, dataset, row_ids: rowIds(scope === "selected" && !sel.length ? "filtered" : scope), columns: visibleKeys(), headers, image_mode: imageMode, filters });

  const toggleCol = (k: string) => {
    const n = new Set(hidden);
    n.has(k) ? n.delete(k) : n.add(k);
    setHidden(n);
    localStorage.setItem("cols:" + (storageKey || dataset), JSON.stringify([...n]));
  };

  return (
    <div className="gridwrap" ref={wrapRef} tabIndex={-1}>
      <div className="toolbar">
        <input className="search" placeholder="Search in table…" value={quick} onChange={e => setQuick(e.target.value)} />
        <span className="sep" />
        <button className="primary" onClick={() => copyScope(scope)}>COPY TO GOOGLE SHEETS</button>
        <select value={scope} onChange={e => setScope(e.target.value as any)} title="Copy / export scope">
          <option value="selected">selected rows</option><option value="filtered">filtered rows</option><option value="all">all rows</option>
        </select>
        <label className="chk"><input type="checkbox" checked={headers} onChange={e => setHeaders(e.target.checked)} /> headers</label>
        <select value={imageMode} onChange={e => setImageMode(e.target.value as any)} title="Image column">
          <option value="url">image = raw URL</option><option value="formula">image = =IMAGE()</option>
        </select>
        <button onClick={copyCells}>COPY SELECTED CELLS</button>
        <button onClick={() => copyScope("selected")}>COPY SELECTED ROWS</button>
        <button onClick={() => copyScope("filtered")}>COPY ALL FILTERED</button>
        <button onClick={() => exportFile("csv")}>EXPORT CSV</button>
        <button onClick={() => exportFile("xlsx")}>EXPORT XLSX</button>
        <div className="colpick">
          <button onClick={() => setShowCols(!showCols)}>Columns ▾</button>
          {showCols && <div className="colmenu">{cols.map(c => <label key={c.key}><input type="checkbox" checked={!hidden.has(c.key)} onChange={() => toggleCol(c.key)} /> {c.label}</label>)}</div>}
        </div>
        {toolbar?.(sel, () => apiRef()?.refreshCells())}
        <span className="count">{rows.length} rows{sel.length ? ` · ${sel.length} selected` : ""}</span>
      </div>
      {msg ? <div className="flash">{msg}</div> : <div className="hint">{rangeInfo || "Mẹo: kéo chuột để bôi đen nhiều ô (Shift+click để mở rộng), rồi Ctrl+C để copy dán vào Google Sheets."}</div>}
      <div style={{ height }}>
        <AgGridReact
          ref={ref}
          theme={themeQuartz.withParams({ fontSize: 12, rowHeight: 30, headerHeight: 34, spacing: 4 })}
          rowData={rows}
          columnDefs={colDefs}
          getRowId={p => String(p.data.row_id)}
          rowSelection={{ mode: "multiRow", enableClickSelection: false }}
          defaultColDef={{ resizable: true, sortable: true, filter: true, floatingFilter: false }}
          quickFilterText={quick}
          ensureDomOrder
          onGridReady={syncCols}
          onDisplayedColumnsChanged={syncCols}
          onColumnMoved={syncCols}
          onCellMouseDown={(e: any) => {
            const ev = e.event as MouseEvent;
            if (!ev || ev.button !== 0 || (ev.target as HTMLElement).closest("a,button,input")) return;
            const cell = cellAt(e);
            if (!cell) return;
            ev.preventDefault();
            if (ev.shiftKey && anchor.current) focus.current = cell;
            else { anchor.current = cell; focus.current = cell; dragging.current = true; }
            repaint();
          }}
          onCellMouseOver={(e: any) => {
            if (!dragging.current) return;
            const cell = cellAt(e);
            if (cell && (cell.r !== focus.current?.r || cell.c !== focus.current?.c)) { focus.current = cell; repaint(); }
          }}
          tooltipShowDelay={600}
          onSelectionChanged={e => setSel(e.api.getSelectedRows())}
          pagination={rows.length > 2000}
          paginationPageSize={1000}
        />
      </div>
    </div>
  );
}
