import { useEffect, useMemo, useState } from "react";
import { api, Row } from "../api";
import Grid, { Col, StatusChip } from "../components/Grid";
import { Bars, CategoryDropdown, fmtDate, MarketDropdown, MarketPicker, RefreshBar, useData } from "../components/common";
import { RESEARCH_COLS, TrendsButton } from "./research";

// ===================================================================== Dashboard
export function Dashboard({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const [win, setWin] = useState(30);
  const [markets, setMarkets] = useState<string[]>([]);
  const [conf, setConf] = useState("");
  const [cats, setCats] = useState<number[]>([]);
  const [drill, setDrill] = useState<Drill | null>(null);
  const filters = { window_days: win, markets: markets.join(","), include_fixture: demo, confidence: conf, categories: cats.join(",") };
  const { data: d, reload } = useData<Row>("/api/dashboard", filters);
  if (!d) return <div>Loading…</div>;
  const ls = d.last_scan;
  return (
    <div>
      <div className="pagehead"><h2>Trend Dashboard</h2><RefreshBar scope={{ markets, category_ids: cats }} /></div>
      <div className="filters">
        <b className="small">Lọc:</b>
        <CategoryDropdown value={cats} onChange={setCats} />
        <MarketDropdown value={markets} onChange={setMarkets} />
        <select value={win} onChange={e => setWin(Number(e.target.value))}>{[1, 3, 7, 14, 30, 90, 365].map(w => <option key={w} value={w}>last {w === 1 ? "24h" : w + "d"}</option>)}</select>
        <select value={conf} onChange={e => setConf(e.target.value)}><option value="">any confidence</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
        <button onClick={reload}>Reload</button>
      </div>
      <div className="kpis">
        <div className="kpi click" title="Xem tất cả sản phẩm" onClick={() => setDrill({ by: "all", label: "Tất cả sản phẩm (Total discoveries)" })}><span>Total discoveries ›</span><b>{d.total}</b></div>
        <div className="kpi hot click" onClick={() => setDrill({ by: "status", value: "HOT NOW", label: "Trend status: HOT NOW" })}><span>HOT NOW ›</span><b>{d.hot_now}</b></div>
        <div className="kpi rise click" onClick={() => setDrill({ by: "status", value: "RISING FAST", label: "Trend status: RISING FAST" })}><span>RISING FAST ›</span><b>{d.rising_fast}</b></div>
        <div className="kpi up click" onClick={() => setDrill({ by: "status", value: "UPCOMING HYPE", label: "Trend status: UPCOMING HYPE" })}><span>UPCOMING HYPE ›</span><b>{d.upcoming_hype}</b></div>
        <div className="kpi click" title="Mở trang What's New" onClick={() => { location.hash = "new"; }}><span>Changes (24h) ›</span><b>{d.changes_24h}</b></div>
        <div className="kpi click" title="Mở Scan Manager" onClick={() => { location.hash = "scans"; }}><span>Last scan ›</span><b className="small">{ls ? `${ls.status} · ${fmtDate(ls.finished_at || ls.created_at)}` : "never"}</b></div>
      </div>
      <div className="cols3">
        <Bars title="Trend status" data={Object.entries(d.status_counts) as any} onPick={v => setDrill({ by: "status", value: v, label: "Trend status: " + v })} />
        <Bars title="Brands" data={d.brands} onPick={v => setDrill({ by: "brand", value: v, label: "Brand: " + v })} />
        <Bars title="Categories" data={d.categories} onPick={v => setDrill({ by: "category", value: v, label: "Category: " + v })} />
        <Bars title="Markets" data={d.markets} onPick={v => setDrill({ by: "market", value: v, label: "Market: " + v })} />
        <Bars title="Industries" data={d.industries} onPick={v => setDrill({ by: "industry", value: v, label: "Industry: " + v })} />
        <div className="card"><h4>Data-source health</h4>
          <table className="tbl"><tbody>{d.sources.filter((s: Row) => s.enabled || s.status !== "NOT_CONFIGURED").map((s: Row) => <tr key={s.key}>
            <td>{s.name}</td><td><span className={"chip src-" + s.status}>{s.status}</span></td><td className="small muted">{s.last_error || fmtDate(s.last_success)}</td></tr>)}</tbody></table></div>
      </div>
      {drill && <DrillPanel drill={drill} filters={filters} open={open} onClose={() => setDrill(null)} />}
      <div className="card"><h4>Top scored products (score is only comparable within the same market/industry)</h4>
        <table className="tbl"><thead><tr><th>Product</th><th>Link</th><th>Market</th><th>Score</th><th>Status</th><th>Coverage</th><th>Confidence</th><th>Why</th></tr></thead>
          <tbody>{d.top.map((r: Row) => <tr key={r.row_id} onClick={() => open(r.product_id)} className="click">
            <td>{r.product_name}{r.is_fixture && <span className="tag demo">DEMO</span>}</td>
            <td className="urltd" style={{ minWidth: 280 }} onClick={e => e.stopPropagation()}>{(r.best_info_url || r.ref_url_1) ? <>
              <a href={r.best_info_url || r.ref_url_1} target="_blank" rel="noreferrer noopener">{r.best_info_url || r.ref_url_1}</a>
              <div className="small muted">{r.best_info_url ? (r.best_link_type || "Info") + " · " + r.link_status : "Reference"}</div></> : <span className="muted">—</span>}</td>
            <td>{r.country}</td><td>{r.trend_score?.toFixed(0)}</td>
            <td><StatusChip v={r.trend_status} /></td><td>{r.coverage}%</td><td>{r.confidence}</td><td className="small">{r.trend_explanation}</td></tr>)}</tbody></table>
      </div>
    </div>
  );
}

// ===================================================================== Dashboard drill-down
type Drill = { by: string; value?: string; label: string };

/** Products behind one dashboard number / bar. Uses the dashboard's own filters so the count matches what was clicked. */
function DrillPanel({ drill, filters, open, onClose }: { drill: Drill; filters: Record<string, any>; open: (id: number) => void; onClose: () => void }) {
  const { data, err } = useData<Row[]>("/api/dashboard/products", { ...filters, by: drill.by, value: drill.value ?? "" }, [drill.by, drill.value]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal drill" onClick={onClose}>
      <div className="modalbody drillbody" onClick={e => e.stopPropagation()}>
        <div className="drillhead">
          <h3>{drill.label} <span className="muted small">· {err ? "lỗi" : data ? `${data.length} dòng` : "đang tải…"}</span></h3>
          <span className="muted small">Bấm "Details" để xem chi tiết sản phẩm · kéo chọn + Ctrl+C để copy · Esc để đóng</span>
          <button onClick={onClose}>Đóng ✕</button>
        </div>
        {err ? <div className="errbox">Không tải được danh sách ({err}).
          {err.startsWith("404") ? <> Phần chạy nền vẫn là bản cũ: hãy <b>tắt cửa sổ đen</b> rồi chạy lại <b>start.bat</b>, sau đó nhấn Ctrl+F5.</> : null}</div> :
          !data ? <div>Loading…</div> : data.length === 0 ? <div className="muted">Không có sản phẩm nào với bộ lọc hiện tại.</div> :
          <Grid rows={data} cols={RESEARCH_COLS} dataset="research" filters={{}} onOpen={r => open(r.product_id)} height="65vh" />}
      </div>
    </div>
  );
}

// ===================================================================== Upcoming
const UP_COLS: Col[] = [
  { key: "product_name", label: "Product Name", width: 220, pinned: "left" },
  { key: "best_info_url", label: "Link (Best Product Information URL)", kind: "url", pinned: "left", width: 280 },
  { key: "country", label: "Market / Country", width: 120 },
  { key: "industry", label: "Industry" },
  { key: "category", label: "Category" },
  { key: "brand", label: "Brand", width: 110 },
  { key: "model_variant", label: "Model/Variant" },
  { key: "sku", label: "SKU", width: 120 },
  { key: "image_url", label: "Image URL", kind: "image" },
  { key: "purchase_url", label: "Optional Official/Purchase URL", kind: "url" },
  { key: "expected_date_text", label: "Expected Release Date", width: 150 },
  { key: "date_precision", label: "Date Precision", width: 110 },
  { key: "release_status", label: "Release Status", kind: "status", width: 170 },
  { key: "rumor_confidence", label: "Rumor Confidence", kind: "status", width: 120 },
  { key: "hype_score", label: "Hype Score", kind: "score", width: 100 },
  { key: "ref_url_1", label: "Reference URL 1", kind: "url" },
  { key: "ref_url_2", label: "Reference URL 2", kind: "url" },
  { key: "ref_url_3", label: "Reference URL 3", kind: "url" },
  { key: "source_type", label: "Source Type" },
  { key: "expected_price", label: "Expected Retail Price", kind: "score" },
  { key: "currency", label: "Currency", width: 90 },
  { key: "first_reported", label: "First Reported" },
  { key: "last_updated", label: "Last Updated" },
  { key: "latest_development", label: "Latest Development", width: 380 }
];

export function Upcoming({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const [kind, setKind] = useState("");
  const [win, setWin] = useState("");
  const [view, setView] = useState<"grid" | "calendar">("grid");
  const [cats, setCats] = useState<number[]>([]);
  const [mks, setMks] = useState<string[]>([]);
  const status = kind === "confirmed" ? "OFFICIALLY CONFIRMED,RETAILER LISTED,RELEASED" : kind === "rumor" ? "RUMORED,LEAKED,REPORTED / EXPECTED" : kind;
  const { data } = useData<Row[]>("/api/upcoming", { status, window: win, include_fixture: demo, categories: cats.join(","), markets: mks.join(",") });
  const rows = data || [];
  const months = useMemo(() => {
    const g: Record<string, Row[]> = {};
    rows.forEach(r => { const k = r.date_precision === "TBA" || !r.expected_date ? "TBA / undated" : r.expected_date.slice(0, 7) + (r.date_precision !== "DAY" ? ` (${r.date_precision.toLowerCase()} precision)` : ""); (g[k] = g[k] || []).push(r); });
    return Object.entries(g).sort();
  }, [rows]);
  return (
    <div>
      <div className="pagehead"><h2>Upcoming Releases & Rumors</h2><RefreshBar scope={{ markets: mks, category_ids: cats }} /></div>
      <div className="filters">
        <b className="small">Lọc:</b><CategoryDropdown value={cats} onChange={setCats} /><MarketDropdown value={mks} onChange={setMks} />
        <select value={kind} onChange={e => setKind(e.target.value)}><option value="">all statuses</option><option value="confirmed">confirmed / listed / released</option>
          <option value="rumor">rumors, leaks, reported</option>{["DELAYED", "CANCELLED"].map(s => <option key={s} value={s}>{s}</option>)}</select>
        <select value={win} onChange={e => setWin(e.target.value)}><option value="">any date</option><option value="7">next 7 days</option><option value="30">next 30 days</option><option value="90">next 90 days</option><option value="TBA">TBA only</option></select>
        <button onClick={() => setView(view === "grid" ? "calendar" : "grid")}>{view === "grid" ? "Calendar view" : "Grid view"}</button>
        <span className="muted small">Rumors are never shown as official. Uncertain dates keep their precision (Q1 2027, Spring 2027, TBA).</span>
      </div>
      {view === "grid" ? <Grid rows={rows} cols={UP_COLS} dataset="upcoming" filters={{ status, window: win, include_fixture: demo, categories: cats.join(","), markets: mks.join(",") }} onOpen={r => open(r.product_id)} /> :
        <div className="calendar">{months.map(([m, rs]) => <div className="card" key={m}><h4>{m}</h4>
          {rs.map(r => <div key={r.row_id} className="calitem click" onClick={() => open(r.product_id)}><b>{r.expected_date_text}</b> {r.product_name} <span className="muted">{r.country}</span> <StatusChip v={r.release_status} /> <StatusChip v={r.rumor_confidence} /></div>)}
        </div>)}</div>}
    </div>
  );
}

// ===================================================================== Early radar
const EARLY_COLS: Col[] = [
  { key: "product_name", label: "Product Name", width: 220, pinned: "left" },
  { key: "best_info_url", label: "Link (Best Product Information URL)", kind: "url", pinned: "left", width: 280 },
  { key: "country", label: "Country", width: 110 },
  { key: "industry", label: "Industry" },
  { key: "category", label: "Category" },
  { key: "brand", label: "Brand", width: 110 },
  { key: "model_variant", label: "Model/Variant" },
  { key: "sku", label: "SKU", width: 120 },
  { key: "image_url", label: "Image URL", kind: "image" },
  { key: "purchase_url", label: "Optional Purchase URL", kind: "url" },
  { key: "early_score", label: "Early Signal Score", kind: "score", width: 110 },
  { key: "lifecycle_stage", label: "Lifecycle Stage", kind: "status", width: 240 },
  { key: "mention_growth_3d", label: "Mention Growth 3D", kind: "growth", width: 110 },
  { key: "mention_growth_7d", label: "Mention Growth 7D", kind: "growth", width: 110 },
  { key: "mention_growth_14d", label: "Mention Growth 14D", kind: "growth", width: 110 },
  { key: "acceleration", label: "Mention Acceleration", kind: "growth", width: 110 },
  { key: "search_growth", label: "Search Growth", kind: "growth", width: 100 },
  { key: "independent_sources", label: "Independent Sources", kind: "score", width: 110 },
  { key: "confidence", label: "Evidence Confidence", kind: "status", width: 110 },
  { key: "coverage", label: "Data Coverage", kind: "pct", width: 100 },
  { key: "first_detected", label: "First Detected" },
  { key: "latest_signal", label: "Latest Signal" },
  { key: "ref_url_1", label: "Reference URL 1", kind: "url" },
  { key: "ref_url_2", label: "Reference URL 2", kind: "url" },
  { key: "ref_url_3", label: "Reference URL 3", kind: "url" },
  { key: "early_explanation", label: "Explanation", width: 380 },
  { key: "last_seen", label: "Last Updated" }
];

export function EarlyRadar({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const [stage, setStage] = useState("");
  const [cats, setCats] = useState<number[]>([]);
  const [mks, setMks] = useState<string[]>([]);
  const { data } = useData<Row[]>("/api/early", { stage, include_fixture: demo, categories: cats.join(","), markets: mks.join(",") });
  return (
    <div>
      <div className="pagehead"><h2>Early Trend Radar</h2><RefreshBar scope={{ markets: mks, category_ids: cats }} /></div>
      <div className="filters">
        <b className="small">Lọc:</b><CategoryDropdown value={cats} onChange={setCats} /><MarketDropdown value={mks} onChange={setMks} />
        <select value={stage} onChange={e => setStage(e.target.value)}><option value="">all stages</option>
          {["NEW SIGNAL — INSUFFICIENT HISTORY", "NEW SIGNAL", "EARLY RISING", "ACCELERATING", "BREAKOUT", "MAINSTREAM", "SATURATED", "COOLING DOWN"].map(s => <option key={s}>{s}</option>)}</select>
        <span className="muted small">Growth uses additive smoothing (2→6 mentions ≈ +100%, not +200%). Without ≥7 days of market history the stage stays “insufficient history” and no score is shown.</span>
      </div>
      <Grid rows={data || []} cols={EARLY_COLS} dataset="early" filters={{ stage, include_fixture: demo, categories: cats.join(","), markets: mks.join(",") }} onOpen={r => open(r.product_id)}
        actions={r => <><button className="mini" onClick={() => api.post("/api/shortlists", { list_type: "EARLY_WATCHLIST", product_id: r.product_id })}>+ Watch</button><TrendsButton r={r} /></>} />
    </div>
  );
}

// ===================================================================== Opportunity finder
const OPP_COLS: Col[] = [
  { key: "product_name", label: "Product Name", width: 220, pinned: "left" },
  { key: "best_info_url", label: "Link (Best Product Information URL)", kind: "url", pinned: "left", width: 280 },
  { key: "brand", label: "Brand", width: 110 },
  { key: "industry", label: "Industry" },
  { key: "category", label: "Category" },
  { key: "sku", label: "SKU", width: 120 },
  { key: "image_url", label: "Image URL", kind: "image" },
  { key: "source_markets", label: "Source Markets", width: 120 },
  { key: "target_market", label: "Target Market", width: 100 },
  { key: "source_trend_score", label: "Source Trend Score", kind: "score", width: 110 },
  { key: "target_trend_score", label: "Target Trend Score", kind: "score", width: 110 },
  { key: "source_growth_7d", label: "Source Growth 7D", kind: "growth", width: 110 },
  { key: "target_growth_7d", label: "Target Growth 7D", kind: "growth", width: 110 },
  { key: "opportunity_score", label: "Opportunity Score", kind: "score", width: 110 },
  { key: "opportunity_type", label: "Opportunity Type", width: 190 },
  { key: "confidence", label: "Evidence Confidence", kind: "status", width: 110 },
  { key: "coverage", label: "Data Coverage", kind: "pct", width: 100 },
  { key: "risk_level", label: "Risk Level", width: 90 },
  { key: "target_data_state", label: "Target data", width: 230 },
  { key: "purchase_url", label: "Optional Purchase URL", kind: "url" },
  { key: "source_evidence_url_1", label: "Source Evidence URL 1", kind: "url" },
  { key: "source_evidence_url_2", label: "Source Evidence URL 2", kind: "url" },
  { key: "target_evidence_url", label: "Target Evidence URL", kind: "url" },
  { key: "release_status", label: "Release Status", kind: "status" },
  { key: "availability", label: "Availability" },
  { key: "explanation", label: "Explanation", width: 380 },
  { key: "first_detected", label: "First Detected" },
  { key: "last_updated", label: "Last Updated" }
];

export function Opportunity({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const { data: settings, reload: rs } = useData<Row>("/api/settings");
  const presets: Row[] = settings?.["opportunity.presets"] || [];
  const [idx, setIdx] = useState(0);
  const [edit, setEdit] = useState<Row | null>(null);
  const [cats, setCats] = useState<number[]>([]);
  const cur = presets[idx];
  const pkey = cur ? `${[...cur.source_markets].sort().join("+")}>${cur.target_market}` : undefined;
  const { data, reload } = useData<Row[]>("/api/opportunities", { preset: pkey, include_fixture: demo, categories: cats.join(",") });
  const save = async (list: Row[]) => { await api.put("/api/settings/opportunity.presets", list); await api.post("/api/opportunities/recompute"); rs(); reload(); };
  return (
    <div>
      <div className="pagehead"><h2>Trend Opportunity Finder</h2><RefreshBar scope={{ markets: cur ? [...cur.source_markets, cur.target_market] : [], category_ids: cats }} /></div>
      <div className="filters">
        <CategoryDropdown value={cats} onChange={setCats} />
        <select value={idx} onChange={e => setIdx(Number(e.target.value))}>{presets.map((p, i) => <option key={i} value={i}>{p.name}: {p.source_markets.join(" + ")} → {p.target_market}</option>)}</select>
        <button onClick={() => setEdit({ name: "New comparison", source_markets: [], target_market: "US" })}>+ New comparison</button>
        {cur && <button onClick={() => setEdit({ ...cur, _i: idx })}>Edit</button>}
        <button onClick={async () => { await api.post("/api/opportunities/recompute"); reload(); }}>Recompute</button>
        <span className="muted small">Missing target-market data is never treated as low popularity. Scores are research signals, not sales forecasts.</span>
      </div>
      {edit && <div className="filterpanel">
        <div><b>Name</b> <input value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} /><br /><b>Source markets</b>
          <MarketPicker value={edit.source_markets} onChange={v => setEdit({ ...edit, source_markets: v })} /></div>
        <div><b>Target market</b><MarketPicker single value={[edit.target_market]} onChange={v => setEdit({ ...edit, target_market: v[0] })} />
          <button className="primary" onClick={async () => { const l = [...presets]; const { _i, ...p } = edit; if (_i !== undefined) l[_i] = p; else l.push(p); await save(l); setEdit(null); }}>Save</button>
          {edit._i !== undefined && <button onClick={async () => { await save(presets.filter((_, i) => i !== edit._i)); setEdit(null); setIdx(0); }}>Delete</button>}
          <button onClick={() => setEdit(null)}>Cancel</button></div>
      </div>}
      <Grid rows={data || []} cols={OPP_COLS} dataset="opportunities" filters={{ preset: pkey, include_fixture: demo, categories: cats.join(",") }} onOpen={r => open(r.product_id)}
        actions={r => <button className="mini" onClick={() => api.post("/api/shortlists", { list_type: "OPPORTUNITY", product_id: r.product_id, target_market: r.target_market })}>+ Shortlist</button>} />
    </div>
  );
}

// ===================================================================== What's new
export function WhatsNew({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const [mode, setMode] = useState("last");
  const [type, setType] = useState("");
  const params = mode === "last" ? { since_last_scan: true } : { days: Number(mode) };
  const { data, reload } = useData<Row[]>("/api/changes", { ...params, event_type: type, include_fixture: demo });
  const types = ["NEW_PRODUCT", "NEW_EVIDENCE", "NEW_PRIMARY_LINK", "NEWLY_HOT_NOW", "NEWLY_RISING_FAST", "EARLY_EARLY_RISING", "EARLY_ACCELERATING", "EARLY_BREAKOUT",
    "NEW_RUMOR", "NEW_RELEASE_EVENT", "RUMOR_CONFIRMED", "RELEASE_DELAYED", "RELEASE_CANCELLED", "RELEASE_DATE_REVISED", "NEW_OPPORTUNITY", "SCORE_CHANGE", "COOLING_DOWN"];
  return (
    <div>
      <div className="pagehead"><h2>What's New Since Last Scan</h2><button onClick={reload}>Reload</button></div>
      <div className="filters">
        <select value={mode} onChange={e => setMode(e.target.value)}><option value="last">since previous successful scan</option><option value="1">last 24h</option><option value="7">last 7 days</option><option value="30">last 30 days</option></select>
        <select value={type} onChange={e => setType(e.target.value)}><option value="">all change types</option>{types.map(t => <option key={t}>{t}</option>)}</select>
        <span className="muted small">Only changes caused by new observations are listed — routine recomputation is not reported as a market change.</span>
      </div>
      <table className="tbl feed"><thead><tr><th>When</th><th>Type</th><th>Product</th><th>Market</th><th>Detail</th><th>Source</th></tr></thead>
        <tbody>{(data || []).map(e => <tr key={e.id}>
          <td>{fmtDate(e.created_at)}</td><td><span className="tag">{e.event_type}</span>{e.is_fixture && <span className="tag demo">DEMO</span>}</td>
          <td className="click" onClick={() => e.product_id && open(e.product_id)}>{e.brand} · {e.product_name}</td><td>{e.market_code}</td><td className="small">{e.detail}</td>
          <td className="urltd">{e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_url}</a>}</td></tr>)}</tbody></table>
    </div>
  );
}

// ===================================================================== Saved lists
const OPP_STATUSES = ["Researching", "Supplier Check", "Ready to Test", "Running Ads", "Monitoring", "Rejected"];

export function SavedLists({ open }: { open: (id: number) => void }) {
  const { data, reload } = useData<Row[]>("/api/shortlists");
  const upd = async (id: number, patch: Row) => { await api.put(`/api/shortlists/${id}`, patch); reload(); };
  const section = (t: string, title: string) => (
    <div className="card"><h4>{title}</h4>
      <table className="tbl"><thead><tr><th>Product</th><th>Target</th><th>Priority</th><th>Status</th><th>Supplier check</th><th>Marketing test</th><th>Notes</th><th>Reviewed</th><th /></tr></thead>
        <tbody>{(data || []).filter(s => s.list_type === t).map(s => <tr key={s.id}>
          <td className="click" onClick={() => open(s.product_id)}>{s.brand} · {s.product_name}{s.is_fixture && <span className="tag demo">DEMO</span>}</td>
          <td><input className="w60" defaultValue={s.target_market || ""} onBlur={e => upd(s.id, { target_market: e.target.value || null })} /></td>
          <td><select value={s.priority || ""} onChange={e => upd(s.id, { priority: e.target.value })}><option value="" />{["High", "Medium", "Low"].map(p => <option key={p}>{p}</option>)}</select></td>
          <td><select value={s.research_status} onChange={e => upd(s.id, { research_status: e.target.value })}>{OPP_STATUSES.map(p => <option key={p}>{p}</option>)}</select></td>
          <td><input defaultValue={s.supplier_check || ""} onBlur={e => upd(s.id, { supplier_check: e.target.value })} /></td>
          <td><input defaultValue={s.marketing_test_status || ""} onBlur={e => upd(s.id, { marketing_test_status: e.target.value })} /></td>
          <td><input defaultValue={s.notes || ""} onBlur={e => upd(s.id, { notes: e.target.value })} /></td>
          <td className="small">{fmtDate(s.reviewed_at)}</td>
          <td><button className="mini" onClick={async () => { if (confirm("Remove from list?")) { await api.del(`/api/shortlists/${s.id}`); reload(); } }}>remove</button></td>
        </tr>)}</tbody></table></div>);
  return <div><div className="pagehead"><h2>Saved Lists</h2></div>{section("EARLY_WATCHLIST", "Early Trend Watchlist")}{section("OPPORTUNITY", "Opportunity Shortlist")}
    <p className="muted small">Saved entries are never removed when rankings change.</p></div>;
}
