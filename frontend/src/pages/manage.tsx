import { useEffect, useState } from "react";
import { api, Row } from "../api";
import { CategoryPicker, fmtDate, ListInput, MarketPicker, useData, useTaxonomy } from "../components/common";

// ===================================================================== Smart Scan Manager
function scopeLabel(j: Row): string {
  if (j.preset_name) return "preset: " + j.preset_name;
  const sc = j.scope || {};
  if (sc.product_ids?.length) return `${sc.product_ids.length} sản phẩm`;
  const parts = [];
  if (sc.category_ids?.length) parts.push(`${sc.category_ids.length} danh mục`);
  else parts.push("tất cả danh mục");
  if (sc.markets?.length) parts.push(sc.markets.join(", "));
  if (sc.source_keys?.includes("demo_fixture")) parts.push("DEMO");
  return parts.join(" · ");
}

const EMPTY = { name: "", markets: [], category_ids: [], industry_ids: [], include_keywords: [], exclude_keywords: [], source_keys: [], priority: "P3",
  mode: "DISCOVERY", depth: "QUICK", enabled: true, schedule_time: "07:00", schedule_weekday: 0, limits: {}, export_columns: [] };
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function ScanManager() {
  const { data: presets, reload } = useData<Row[]>("/api/presets");
  const { data: jobs, reload: rj } = useData<Row[]>("/api/jobs", { limit: 40 });
  const { data: sources } = useData<Row[]>("/api/sources");
  const [edit, setEdit] = useState<Row | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  useEffect(() => { const t = setInterval(() => { rj(); reload(); }, 4000); return () => clearInterval(t); }, []);
  const save = async () => {
    if (!edit!.name.trim()) return alert("Give the preset a name");
    edit!.id ? await api.put(`/api/presets/${edit!.id}`, edit) : await api.post("/api/presets", edit);
    setEdit(null); reload();
  };
  const run = async (p: Row, depth: string) => { const r = await api.post("/api/scans", { preset_id: p.id, depth }); rj(); alert(`Job #${r.job_id} queued. The saved preset is not changed by a one-off run.`); };
  const act = async (id: number, a: string) => { try { await api.post(`/api/jobs/${id}/${a}`); } catch (e: any) { alert(e.message); } rj(); };
  return (
    <div>
      <div className="pagehead"><h2>Smart Scan Manager</h2><button className="primary" onClick={() => setEdit({ ...EMPTY })}>+ Add New Scan Preset</button></div>
      <p className="muted small">Every preset is yours: names are labels only. P1 = daily 07:00, P2 = weekly (Monday 07:00 by default), P3 = on demand only (never automatic).
        Timezone Asia/Ho_Chi_Minh. Scheduled scans need the app (or the Windows scheduled task) running — a powered-off computer cannot scan at 07:00.</p>
      <table className="tbl"><thead><tr><th>Preset</th><th>Markets</th><th>Categories</th><th>Priority</th><th>Mode</th><th>Enabled</th><th>Last success</th><th>Last attempt</th><th>Next run</th><th /></tr></thead>
        <tbody>{(presets || []).map(p => <tr key={p.id}>
          <td><b>{p.name}</b></td><td>{p.markets.join(", ") || "—"}</td><td>{p.category_ids.length} selected{p.industry_ids?.length ? ` + ${p.industry_ids.length} industries` : ""}</td>
          <td><span className={"chip pr-" + p.priority}>{p.priority} {p.priority === "P1" ? `daily ${p.schedule_time}` : p.priority === "P2" ? `${DAYS[p.schedule_weekday]} ${p.schedule_time}` : "on demand"}</span></td>
          <td>{p.mode} / {p.depth}</td><td>{p.enabled ? "yes" : "no"}</td><td>{fmtDate(p.last_success_at)}</td><td>{fmtDate(p.last_attempt_at)}</td>
          <td>{p.priority === "P3" ? "manual only" : fmtDate(p.next_run_at)}</td>
          <td className="rowact"><button className="mini" onClick={() => run(p, "QUICK")}>Quick</button><button className="mini" onClick={() => run(p, "FULL")}>Full</button>
            <button className="mini" onClick={() => setEdit({ ...p })}>Edit</button>
            <button className="mini" onClick={async () => { await api.post(`/api/presets/${p.id}/duplicate`); reload(); }}>Duplicate</button>
            <button className="mini" onClick={async () => { await api.put(`/api/presets/${p.id}`, { enabled: !p.enabled }); reload(); }}>{p.enabled ? "Disable" : "Enable"}</button>
            <button className="mini" onClick={async () => { if (confirm("Delete preset? Products, evidence, history and saved lists are kept.")) { await api.del(`/api/presets/${p.id}`); reload(); } }}>Delete</button></td>
        </tr>)}</tbody></table>
      {edit && <div className="modal"><div className="modalbody">
        <h3>{edit.id ? "Edit preset" : "New scan preset"}</h3>
        <div className="form">
          <label>Name <input value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} placeholder="e.g. My US sneakers" /></label>
          <label>Priority <select value={edit.priority} onChange={e => setEdit({ ...edit, priority: e.target.value })}><option value="P1">P1 — Daily</option><option value="P2">P2 — Weekly</option><option value="P3">P3 — On Demand</option></select></label>
          {edit.priority !== "P3" && <label>Time <input type="time" value={edit.schedule_time} onChange={e => setEdit({ ...edit, schedule_time: e.target.value })} /></label>}
          {edit.priority === "P2" && <label>Weekday <select value={edit.schedule_weekday} onChange={e => setEdit({ ...edit, schedule_weekday: Number(e.target.value) })}>{DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>}
          <label>Mode <select value={edit.mode} onChange={e => setEdit({ ...edit, mode: e.target.value })}><option value="DISCOVERY">Discovery (find new products)</option><option value="TRACKING">Tracking (update known products)</option></select></label>
          <label>Depth <select value={edit.depth} onChange={e => setEdit({ ...edit, depth: e.target.value })}><option value="QUICK">Quick</option><option value="FULL">Full</option></select></label>
          <label>Enabled <input type="checkbox" checked={edit.enabled} onChange={e => setEdit({ ...edit, enabled: e.target.checked })} /></label>
          <label>Include keywords <ListInput value={edit.include_keywords} onChange={v => setEdit({ ...edit, include_keywords: v })} /></label>
          <label>Exclude keywords <ListInput value={edit.exclude_keywords} onChange={v => setEdit({ ...edit, exclude_keywords: v })} /></label>
          <label>Max results / task <input type="number" value={edit.limits?.max_results || ""} onChange={e => setEdit({ ...edit, limits: { ...edit.limits, max_results: Number(e.target.value) || undefined } })} /></label>
          <label>Max duration (s) <input type="number" value={edit.limits?.max_duration_s || ""} onChange={e => setEdit({ ...edit, limits: { ...edit.limits, max_duration_s: Number(e.target.value) || undefined } })} /></label>
        </div>
        <div className="filterpanel">
          <div><b>Markets</b><MarketPicker value={edit.markets} onChange={v => setEdit({ ...edit, markets: v })} /></div>
          <div><b>Industries / categories / subcategories</b><CategoryPicker value={edit.category_ids} onChange={v => setEdit({ ...edit, category_ids: v })} /></div>
          <div><b>Sources</b> <span className="muted small">(none ticked = all enabled & applicable)</span>
            {(sources || []).filter(s => !s.is_fixture).map(s => <label key={s.key} className="pitem"><input type="checkbox" checked={edit.source_keys.includes(s.key)}
              onChange={e => setEdit({ ...edit, source_keys: e.target.checked ? [...edit.source_keys, s.key] : edit.source_keys.filter((k: string) => k !== s.key) })} /> {s.name} <span className="muted">{s.status}</span></label>)}</div>
        </div>
        <div className="btnrow"><button className="primary" onClick={save}>Save preset</button><button onClick={() => setEdit(null)}>Cancel</button></div>
      </div></div>}
      <h3>Scan queue & history</h3>
      <table className="tbl"><thead><tr><th>#</th><th>Kind</th><th>Preset / scope</th><th>Trigger</th><th>Mode</th><th>Status</th><th>Current source</th><th>Tasks</th><th>New / updated</th><th>Errors</th><th>Created</th><th>Elapsed</th><th /></tr></thead>
        <tbody>{(jobs || []).map(j => <tr key={j.id}>
          <td>{j.id}</td><td>{j.kind}</td><td>{scopeLabel(j)}</td><td>{j.trigger}</td>
          <td>{j.mode}/{j.depth}</td><td><span className={"chip job-" + j.status}>{j.status}</span></td><td>{j.current_source || ""}</td>
          <td>{j.stats?.tasks_done ?? j.stats?.done ?? ""}{j.stats?.tasks_total ? `/${j.stats.tasks_total}` : j.stats?.total ? `/${j.stats.total}` : ""}{j.stats?.tasks_failed ? ` (${j.stats.tasks_failed} failed)` : ""}</td>
          <td>{j.stats?.products_new ?? ""}{j.stats?.products_updated !== undefined ? ` / ${j.stats.products_updated}` : ""}</td>
          <td className="small">{(j.stats?.errors || []).length || ""}{j.error ? " crash" : ""}</td><td>{fmtDate(j.created_at)}</td><td>{j.stats?.elapsed_s ? j.stats.elapsed_s + "s" : ""}</td>
          <td className="rowact">{j.kind === "SCAN" && <a className="mini btnlink" href={`#sheet?job=${j.id}`}>xem kết quả</a>}
            <button className="mini" onClick={async () => setDetail(await api.get(`/api/jobs/${j.id}`))}>details</button>
            {["RUNNING", "QUEUED"].includes(j.status) && <button className="mini" onClick={() => act(j.id, "pause")}>pause</button>}
            {j.status === "PAUSED" && <button className="mini" onClick={() => act(j.id, "resume")}>resume</button>}
            {["RUNNING", "QUEUED", "PAUSED"].includes(j.status) && <button className="mini" onClick={() => act(j.id, "cancel")}>cancel</button>}
            {["FAILED", "PARTIAL", "CANCELLED"].includes(j.status) && <button className="mini" onClick={() => act(j.id, "retry")}>retry failed</button>}</td>
        </tr>)}</tbody></table>
      {detail && <div className="modal" onClick={() => setDetail(null)}><div className="modalbody" onClick={e => e.stopPropagation()}>
        <h3>Job #{detail.id} — {detail.status}</h3>
        <div>{JSON.stringify(detail.task_counts)}</div>
        {detail.stats?.articles_read !== undefined && <div className="card small">
          Đọc <b>{detail.stats.articles_read}</b> bài/bài đăng · nhận ra <b>{detail.stats.product_mentions}</b> lượt nhắc sản phẩm ·
          {" "}<b>{detail.stats.no_product_recognised}</b> bài không có sản phẩm của hãng đã biết (thêm hãng ở Industries & Categories → Brand dictionary) ·
          {" "}<b>{detail.stats.outside_selected_categories}</b> bài ngoài danh mục đã chọn · <b>{detail.stats.new_evidence}</b> bằng chứng mới.
          {detail.stats.failed_sources?.length > 0 && <div className="warn">Nguồn lỗi: {detail.stats.failed_sources.join(", ")} — xem cột Error bên dưới / bấm Test ở Source Manager.</div>}
        </div>}
        {detail.error && <pre className="warn">{detail.error}</pre>}
        <table className="tbl"><thead><tr><th>Source</th><th>Market</th><th>Query</th><th>Status</th><th>Items</th><th>New</th><th>Cache</th><th>Error</th></tr></thead>
          <tbody>{detail.tasks.map((t: Row) => <tr key={t.id}><td>{t.source_key}</td><td>{t.market_code}</td><td className="small">{t.query}</td><td>{t.status}</td>
            <td>{t.items_found}</td><td>{t.products_new}</td><td>{t.from_cache ? "cached" : ""}</td><td className="small warn">{t.error}</td></tr>)}</tbody></table>
        <button onClick={() => setDetail(null)}>Close</button></div></div>}
    </div>
  );
}

