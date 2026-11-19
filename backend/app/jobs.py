"""Persistent shared queue for scheduled scans, manual scans and bulk link-finder jobs.

* Jobs and tasks live in the database -> survive restarts; RUNNING jobs with a stale heartbeat are re-queued.
* dedup_key is UNIQUE -> the same scheduled slot cannot be enqueued twice, even from two processes.
* Tasks are idempotent (upserts keyed by product+URL), so re-running after a crash is safe.
* A failed source never deletes or overwrites earlier data."""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from . import config
from .adapters.base import FetchCtx, SourceError
from .adapters.rss import get_adapter
from .db import session_scope, utcnow
from .models import Category, Industry, Market, MarketSignalCoverage, Product, ProductCategory, ProductMarket, ScanJob, ScanPreset, ScanTask, Source
from .pipeline.ingest import IngestStats, ScopeContext, ingest_items
from .pipeline.links import find_links
from .scoring.engine import compute_opportunities, recompute_products

log = logging.getLogger("gpti.jobs")
WRITE_LOCK = threading.Lock()  # serialise SQLite writes from source threads
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
PRIORITY = {"MANUAL": 10, "CATCHUP": 30, "SCHEDULED": 40}
STALE_AFTER = timedelta(minutes=10)


# ---------------------------------------------------------------- scope helpers
def expand_categories(db, category_ids: list[int], industry_ids: list[int]) -> list[Category]:
    cats = list(db.scalars(select(Category).where(Category.active.is_(True))))
    by_parent: dict[Optional[int], list[Category]] = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)
    if not category_ids and not industry_ids:
        return cats
    chosen: dict[int, Category] = {}
    if industry_ids:
        for c in cats:
            if c.industry_id in industry_ids:
                chosen[c.id] = c
    stack = [c for c in cats if c.id in set(category_ids)]
    while stack:
        c = stack.pop()
        chosen[c.id] = c
        stack.extend(by_parent.get(c.id, []))
    return list(chosen.values())


def _query_terms(cat: Category, lang: Optional[str], include_local: bool) -> list[str]:
    terms = [k.rstrip("*") for k in (cat.keywords or [])][:4] + list(cat.brands or [])[:3]
    if cat.parent_id is not None and cat.name not in terms:
        terms.insert(0, cat.name)
    if include_local and lang:
        terms += (cat.local_keywords or {}).get(lang, [])
    seen, out = set(), []
    for t in terms:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:6]


def build_query(terms: list[str], include: list[str], exclude: list[str]) -> str:
    q = " OR ".join(f'"{t}"' if " " in t else t for t in terms)
    if include:
        q = f"({q}) " + " ".join(f'"{k}"' if " " in k else k for k in include)
    if exclude:
        q += " " + " ".join(f"-{k}" for k in exclude if " " not in k)
    return q + " when:30d"


GNEWS_TOPICS = {
    "Electronics & Technology": ["TECHNOLOGY"], "Fashion & Footwear": ["BUSINESS", "ENTERTAINMENT"],
    "Beauty & Personal Care": ["BUSINESS", "ENTERTAINMENT"], "Toys & Collectibles": ["ENTERTAINMENT", "BUSINESS"],
    "Sports & Outdoor": ["SPORTS", "BUSINESS"], "Home & Living": ["BUSINESS"], "Food & Beverage": ["BUSINESS"],
    "Automotive Accessories": ["TECHNOLOGY", "BUSINESS"], "Lifestyle & Pet": ["BUSINESS", "ENTERTAINMENT"],
}
_gnews_check: dict[str, tuple[float, bool]] = {}


def _gnews_search_allowed() -> bool:
    from .adapters.base import robots_allowed
    cached = _gnews_check.get("search")
    if cached and time.time() - cached[0] < 3600:
        return cached[1]
    ok = robots_allowed("https://news.google.com/rss/search?q=test&hl=en-US&gl=US&ceid=US:en")
    _gnews_check["search"] = (time.time(), ok)
    return ok


