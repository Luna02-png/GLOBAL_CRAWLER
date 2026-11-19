from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from . import config, db as dbmod, scheduler
from .db import get_session, utcnow
from .export import columns_for, to_csv, to_tsv, to_xlsx
from .jobs import Worker, enqueue, preset_scope, recover_stale
from .migrate import upgrade
from .models import (
    Brand, Category, ChangeEvent, ProductAlias, Evidence, Industry, Market, OpportunityScore, Product, ProductAttributeDefinition,
    ProductCategory, ProductLink, ProductMarket, ProductMarketTrend, ReleaseHistory, ScanJob, ScanPreset, ScanTask,
    Setting, Shortlist, Source, TrendHistory, UpcomingRelease,
)
from .pipeline.links import add_manual_candidate, find_links, set_primary
from .scoring.engine import compute_opportunities, recompute_all
from .seed import seed
from .views import RESEARCH_COLUMNS, research_rows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_worker: Optional[Worker] = None


def init_db() -> None:
    upgrade()
    with dbmod.session_scope() as s:
        seed(s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker
    init_db()
    recover_stale()
    if config.ENABLE_WORKER:
        _worker = Worker()
        _worker.start()
    if config.ENABLE_SCHEDULER:
        scheduler.start()
    yield
    scheduler.stop()
    if _worker:
        _worker.stop()


app = FastAPI(title="Global Product Trend Intelligence", version="0.1.0", lifespan=lifespan)
DB = Depends(get_session)


def row(obj) -> dict:
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def _upd(obj, data: dict, allowed: set[str]):
    for k, v in data.items():
        if k in allowed:
            setattr(obj, k, v)


# ======================================================================== health / meta
@app.get("/api/health")
def health(db: Session = DB):
    return {"ok": True, "time_utc": utcnow().isoformat(), "timezone": config.TIMEZONE,
            "products": db.scalar(select(func.count(Product.id))),
            "live_products": db.scalar(select(func.count(Product.id)).where(Product.is_fixture.is_(False))),
            "scheduler": config.ENABLE_SCHEDULER, "worker": config.ENABLE_WORKER}


# ======================================================================== taxonomy
@app.get("/api/taxonomy")
def taxonomy(db: Session = DB, include_inactive: bool = True):
    inds = list(db.scalars(select(Industry).order_by(Industry.sort_order, Industry.name)))
    cats = list(db.scalars(select(Category).order_by(Category.name)))
    counts = dict(db.execute(select(ProductCategory.category_id, func.count()).group_by(ProductCategory.category_id)).all())
    attrs = list(db.scalars(select(ProductAttributeDefinition)))
    def node(c):
        return {**row(c), "product_count": counts.get(c.id, 0), "children": [node(x) for x in cats if x.parent_id == c.id]}
    return [{**row(i), "attributes": [row(a) for a in attrs if a.industry_id == i.id],
             "categories": [node(c) for c in cats if c.industry_id == i.id and c.parent_id is None]}
            for i in inds if include_inactive or i.active]


class IndustryIn(BaseModel):
    name: str
    aliases: list[str] = []
    active: bool = True


@app.post("/api/industries")
def create_industry(body: IndustryIn, db: Session = DB):
    if db.scalar(select(Industry).where(Industry.name == body.name)):
        raise HTTPException(409, "industry exists")
    i = Industry(**body.model_dump())
    db.add(i)
    db.flush()
    return row(i)


@app.put("/api/industries/{iid}")
def update_industry(iid: int, data: dict = Body(...), db: Session = DB):
    i = db.get(Industry, iid) or _404()
    _upd(i, data, {"name", "aliases", "active", "sort_order"})
    return row(i)


@app.delete("/api/industries/{iid}")
def delete_industry(iid: int, db: Session = DB):
    """Safe delete: an industry that still has products is deactivated instead of removed."""
    i = db.get(Industry, iid) or _404()
    cat_ids = [c.id for c in db.scalars(select(Category).where(Category.industry_id == iid))]
    used = db.scalar(select(func.count()).select_from(ProductCategory).where(ProductCategory.category_id.in_(cat_ids))) if cat_ids else 0
    if used:
        i.active = False
        for c in db.scalars(select(Category).where(Category.industry_id == iid)):
            c.active = False
        return {"deactivated": True, "reason": f"{used} product associations preserved"}
    for c in db.scalars(select(Category).where(Category.industry_id == iid).order_by(Category.parent_id.desc())):
        db.delete(c)
    db.flush()
    db.delete(i)
    return {"deleted": True}


class CategoryIn(BaseModel):
    industry_id: int
    parent_id: Optional[int] = None
    name: str
    keywords: list[str] = []
    exclude_keywords: list[str] = []
    local_keywords: dict[str, list[str]] = {}
    brands: list[str] = []
    preferred_sources: list[str] = []
    group_label: Optional[str] = None
    active: bool = True


@app.post("/api/categories")
def create_category(body: CategoryIn, db: Session = DB):
    c = Category(**body.model_dump())
    db.add(c)
    db.flush()
    return row(c)


@app.put("/api/categories/{cid}")
def update_category(cid: int, data: dict = Body(...), db: Session = DB):
    c = db.get(Category, cid) or _404()
    _upd(c, data, {"name", "keywords", "exclude_keywords", "local_keywords", "brands", "preferred_sources", "group_label",
                   "active", "parent_id", "industry_id"})
    return row(c)


@app.delete("/api/categories/{cid}")
def delete_category(cid: int, db: Session = DB):
    c = db.get(Category, cid) or _404()
    child_ids = [x.id for x in db.scalars(select(Category).where(Category.parent_id == cid))]
    used = db.scalar(select(func.count()).select_from(ProductCategory).where(ProductCategory.category_id.in_([cid] + child_ids)))
    if used or child_ids:
        c.active = False
        return {"deactivated": True, "reason": "has products or subcategories; data preserved"}
    db.delete(c)
    return {"deleted": True}


@app.post("/api/categories/{cid}/merge-into/{target}")
def merge_category(cid: int, target: int, db: Session = DB):
    """Move product associations and subcategories to target, then deactivate the source node."""
    src = db.get(Category, cid) or _404()
    tgt = db.get(Category, target) or _404()
    moved = 0
    for pc in list(db.scalars(select(ProductCategory).where(ProductCategory.category_id == cid))):
        if not db.get(ProductCategory, (pc.product_id, tgt.id)):
            db.add(ProductCategory(product_id=pc.product_id, category_id=tgt.id))
            moved += 1
        db.delete(pc)
    for ch in db.scalars(select(Category).where(Category.parent_id == cid)):
        ch.parent_id = tgt.id
    tgt.keywords = list(dict.fromkeys((tgt.keywords or []) + (src.keywords or [])))
    tgt.brands = list(dict.fromkeys((tgt.brands or []) + (src.brands or [])))
    src.active = False
    return {"moved_associations": moved}


@app.get("/api/brands")
def list_brands(db: Session = DB):
    return [row(b) for b in db.scalars(select(Brand).order_by(Brand.name))]


@app.post("/api/brands")
def create_brand(data: dict = Body(...), db: Session = DB):
    b = Brand(name=data["name"], aliases=data.get("aliases", []), official_domains=data.get("official_domains", []),
              industry_ids=data.get("industry_ids", []))
    db.add(b)
    db.flush()
    return row(b)


@app.put("/api/brands/{bid}")
def update_brand(bid: int, data: dict = Body(...), db: Session = DB):
    b = db.get(Brand, bid) or _404()
    _upd(b, data, {"name", "aliases", "official_domains", "industry_ids"})
    return row(b)


@app.delete("/api/brands/{bid}")
def delete_brand(bid: int, db: Session = DB):
    db.delete(db.get(Brand, bid) or _404())
    return {"deleted": True}


@app.post("/api/attributes")
def create_attribute(data: dict = Body(...), db: Session = DB):
    a = ProductAttributeDefinition(industry_id=data["industry_id"], key=data["key"], label=data.get("label", data["key"]),
                                   identity_relevant=bool(data.get("identity_relevant")))
    db.add(a)
    db.flush()
    return row(a)


# ======================================================================== markets
@app.get("/api/markets")
def list_markets(db: Session = DB):
    return [row(m) for m in db.scalars(select(Market).order_by(Market.region, Market.name))]


@app.post("/api/markets")
def create_market(data: dict = Body(...), db: Session = DB):
    if db.scalar(select(Market).where(Market.code == data["code"])):
        raise HTTPException(409, "market code exists")
    m = Market(code=data["code"].upper(), name=data["name"], region=data.get("region", "Other"), languages=data.get("languages", ["en"]),
               is_city=bool(data.get("is_city")), parent_code=data.get("parent_code"), google_news_ceid=data.get("google_news_ceid"))
    db.add(m)
    db.flush()
    return row(m)


@app.put("/api/markets/{mid}")
def update_market(mid: int, data: dict = Body(...), db: Session = DB):
    m = db.get(Market, mid) or _404()
    _upd(m, data, {"name", "region", "languages", "is_city", "parent_code", "google_news_ceid", "active"})
    return row(m)


# ======================================================================== sources
@app.get("/api/sources")
def list_sources(db: Session = DB):
    out = []
    for s in db.scalars(select(Source).order_by(Source.source_type, Source.name)):
        d = row(s)
        d["evidence_count"] = db.scalar(select(func.count(Evidence.id)).where(Evidence.source_key == s.key))
        out.append(d)
    return out


@app.put("/api/sources/{sid}")
def update_source(sid: int, data: dict = Body(...), db: Session = DB):
    s = db.get(Source, sid) or _404()
    _upd(s, data, {"name", "url", "enabled", "industry_ids", "markets", "credibility", "rate_per_minute", "concurrency", "notes"})
    return row(s)


@app.post("/api/sources")
def create_source(data: dict = Body(...), db: Session = DB):
    """Add a custom permitted RSS feed."""
    s = Source(key=data["key"], name=data.get("name", data["key"]), adapter=data.get("adapter", "rss"), url=data.get("url"),
               source_type=data.get("source_type", "EDITORIAL"), platform=data.get("platform", data.get("name")),
               industry_ids=data.get("industry_ids", []), markets=data.get("markets", ["GLOBAL"]), status="UNTESTED",
               notes=data.get("notes", "User-added source"))
    db.add(s)
    db.flush()
    return row(s)


@app.post("/api/sources/{sid}/test")
def test_source(sid: int, db: Session = DB):
    from .adapters.base import FetchCtx, SourceError
    from .adapters.rss import get_adapter
    s = db.get(Source, sid) or _404()
    if s.adapter in ("manual", "trends_import"):
        return {"status": s.status, "error": "Filled by you on the 'Add Evidence & Imports' page - nothing to fetch."}
    a = get_adapter(s.adapter)
    m = db.scalar(select(Market).where(Market.code == "US"))
    try:
        a.check_configured(s)
        out = a.fetch(s, FetchCtx(market_code=(s.markets or ["US"])[0] if not a.per_query else "US", languages=["en"],
                                  query="sneakers when:7d", google_news_locale=m.google_news_ceid if m else None,
                                  max_results=5, use_cache=False))
        s.status, s.last_error, s.last_checked, s.last_success = "WORKING", None, utcnow(), utcnow()
        return {"status": "WORKING", "sample": [{"title": i.title, "url": i.url} for i in out.items[:5]]}
    except SourceError as e:
        s.status, s.last_error, s.last_checked = e.status, e.message, utcnow()
        return {"status": e.status, "error": e.message}


# ======================================================================== presets & scans
class PresetIn(BaseModel):
    name: str
    markets: list[str] = []
    category_ids: list[int] = []
    industry_ids: list[int] = []
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []
    local_aliases: dict[str, list[str]] = {}
    source_keys: list[str] = []
    source_priorities: dict[str, int] = {}
    priority: str = "P3"
    mode: str = "DISCOVERY"
    depth: str = "QUICK"
    enabled: bool = True
    schedule_time: str = "07:00"
    schedule_weekday: int = 0
    limits: dict[str, Any] = {}
    export_columns: list[str] = []


@app.get("/api/presets")
def list_presets(db: Session = DB):
    out = []
    for p in db.scalars(select(ScanPreset).where(ScanPreset.deleted.is_(False)).order_by(ScanPreset.priority, ScanPreset.name)):
        d = row(p)
        last = db.scalar(select(ScanJob).where(ScanJob.preset_id == p.id).order_by(ScanJob.created_at.desc()).limit(1))
        d["last_job"] = row(last) if last else None
        out.append(d)
    return out


@app.post("/api/presets")
def create_preset(body: PresetIn, db: Session = DB):
    p = ScanPreset(**body.model_dump(), schedule_anchor_at=utcnow())
    db.add(p)
    db.flush()
    return row(p)


@app.put("/api/presets/{pid}")
def update_preset(pid: int, data: dict = Body(...), db: Session = DB):
    p = db.get(ScanPreset, pid) or _404()
    sched_change = any(k in data and data[k] != getattr(p, k) for k in ("priority", "schedule_time", "schedule_weekday", "enabled"))
    _upd(p, data, set(PresetIn.model_fields))
    if sched_change:
        p.schedule_anchor_at = utcnow()
    return row(p)


@app.post("/api/presets/{pid}/duplicate")
def duplicate_preset(pid: int, db: Session = DB):
    p = db.get(ScanPreset, pid) or _404()
    d = {k: getattr(p, k) for k in PresetIn.model_fields}
    d["name"] = p.name + " (copy)"
    d["enabled"] = False
    n = ScanPreset(**d, schedule_anchor_at=utcnow())
    db.add(n)
    db.flush()
    return row(n)


@app.delete("/api/presets/{pid}")
def delete_preset(pid: int, db: Session = DB):
    """Soft delete: products, evidence, scan history and saved lists are untouched."""
    p = db.get(ScanPreset, pid) or _404()
    p.deleted, p.enabled = True, False
    return {"deleted": True}


class ScanIn(BaseModel):
    preset_id: Optional[int] = None
    markets: list[str] = []
    category_ids: list[int] = []
    industry_ids: list[int] = []
    product_ids: list[int] = []
    source_keys: list[str] = []
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []
    mode: Optional[str] = None
    depth: str = "QUICK"
    include_fixture: bool = False


@app.post("/api/scans")
def start_scan(body: ScanIn, db: Session = DB):
    """Manual Quick/Full refresh. A one-off scan never modifies the saved preset."""
    preset = None
    if body.preset_id:
        preset = db.get(ScanPreset, body.preset_id) or _404()
        scope = preset_scope(preset)
        mode = body.mode or preset.mode
    else:
        scope = body.model_dump(exclude={"preset_id", "mode", "depth"})
        mode = body.mode or ("TRACKING" if body.product_ids else "DISCOVERY")
    if body.product_ids:
        scope["product_ids"] = body.product_ids
        if not scope.get("markets"):
            scope["markets"] = sorted({r[0] for r in db.execute(select(ProductMarket.market_code)
                                                                .where(ProductMarket.product_id.in_(body.product_ids)))} - {"GLOBAL"}) or ["US"]
    if body.include_fixture:
        scope["include_fixture"] = True
        scope["source_keys"] = list(set(scope.get("source_keys") or []) | {"demo_fixture"})
    db.commit()
    jid, _ = enqueue("SCAN", scope, trigger="MANUAL", preset=preset, mode=mode, depth=body.depth)
    return {"job_id": jid}


@app.get("/api/jobs")
def list_jobs(db: Session = DB, limit: int = 50, kind: Optional[str] = None):
    q = select(ScanJob).order_by(ScanJob.created_at.desc()).limit(limit)
    if kind:
        q = q.where(ScanJob.kind == kind)
    return [row(j) for j in db.scalars(q)]


@app.get("/api/jobs/{jid}")
def job_detail(jid: int, db: Session = DB):
    j = db.get(ScanJob, jid) or _404()
    tasks = [row(t) for t in db.scalars(select(ScanTask).where(ScanTask.job_id == jid).order_by(ScanTask.id))]
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    d = row(j)
    d.pop("checkpoint", None)
    return {**d, "task_counts": counts, "tasks": tasks}


@app.post("/api/jobs/{jid}/{action}")
def job_action(jid: int, action: str, db: Session = DB):
    j = db.get(ScanJob, jid) or _404()
    if action == "pause" and j.status in ("RUNNING", "QUEUED"):
        j.status = "PAUSE_REQUESTED" if j.status == "RUNNING" else "PAUSED"
    elif action == "resume" and j.status in ("PAUSED", "PAUSE_REQUESTED"):
        j.status = "QUEUED"
    elif action == "cancel" and j.status in ("RUNNING", "QUEUED", "PAUSED", "PAUSE_REQUESTED"):
        j.status = "CANCEL_REQUESTED" if j.status == "RUNNING" else "CANCELLED"
    elif action == "retry" and j.status in ("FAILED", "PARTIAL", "CANCELLED"):
        db.execute(update(ScanTask).where(ScanTask.job_id == jid, ScanTask.status.in_(["FAILED", "CANCELLED", "SKIPPED"]))
                   .values(status="QUEUED", error=None))
        j.status, j.finished_at = "QUEUED", None
    else:
        raise HTTPException(400, f"cannot {action} job in state {j.status}")
    return row(j)


# ======================================================================== products / research sheet
def _csv(v: Optional[str]) -> Optional[list]:
    return [x for x in v.split(",") if x] if v else None


def _job_scope(db: Session, job_id: Optional[int]) -> tuple[Optional[list[int]], Optional[list[str]]]:
    """Products touched by one scan job (+ the markets it scanned) - used for 'show results of this scan'."""
    if not job_id:
        return None, None
    j = db.get(ScanJob, job_id)
    if j is None:
        return [], None
    cp, sc = j.checkpoint or {}, j.scope or {}
    ids = sorted(set(cp.get("touched", [])) | set(cp.get("done", [])) | set(sc.get("product_ids") or []))
    mk = list(sc.get("markets") or [])
    return ids, (mk + ["GLOBAL"] if mk else None)


def _cat_ids(v: Optional[str]) -> Optional[list[int]]:
    return [int(x) for x in _csv(v) or []] or None


@app.get("/api/research")
def research(db: Session = DB, markets: Optional[str] = None, industries: Optional[str] = None, categories: Optional[str] = None,
             status: Optional[str] = None, q: Optional[str] = None, include_fixture: bool = True, expand: bool = False,
             window_days: Optional[int] = None, job_id: Optional[int] = None):
    since = utcnow() - timedelta(days=window_days) if window_days else None
    jp, jm = _job_scope(db, job_id)
    if jp is not None and not jp:
        return {"columns": [{"key": k, "label": l} for k, l in RESEARCH_COLUMNS], "rows": []}
    rows = research_rows(db, markets=_csv(markets) or jm, product_ids=jp, industry_ids=[int(x) for x in _csv(industries) or []] or None,
                         category_ids=[int(x) for x in _csv(categories) or []] or None, status=_csv(status), search=q,
                         include_fixture=include_fixture, expand_categories=expand, since=since)
    return {"columns": [{"key": k, "label": l} for k, l in RESEARCH_COLUMNS], "rows": rows}


@app.get("/api/products/{pid}")
def product_detail(pid: int, db: Session = DB):
    p = db.get(Product, pid) or _404()
    cats = {c.id: c for c in db.scalars(select(Category))}
    return {
        "product": row(p),
        "categories": [cats[pc.category_id].name for pc in db.scalars(select(ProductCategory).where(ProductCategory.product_id == pid)) if pc.category_id in cats],
        "markets": [row(m) for m in db.scalars(select(ProductMarket).where(ProductMarket.product_id == pid))],
        "evidence": [row(e) for e in db.scalars(select(Evidence).where(Evidence.product_id == pid).order_by(Evidence.published_at.desc()))],
        "links": [row(l) for l in db.scalars(select(ProductLink).where(ProductLink.product_id == pid).order_by(ProductLink.completeness_score.desc()))],
        "trends": [row(t) for t in db.scalars(select(ProductMarketTrend).where(ProductMarketTrend.product_id == pid))],
        "history": [row(h) for h in db.scalars(select(TrendHistory).where(TrendHistory.product_id == pid).order_by(TrendHistory.recorded_at))],
        "releases": [{**row(r), "history": [row(h) for h in db.scalars(select(ReleaseHistory).where(ReleaseHistory.release_id == r.id).order_by(ReleaseHistory.changed_at))]}
                     for r in db.scalars(select(UpcomingRelease).where(UpcomingRelease.product_id == pid))],
        "aliases": [a.alias for a in db.scalars(select(ProductAlias).where(ProductAlias.product_id == pid))],
    }


@app.put("/api/products/{pid}")
def update_product(pid: int, data: dict = Body(...), db: Session = DB):
    p = db.get(Product, pid) or _404()
    _upd(p, data, {"name", "brand", "model_variant", "sku", "image_url", "needs_review", "attributes"})
    return row(p)


@app.put("/api/products/{pid}/trends-term")
def set_trends_term(pid: int, data: dict = Body(...), db: Session = DB):
    """Remember the Google Trends search term used for this product (used to auto-map CSV imports)."""
    p = db.get(Product, pid) or _404()
    term = (data.get("term") or "").strip()
    p.attributes = {**(p.attributes or {}), "trends_term": term} if term else {k: v for k, v in (p.attributes or {}).items() if k != "trends_term"}
    return {"product_id": pid, "trends_term": term}


@app.post("/api/products/{pid}/categories")
def add_product_category(pid: int, data: dict = Body(...), db: Session = DB):
    if not db.get(ProductCategory, (pid, data["category_id"])):
        db.add(ProductCategory(product_id=pid, category_id=data["category_id"]))
    return {"ok": True}


# ---------------------------------------------------------------- link finder
@app.post("/api/products/{pid}/find-links")
def find_product_links(pid: int, purchase: bool = False, db: Session = DB):
    """Searches ONLY for this product (never triggers a category-wide scan)."""
    db.get(Product, pid) or _404()
    r = find_links(db, pid, purchase_mode=purchase)
    return r.__dict__


@app.post("/api/products/{pid}/links")
def add_link(pid: int, data: dict = Body(...), db: Session = DB):
    db.get(Product, pid) or _404()
    l = add_manual_candidate(db, pid, data["url"])
    r = find_links(db, pid, use_search=False)
    return {"link_id": l.id, "result": r.__dict__}


@app.put("/api/products/{pid}/primary-link/{lid}")
def choose_primary(pid: int, lid: int, db: Session = DB):
    try:
        return row(set_primary(db, pid, lid))
    except ValueError as e:
        raise HTTPException(400, str(e))


class BulkLinksIn(BaseModel):
    mode: str = "selected"  # selected | missing | purchase
    product_ids: list[int] = []


@app.post("/api/links/bulk")
def bulk_links(body: BulkLinksIn, db: Session = DB):
    if body.mode == "missing":
        verified = select(ProductLink.product_id).where(ProductLink.is_primary_information_url.is_(True))
        ids = [r[0] for r in db.execute(select(Product.id).where(Product.id.not_in(verified)))]
        if body.product_ids:
            ids = [i for i in ids if i in set(body.product_ids)]
    else:
        ids = body.product_ids
    if not ids:
        return {"job_id": None, "count": 0}
    db.commit()
    jid, _ = enqueue("LINK_FINDER", {"product_ids": ids, "purchase_mode": body.mode == "purchase"}, trigger="MANUAL")
    return {"job_id": jid, "count": len(ids)}


# ======================================================================== dashboard
def _window(days: Optional[int]):
    return utcnow() - timedelta(days=days or 30)


DRILL_KEYS = {"status": "trend_status", "brand": "brand", "category": "category", "market": "country", "industry": "industry"}


def _dash_rows(db, markets, window_days, include_fixture, industries, categories, source, confidence):
    rows = research_rows(db, markets=_csv(markets), include_fixture=include_fixture, since=_window(window_days),
                         industry_ids=[int(x) for x in _csv(industries) or []] or None,
                         category_ids=[int(x) for x in _csv(categories) or []] or None)
    if source:
        rows = [r for r in rows if r["source_platforms"] and source.lower() in r["source_platforms"].lower()]
    if confidence:
        rows = [r for r in rows if r["confidence"] in _csv(confidence)]
    return rows


@app.get("/api/dashboard/products")
def dashboard_products(db: Session = DB, by: str = "all", value: Optional[str] = None, markets: Optional[str] = None,
                       window_days: int = 30, include_fixture: bool = True, industries: Optional[str] = None,
                       categories: Optional[str] = None, source: Optional[str] = None, confidence: Optional[str] = None):
    """Rows behind one dashboard number or bar (same filters as /api/dashboard, so the counts match)."""
    rows = _dash_rows(db, markets, window_days, include_fixture, industries, categories, source, confidence)
    if by != "all":
        key = DRILL_KEYS.get(by)
        if key is None:
            raise HTTPException(400, f"unknown drill dimension '{by}'")
        if value == "Unassigned":
            rows = [r for r in rows if not r.get(key)]
        else:
            rows = [r for r in rows if value in (r.get(key) or "").split("; ")]
    return sorted(rows, key=lambda r: (r["trend_score"] is None, -(r["trend_score"] or 0), r["product_name"] or ""))


@app.get("/api/dashboard")
def dashboard(db: Session = DB, markets: Optional[str] = None, window_days: int = 30, include_fixture: bool = True,
              industries: Optional[str] = None, categories: Optional[str] = None, source: Optional[str] = None,
              confidence: Optional[str] = None):
    rows = _dash_rows(db, markets, window_days, include_fixture, industries, categories, source, confidence)
    def dist(key):
        d: dict[str, int] = {}
        for r in rows:
            for v in (r.get(key) or "Unassigned").split("; "):
                d[v] = d.get(v, 0) + 1
        return sorted(d.items(), key=lambda x: -x[1])[:15]
    status_counts: dict[str, int] = {}
    for r in rows:
        status_counts[r["trend_status"]] = status_counts.get(r["trend_status"], 0) + 1
    last_job = db.scalar(select(ScanJob).where(ScanJob.kind == "SCAN").order_by(ScanJob.created_at.desc()).limit(1))
    sources = [{"key": s.key, "name": s.name, "status": s.status, "last_error": s.last_error,
                "last_success": s.last_success.isoformat() if s.last_success else None, "enabled": s.enabled}
               for s in db.scalars(select(Source).order_by(Source.name))]
    since = _window(window_days)
    hist = db.execute(select(func.date(TrendHistory.recorded_at), TrendHistory.trend_status, func.count())
                      .where(TrendHistory.recorded_at >= since).group_by(func.date(TrendHistory.recorded_at), TrendHistory.trend_status)).all()
    changes = db.scalar(select(func.count(ChangeEvent.id)).where(ChangeEvent.created_at >= utcnow() - timedelta(days=1)))
    top = sorted([r for r in rows if r["trend_score"] is not None], key=lambda r: -r["trend_score"])[:20]
    return {"total": len({r["product_id"] for r in rows}), "rows": len(rows), "status_counts": status_counts,
            "hot_now": status_counts.get("HOT NOW", 0), "rising_fast": status_counts.get("RISING FAST", 0),
            "upcoming_hype": status_counts.get("UPCOMING HYPE", 0),
            "brands": dist("brand"), "categories": dist("category"), "markets": dist("country"), "industries": dist("industry"),
            "last_scan": row(last_job) if last_job else None, "sources": sources,
            "trend_changes": [{"day": str(d), "status": s, "count": c} for d, s, c in hist], "changes_24h": changes,
            "top": top}


# ======================================================================== upcoming
@app.get("/api/upcoming")
def upcoming(db: Session = DB, markets: Optional[str] = None, status: Optional[str] = None, window: Optional[str] = None,
             include_fixture: bool = True, categories: Optional[str] = None):
    q = select(UpcomingRelease, Product).join(Product, Product.id == UpcomingRelease.product_id)
    if markets:
        q = q.where(UpcomingRelease.market_code.in_(_csv(markets)))
    if status:
        q = q.where(UpcomingRelease.release_status.in_(_csv(status)))
    if not include_fixture:
        q = q.where(Product.is_fixture.is_(False))
    today = utcnow().date()
    if window in ("7", "30", "90"):
        q = q.where(UpcomingRelease.expected_date.is_not(None), UpcomingRelease.expected_date >= today,
                    UpcomingRelease.expected_date <= today + timedelta(days=int(window)))
    elif window == "TBA":
        q = q.where(or_(UpcomingRelease.expected_date.is_(None), UpcomingRelease.date_precision == "TBA"))
    out = []
    base = {r["row_id"]: r for r in research_rows(db, include_fixture=include_fixture, category_ids=_cat_ids(categories))}
    for rel, p in db.execute(q.order_by(UpcomingRelease.expected_date.is_(None), UpcomingRelease.expected_date)).all():
        if categories and f"{p.id}:{rel.market_code}" not in base:
            continue
        b = base.get(f"{p.id}:{rel.market_code}", {})
        out.append({**{k: b.get(k) for k in ("industry", "category", "country", "image_url", "best_info_url", "purchase_url",
                                              "ref_url_1", "ref_url_2", "ref_url_3", "is_fixture")},
                    "row_id": f"{p.id}:{rel.market_code}", "product_id": p.id, "market_code": rel.market_code,
                    "brand": p.brand, "product_name": p.name, "model_variant": p.model_variant, "sku": p.sku,
                    "expected_date": rel.expected_date.isoformat() if rel.expected_date else None,
                    "expected_date_text": rel.expected_date_text, "date_precision": rel.date_precision,
                    "release_status": rel.release_status, "rumor_confidence": rel.rumor_confidence, "hype_score": rel.hype_score,
                    "source_type": rel.source_type, "expected_price": rel.expected_price, "currency": rel.currency,
                    "first_reported": rel.first_reported.isoformat() if rel.first_reported else None,
                    "last_updated": rel.last_updated.isoformat() if rel.last_updated else None,
                    "latest_development": rel.latest_development,
                    "history": [row(h) for h in db.scalars(select(ReleaseHistory).where(ReleaseHistory.release_id == rel.id).order_by(ReleaseHistory.changed_at))]})
    return out


# ======================================================================== early radar
@app.get("/api/early")
def early(db: Session = DB, markets: Optional[str] = None, stage: Optional[str] = None, include_fixture: bool = True,
          categories: Optional[str] = None, job_id: Optional[int] = None):
    jp, jm = _job_scope(db, job_id)
    if jp is not None and not jp:
        return []
    rows = research_rows(db, markets=_csv(markets) or jm, include_fixture=include_fixture, category_ids=_cat_ids(categories), product_ids=jp)
    trends = {(t.product_id, t.market_code): t for t in db.scalars(select(ProductMarketTrend))}
    out = []
    for r in rows:
        t = trends.get((r["product_id"], r["market_code"]))
        if not t:
            continue
        if stage and t.lifecycle_stage not in _csv(stage):
            continue
        b = t.early_breakdown or {}
        latest = db.scalar(select(func.max(Evidence.published_at)).where(Evidence.product_id == r["product_id"], Evidence.market_code == r["market_code"]))
        out.append({**r, "early_score": t.early_score, "lifecycle_stage": t.lifecycle_stage, "early_provisional": t.early_provisional,
                    "mention_growth_3d": b.get("mention_growth_3d"), "mention_growth_7d": b.get("mention_growth_7d"),
                    "mention_growth_14d": b.get("mention_growth_14d"), "acceleration": b.get("acceleration"),
                    "search_growth": b.get("search_growth_raw"), "independent_sources": b.get("independent_sources_7d", b.get("provisional_independent_sources")),
                    "latest_signal": latest.isoformat() if latest else None, "early_explanation": t.early_explanation,
                    "early_breakdown": b})
    out.sort(key=lambda x: (x["early_score"] is None, -(x["early_score"] or 0)))
    return out


# ======================================================================== opportunities
@app.get("/api/opportunities")
def opportunities(db: Session = DB, preset: Optional[str] = None, include_fixture: bool = True, otype: Optional[str] = None,
                  categories: Optional[str] = None):
    q = select(OpportunityScore, Product).join(Product, Product.id == OpportunityScore.product_id)
    if preset:
        q = q.where(OpportunityScore.preset_key == preset)
    if not include_fixture:
        q = q.where(Product.is_fixture.is_(False))
    if otype:
        q = q.where(OpportunityScore.opportunity_type.in_(_csv(otype)))
    base = {}
    for r in research_rows(db, include_fixture=include_fixture):
        base.setdefault(r["product_id"], {})[r["market_code"]] = r
    trends = {(t.product_id, t.market_code): t for t in db.scalars(select(ProductMarketTrend))}
    out = []
    allowed = {r["product_id"] for r in research_rows(db, include_fixture=include_fixture, category_ids=_cat_ids(categories))} if categories else None
    for o, p in db.execute(q.order_by(OpportunityScore.score.desc())).all():
        if allowed is not None and p.id not in allowed:
            continue
        rows_by_m = base.get(p.id, {})
        any_row = next(iter(rows_by_m.values()), {})
        src_t = [trends[(p.id, m)] for m in o.source_markets if (p.id, m) in trends]
        tgt_t = trends.get((p.id, o.target_market))
        def g7(t):
            return (t.early_breakdown or {}).get("mention_growth_7d") if t else None
        src_ev = [rows_by_m[m].get("ref_url_1") for m in o.source_markets if m in rows_by_m and rows_by_m[m].get("ref_url_1")]
        out.append({"row_id": f"{p.id}:{o.preset_key}", "product_id": p.id, "product_name": p.name, "brand": p.brand,
                    "industry": any_row.get("industry"), "category": any_row.get("category"), "sku": p.sku, "image_url": p.image_url,
                    "source_markets": ", ".join(o.source_markets), "target_market": o.target_market, "preset_key": o.preset_key,
                    "source_trend_score": max([t.trend_score for t in src_t if t.trend_score is not None], default=None),
                    "target_trend_score": tgt_t.trend_score if tgt_t else None,
                    "source_growth_7d": max([g for g in (g7(t) for t in src_t) if g is not None], default=None),
                    "target_growth_7d": g7(tgt_t), "opportunity_score": o.score, "opportunity_type": o.opportunity_type,
                    "confidence": o.confidence, "coverage": round(o.coverage * 100), "risk_level": o.risk_level,
                    "target_data_state": o.target_data_state, "best_info_url": any_row.get("best_info_url"),
                    "purchase_url": any_row.get("purchase_url"),
                    "source_evidence_url_1": src_ev[0] if src_ev else None, "source_evidence_url_2": src_ev[1] if len(src_ev) > 1 else None,
                    "target_evidence_url": rows_by_m.get(o.target_market, {}).get("ref_url_1"),
                    "release_status": p.release_status, "availability": None, "explanation": o.explanation,
                    "breakdown": o.breakdown, "first_detected": p.first_detected.isoformat(), "last_updated": o.computed_at.isoformat(),
                    "is_fixture": p.is_fixture})
    return out


@app.post("/api/opportunities/recompute")
def recompute_opps(db: Session = DB):
    return {"rows": compute_opportunities(db)}


@app.post("/api/recompute")
def recompute(db: Session = DB):
    """Recompute every score from stored raw observations (e.g. after changing weights)."""
    return {"rows": recompute_all(db)}


# ======================================================================== shortlists
@app.get("/api/shortlists")
def list_shortlists(db: Session = DB, list_type: Optional[str] = None):
    q = select(Shortlist, Product).join(Product, Product.id == Shortlist.product_id).order_by(Shortlist.created_at.desc())
    if list_type:
        q = q.where(Shortlist.list_type == list_type)
    return [{**row(s), "product_name": p.name, "brand": p.brand, "sku": p.sku, "image_url": p.image_url, "is_fixture": p.is_fixture}
            for s, p in db.execute(q).all()]


@app.post("/api/shortlists")
def add_shortlist(data: dict = Body(...), db: Session = DB):
    existing = db.scalar(select(Shortlist).where(Shortlist.list_type == data["list_type"], Shortlist.product_id == data["product_id"],
                                                 Shortlist.target_market.is_(None) if not data.get("target_market") else Shortlist.target_market == data["target_market"]))
    if existing:
        return row(existing)
    s = Shortlist(list_type=data["list_type"], product_id=data["product_id"], target_market=data.get("target_market"),
                  priority=data.get("priority"), notes=data.get("notes"), research_status=data.get("research_status", "Researching"))
    db.add(s)
    db.flush()
    return row(s)


@app.put("/api/shortlists/{sid}")
def update_shortlist(sid: int, data: dict = Body(...), db: Session = DB):
    s = db.get(Shortlist, sid) or _404()
    _upd(s, data, {"priority", "notes", "research_status", "supplier_check", "marketing_test_status", "target_market"})
    s.reviewed_at = utcnow()
    return row(s)


@app.delete("/api/shortlists/{sid}")
def delete_shortlist(sid: int, db: Session = DB):
    db.delete(db.get(Shortlist, sid) or _404())
    return {"deleted": True}


# ======================================================================== what's new
@app.get("/api/changes")
def changes(db: Session = DB, since_last_scan: bool = True, days: Optional[int] = None, event_type: Optional[str] = None,
            markets: Optional[str] = None, include_fixture: bool = True, limit: int = 500):
    q = select(ChangeEvent, Product).outerjoin(Product, Product.id == ChangeEvent.product_id).order_by(ChangeEvent.created_at.desc())
    if days:
        q = q.where(ChangeEvent.created_at >= utcnow() - timedelta(days=days))
    elif since_last_scan:
        jobs = list(db.scalars(select(ScanJob).where(ScanJob.kind == "SCAN", ScanJob.status.in_(["COMPLETED", "PARTIAL"]))
                               .order_by(ScanJob.finished_at.desc()).limit(2)))
        if len(jobs) == 2 and jobs[1].finished_at:
            q = q.where(ChangeEvent.created_at > jobs[1].finished_at)
    if event_type:
        q = q.where(ChangeEvent.event_type.in_(_csv(event_type)))
    if markets:
        q = q.where(ChangeEvent.market_code.in_(_csv(markets)))
    if not include_fixture:
        q = q.where(ChangeEvent.is_fixture.is_(False))
    return [{**row(e), "product_name": p.name if p else None, "brand": p.brand if p else None} for e, p in db.execute(q.limit(limit)).all()]


# ======================================================================== settings
@app.get("/api/settings")
def get_settings(db: Session = DB):
    return {s.key: s.value for s in db.scalars(select(Setting))}


@app.put("/api/settings/{key}")
def put_setting(key: str, value: Any = Body(...), db: Session = DB):
    s = db.get(Setting, key)
    if s is None:
        s = Setting(key=key, value=value)
        db.add(s)
    else:
        s.value = value
    return {"key": key, "value": value}


# ======================================================================== manual capture & imports
class CaptureItemIn(BaseModel):
    url: str
    market_code: str = "GLOBAL"
    title: str = ""
    text: str = ""
    product_name: Optional[str] = None
    brand: Optional[str] = None
    model_variant: Optional[str] = None
    sku: Optional[str] = None
    category_id: Optional[int] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None


@app.post("/api/capture/preview")
def capture_preview(data: dict = Body(...), db: Session = DB):
    from .pipeline.manual import preview
    return preview(db, data.get("url", ""), data.get("title", ""), data.get("text", ""))


@app.post("/api/capture")
def capture_items(items: list[CaptureItemIn], db: Session = DB):
    """Save pages the user browsed (bookmarklet / form / bulk paste) as evidence, then rescore those products."""
    from .pipeline.links import find_links as _fl
    from .pipeline.manual import CaptureIn, capture
    from .scoring.engine import recompute_products
    entries = [CaptureIn(url=i.url, market_code=i.market_code or "GLOBAL", title=i.title, text=i.text, product_name=i.product_name or None,
                         brand=i.brand or None, model_variant=i.model_variant or None, sku=i.sku or None, category_id=i.category_id,
                         author=i.author or None, image_url=i.image_url or None,
                         engagement={k: getattr(i, k) for k in ("views", "likes", "comments", "shares") if getattr(i, k) is not None})
               for i in items]
    results, stats = capture(db, entries)
    for pid in stats.touched_products:
        p = db.get(Product, pid)
        if p is not None and p.link_status in ("NOT_CHECKED", "NOT_FOUND", "TITLE_MATCH"):
            _fl(db, pid, use_search=False, fetch_pages=False)
    recompute_products(db, stats.touched_products, new_evidence_ids=stats.products_with_new_evidence)
    compute_opportunities(db)
    return {"results": [r.__dict__ for r in results], "saved": sum(r.status == "SAVED" for r in results),
            "products": len(stats.touched_products)}


@app.post("/api/trends/preview")
def trends_preview(data: dict = Body(...), db: Session = DB):
    from .pipeline.trends import preview
    try:
        return preview(db, data.get("csv", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/trends/import")
def trends_import(data: dict = Body(...), db: Session = DB):
    from .pipeline.trends import import_csv
    from .scoring.engine import recompute_products
    try:
        r = import_csv(db, data.get("csv", ""), data.get("mapping", []), data.get("file_name"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    recompute_products(db, r["product_ids"])
    compute_opportunities(db)
    return r


@app.get("/api/products-lookup")
def products_lookup(q: str = "", db: Session = DB, limit: int = 20):
    like = f"%{q.lower()}%"
    rows = db.execute(select(Product.id, Product.brand, Product.name, Product.model_variant, Product.is_fixture)
                      .where(or_(func.lower(Product.name).like(like), func.lower(Product.brand).like(like)))
                      .order_by(Product.last_seen.desc()).limit(limit)).all()
    return [{"product_id": r[0], "label": f"{r[1] or ''} · {r[2]}" + (f" \"{r[3]}\"" if r[3] else "") + (" [DEMO]" if r[4] else "")} for r in rows]


@app.get("/api/products/{pid}/search-interest")
def product_search_interest(pid: int, db: Session = DB):
    from .models import SearchInterest
    return [row(r) for r in db.scalars(select(SearchInterest).where(SearchInterest.product_id == pid).order_by(SearchInterest.day))]


# ======================================================================== export
class ExportIn(BaseModel):
    format: str = "tsv"  # tsv | csv | xlsx
    dataset: str = "research"  # research | upcoming | early | opportunities
    row_ids: list[str] = []
    columns: list[str] = []
    headers: bool = True
    image_mode: str = "url"  # url | formula
    filters: dict[str, Any] = {}


DATASET_COLUMNS = {
    "research": RESEARCH_COLUMNS,
    "upcoming": [("country", "Market / Country"), ("industry", "Industry"), ("category", "Category"), ("brand", "Brand"),
                 ("product_name", "Product Name"), ("model_variant", "Model/Variant"), ("sku", "SKU"), ("image_url", "Image URL"),
                 ("best_info_url", "Best Product Information URL"), ("purchase_url", "Optional Official/Purchase URL"),
                 ("expected_date_text", "Expected Release Date"), ("date_precision", "Date Precision"), ("release_status", "Release Status"),
                 ("rumor_confidence", "Rumor Confidence"), ("hype_score", "Hype Score"), ("ref_url_1", "Reference URL 1"),
                 ("ref_url_2", "Reference URL 2"), ("ref_url_3", "Reference URL 3"), ("source_type", "Source Type"),
                 ("expected_price", "Expected Retail Price"), ("currency", "Currency"), ("first_reported", "First Reported"),
                 ("last_updated", "Last Updated"), ("latest_development", "Latest Development")],
    "early": [("country", "Country"), ("industry", "Industry"), ("category", "Category"), ("brand", "Brand"), ("product_name", "Product Name"),
              ("model_variant", "Model/Variant"), ("sku", "SKU"), ("image_url", "Image URL"), ("best_info_url", "Best Product Information URL"),
              ("purchase_url", "Optional Purchase URL"), ("early_score", "Early Signal Score"), ("lifecycle_stage", "Lifecycle Stage"),
              ("mention_growth_3d", "Mention Growth 3D"), ("mention_growth_7d", "Mention Growth 7D"), ("mention_growth_14d", "Mention Growth 14D"),
              ("acceleration", "Mention Acceleration"), ("search_growth", "Search Growth"), ("independent_sources", "Independent Sources"),
              ("confidence", "Evidence Confidence"), ("coverage", "Data Coverage"), ("first_detected", "First Detected"),
              ("latest_signal", "Latest Signal"), ("ref_url_1", "Reference URL 1"), ("ref_url_2", "Reference URL 2"),
              ("ref_url_3", "Reference URL 3"), ("early_explanation", "Explanation"), ("last_seen", "Last Updated")],
    "opportunities": [("product_name", "Product Name"), ("brand", "Brand"), ("industry", "Industry"), ("category", "Category"), ("sku", "SKU"),
                      ("image_url", "Image URL"), ("source_markets", "Source Markets"), ("target_market", "Target Market"),
                      ("source_trend_score", "Source Trend Score"), ("target_trend_score", "Target Trend Score"),
                      ("source_growth_7d", "Source Growth 7D"), ("target_growth_7d", "Target Growth 7D"),
                      ("opportunity_score", "Opportunity Score"), ("opportunity_type", "Opportunity Type"), ("confidence", "Evidence Confidence"),
                      ("coverage", "Data Coverage"), ("risk_level", "Risk Level"), ("best_info_url", "Best Product Information URL"),
                      ("purchase_url", "Optional Purchase URL"), ("source_evidence_url_1", "Source Evidence URL 1"),
                      ("source_evidence_url_2", "Source Evidence URL 2"), ("target_evidence_url", "Target Evidence URL"),
                      ("release_status", "Release Status"), ("availability", "Availability"), ("explanation", "Explanation"),
                      ("first_detected", "First Detected"), ("last_updated", "Last Updated")],
}


@app.post("/api/export")
def export(body: ExportIn, db: Session = DB):
    f = body.filters or {}
    if body.dataset == "upcoming":
        rows = upcoming(db, markets=f.get("markets"), status=f.get("status"), window=f.get("window"), include_fixture=f.get("include_fixture", True),
                        categories=f.get("categories"))
    elif body.dataset == "early":
        rows = early(db, markets=f.get("markets"), stage=f.get("stage"), include_fixture=f.get("include_fixture", True), categories=f.get("categories"),
                     job_id=f.get("job_id"))
    elif body.dataset == "opportunities":
        rows = opportunities(db, preset=f.get("preset"), include_fixture=f.get("include_fixture", True), categories=f.get("categories"))
    else:
        jp, jm = _job_scope(db, f.get("job_id"))
        rows = research_rows(db, markets=_csv(f.get("markets")) or jm, product_ids=jp, search=f.get("q"), status=_csv(f.get("status")), category_ids=_cat_ids(f.get("categories")),
                             include_fixture=f.get("include_fixture", True), expand_categories=bool(f.get("expand")))
    if body.row_ids:
        order = {rid: i for i, rid in enumerate(body.row_ids)}
        rows = sorted([r for r in rows if r["row_id"] in order], key=lambda r: order[r["row_id"]])
    cols = columns_for(body.columns, DATASET_COLUMNS.get(body.dataset, RESEARCH_COLUMNS))
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if body.format == "csv":
        return Response(to_csv(rows, cols, body.headers, body.image_mode), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="gpti_{body.dataset}_{stamp}.csv"'})
    if body.format == "xlsx":
        return Response(to_xlsx(rows, cols, body.headers, body.image_mode),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="gpti_{body.dataset}_{stamp}.xlsx"'})
    return Response(to_tsv(rows, cols, body.headers, body.image_mode), media_type="text/tab-separated-values; charset=utf-8")


def _404():
    raise HTTPException(404, "not found")


# ======================================================================== static frontend
if (config.STATIC_DIR / "index.html").exists():
    if (config.STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = config.STATIC_DIR / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(config.STATIC_DIR / "index.html")