// ===================================================================== Taxonomy manager
export function TaxonomyManager() {
  const { data, reload } = useTaxonomy();
  const { data: brands, reload: rb } = useData<Row[]>("/api/brands");
  const [sel, setSel] = useState<Row | null>(null);
  const [newInd, setNewInd] = useState("");
  const [nb, setNb] = useState({ name: "", aliases: [] as string[], official_domains: [] as string[] });
  const flat: Row[] = [];
  const walk = (n: Row, path: string) => { flat.push({ ...n, path }); (n.children || []).forEach((c: Row) => walk(c, path + " › " + c.name)); };
  (data || []).forEach(i => i.categories.forEach((c: Row) => walk(c, i.name + " › " + c.name)));
  const saveCat = async () => { const { children, path, product_count, ...c } = sel!; c.id ? await api.put(`/api/categories/${c.id}`, c) : await api.post("/api/categories", c); setSel(null); reload(); };
  const Node = ({ n, ind, depth }: { n: Row; ind: Row; depth: number }) => (
    <div style={{ marginLeft: depth * 16 }} className={"tnode" + (n.active ? "" : " inactive")}>
      <a onClick={() => setSel({ ...n })}>{n.name}</a> <span className="muted">({n.product_count})</span>
      <a className="small" onClick={() => setSel({ industry_id: ind.id, parent_id: n.id, name: "", keywords: [], exclude_keywords: [], local_keywords: {}, brands: [], active: true })}> + sub</a>
      {(n.children || []).map((c: Row) => <Node key={c.id} n={c} ind={ind} depth={depth + 1} />)}
    </div>);
  return (
    <div>
      <div className="pagehead"><h2>Industry & Category Manager</h2>
        <span><input placeholder="New industry name" value={newInd} onChange={e => setNewInd(e.target.value)} />
          <button onClick={async () => { if (newInd) { await api.post("/api/industries", { name: newInd }); setNewInd(""); reload(); } }}>+ Industry</button></span></div>
      <p className="muted small">Deleting a node that still has products only deactivates it, so no collected data is lost. Merge moves product associations to another node.</p>
      <div className="split">
        <div className="tree">{(data || []).map(ind => <div key={ind.id} className={"pgroup" + (ind.active ? "" : " inactive")}>
          <div className="pghead"><b>{ind.name}</b>
            <a onClick={() => setSel({ industry_id: ind.id, parent_id: null, name: "", keywords: [], exclude_keywords: [], local_keywords: {}, brands: [], active: true })}>+ category</a>
            <a onClick={async () => { const n = prompt("Rename industry", ind.name); if (n) { await api.put(`/api/industries/${ind.id}`, { name: n }); reload(); } }}>rename</a>
            <a onClick={async () => { await api.put(`/api/industries/${ind.id}`, { active: !ind.active }); reload(); }}>{ind.active ? "deactivate" : "activate"}</a>
            <a onClick={async () => { if (confirm("Delete industry? (deactivated instead if it has products)")) { alert(JSON.stringify(await api.del(`/api/industries/${ind.id}`))); reload(); } }}>delete</a></div>
          {ind.categories.map((c: Row) => <Node key={c.id} n={c} ind={ind} depth={1} />)}
          {ind.attributes.length > 0 && <div className="small muted">Attributes: {ind.attributes.map((a: Row) => a.label + (a.identity_relevant ? "*" : "")).join(", ")}</div>}
          <a className="small" onClick={async () => { const k = prompt("New attribute key (e.g. storage, edition)"); if (k) { await api.post("/api/attributes", { industry_id: ind.id, key: k, label: k, identity_relevant: confirm("Is it part of product identity?") }); reload(); } }}>+ attribute</a>
        </div>)}</div>
        {sel && <div className="card editor">
          <h4>{sel.id ? "Edit" : "New"} {sel.parent_id ? "subcategory" : "category"}</h4>
          <div className="form">
            <label>Name <input value={sel.name} onChange={e => setSel({ ...sel, name: e.target.value })} /></label>
            <label>Keywords (end with * for prefix) <ListInput value={sel.keywords} onChange={v => setSel({ ...sel, keywords: v })} /></label>
            <label>Excluded keywords <ListInput value={sel.exclude_keywords} onChange={v => setSel({ ...sel, exclude_keywords: v })} /></label>
            <label>Brands mapped <ListInput value={sel.brands} onChange={v => setSel({ ...sel, brands: v })} /></label>
            <label>Group label <input value={sel.group_label || ""} onChange={e => setSel({ ...sel, group_label: e.target.value })} /></label>
            <label>Local-language keywords (JSON) <textarea rows={3} defaultValue={JSON.stringify(sel.local_keywords || {})} onBlur={e => { try { setSel({ ...sel, local_keywords: JSON.parse(e.target.value) }); } catch { alert('Use JSON like {"vi": ["giày"], "ja": ["スニーカー"]}'); } }} /></label>
            <label>Active <input type="checkbox" checked={sel.active} onChange={e => setSel({ ...sel, active: e.target.checked })} /></label>
          </div>
          <div className="btnrow"><button className="primary" onClick={saveCat}>Save</button>
            {sel.id && <button onClick={async () => { alert(JSON.stringify(await api.del(`/api/categories/${sel.id}`))); setSel(null); reload(); }}>Delete</button>}
            {sel.id && <select defaultValue="" onChange={async e => { if (e.target.value && confirm("Merge into selected node?")) { await api.post(`/api/categories/${sel.id}/merge-into/${e.target.value}`); setSel(null); reload(); } }}>
              <option value="">Merge into…</option>{flat.filter(f => f.id !== sel.id).map(f => <option key={f.id} value={f.id}>{f.path}</option>)}</select>}
            <button onClick={() => setSel(null)}>Close</button></div>
        </div>}
      </div>
      <h3>Brand dictionary (used for product extraction)</h3>
      <div className="btnrow"><input placeholder="Brand" value={nb.name} onChange={e => setNb({ ...nb, name: e.target.value })} />
        <ListInput value={nb.aliases} onChange={v => setNb({ ...nb, aliases: v })} placeholder="aliases, comma separated" />
        <ListInput value={nb.official_domains} onChange={v => setNb({ ...nb, official_domains: v })} placeholder="official domains" />
        <button onClick={async () => { if (nb.name) { await api.post("/api/brands", nb); setNb({ name: "", aliases: [], official_domains: [] }); rb(); } }}>+ Brand</button></div>
      <table className="tbl"><thead><tr><th>Brand</th><th>Aliases</th><th>Official domains</th><th /></tr></thead>
        <tbody>{(brands || []).map(b => <tr key={b.id}><td>{b.name}</td>
          <td><ListInput value={b.aliases} onChange={v => api.put(`/api/brands/${b.id}`, { aliases: v }).then(rb)} /></td>
          <td><ListInput value={b.official_domains} onChange={v => api.put(`/api/brands/${b.id}`, { official_domains: v }).then(rb)} /></td>
          <td><button className="mini" onClick={async () => { if (confirm("Delete brand?")) { await api.del(`/api/brands/${b.id}`); rb(); } }}>delete</button></td></tr>)}</tbody></table>
    </div>
  );
}