def plan_tasks(db, job: ScanJob) -> list[ScanTask]:
    scope = job.scope or {}
    markets = scope.get("markets") or []
    cats = expand_categories(db, scope.get("category_ids") or [], scope.get("industry_ids") or [])
    cat_inds = {c.industry_id for c in cats}
    src_filter = set(scope.get("source_keys") or [])
    include_fixture = scope.get("include_fixture", False)
    tasks: list[ScanTask] = []
    product_ids = scope.get("product_ids") or []
    tops = [c for c in cats if c.parent_id is None] or cats
    for src in db.scalars(select(Source)):
        if src_filter and src.key not in src_filter:
            continue
        if not src_filter and not src.enabled:
            continue
        if src.is_fixture and not include_fixture and src.key not in src_filter:
            continue
        if src.industry_ids and cat_inds and not (set(src.industry_ids) & cat_inds):
            continue
        if src.adapter in ("manual", "trends_import"):
            continue  # filled by the user (capture / CSV import), never scanned
        adapter = get_adapter(src.adapter)
        try:
            adapter.check_configured(src)
        except SourceError as e:
            src.status, src.last_error, src.last_checked = e.status, e.message, utcnow()
            tasks.append(ScanTask(job_id=job.id, source_key=src.key, work_key=f"{src.key}|skip", status="SKIPPED", error=f"{e.status}: {e.message}"))
            continue
        if not adapter.per_query:
            src_markets = src.markets or ["GLOBAL"]
            if markets and "GLOBAL" not in src_markets and not set(src_markets) & set(markets):
                continue
            tasks.append(ScanTask(job_id=job.id, source_key=src.key, market_code=src_markets[0], work_key=f"{src.key}|feed"))
            continue
        if src.adapter == "fixture":
            for mc in markets or ["US"]:
                tasks.append(ScanTask(job_id=job.id, source_key=src.key, market_code=mc, work_key=f"{src.key}|{mc}"))
            continue
        if src.adapter == "google_news" and not _gnews_search_allowed():
            # robots.txt forbids automated use of the Google News *search* feed: never bypass it. Use the
            # section headline feeds for the selected industries instead (one task per market x topic).
            ind_names = {i.id: i.name for i in db.scalars(select(Industry))}
            topics = sorted({t for c in cats for t in GNEWS_TOPICS.get(ind_names.get(c.industry_id, ""), ["BUSINESS"])})
            for mc in markets or ["US"]:
                mk = db.scalar(select(Market).where(Market.code == mc))
                if mk is None or mk.is_city or not mk.google_news_ceid:
                    continue
                for tp in topics:
                    tasks.append(ScanTask(job_id=job.id, source_key=src.key, market_code=mc, query=f"topic:{tp}",
                                          work_key=f"{src.key}|{mc}|topic:{tp}"))
            src.notes = ("Search feed disallowed by news.google.com/robots.txt - using section headline feeds "
                         f"({', '.join(topics)}) filtered by your categories.")
            continue
        for mc in markets or ["US"]:
            mk = db.scalar(select(Market).where(Market.code == mc))
            if mk is None or mk.is_city:
                continue  # city-level data only where a trustworthy localized source exists
            lang = (mk.languages or ["en"])[0]
            if product_ids or job.mode == "TRACKING":
                prods = (list(db.scalars(select(Product).where(Product.id.in_(product_ids)))) if product_ids else
                         list(db.scalars(select(Product).join(ProductMarket).where(ProductMarket.market_code == mc)
                                         .order_by(Product.last_seen.desc()).limit(25 if job.depth == "FULL" else 10))))
                for p in prods:
                    q = f'"{p.name}"' + (f" {p.sku}" if p.sku else "") + " when:30d"
                    tasks.append(ScanTask(job_id=job.id, source_key=src.key, market_code=mc, query=q,
                                          work_key=f"{src.key}|{mc}|p{p.id}"))
                continue
            # Quick: top categories + their subcategories (brand-level queries find far more products), capped per market
            groups = cats if job.depth == "FULL" else (tops + [c for c in cats if c.parent_id is not None])[:12]
            for c in groups:
                terms = _query_terms(c, lang if lang != "en" else None, include_local=True)
                if not terms:
                    continue
                q = build_query(terms, scope.get("include_keywords") or [], scope.get("exclude_keywords") or [])
                tasks.append(ScanTask(job_id=job.id, source_key=src.key, market_code=mc, category_id=c.id, query=q,
                                      work_key=f"{src.key}|{mc}|c{c.id}|{q}"))
                if job.depth == "FULL" and lang != "en":
                    q2 = build_query(_query_terms(c, None, False), scope.get("include_keywords") or [], scope.get("exclude_keywords") or [])
                    tasks.append(ScanTask(job_id=job.id, source_key=src.key, market_code=mc, category_id=c.id, query=q2,
                                          work_key=f"{src.key}|{mc}|c{c.id}|{q2}"))
    # de-duplicate overlapping work inside the job
    seen, uniq = set(), []
    for t in tasks:
        if t.work_key in seen:
            continue
        seen.add(t.work_key)
        uniq.append(t)
    return uniq


