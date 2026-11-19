import { useEffect, useMemo, useRef, useState } from "react";
import { api, Row } from "../api";
import { MarketPicker, useData } from "../components/common";
import { StatusChip } from "../components/Grid";

const BOOKMARKLET = `javascript:(()=>{const m=n=>(document.querySelector('meta[property="'+n+'"],meta[name="'+n+'"]')||{}).content||"";const s=(window.getSelection()||"").toString().slice(0,1500);const p=new URLSearchParams({url:location.href,title:m("og:title")||document.title,text:s||m("og:description")||m("description"),img:m("og:image")});window.open("${location.origin}/#capture?"+p.toString(),"gpti_capture","width=760,height=900");})()`;

function hashParams(): URLSearchParams {
  const h = location.hash.slice(1);
  const i = h.indexOf("?");
  return new URLSearchParams(i >= 0 ? h.slice(i + 1) : "");
}

function useMarket(): [string, (v: string) => void] {
  const [m, setM] = useState(() => localStorage.getItem("captureMarket") || "VN");
  return [m, v => { setM(v); localStorage.setItem("captureMarket", v); }];
}

function CaptureForm() {
  const hp = useMemo(hashParams, []);
  const [market, setMarket] = useMarket();
  const [f, setF] = useState<Row>({ url: hp.get("url") || "", title: hp.get("title") || "", text: hp.get("text") || "", image_url: hp.get("img") || "",
    product_name: "", brand: "", model_variant: "", sku: "", author: "", views: "", likes: "", comments: "", shares: "" });
  const [pv, setPv] = useState<Row | null>(null);
  const [res, setRes] = useState<Row | null>(null);
  const preview = async () => {
    if (!f.url) return;
    const r = await api.post("/api/capture/preview", { url: f.url, title: f.title, text: f.text });
    setPv(r);
    setF((x: Row) => ({ ...x, author: x.author || r.author || "", ...Object.fromEntries(Object.entries(r.engagement || {}).filter(([k]) => !x[k]).map(([k, v]) => [k, String(v)])),
      product_name: x.product_name || (r.mentions?.[0]?.name ?? ""), model_variant: x.model_variant || (r.mentions?.[0]?.model_variant ?? ""), sku: x.sku || (r.mentions?.[0]?.sku ?? "") }));
  };
  useEffect(() => { if (f.url) preview(); }, []);
  const save = async () => {
    const num = (v: string) => (v === "" ? null : Number(String(v).replace(/[^\d]/g, "")) || null);
    const r = await api.post("/api/capture", [{ ...f, market_code: market, views: num(f.views), likes: num(f.likes), comments: num(f.comments), shares: num(f.shares) }]);
    setRes(r);
  };
  const inp = (k: string, label: string, ph = "") => <label>{label}<input value={f[k]} placeholder={ph} onChange={e => setF({ ...f, [k]: e.target.value })} onBlur={k === "title" || k === "url" ? preview : undefined} /></label>;
  return (
    <div className="card">
      <h4>Capture one page</h4>
      <div className="form">
        {inp("url", "Page URL *", "https://www.tiktok.com/@user/video/…")}
        {inp("title", "Title / caption (copy from the page)")}
        <label>Market<select value={market} onChange={e => setMarket(e.target.value)}>{["VN", "US", "JP", "KR", "CN", "TH", "SG", "GB", "DE", "FR", "GLOBAL"].map(m => <option key={m}>{m}</option>)}</select></label>
        {inp("product_name", "Product name (leave empty = auto-detect)", "POP MART Labubu Big Into Energy")}
        {inp("model_variant", "Model / colorway / version")}
        {inp("sku", "SKU / model number")}
        {inp("author", "Account / author", "@handle")}
        {inp("views", "Views (as shown on page)")}
        {inp("likes", "Likes")}
        {inp("comments", "Comments")}
        {inp("shares", "Shares")}
        {inp("image_url", "Image URL")}
      </div>
      <label className="small">Extra text (description, selected text)<textarea rows={3} style={{ width: "100%" }} value={f.text} onChange={e => setF({ ...f, text: e.target.value })} onBlur={preview} /></label>
      {pv && <div className="small muted">Detected: {pv.platform} ({pv.source_type}) · claim {pv.claim_type} · {pv.mentions.length ? "product: " + pv.mentions.map((m: Row) => m.name).join(", ") : "no product recognised - type the product name"}</div>}
      <div className="btnrow"><button className="primary" disabled={!f.url} onClick={save}>Save as evidence</button>
        {res && res.results.map((r: Row, i: number) => <span key={i}><StatusChip v={r.status} /> {r.product_name || ""} <span className="muted small">{r.message}</span></span>)}</div>
    </div>
  );
}