// ===================================================================== Source manager
export function SourceManager() {
  const { data, reload } = useData<Row[]>("/api/sources");
  const [res, setRes] = useState<Record<number, Row>>({});
  const [n, setN] = useState({ key: "", name: "", url: "", markets: ["GLOBAL"] as string[] });
  return (
    <div>
      <div className="pagehead"><h2>Source Manager</h2></div>
      <p className="muted small">Only official APIs, RSS feeds and public pages are used. Logins, paywalls, CAPTCHAs and anti-bot systems are never bypassed; such sources are reported as BLOCKED / AUTH_REQUIRED.</p>
      <table className="tbl"><thead><tr><th>On</th><th>Source</th><th>Type</th><th>Adapter</th><th>Markets</th><th>Status</th><th>Evidence</th><th>Last success</th><th>Error / notes</th><th>Rate/min</th><th /></tr></thead>
        <tbody>{(data || []).map(s => <tr key={s.id}>
          <td><input type="checkbox" checked={s.enabled} onChange={async e => { await api.put(`/api/sources/${s.id}`, { enabled: e.target.checked }); reload(); }} /></td>
          <td><b>{s.name}</b><div className="small muted urltext">{s.url}</div></td><td>{s.source_type}</td><td>{s.adapter}</td><td>{(s.markets || []).join(", ") || "per market"}</td>
          <td><span className={"chip src-" + s.status}>{s.status}</span></td><td>{s.evidence_count}</td><td>{fmtDate(s.last_success)}</td>
          <td className="small">{s.last_error && <div className="warn">{s.last_error}</div>}{s.notes}{res[s.id] && <div>{res[s.id].status}: {res[s.id].error || res[s.id].sample?.map((x: Row) => x.title).join(" | ")}</div>}</td>
          <td><input className="w60" type="number" defaultValue={s.rate_per_minute} onBlur={e => api.put(`/api/sources/${s.id}`, { rate_per_minute: Number(e.target.value) })} /></td>
          <td><button className="mini" onClick={async () => { const r = await api.post(`/api/sources/${s.id}/test`); setRes({ ...res, [s.id]: r }); reload(); }}>Test</button></td></tr>)}</tbody></table>
      <h3>Add a permitted RSS feed</h3>
      <div className="btnrow">
        <input placeholder="key (unique)" value={n.key} onChange={e => setN({ ...n, key: e.target.value })} />
        <input placeholder="Name" value={n.name} onChange={e => setN({ ...n, name: e.target.value })} />
        <input placeholder="https://site.com/feed" style={{ flex: 1 }} value={n.url} onChange={e => setN({ ...n, url: e.target.value })} />
        <ListInput value={n.markets} onChange={v => setN({ ...n, markets: v })} placeholder="market codes, e.g. JP" />
        <button onClick={async () => { await api.post("/api/sources", { ...n, adapter: "rss", platform: n.name }); setN({ key: "", name: "", url: "", markets: ["GLOBAL"] }); reload(); }}>+ Add source</button>
      </div>
    </div>
  );
}