# ---------------------------------------------------------------- enqueue
def enqueue(kind: str, scope: dict, trigger: str = "MANUAL", preset: Optional[ScanPreset] = None, mode: str = "DISCOVERY",
            depth: str = "QUICK", dedup_key: Optional[str] = None, priority: Optional[int] = None) -> tuple[int, bool]:
    """Returns (job_id, created). If dedup_key already exists the existing job id is returned."""
    with session_scope() as db:
        if dedup_key:
            existing = db.scalar(select(ScanJob.id).where(ScanJob.dedup_key == dedup_key))
            if existing:
                return existing, False
        job = ScanJob(kind=kind, scope=scope, trigger=trigger, mode=mode, depth=depth, dedup_key=dedup_key,
                      priority=priority if priority is not None else PRIORITY.get(trigger, 50),
                      preset_id=preset.id if preset else None, preset_name=preset.name if preset else None)
        db.add(job)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return db.scalar(select(ScanJob.id).where(ScanJob.dedup_key == dedup_key)), False
        return job.id, True


def preset_scope(p: ScanPreset) -> dict:
    return {"markets": p.markets, "category_ids": p.category_ids, "industry_ids": p.industry_ids,
            "include_keywords": p.include_keywords, "exclude_keywords": p.exclude_keywords,
            "source_keys": p.source_keys, "limits": p.limits or {}}


# ---------------------------------------------------------------- worker
def recover_stale() -> int:
    with session_scope() as db:
        cutoff = utcnow() - STALE_AFTER
        stale = list(db.scalars(select(ScanJob).where(ScanJob.status == "RUNNING",
                                                      or_(ScanJob.heartbeat_at.is_(None), ScanJob.heartbeat_at < cutoff))))
        for j in stale:
            j.status = "QUEUED"
            j.error = (j.error or "") + f"\nrecovered after interruption at {utcnow().isoformat()}"
            db.execute(update(ScanTask).where(ScanTask.job_id == j.id, ScanTask.status == "RUNNING").values(status="QUEUED"))
        return len(stale)


def claim_next() -> Optional[int]:
    with session_scope() as db:
        jobs = list(db.scalars(select(ScanJob).where(ScanJob.status == "QUEUED").order_by(ScanJob.created_at).limit(50)))
        if not jobs:
            return None
        now = utcnow()
        # ageing: every 10 minutes of waiting improves priority by 1 so scheduled jobs are never starved
        jobs.sort(key=lambda j: j.priority - (now - j.created_at).total_seconds() / 600)
        for j in jobs:
            res = db.execute(update(ScanJob).where(ScanJob.id == j.id, ScanJob.status == "QUEUED")
                             .values(status="RUNNING", worker_id=WORKER_ID, heartbeat_at=now, started_at=j.started_at or now))
            if res.rowcount == 1:
                return j.id
    return None


def _heartbeat(job_id: int, **fields) -> str:
    with session_scope() as db:
        j = db.get(ScanJob, job_id)
        j.heartbeat_at = utcnow()
        for k, v in fields.items():
            setattr(j, k, v)
        return j.status


def _source_failure(db, src: Source, err: SourceError) -> None:
    src.status, src.last_error, src.last_checked = err.status, err.message, utcnow()
    src.consecutive_failures = (src.consecutive_failures or 0) + 1
    mins = min(2 ** src.consecutive_failures, 360)
    src.cooldown_until = utcnow() + timedelta(minutes=mins)


