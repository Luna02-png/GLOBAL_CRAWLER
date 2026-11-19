import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Row } from "../api";

export function useData<T = any>(url: string | null, params?: Record<string, any>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const key = JSON.stringify(params || {});
  const load = useCallback(async () => {
    if (!url) return;
    setLoading(true);
    try { setData(await api.get<T>(url, params)); setErr(""); } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }, [url, key, ...deps]);
  useEffect(() => { load(); }, [load]);
  return { data, err, loading, reload: load, setData };
}

export function ListInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [txt, setTxt] = useState(value.join(", "));
  useEffect(() => setTxt(value.join(", ")), [value.join("|")]);
  return <input value={txt} placeholder={placeholder || "comma separated"} onChange={e => setTxt(e.target.value)}
    onBlur={() => onChange(txt.split(",").map(s => s.trim()).filter(Boolean))} />;
}

export function MarketPicker({ value, onChange, single }: { value: string[]; onChange: (v: string[]) => void; single?: boolean }) {
  const { data } = useData<Row[]>("/api/markets");
  const groups = useMemo(() => {
    const g: Record<string, Row[]> = {};
    (data || []).filter(m => m.active).forEach(m => (g[m.region] = g[m.region] || []).push(m));
    return g;
  }, [data]);
  const toggle = (code: string) => {
    if (single) return onChange([code]);
    onChange(value.includes(code) ? value.filter(v => v !== code) : [...value, code]);
  };
  return (
    <div className="picker">
      {Object.entries(groups).map(([region, ms]) => (
        <div key={region} className="pgroup">
          <div className="pghead"><b>{region}</b>{!single && <>
            <a onClick={() => onChange([...new Set([...value, ...ms.map(m => m.code)])])}>all</a>
            <a onClick={() => onChange(value.filter(v => !ms.some(m => m.code === v)))}>clear</a></>}
          </div>
          {ms.map(m => <label key={m.code} className="pitem" title={m.is_city ? "City: only scanned where a trustworthy localized source exists" : m.languages?.join(", ")}>
            <input type={single ? "radio" : "checkbox"} checked={value.includes(m.code)} onChange={() => toggle(m.code)} /> {m.name}{m.is_city ? " (city)" : ""}
          </label>)}
        </div>
      ))}
    </div>
  );
}

export function Dropdown({ label, children, width = 360 }: { label: string; children: React.ReactNode; width?: number }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <span className="dd" ref={ref}>
      <button onClick={() => setOpen(!open)} title={label}>{label} ▾</button>
      {open && <div className="ddmenu" style={{ width }}>{children}</div>}
    </span>
  );
}

function catNames(tree: Row[] | null, ids: number[]): string[] {
  const names: string[] = [];
  const walk = (n: Row) => { if (ids.includes(n.id)) names.push(n.name); (n.children || []).forEach(walk); };
  (tree || []).forEach(i => i.categories.forEach(walk));
  return names;
}

export function CategoryDropdown({ value, onChange, prefix = "Danh mục" }: { value: number[]; onChange: (v: number[]) => void; prefix?: string }) {
  const { data } = useTaxonomy();
  const names = catNames(data, value);
  const label = !value.length ? `${prefix}: tất cả` : `${prefix}: ${names.slice(0, 2).join(", ")}${names.length > 2 ? ` +${names.length - 2}` : ""}`;
  return <Dropdown label={label} width={380}><CategoryPicker value={value} onChange={onChange} /></Dropdown>;
}

export function MarketDropdown({ value, onChange, prefix = "Thị trường" }: { value: string[]; onChange: (v: string[]) => void; prefix?: string }) {
  const label = !value.length ? `${prefix}: tất cả` : `${prefix}: ${value.slice(0, 3).join(", ")}${value.length > 3 ? ` +${value.length - 3}` : ""}`;
  return <Dropdown label={label} width={520}><MarketPicker value={value} onChange={onChange} /></Dropdown>;
}

export function useTaxonomy() {
  return useData<Row[]>("/api/taxonomy");
}

export function CategoryPicker({ value, onChange, industries, onIndustries }: { value: number[]; onChange: (v: number[]) => void;
  industries?: number[]; onIndustries?: (v: number[]) => void }) {
  const { data } = useTaxonomy();
  const [q, setQ] = useState("");
  const all = (n: Row): number[] => [n.id, ...(n.children || []).flatMap(all)];
  const match = (n: Row): boolean => !q || n.name.toLowerCase().includes(q.toLowerCase()) || (n.children || []).some(match);
  const toggle = (ids: number[], on: boolean) => onChange(on ? [...new Set([...value, ...ids])] : value.filter(v => !ids.includes(v)));
  const Node = ({ n, depth }: { n: Row; depth: number }) => !match(n) || !n.active ? null : (
    <div style={{ marginLeft: depth * 14 }}>
      <label className="pitem"><input type="checkbox" checked={value.includes(n.id)} onChange={e => toggle(all(n), e.target.checked)} /> {n.name}
        {n.product_count ? <span className="muted"> ({n.product_count})</span> : null}{n.group_label ? <span className="tag">{n.group_label}</span> : null}</label>
      {(n.children || []).map((c: Row) => <Node key={c.id} n={c} depth={depth + 1} />)}
    </div>);
  return (
    <div className="picker">
      <input className="search" placeholder="Search categories…" value={q} onChange={e => setQ(e.target.value)} />
      <div className="pghead"><a onClick={() => onChange((data || []).flatMap(i => i.categories.flatMap(all)))}>select all</a><a onClick={() => { onChange([]); onIndustries?.([]); }}>clear</a></div>
      {(data || []).filter(i => i.active).map(ind => {
        const ids = ind.categories.flatMap(all);
        return (
          <div key={ind.id} className="pgroup">
            <div className="pghead">
              <label><input type="checkbox" checked={ids.length > 0 && ids.every((i: number) => value.includes(i))} onChange={e => toggle(ids, e.target.checked)} /> <b>{ind.name}</b></label>
            </div>
            {ind.categories.map((c: Row) => <Node key={c.id} n={c} depth={1} />)}
          </div>);
      })}
    </div>
  );
}

