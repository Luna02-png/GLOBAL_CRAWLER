import { useEffect, useState } from "react";
import ProductPanel from "./components/ProductPanel";
import { useData } from "./components/common";
import { LinkFinderPage, ResearchSheet } from "./pages/research";
import { Dashboard, EarlyRadar, Opportunity, SavedLists, Upcoming, WhatsNew } from "./pages/modules";
import { ScanManager, Settings, SourceManager, TaxonomyManager } from "./pages/manage";
import { CapturePage } from "./pages/capture";

const PAGES = [
  { id: "dashboard", label: "Trend Dashboard", group: "Research" },
  { id: "sheet", label: "Product Research Sheet", group: "Research" },
  { id: "upcoming", label: "Upcoming Releases & Rumors", group: "Research" },
  { id: "opportunity", label: "Trend Opportunity Finder", group: "Research" },
  { id: "early", label: "Early Trend Radar", group: "Research" },
  { id: "capture", label: "Add Evidence & Imports", group: "Tools" },
  { id: "new", label: "What's New", group: "Tools" },
  { id: "links", label: "Product Link Finder", group: "Tools" },
  { id: "lists", label: "Saved Lists", group: "Tools" },
  { id: "scans", label: "Smart Scan Manager", group: "Manage" },
  { id: "taxonomy", label: "Industries & Categories", group: "Manage" },
  { id: "sources", label: "Source Manager", group: "Manage" },
  { id: "settings", label: "Settings", group: "Manage" },
];

export default function App() {
  const [page, setPage] = useState(() => location.hash.slice(1).split("?")[0] || "dashboard");
  const [demo, setDemo] = useState(() => localStorage.getItem("demo") !== "0");
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [product, setProduct] = useState<number | null>(null);
  const { data: health } = useData<any>("/api/health", undefined, [page]);
  useEffect(() => { if (location.hash.slice(1).split("?")[0] !== page) location.hash = page; }, [page]);
  useEffect(() => {
    const h = () => setPage(location.hash.slice(1).split("?")[0] || "dashboard");
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  useEffect(() => { localStorage.setItem("demo", demo ? "1" : "0"); }, [demo]);
  useEffect(() => { localStorage.setItem("theme", theme); document.documentElement.dataset.theme = theme; }, [theme]);
  const open = (id: number) => setProduct(id);
  const props = { demo, open };
  return (
    <div className="app">
      <nav className="side">
        <div className="brand">GPTI<span>Global Product Trend Intelligence</span></div>
        {["Research", "Tools", "Manage"].map(g => <div key={g}><div className="navg">{g}</div>
          {PAGES.filter(p => p.group === g).map(p => <a key={p.id} className={page === p.id ? "active" : ""} onClick={() => setPage(p.id)}>{p.label}</a>)}</div>)}
        <div className="sidefoot">
          <label className="chk" title="Demo/test fixture rows are synthetic and are never live findings">
            <input type="checkbox" checked={demo} onChange={e => setDemo(e.target.checked)} /> show DEMO data</label>
          {health && <div className="small">{health.live_products} live · {health.products - health.live_products} demo products</div>}
        </div>
      </nav>
      <main>
        {page === "dashboard" && <Dashboard {...props} />}
        {page === "sheet" && <ResearchSheet {...props} />}
        {page === "upcoming" && <Upcoming {...props} />}
        {page === "opportunity" && <Opportunity {...props} />}
        {page === "early" && <EarlyRadar {...props} />}
        {page === "capture" && <CapturePage />}
        {page === "new" && <WhatsNew {...props} />}
        {page === "links" && <LinkFinderPage {...props} />}
        {page === "lists" && <SavedLists open={open} />}
        {page === "scans" && <ScanManager />}
        {page === "taxonomy" && <TaxonomyManager />}
        {page === "sources" && <SourceManager />}
        {page === "settings" && <Settings theme={theme} setTheme={setTheme} />}
      </main>
      {product !== null && <ProductPanel productId={product} onClose={() => setProduct(null)} />}
    </div>
  );
}