def _run_task(job_id: int, task_id: int, max_results: int, tracking: bool) -> None:
    with session_scope() as db:
        task = db.get(ScanTask, task_id)
        src = db.scalar(select(Source).where(Source.key == task.source_key))
        job = db.get(ScanJob, job_id)
        if src.cooldown_until and src.cooldown_until > utcnow() and job.trigger != "MANUAL":
            task.status, task.error = "SKIPPED", f"source cooling down until {src.cooldown_until.isoformat()} after failures"
            return
        mk = db.scalar(select(Market).where(Market.code == task.market_code)) if task.market_code else None
        ctx = FetchCtx(market_code=task.market_code, languages=(mk.languages if mk else []), query=task.query,
                       google_news_locale=(mk.google_news_ceid if mk else None), max_results=max_results,
                       use_cache=job.depth != "FULL", pages=5 if job.depth == "FULL" else 3)
        task.status, task.started_at = "RUNNING", utcnow()
        task.attempts += 1
        scope = job.scope or {}
        src_snapshot = Source(**{c.name: getattr(src, c.name) for c in Source.__table__.columns})
    adapter = get_adapter(src_snapshot.adapter)
    out, err = None, None
    for attempt in range(3):
        try:
            out = adapter.fetch(src_snapshot, ctx)
            err = None
            break
        except SourceError as e:
            err = e
            if not e.retryable:
                break
            time.sleep(min(2 ** attempt, 8))
        except Exception as e:  # adapter bug: report, never crash the worker
            err = SourceError("ERROR", f"{type(e).__name__}: {e}")
            break
    with WRITE_LOCK, session_scope() as db:
        task = db.get(ScanTask, task_id)
        src = db.scalar(select(Source).where(Source.key == task.source_key))
        if err is not None:
            task.status, task.error, task.finished_at = "FAILED", f"{err.status}: {err.message}", utcnow()
            _source_failure(db, src, err)
            return
        cats = expand_categories(db, scope.get("category_ids") or [], scope.get("industry_ids") or [])
        if task.category_id:
            cats_task = [c for c in cats if c.id == task.category_id or c.parent_id == task.category_id] or cats
        else:
            cats_task = cats
        sc = ScopeContext(categories=cats_task, include_keywords=scope.get("include_keywords") or [],
                          exclude_keywords=scope.get("exclude_keywords") or [], tracking_only=tracking,
                          restrict_product_ids=set(scope["product_ids"]) if scope.get("product_ids") else None, job_id=job_id)
        stats = ingest_items(db, src, out.items, sc, IngestStats())
        task.items_found, task.products_new, task.products_updated = stats.items, stats.products_new, stats.products_updated
        task.from_cache = out.from_cache
        task.status, task.finished_at = "DONE", utcnow()
        src.status, src.last_error, src.last_checked, src.last_success = "WORKING", None, utcnow(), utcnow()
        src.consecutive_failures, src.cooldown_until = 0, None
        for c in (cats_task if task.category_id else [None]):
            cid = c.id if c is not None else None
            mc = task.market_code or "GLOBAL"
            cov = db.scalar(select(MarketSignalCoverage).where(MarketSignalCoverage.market_code == mc,
                                                               MarketSignalCoverage.category_id.is_(cid) if cid is None else MarketSignalCoverage.category_id == cid,
                                                               MarketSignalCoverage.source_key == src.key))
            if cov is None:
                cov = MarketSignalCoverage(market_code=mc, category_id=cid, source_key=src.key, source_type=src.source_type, successful_scans=0)
                db.add(cov)
            cov.successful_scans += 1
            cov.last_success_at = utcnow()
        job = db.get(ScanJob, job_id)
        cp = dict(job.checkpoint or {})
        cp.setdefault("touched", [])
        cp["touched"] = sorted(set(cp["touched"]) | stats.touched_products)
        cp.setdefault("new_evidence", [])
        cp["new_evidence"] = sorted(set(cp["new_evidence"]) | stats.products_with_new_evidence)
        diag = dict(cp.get("diag") or {})
        for k, v in (("items", stats.items), ("mentions", stats.mentions), ("out_of_scope", stats.skipped_out_of_scope),
                     ("evidence_new", stats.evidence_new)):
            diag[k] = diag.get(k, 0) + v
        diag["no_product"] = diag.get("no_product", 0) + max(0, stats.items - stats.mentions - stats.skipped_out_of_scope)
        cp["diag"] = diag
        job.checkpoint = cp


