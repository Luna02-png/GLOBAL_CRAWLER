import { useEffect, useState } from "react";
import { api, Row } from "../api";
import Grid, { Col } from "../components/Grid";
import { CategoryDropdown, MarketDropdown, RefreshBar, useData } from "../components/common";
import { openTrends, suggestTerm } from "../trends";

export function TrendsButton({ r }: { r: Row }) {
  return <button className="mini" title="Opens Google Trends (90 days, this market). Download the CSV with ⬇ and import it on Add Evidence & Imports."
    onClick={() => openTrends([suggestTerm(r)], r.market_code)}>Mở Google Trends</button>;
}

export const RESEARCH_COLS: Col[] = [
  { key: "product_name", label: "Product Name", width: 220, pinned: "left" },
  { key: "best_info_url", label: "Link (Best Product Information URL)", kind: "url", pinned: "left", width: 280 },
  { key: "industry", label: "Industry" },
  { key: "category", label: "Category" },
  { key: "subcategory", label: "Subcategory" },
  { key: "region", label: "Market / Region", width: 120 },
  { key: "country", label: "Country", width: 120 },
  { key: "brand", label: "Brand", width: 110 },
  { key: "model_variant", label: "Model / Colorway / Version", width: 170 },
  { key: "sku", label: "SKU / Model Number", width: 130 },
  { key: "image_url", label: "Product Image URL", kind: "image" },
  { key: "best_link_type", label: "Best Link Type", width: 110 },
  { key: "alt_info_url_1", label: "Alternative Information URL 1", kind: "url" },
  { key: "alt_info_url_2", label: "Alternative Information URL 2", kind: "url" },
  { key: "purchase_url", label: "Optional Purchase URL", kind: "url" },
  { key: "ref_url_1", label: "Reference URL 1", kind: "url" },
  { key: "ref_url_2", label: "Reference URL 2", kind: "url" },
  { key: "ref_url_3", label: "Reference URL 3", kind: "url" },
  { key: "source_platforms", label: "Source Platforms" },
  { key: "trend_score", label: "Trend Score", kind: "score", width: 100 },
  { key: "trend_status", label: "Trend Status", kind: "status", width: 150 },
  { key: "early_score", label: "Early Signal Score", kind: "score", width: 110 },
  { key: "opportunity_score", label: "Opportunity Score", kind: "score", width: 110 },
  { key: "confidence", label: "Evidence Confidence", kind: "status", width: 110 },
  { key: "coverage", label: "Data Coverage", kind: "pct", width: 100 },
  { key: "trend_explanation", label: "Trend Explanation", width: 360 },
  { key: "release_status", label: "Release Status", kind: "status", width: 150 },
  { key: "first_detected", label: "First Detected", width: 130 },
  { key: "last_seen", label: "Last Seen / Updated", width: 130 },
  { key: "link_status", label: "Product Link Verification Status", kind: "status", width: 140 }
];

const PRESETS: Record<string, string[]> = {
  "All columns": [],
  Fashion: ["industry", "category", "subcategory", "region", "trend_explanation", "alt_info_url_2"],
  Technology: ["subcategory", "region", "alt_info_url_2", "ref_url_3", "trend_explanation"],
  "Links only": ["industry", "category", "subcategory", "region", "source_platforms", "trend_score", "trend_status", "early_score", "opportunity_score",
    "confidence", "coverage", "trend_explanation", "release_status", "first_detected", "last_seen"],
};

function jobFromHash(): number | null {
  const h = location.hash.slice(1);
  const i = h.indexOf("?");
  const v = new URLSearchParams(i >= 0 ? h.slice(i + 1) : "").get("job");
  return v ? Number(v) : null;
}

