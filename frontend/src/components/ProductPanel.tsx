import { useState } from "react";
import { api, Row } from "../api";
import { fmtDate, useData } from "./common";
import { StatusChip } from "./Grid";
import { openTrends, suggestTerm } from "../trends";

function TrendsBox({ productId, product, markets }: { productId: number; product: Row; markets: Row[] }) {
  const [term, setTerm] = useState(() => suggestTerm({ product_name: product.name, trends_term: product.attributes?.trends_term }));
  const codes = markets.map(m => m.market_code);
  const [mk, setMk] = useState(codes.find(c => c !== "GLOBAL") || codes[0] || "US");
  const { data: si } = useData<Row[]>(`/api/products/${productId}/search-interest`, undefined, [productId]);
  const last = (si || []).reduce((a: Row | null, r: Row) => (!a || r.imported_at > a.imported_at ? r : a), null);
  return (
    <div className="card">
      <b>Google Trends</b>
      <div className="btnrow">
        <input value={term} onChange={e => setTerm(e.target.value)} title="Short terms work best, e.g. 'labubu', 'samba og'" />
        <select value={mk} onChange={e => setMk(e.target.value)}>{[...new Set([...codes, "US", "VN", "JP", "KR", "GLOBAL"])].map(c => <option key={c}>{c}</option>)}</select>
        <button className="primary" onClick={async () => { await api.put(`/api/products/${productId}/trends-term`, { term }); openTrends([term], mk); }}>Mở Google Trends</button>
      </div>
      <div className="small muted">Then press ⬇ on “Interest over time” → import the CSV on <a href="#capture">Add Evidence & Imports</a> (this term is remembered, so the import maps to this product automatically).
        {last ? ` Last import: ${fmtDate(last.imported_at)} · ${(si || []).length} points.` : " No search data imported yet."}</div>
    </div>
  );
}

