from datetime import timedelta

from sqlalchemy import func, select

from app.adapters import rss
from app.adapters.base import SourceError
from app.db import session_scope, utcnow
from app.jobs import claim_next, drain, enqueue, recover_stale
from app.models import Evidence, Product, ScanJob, ScanPreset, ScanTask, Source


def test_failed_source_is_reported_honestly_and_keeps_data(demo_loaded, monkeypatch):
    def boom(self, source, ctx):
        raise SourceError("BLOCKED", "HTTP 403 Forbidden (access refused; not bypassed)")
    monkeypatch.setattr(rss.FixtureAdapter, "fetch", boom)
    with session_scope() as db:
        n_ev = db.scalar(select(func.count(Evidence.id)))
        preset = db.scalar(select(ScanPreset))
        preset.last_success_at = None
        pid = preset.id
    jid, _ = enqueue("SCAN", {"markets": ["JP"], "source_keys": ["demo_fixture"], "include_fixture": True}, preset=None)
    with session_scope() as db:
        db.get(ScanJob, jid).preset_id = pid
    drain()
    with session_scope() as db:
        j = db.get(ScanJob, jid)
        assert j.status == "FAILED"  # no phantom success
        assert db.scalar(select(func.count(Evidence.id))) == n_ev  # nothing overwritten / deleted
        src = db.scalar(select(Source).where(Source.key == "demo_fixture"))
        assert src.status == "BLOCKED" and src.cooldown_until is not None
        assert db.get(ScanPreset, pid).last_success_at is None


def test_dedup_key_prevents_duplicate_jobs(fresh_db):
    a = enqueue("SCAN", {}, trigger="SCHEDULED", dedup_key="preset:1:slot")
    b = enqueue("SCAN", {}, trigger="SCHEDULED", dedup_key="preset:1:slot")
    assert a[1] is True and b == (a[0], False)


def test_manual_jobs_run_first_but_scheduled_not_starved(fresh_db):
    old, _ = enqueue("SCAN", {}, trigger="SCHEDULED")
    with session_scope() as db:
        db.get(ScanJob, old).created_at = utcnow() - timedelta(hours=10)
    new, _ = enqueue("SCAN", {}, trigger="MANUAL")
    assert claim_next() == old  # waited 10h: ageing beats manual priority
    m2, _ = enqueue("SCAN", {}, trigger="MANUAL")
    s2, _ = enqueue("SCAN", {}, trigger="SCHEDULED")
    assert claim_next() == new


def test_restart_recovers_interrupted_job(fresh_db):
    jid, _ = enqueue("SCAN", {"markets": ["US"], "source_keys": ["demo_fixture"], "include_fixture": True})
    with session_scope() as db:
        j = db.get(ScanJob, jid)
        j.status, j.heartbeat_at = "RUNNING", utcnow() - timedelta(hours=1)
        db.add(ScanTask(job_id=jid, source_key="demo_fixture", market_code="US", work_key="demo_fixture|US", status="RUNNING"))
    assert recover_stale() == 1
    drain()
    with session_scope() as db:
        assert db.get(ScanJob, jid).status == "COMPLETED"
        assert db.scalar(select(func.count(ScanTask.id)).where(ScanTask.job_id == jid)) == 1  # checkpointed task re-used


def test_link_job_pause_resume_checkpoint(client, demo_loaded, monkeypatch):
    from app import jobs
    calls = []
    real = jobs.find_links

    def fake(db, pid, purchase_mode=False):
        calls.append(pid)
        if len(calls) == 2:
            db.get(ScanJob, jid_holder[0]).status = "PAUSE_REQUESTED"
        return real(db, pid, purchase_mode=purchase_mode, use_search=False, fetch_pages=False)
    monkeypatch.setattr(jobs, "find_links", fake)
    ids = [p["product_id"] for p in client.get("/api/research").json()["rows"]]
    ids = list(dict.fromkeys(ids))
    jid_holder = [client.post("/api/links/bulk", json={"mode": "selected", "product_ids": ids}).json()["job_id"]]
    drain()
    j = client.get(f"/api/jobs/{jid_holder[0]}").json()
    assert j["status"] == "PAUSED" and j["stats"]["done"] == 2
    client.post(f"/api/jobs/{jid_holder[0]}/resume")
    drain()
    j = client.get(f"/api/jobs/{jid_holder[0]}").json()
    assert j["status"] == "COMPLETED" and j["stats"]["done"] == len(ids)
    assert len(calls) == len(ids)  # nothing processed twice


def test_google_news_uses_topic_feeds_when_search_is_disallowed(fresh_db, monkeypatch):
    from app import jobs
    from app.models import Category
    monkeypatch.setattr(jobs, "_gnews_search_allowed", lambda: False)
    with session_scope() as db:
        cat_ids = [c.id for c in db.scalars(select(Category).where(Category.name.in_(["Smartphones", "Sneakers"])))]
    jid, _ = enqueue("SCAN", {"markets": ["US", "VN"], "category_ids": cat_ids, "source_keys": ["google_news"]})
    with session_scope() as db:
        tasks = jobs.plan_tasks(db, db.get(ScanJob, jid))
        qs = sorted({(t.market_code, t.query) for t in tasks})
    # one task per market x topic instead of one search per category; search URLs are never requested
    assert qs == sorted({(m, f"topic:{t}") for m in ("US", "VN") for t in ("TECHNOLOGY", "BUSINESS", "ENTERTAINMENT")})