// ===================================================================== Settings
function WeightsEditor({ kind, settings, industries, onSaved }: { kind: string; settings: Row; industries: Row[]; onSaved: () => void }) {
  const [ind, setInd] = useState("default");
  const key = `weights.${kind}.${ind}`;
  const base = settings[key] || settings[`weights.${kind}.default`] || {};
  const [w, setW] = useState<Row>(base);
  useEffect(() => setW(settings[key] || settings[`weights.${kind}.default`] || {}), [key, settings]);
  const total = Object.values(w).reduce((a: number, b: any) => a + Number(b || 0), 0);
  return (
    <div className="card"><h4>{kind[0].toUpperCase() + kind.slice(1)} score weights</h4>
      <select value={ind} onChange={e => setInd(e.target.value)}><option value="default">default (all industries)</option>{industries.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select>
      {Object.keys(settings[`weights.${kind}.default`] || {}).map(k => <label key={k} className="wrow">{k} <input type="number" value={w[k] ?? 0} onChange={e => setW({ ...w, [k]: Number(e.target.value) })} /></label>)}
      <div className="small muted">total {total} (normalised automatically; missing signals are excluded, not counted as zero)</div>
      <button onClick={async () => { await api.put(`/api/settings/${key}`, w); await api.post("/api/recompute"); onSaved(); alert("Saved — scores recomputed from stored observations."); }}>Save & recompute</button>
    </div>);
}

export function Settings({ theme, setTheme }: { theme: string; setTheme: (t: string) => void }) {
  const { data: s, reload } = useData<Row>("/api/settings");
  const { data: tax } = useTaxonomy();
  const { data: markets, reload: rm } = useData<Row[]>("/api/markets");
  const [nm, setNm] = useState({ code: "", name: "", region: "Asia", languages: ["en"] as string[], google_news_ceid: "", is_city: false });
  if (!s) return <div>Loading…</div>;
  const th = s.thresholds || {};
  return (
    <div>
      <div className="pagehead"><h2>Settings</h2></div>
      <div className="cols3">
        {["trend", "early", "opportunity"].map(k => <WeightsEditor key={k} kind={k} settings={s} industries={tax || []} onSaved={reload} />)}
        <div className="card"><h4>Confidence & evidence thresholds</h4>
          {Object.entries(th).map(([k, v]) => <label key={k} className="wrow">{k} <input type="number" step="0.05" defaultValue={v as any}
            onBlur={async e => { await api.put("/api/settings/thresholds", { ...th, [k]: Number(e.target.value) }); reload(); }} /></label>)}</div>
        <div className="card"><h4>Display</h4>
          <label className="wrow">Theme <select value={theme} onChange={e => setTheme(e.target.value)}><option value="light">light</option><option value="dark">dark</option></select></label>
          <div className="small muted">Scheduler timezone: {s.scheduler?.timezone} (change GPTI_TIMEZONE in .env).</div></div>
      </div>
      <h3>Markets</h3>
      <table className="tbl"><thead><tr><th>Code</th><th>Name</th><th>Region</th><th>Languages</th><th>Google News edition (hl|gl|ceid)</th><th>City</th><th>Active</th></tr></thead>
        <tbody>{(markets || []).map(m => <tr key={m.id}><td>{m.code}</td><td>{m.name}</td><td>{m.region}</td>
          <td><ListInput value={m.languages} onChange={v => api.put(`/api/markets/${m.id}`, { languages: v }).then(rm)} /></td>
          <td><input defaultValue={m.google_news_ceid || ""} onBlur={e => api.put(`/api/markets/${m.id}`, { google_news_ceid: e.target.value || null }).then(rm)} /></td>
          <td>{m.is_city ? "city" : ""}</td>
          <td><input type="checkbox" checked={m.active} onChange={e => api.put(`/api/markets/${m.id}`, { active: e.target.checked }).then(rm)} /></td></tr>)}</tbody></table>
      <div className="btnrow">
        <input placeholder="Code (e.g. AU)" value={nm.code} onChange={e => setNm({ ...nm, code: e.target.value })} className="w60" />
        <input placeholder="Name" value={nm.name} onChange={e => setNm({ ...nm, name: e.target.value })} />
        <input placeholder="Region" value={nm.region} onChange={e => setNm({ ...nm, region: e.target.value })} />
        <ListInput value={nm.languages} onChange={v => setNm({ ...nm, languages: v })} placeholder="languages" />
        <input placeholder="en-AU|AU|AU:en" value={nm.google_news_ceid} onChange={e => setNm({ ...nm, google_news_ceid: e.target.value })} />
        <label className="chk"><input type="checkbox" checked={nm.is_city} onChange={e => setNm({ ...nm, is_city: e.target.checked })} /> city</label>
        <button onClick={async () => { await api.post("/api/markets", nm); setNm({ ...nm, code: "", name: "" }); rm(); }}>+ Market</button>
      </div>
    </div>
  );
}