export function ResearchSheet({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const [jobId, setJobId] = useState<number | null>(jobFromHash);
  useEffect(() => { const h = () => setJobId(jobFromHash()); window.addEventListener("hashchange", h); return () => window.removeEventListener("hashchange", h); }, []);
  const { data: job, reload: reloadJob } = useData<Row>(jobId ? `/api/jobs/${jobId}` : null, undefined, [jobId]);
  const running = !!job && ["QUEUED", "RUNNING"].includes(job.status);
  const [markets, setMarkets] = useState<string[]>([]);
  const [cats, setCats] = useState<number[]>([]);
  const [status, setStatus] = useState<string>("");
  const [expand, setExpand] = useState(false);
  const [preset, setPreset] = useState("All columns");
  const [msg, setMsg] = useState("");
  const params = { markets: markets.join(","), categories: cats.join(","), status, include_fixture: demo, expand, job_id: jobId ?? undefined };
  const { data, reload, loading } = useData<Row>("/api/research", params);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => { reloadJob(); reload(); }, 4000);
    return () => clearInterval(t);
  }, [running, reload, reloadJob]);
  const clearJob = () => { setJobId(null); location.hash = "sheet"; };
  const cols = RESEARCH_COLS.map(c => ({ ...c, hide: PRESETS[preset].includes(c.key) }));
  const bulk = async (mode: string, ids: number[]) => {
    const r = await api.post("/api/links/bulk", { mode, product_ids: ids });
    setMsg(r.job_id ? `Link job #${r.job_id} queued for ${r.count} product(s) — only these products are searched.` : "Nothing to do.");
  };
  return (
    <div>
      <div className="pagehead">
        <h2>Product Research Sheet</h2>
        <RefreshBar scope={{ markets, category_ids: cats }} onStarted={id => { setJobId(id); location.hash = `sheet?job=${id}`; }} />
      </div>
      {jobId && <div className="jobbanner">
        Đang xem <b>kết quả lần quét #{jobId}</b>{job ? <> · {job.preset_name || "tự chọn"} · <span className={"chip job-" + job.status}>{job.status}</span>
          {job.stats?.products_updated !== undefined && <> · {job.stats.products_new ?? 0} sản phẩm mới, {job.stats.products_updated} sản phẩm có dữ liệu</>}
          {job.stats?.articles_read !== undefined && <span className="small muted"> · đọc {job.stats.articles_read} bài, {job.stats.no_product_recognised} bài không nhận ra sản phẩm, {job.stats.outside_selected_categories} ngoài danh mục{job.stats.failed_sources?.length ? `, nguồn lỗi: ${job.stats.failed_sources.join(", ")}` : ""}</span>}
          {running && <span className="muted"> · đang quét, bảng tự cập nhật…</span>}</> : null}
        <button className="mini" onClick={clearJob}>Bỏ lọc, xem tất cả</button>
      </div>}
      <div className="filters">
        <b className="small">Lọc bảng:</b>
        <CategoryDropdown value={cats} onChange={setCats} prefix="Danh mục" />
        <MarketDropdown value={markets} onChange={setMarkets} prefix="Thị trường" />
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">all statuses</option>
          {["HOT NOW", "RISING FAST", "UPCOMING HYPE", "STABLE DEMAND", "DECLINING", "INSUFFICIENT DATA"].map(s => <option key={s}>{s}</option>)}
        </select>
        <label className="chk"><input type="checkbox" checked={expand} onChange={e => setExpand(e.target.checked)} /> one row per category</label>
        <select value={preset} onChange={e => setPreset(e.target.value)} title="Column preset">{Object.keys(PRESETS).map(p => <option key={p}>{p}</option>)}</select>
        <button onClick={reload}>{loading ? "Loading…" : "Reload"}</button>
        <span className="muted small">Lọc chỉ đổi phần hiển thị, không tự quét. Phạm vi quét chọn ở góc trên (mặc định lấy theo bộ lọc này).</span>
        {msg && <span className="okmsg">{msg}</span>}
      </div>
      <Grid key={preset} rows={data?.rows || []} cols={cols} dataset="research" storageKey={"research:" + preset}
        filters={{ markets: markets.join(","), status, include_fixture: demo, expand, categories: cats.join(","), job_id: jobId ?? undefined }}
        onOpen={r => open(r.product_id)}
        actions={r => <><button className="mini" onClick={async () => { await api.post(`/api/products/${r.product_id}/find-links`); reload(); }}>Find Product Links</button><TrendsButton r={r} /></>}
        toolbar={sel => <>
          <span className="sep" />
          <button disabled={!sel.length} title="Compare up to 5 selected products in one Google Trends chart (same market)" onClick={() => {
            const markets = [...new Set(sel.map(s => s.market_code))];
            if (markets.length > 1 && !confirm(`Selected rows are in ${markets.length} markets. Google Trends compares one market at a time - use ${markets[0]}?`)) return;
            const terms = [...new Set(sel.filter(s => s.market_code === markets[0]).map(suggestTerm))];
            if (terms.length > 5) alert("Google Trends compares at most 5 terms - the first 5 are opened.");
            openTrends(terms, markets[0]);
          }}>Mở Google Trends (selected)</button>
          <button disabled={!sel.length} onClick={() => bulk("selected", [...new Set(sel.map(s => s.product_id))])}>Find Links for Selected</button>
          <button onClick={() => bulk("missing", [])}>Find Missing Information Links</button>
          <button disabled={!sel.length} onClick={() => bulk("purchase", [...new Set(sel.map(s => s.product_id))])}>Find Purchase Links</button>
          <button disabled={!sel.length} onClick={async () => { const r = await api.post("/api/scans", { product_ids: [...new Set(sel.map(s => s.product_id))], depth: "QUICK" }); setMsg(`Refresh job #${r.job_id} queued for selected products.`); }}>Refresh selected</button>
        </>} />
    </div>
  );
}

