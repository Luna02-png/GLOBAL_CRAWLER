export type Row = Record<string, any>;

async function req<T = any>(method: string, url: string, body?: any): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg += ": " + JSON.stringify((await r.json()).detail); } catch { /* ignore */ }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}

export const api = {
  get: <T = any>(url: string, params?: Record<string, any>) => {
    const qs = params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)])).toString() : "";
    return req<T>("GET", url + qs);
  },
  post: <T = any>(url: string, body: any = {}) => req<T>("POST", url, body),
  put: <T = any>(url: string, body: any = {}) => req<T>("PUT", url, body),
  del: <T = any>(url: string) => req<T>("DELETE", url),
  async exportFile(body: any) {
    const r = await fetch("/api/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error("export failed");
    const blob = await r.blob();
    const cd = r.headers.get("content-disposition") || "";
    const name = /filename="([^"]+)"/.exec(cd)?.[1] || `gpti_export.${body.format}`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  },
};