def run_scan_job(job_id: int) -> None:
    with session_scope() as db:
        job = db.get(ScanJob, job_id)
        if not db.scalar(select(ScanTask.id).where(ScanTask.job_id == job_id).limit(1)):
            for t in plan_tasks(db, job):
                db.add(t)
        limits = (job.scope or {}).get("limits") or {}
        max_results = int(limits.get("max_results", config.MAX_RESULTS_PER_TASK))
        max_duration = int(limits.get("max_duration_s", 1800 if job.depth == "FULL" else 600))
        tracking = job.mode == "TRACKING"
    started = time.monotonic()
    with session_scope() as db:
        pending = list(db.scalars(select(ScanTask).where(ScanTask.job_id == job_id, ScanTask.status.in_(["QUEUED", "RUNNING"]))
                                  .order_by(ScanTask.id)))
        by_source: dict[str, list[int]] = {}
        for t in pending:
            by_source.setdefault(t.source_key, []).append(t.id)

    def run_source(task_ids: list[int]):
        for tid in task_ids:
            status = _heartbeat(job_id)
            if status in ("PAUSE_REQUESTED", "CANCEL_REQUESTED"):
                return
            if time.monotonic() - started > max_duration:
                with session_scope() as db:
                    t = db.get(ScanTask, tid)
                    t.status, t.error = "SKIPPED", "scan duration limit reached"
                continue
            with session_scope() as db:
                db.get(ScanJob, job_id).current_source = db.get(ScanTask, tid).source_key
            _run_task(job_id, tid, max_results, tracking)

    with ThreadPoolExecutor(max_workers=max(1, config.GLOBAL_CONCURRENCY)) as ex:
        list(ex.map(run_source, by_source.values()))
    finalize(job_id)


def finalize(job_id: int) -> None:
    with WRITE_LOCK, session_scope() as db:
        job = db.get(ScanJob, job_id)
        if job.status == "PAUSE_REQUESTED":
            job.status = "PAUSED"
            return
        if job.status == "CANCEL_REQUESTED":
            db.execute(update(ScanTask).where(ScanTask.job_id == job_id, ScanTask.status == "QUEUED").values(status="CANCELLED"))
            job.status, job.finished_at = "CANCELLED", utcnow()
            return
        tasks = list(db.scalars(select(ScanTask).where(ScanTask.job_id == job_id)))
        done = [t for t in tasks if t.status == "DONE"]
        failed = [t for t in tasks if t.status == "FAILED"]
        cp = job.checkpoint or {}
        touched = set(cp.get("touched", []))
        # lightweight evidence-only link resolution (no page fetch) for products never checked
        for pid in touched:
            prod = db.get(Product, pid)
            if prod is not None and prod.link_status in ("NOT_CHECKED", "NOT_FOUND", "TITLE_MATCH"):
                find_links(db, pid, use_search=False, fetch_pages=False)
        n = recompute_products(db, touched, job_id=job_id, new_evidence_ids=set(cp.get("new_evidence", [])))
        compute_opportunities(db)
        job.stats = {"tasks_total": len(tasks), "tasks_done": len(done), "tasks_failed": len(failed),
                     "tasks_skipped": len([t for t in tasks if t.status == "SKIPPED"]),
                     "items_found": sum(t.items_found for t in done), "products_new": sum(t.products_new for t in done),
                     "products_updated": len(touched), "trend_rows_recomputed": n,
                     "from_cache": len([t for t in done if t.from_cache]),
                     "articles_read": (cp.get("diag") or {}).get("items", 0),
                     "product_mentions": (cp.get("diag") or {}).get("mentions", 0),
                     "no_product_recognised": (cp.get("diag") or {}).get("no_product", 0),
                     "outside_selected_categories": (cp.get("diag") or {}).get("out_of_scope", 0),
                     "new_evidence": (cp.get("diag") or {}).get("evidence_new", 0),
                     "failed_sources": sorted({t.source_key for t in failed}),
                     "elapsed_s": round((utcnow() - job.started_at).total_seconds(), 1) if job.started_at else None,
                     "errors": [f"{t.source_key} {t.market_code or ''}: {t.error}" for t in tasks if t.error][:30]}
        if done and not failed:
            job.status = "COMPLETED"
        elif done:
            job.status = "PARTIAL"
        else:
            job.status = "FAILED"  # no phantom success: nothing was fetched
        job.finished_at = utcnow()
        job.current_source = None
        if job.preset_id:
            p = db.get(ScanPreset, job.preset_id)
            if p:
                p.last_attempt_at = utcnow()
                if job.status in ("COMPLETED", "PARTIAL"):
                    p.last_success_at = utcnow()