export default function ProductPanel({ productId, onClose, onChanged }: { productId: number; onClose: () => void; onChanged?: () => void }) {
  const { data, reload } = useData<Row>(`/api/products/${productId}`, undefined, [productId]);
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<Row | null>(null);
  const [url, setUrl] = useState("");
  if (!data) return <div className="drawer"><button className="close" onClick={onClose}>×</button>Loading…</div>;
  const p = data.product;
  const run = async (label: string, fn: () => Promise<any>) => {
    setBusy(label);
    try { const r = await fn(); if (r && r.checked) setResult(r); await reload(); onChanged?.(); }
    catch (e: any) { alert(e.message); } finally { setBusy(""); }
  };
  return (
    <div className="drawer">
      <button className="close" onClick={onClose}>×</button>
      <div className="phead">
        {p.image_url && <img src={p.image_url} className="pimg" referrerPolicy="no-referrer" alt="" />}
        <div>
          <h3>{p.name} {p.model_variant && <span className="muted">“{p.model_variant}”</span>}</h3>
          <div>{p.brand} · SKU {p.sku || "unknown"} · {data.categories.join(", ") || "no category"}</div>
          <div>First detected {fmtDate(p.first_detected)} · last seen {fmtDate(p.last_seen)}</div>
          {p.is_fixture && <div className="demo">DEMO / TEST FIXTURE — not a live market finding</div>}
          {p.needs_review && <div className="warn">Possible duplicate identity — review before merging (product #{p.attributes?.possible_duplicate_of}).</div>}
          {p.image_url && <div className="small">Image URL: <span className="urltext">{p.image_url}</span> <span className="muted">({p.attributes?.image_source || "source unknown"})</span></div>}
        </div>
      </div>
      <div className="btnrow">
        <button className="primary" disabled={!!busy} onClick={() => run("links", () => api.post(`/api/products/${productId}/find-links`))}>
          {busy === "links" ? "Searching this product…" : "Find Product Information Links"}</button>
        <button disabled={!!busy} onClick={() => run("buy", () => api.post(`/api/products/${productId}/find-links?purchase=true`))}>Find Purchase Links</button>
        <button disabled={!!busy} onClick={() => run("scan", () => api.post("/api/scans", { product_ids: [productId], depth: "QUICK" }))}>Refresh this product</button>
        <button onClick={() => run("w", () => api.post("/api/shortlists", { list_type: "EARLY_WATCHLIST", product_id: productId }))}>+ Watchlist</button>
        <button onClick={() => run("o", () => api.post("/api/shortlists", { list_type: "OPPORTUNITY", product_id: productId, target_market: "US" }))}>+ Opportunity shortlist</button>
      </div>
      <TrendsBox productId={productId} product={p} markets={data.markets} />
      {result && (
        <div className="card">
          <b>Link finder result: <StatusChip v={result.status} /></b>
          <div>Primary information URL: {result.primary_url ? <a href={result.primary_url} target="_blank" rel="noreferrer">{result.primary_url}</a> : "none verified"}</div>
          <div>Optional purchase URL: {result.purchase_url || "none (not required)"}</div>
          {result.missing_fields?.length > 0 && <div className="muted">Not observed on primary page: {result.missing_fields.join(", ")}</div>}
          {result.failures?.length > 0 && <div className="warn">Failures: {result.failures.join("; ")}</div>}
        </div>
      )}
      <h4>Link candidates ({data.links.length})</h4>
      <table className="tbl">
        <thead><tr><th>Primary</th><th>Type</th><th>Identity</th><th>Info score</th><th>URL</th><th>Purchase</th><th>Checked</th></tr></thead>
        <tbody>{data.links.map((l: Row) => (
          <tr key={l.id} className={l.is_primary_information_url ? "sel" : ""}>
            <td>{l.is_primary_information_url ? "★" : l.identity_match !== "REJECTED" ? <button className="mini" onClick={() => run("p", () => api.put(`/api/products/${productId}/primary-link/${l.id}`))}>set</button> : ""}</td>
            <td>{l.page_type}</td><td><StatusChip v={l.identity_match} /></td><td>{l.completeness_score}</td>
            <td className="urltd"><a href={l.url} target="_blank" rel="noreferrer">{l.url}</a>{l.fetch_error && <div className="muted">{l.fetch_error}</div>}</td>
            <td>{l.is_purchase_url ? `${l.price ?? ""} ${l.currency ?? ""} ${l.stock_state ?? ""}` : ""}</td>
            <td>{fmtDate(l.last_verified_at)}</td>
          </tr>))}</tbody>
      </table>
      <div className="btnrow">
        <input placeholder="Add candidate URL (it will be verified)…" value={url} onChange={e => setUrl(e.target.value)} style={{ flex: 1 }} />
        <button disabled={!url} onClick={() => run("add", async () => { const r = await api.post(`/api/products/${productId}/links`, { url }); setUrl(""); return r.result; })}>Add & verify</button>
      </div>
      <h4>Market trends</h4>
      <table className="tbl"><thead><tr><th>Market</th><th>Trend</th><th>Status</th><th>Coverage</th><th>Early</th><th>Stage</th><th>Explanation</th></tr></thead>
        <tbody>{data.trends.map((t: Row) => <tr key={t.id}><td>{t.market_code}</td><td>{t.trend_score ?? "—"}</td><td><StatusChip v={t.trend_status} /></td>
          <td>{Math.round(t.coverage * 100)}%</td><td>{t.early_score ?? "—"}</td><td><StatusChip v={t.lifecycle_stage} /></td>
          <td className="small">{t.explanation}<br />{t.early_explanation}<br /><span className="muted">breakdown: {JSON.stringify(t.breakdown)}</span></td></tr>)}</tbody></table>
      {data.releases.length > 0 && <>
        <h4>Release / rumor timeline</h4>
        {data.releases.map((r: Row) => <div key={r.id} className="card">
          <b>{r.market_code}</b>: <StatusChip v={r.release_status} /> · {r.expected_date_text} ({r.date_precision}) · confidence <StatusChip v={r.rumor_confidence} />
          <ul>{r.history.map((h: Row) => <li key={h.id} className="small">{fmtDate(h.changed_at)} {h.field}: {h.old_value ?? "∅"} → {h.new_value} {h.source_url && <a href={h.source_url} target="_blank" rel="noreferrer">source</a>}</li>)}</ul>
        </div>)}
      </>}
      <h4>Evidence ({data.evidence.length})</h4>
      <table className="tbl"><thead><tr><th>Published</th><th>Market</th><th>Outlet</th><th>Claim</th><th>Title / URL</th></tr></thead>
        <tbody>{data.evidence.map((e: Row) => <tr key={e.id} className={e.is_syndicated_copy ? "muted" : ""}>
          <td>{fmtDate(e.published_at)}</td><td>{e.market_code}</td><td>{e.outlet}{e.is_syndicated_copy ? " (syndicated copy)" : ""}</td><td>{e.claim_type}</td>
          <td className="urltd">{e.title}<br /><a href={e.url} target="_blank" rel="noreferrer">{e.url}</a>{e.url_is_aggregator ? <span className="tag">aggregator link</span> : null}
            {Object.keys(e.engagement || {}).length > 0 && <div className="small">engagement: {JSON.stringify(e.engagement)}</div>}</td></tr>)}</tbody></table>
      {data.aliases.length > 0 && <div className="small">Aliases seen: {data.aliases.join(" · ")}</div>}
    </div>
  );
}