function BulkPaste() {
  const [market, setMarket] = useMarket();
  const [txt, setTxt] = useState("");
  const [res, setRes] = useState<Row | null>(null);
  const parse = () => txt.split(/\r?\n/).map(l => l.trim()).filter(l => /^https?:\/\//.test(l)).map(l => {
    const c = l.split("\t");
    const n = (v?: string) => (v ? Number(v.replace(/[^\d]/g, "")) || null : null);
    return { url: c[0], title: c[1] || "", product_name: c[2] || null, market_code: c[3] || market, views: n(c[4]), likes: n(c[5]), comments: n(c[6]), author: c[7] || null };
  });
  const rows = parse();
  return (
    <div className="card">
      <h4>Bulk paste links</h4>
      <p className="small muted">One link per line. Optional tab-separated columns (paste straight from Google Sheets):
        <code> URL · Title/caption · Product name · Market · Views · Likes · Comments · Account</code>. Social links need a title or product name (they are not fetched automatically); article links without a title are read once from the page (robots.txt respected).</p>
      <textarea rows={8} style={{ width: "100%" }} value={txt} onChange={e => setTxt(e.target.value)} placeholder={"https://www.tiktok.com/@kicks/video/123\tLabubu restock haul\tPOP MART Labubu Big Into Energy\tVN\t120000\t8000\t300"} />
      <div className="btnrow">Default market <select value={market} onChange={e => setMarket(e.target.value)}>{["VN", "US", "JP", "KR", "CN", "TH", "SG", "GB", "GLOBAL"].map(m => <option key={m}>{m}</option>)}</select>
        <button className="primary" disabled={!rows.length} onClick={async () => setRes(await api.post("/api/capture", rows))}>Save {rows.length} link(s)</button>
        {res && <span className="okmsg">{res.saved} saved · {res.products} product(s) updated</span>}</div>
      {res && <table className="tbl"><tbody>{res.results.map((r: Row, i: number) => <tr key={i}><td><StatusChip v={r.status} /></td><td>{r.product_name}</td><td className="urltd">{r.url}</td><td className="small">{r.message}</td></tr>)}</tbody></table>}
    </div>
  );
}

