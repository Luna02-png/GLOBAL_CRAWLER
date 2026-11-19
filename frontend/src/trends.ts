import { Row } from "./api";

// Brand prefixes people rarely type into Google; the user can always edit the term.
const DROP_PREFIX = /^(pop mart|apple|samsung|google|sony|xiaomi|nike|adidas|new balance|asics|lego)\s+/i;

export function suggestTerm(r: Row): string {
  if (r.trends_term) return r.trends_term;
  const name: string = r.product_name || r.name || "";
  const short = name.replace(DROP_PREFIX, "").trim();
  return (short.split(/\s+/).length >= 1 && short ? short : name).toLowerCase();
}

export function geoFor(market?: string | null): string {
  if (!market || market === "GLOBAL") return "";
  return market.split("-")[0].toUpperCase(); // city codes (US-NYC) fall back to the country
}

/** hl=en-US keeps CSV headers in English (e.g. "(Vietnam)") so the importer can map the market automatically. */
export function trendsUrl(terms: string[], market?: string | null, date = "today 3-m"): string {
  const p = new URLSearchParams({ date, q: terms.slice(0, 5).map(t => t.replace(/,/g, " ")).join(","), hl: "en-US" });
  const geo = geoFor(market);
  if (geo) p.set("geo", geo);
  return "https://trends.google.com/trends/explore?" + p.toString();
}

export function openTrends(terms: string[], market?: string | null) {
  window.open(trendsUrl(terms, market), "_blank", "noopener");
}