export function LinkFinderPage({ demo, open }: { demo: boolean; open: (id: number) => void }) {
  const { data, reload } = useData<Row>("/api/research", { include_fixture: demo });
  const { data: jobs, reload: rj } = useData<Row[]>("/api/jobs", { kind: "LINK_FINDER", limit: 20 });
  const rows = (data?.rows || []).filter((r: Row) => !r.best_info_url || r.link_status !== "VERIFIED");
  const [msg, setMsg] = useState("");
  const bulk = async (mode: string, ids: number[] = []) => {
    const r = await api.post("/api/links/bulk", { mode, product_ids: ids });
    setMsg(r.job_id ? `Job #${r.job_id}: ${r.count} products queued` : "Nothing to do");
    rj();
  };
  const act = async (id: number, a: string) => { await api.post(`/api/jobs/${id}/${a}`); rj(); };
  return (
    <div>
      <div className="pagehead"><h2>Product Link Finder</h2>
        <span><button className="primary" onClick={() => bulk("missing")}>Find Missing Information Links</button> {msg && <span className="okmsg">{msg}</span>}</span></div>
      <p className="muted small">Primary goal: the most informative page about the exact product (official page, article, review, release info or detailed listing).
        A purchase link is optional; a product with a verified article is <b>not</b> “missing a link”. TITLE_MATCH = identity matched from the source feed title only; run Find Product Links to verify the page itself.</p>
      <div className="card"><h4>Link jobs</h4>
        <table className="tbl"><thead><tr><th>#</th><th>Status</th><th>Progress</th><th>Verified</th><th>Review</th><th>Not found</th><th>Failed</th><th /></tr></thead>
          <tbody>{(jobs || []).map(j => <tr key={j.id}><td>{j.id}</td><td>{j.status}</td><td>{j.stats?.done ?? 0}/{j.stats?.total ?? "?"}</td>
            <td>{j.stats?.verified ?? 0}</td><td>{j.stats?.needs_review ?? 0}</td><td>{j.stats?.not_found ?? 0}</td><td>{j.stats?.failed ?? 0}</td>
            <td>{["RUNNING", "QUEUED"].includes(j.status) && <button className="mini" onClick={() => act(j.id, "pause")}>pause</button>}
              {["PAUSED"].includes(j.status) && <button className="mini" onClick={() => act(j.id, "resume")}>resume</button>}
              {["RUNNING", "QUEUED", "PAUSED"].includes(j.status) && <button className="mini" onClick={() => act(j.id, "cancel")}>cancel</button>}</td></tr>)}</tbody></table>
        <button onClick={() => { rj(); reload(); }}>Refresh status</button>
      </div>
      <Grid rows={rows} cols={RESEARCH_COLS.filter(c => ["country", "brand", "product_name", "model_variant", "sku", "best_info_url", "best_link_type", "purchase_url", "ref_url_1", "link_status"].includes(c.key))}
        dataset="research" storageKey="linkfinder" filters={{ include_fixture: demo }} onOpen={r => open(r.product_id)} height="calc(100vh - 420px)"
        actions={r => <button className="mini" onClick={async () => { await api.post(`/api/products/${r.product_id}/find-links`); reload(); }}>Find Product Links</button>}
        toolbar={sel => <button disabled={!sel.length} onClick={() => bulk("selected", [...new Set(sel.map(s => s.product_id))])}>Find Links for Selected</button>} />
    </div>
  );
}