def run_link_job(job_id: int) -> None:
    with session_scope() as db:
        job = db.get(ScanJob, job_id)
        ids = list((job.scope or {}).get("product_ids") or [])
        purchase = bool((job.scope or {}).get("purchase_mode"))
        cp = dict(job.checkpoint or {})
        done_ids = set(cp.get("done", []))
    results = cp.get("results", {})
    for pid in ids:
        if pid in done_ids:
            continue
        if _heartbeat(job_id) in ("PAUSE_REQUESTED", "CANCEL_REQUESTED"):
            break
        try:
            with WRITE_LOCK, session_scope() as db:
                r = find_links(db, pid, purchase_mode=purchase)
                results[str(pid)] = r.status
        except Exception as e:  # partial failure is reported, the batch continues
            results[str(pid)] = f"ERROR: {e}"
        done_ids.add(pid)
        with session_scope() as db:
            j = db.get(ScanJob, job_id)
            j.checkpoint = {"done": sorted(done_ids), "results": results}
            j.stats = {"total": len(ids), "done": len(done_ids),
                       "verified": sum(1 for v in results.values() if v == "VERIFIED"),
                       "needs_review": sum(1 for v in results.values() if v == "NEEDS_REVIEW"),
                       "not_found": sum(1 for v in results.values() if v == "NOT_FOUND"),
                       "failed": sum(1 for v in results.values() if v.startswith(("ERROR", "FAILED")))}
    with session_scope() as db:
        j = db.get(ScanJob, job_id)
        if j.status == "PAUSE_REQUESTED":
            j.status = "PAUSED"
        elif j.status == "CANCEL_REQUESTED":
            j.status, j.finished_at = "CANCELLED", utcnow()
        else:
            j.status = "COMPLETED" if len(done_ids) == len(ids) else "PARTIAL"
            j.finished_at = utcnow()


def run_job(job_id: int) -> None:
    with session_scope() as db:
        kind = db.get(ScanJob, job_id).kind
    try:
        if kind == "LINK_FINDER":
            run_link_job(job_id)
        else:
            run_scan_job(job_id)
    except Exception as e:
        log.exception("job %s crashed", job_id)
        with session_scope() as db:
            j = db.get(ScanJob, job_id)
            j.status, j.error, j.finished_at = "FAILED", f"{type(e).__name__}: {e}", utcnow()


def drain(max_jobs: int = 100) -> int:
    """Process queued jobs until the queue is empty (used by CLI / Task Scheduler and tests)."""
    n = 0
    while n < max_jobs:
        jid = claim_next()
        if jid is None:
            break
        run_job(jid)
        n += 1
    return n


class Worker(threading.Thread):
    def __init__(self, poll: float = 2.0):
        super().__init__(daemon=True, name="gpti-worker")
        self.poll = poll
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        recover_stale()
        while not self._stop.is_set():
            try:
                jid = claim_next()
                if jid is None:
                    self._stop.wait(self.poll)
                    continue
                run_job(jid)
            except Exception:  # pragma: no cover
                log.exception("worker loop error")
                self._stop.wait(5)