export function Bars({ data, title, onPick }: { data: [string, number][]; title: string; onPick?: (key: string) => void }) {
  const max = Math.max(1, ...data.map(d => d[1]));
  return (
    <div className="card">
      <h4>{title}{onPick && data.length > 0 && <span className="muted small" style={{ fontWeight: 400 }}> · bấm vào dòng để xem sản phẩm</span>}</h4>
      {data.length === 0 && <div className="muted">No observations yet.</div>}
      {data.map(([k, v]) => (
        <div key={k} className={"bar" + (onPick ? " click" : "")} onClick={onPick ? () => onPick(k) : undefined}
          title={onPick ? `Xem ${v} sản phẩm: ${k}` : k}><span className="blabel">{k}</span><span className="btrack"><span className="bfill" style={{ width: `${(v / max) * 100}%` }} /></span><span className="bval">{v}</span></div>
      ))}
    </div>
  );
}

/** Explicit scan launcher. Its scope (categories + markets) is separate from table filters; it only scans when the button is pressed. */
export function RefreshBar({ scope, onStarted }: { scope?: { markets?: string[]; category_ids?: number[] }; onStarted?: (jobId: number) => void }) {
  const { data: presets } = useData<Row[]>("/api/presets");
  const saved = (() => { try { return JSON.parse(localStorage.getItem("scanScope") || "{}"); } catch { return {}; } })();
  const [pid, setPid] = useState<string>("");
  const [cats, setCats] = useState<number[]>(scope?.category_ids?.length ? scope.category_ids : saved.cats || []);
  const [mks, setMks] = useState<string[]>(scope?.markets?.length ? scope.markets : saved.mks || []);
  const [msg, setMsg] = useState("");
  const [lastJob, setLastJob] = useState<number | null>(null);
  useEffect(() => { if (scope?.category_ids?.length) setCats(scope.category_ids); }, [JSON.stringify(scope?.category_ids)]);
  useEffect(() => { if (scope?.markets?.length) setMks(scope.markets); }, [JSON.stringify(scope?.markets)]);
  useEffect(() => { localStorage.setItem("scanScope", JSON.stringify({ cats, mks })); }, [cats, mks]);
  const run = async (depth: "QUICK" | "FULL") => {
    if (!pid && !cats.length) return alert("Chọn ít nhất 1 danh mục (hoặc 1 preset) để quét tập trung.");
    if (!pid && !mks.length) return alert("Chọn ít nhất 1 thị trường để quét.");
    const body = pid ? { preset_id: Number(pid), depth } : { category_ids: cats, markets: mks, depth };
    const r = await api.post("/api/scans", body);
    setMsg(`Lần quét #${r.job_id} đã bắt đầu.`);
    setLastJob(r.job_id);
    onStarted?.(r.job_id);
    setTimeout(() => setMsg(""), 6000);
  };
  return (
    <span className="refresh">
      <b className="small">Phạm vi quét:</b>
      <select value={pid} onChange={e => setPid(e.target.value)} title="Quét theo preset đã lưu, hoặc theo danh mục + thị trường chọn bên cạnh">
        <option value="">tự chọn danh mục ▸</option>
        {(presets || []).map(p => <option key={p.id} value={p.id}>preset: {p.name} ({p.priority})</option>)}
      </select>
      {!pid && <><CategoryDropdown value={cats} onChange={setCats} prefix="Quét danh mục" /><MarketDropdown value={mks} onChange={setMks} prefix="Quét thị trường" /></>}
      <button className="primary" onClick={() => run("QUICK")}>Quét ngay · Quick</button>
      <button onClick={() => run("FULL")}>Full</button>
      {msg && <span className="okmsg">{msg}</span>}
      {lastJob && <a href={`#sheet?job=${lastJob}`} className="small">Xem kết quả lần quét #{lastJob} →</a>}
    </span>
  );
}

export const fmtDate = (s?: string | null) => {
  if (!s) return "—";
  const d = new Date(s.replace(" ", "T") + (/[zZ]|[+-]\d\d:\d\d$/.test(s) ? "" : "Z"));
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString("sv-SE", { timeZone: "Asia/Ho_Chi_Minh" }).slice(0, 16);
};

export function DemoToggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return <label className="chk" title="Demo/test fixture rows are synthetic and never live market findings"><input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} /> show DEMO rows</label>;
}