function TrendsImport() {
  const [csv, setCsv] = useState("");
  const [name, setName] = useState("");
  const [pv, setPv] = useState<Row | null>(null);
  const [map, setMap] = useState<Record<string, Row>>({});
  const [res, setRes] = useState<Row | null>(null);
  const [err, setErr] = useState("");
  const { data: markets } = useData<Row[]>("/api/markets");
  const load = async (text: string, fname: string) => {
    setCsv(text); setName(fname); setRes(null); setErr("");
    try {
      const r = await api.post("/api/trends/preview", { csv: text });
      setPv(r);
      setMap(Object.fromEntries(r.series.map((s: Row) => [s.term, { product_id: s.suggestions?.[0]?.product_id ?? "", market_code: s.market_guess || "" }])));
    } catch (e: any) { setErr(e.message); setPv(null); }
  };
  return (
    <div className="card">
      <h4>Google Trends CSV import</h4>
      <p className="small muted">On trends.google.com search your term, pick the country, then use the ⬇ download button of “Interest over time”. Drop the CSV here and map each term to a product.
        Values are a relative 0-100 index for that export only, never absolute search volume. Only the latest import per product/market is used.</p>
      <input type="file" accept=".csv,text/csv" onChange={async e => { const fl = e.target.files?.[0]; if (fl) load(await fl.text(), fl.name); }} />
      {err && <div className="warn">{err}</div>}
      {pv && <>
        <div className="small">Granularity: {pv.granularity}</div>
        <table className="tbl"><thead><tr><th>Term</th><th>Geo</th><th>Points</th><th>Range</th><th>Latest</th><th>Product</th><th>Market</th></tr></thead>
          <tbody>{pv.series.map((s: Row) => <tr key={s.term}><td><b>{s.term}</b></td><td>{s.geo_label || "—"}</td><td>{s.points}</td><td className="small">{s.first} → {s.last}</td>
            <td className="small">{s.latest_values.join(", ")}</td>
            <td><ProductSelect value={map[s.term]?.product_id} suggestions={s.suggestions} onChange={v => setMap({ ...map, [s.term]: { ...map[s.term], product_id: v } })} /></td>
            <td><select value={map[s.term]?.market_code || ""} onChange={e => setMap({ ...map, [s.term]: { ...map[s.term], market_code: e.target.value } })}>
              <option value="">— choose —</option>{(markets || []).filter(m => !m.is_city).map(m => <option key={m.code} value={m.code}>{m.name}</option>)}</select></td></tr>)}</tbody></table>
        <div className="btnrow"><button className="primary" onClick={async () => {
          const mapping = Object.entries(map).filter(([, v]) => v.product_id && v.market_code).map(([term, v]) => ({ term, product_id: Number(v.product_id), market_code: v.market_code }));
          if (!mapping.length) return alert("Map at least one term to a product and market.");
          setRes(await api.post("/api/trends/import", { csv, mapping, file_name: name }));
        }}>Import</button>{res && <span className="okmsg">Imported {res.points} points for {res.product_ids.length} product(s); scores recomputed.</span>}</div>
      </>}
    </div>
  );
}

function ProductSelect({ value, suggestions, onChange }: { value: any; suggestions: Row[]; onChange: (v: any) => void }) {
  const [q, setQ] = useState("");
  const { data } = useData<Row[]>(q.length >= 2 ? "/api/products-lookup" : null, { q });
  const opts = [...(suggestions || []).map(s => ({ product_id: s.product_id, label: `${s.name} (match ${s.score})` })), ...(data || [])];
  return <span><input placeholder="search product…" value={q} onChange={e => setQ(e.target.value)} style={{ width: 120 }} />
    <select value={value || ""} onChange={e => onChange(e.target.value)}><option value="">— skip —</option>
      {opts.map((o, i) => <option key={o.product_id + ":" + i} value={o.product_id}>{o.label}</option>)}</select></span>;
}

export function CapturePage() {
  const bm = useRef<HTMLAnchorElement>(null);
  useEffect(() => { bm.current?.setAttribute("href", BOOKMARKLET); }, []);
  return (
    <div>
      <div className="pagehead"><h2>Add Evidence & Imports</h2></div>
      <div className="card">
        <h4>① Browser button (bookmarklet)</h4>
        <p className="small">Drag this button to your Chrome bookmarks bar (Ctrl+Shift+B shows the bar):&nbsp;
          <a ref={bm} className="bookmarklet" onClick={e => { e.preventDefault(); alert("Drag this button onto the bookmarks bar, don't click it here."); }}>➕ Send to Global Crawler</a></p>
        <p className="small muted">Then browse TikTok, Instagram, X, Shopee, news sites… normally — as a visitor or logged in with your own account, solving any CAPTCHA yourself as usual.
          On a post about a product, click the bookmark: this form opens pre-filled with the link, title and description (select text first to send it instead). Check the product name, likes/views, then Save.
          The app never logs in, never crawls those sites by itself and never stores passwords.</p>
      </div>
      <CaptureForm />
      <BulkPaste />
      <TrendsImport />
    </div>
  );
}
