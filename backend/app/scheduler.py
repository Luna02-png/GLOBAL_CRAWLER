"""P1 Daily / P2 Weekly / P3 On-Demand scheduling in Asia/Ho_Chi_Minh.

A single 'tick' finds, for every enabled P1/P2 preset, the most recent scheduled slot that has passed.
If no job exists for that slot it enqueues exactly one job (dedup_key = preset+slot, UNIQUE in the DB).
Because only the *latest* slot is considered, a restart after downtime produces one controlled catch-up
scan, never a backlog. P3 presets are never scheduled. Manual scans never modify presets."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import config
from .db import session_scope, utcnow
from .jobs import enqueue, preset_scope
from .models import ScanPreset

log = logging.getLogger("gpti.scheduler")


def tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def _parse_hm(s: str) -> time:
    try:
        h, m = (int(x) for x in (s or "07:00").split(":"))
        return time(h, m)
    except ValueError:
        return time(7, 0)


def latest_slot(p: ScanPreset, now_local: datetime) -> Optional[datetime]:
    """Most recent scheduled local datetime <= now for this preset, or None for P3."""
    if p.priority == "P3":
        return None
    t = _parse_hm(p.schedule_time)
    cand = now_local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if p.priority == "P1":
        return cand if cand <= now_local else cand - timedelta(days=1)
    if p.priority == "P2":
        wd = p.schedule_weekday if p.schedule_weekday is not None else 0
        cand = cand - timedelta(days=(cand.weekday() - wd) % 7)
        return cand if cand <= now_local else cand - timedelta(days=7)
    return None


def next_slot(p: ScanPreset, now_local: datetime) -> Optional[datetime]:
    last = latest_slot(p, now_local)
    if last is None:
        return None
    return last + (timedelta(days=1) if p.priority == "P1" else timedelta(days=7))


def to_utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def tick(now_utc: Optional[datetime] = None) -> list[int]:
    now_utc = now_utc or utcnow()
    now_local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz())
    created: list[int] = []
    with session_scope() as db:
        presets = list(db.scalars(select(ScanPreset).where(ScanPreset.enabled.is_(True), ScanPreset.deleted.is_(False))))
        for p in presets:
            nxt = next_slot(p, now_local)
            p.next_run_at = to_utc_naive(nxt) if nxt else None
            slot = latest_slot(p, now_local)
            if slot is None:
                continue
            slot_utc = to_utc_naive(slot)
            if slot_utc < (p.schedule_anchor_at or p.created_at):
                continue  # preset (or its priority/time) changed after this slot: wait for the next one
            late = now_utc - slot_utc > timedelta(minutes=20)
            jid, new = enqueue("SCAN", preset_scope(p), trigger="CATCHUP" if late else "SCHEDULED", preset=p,
                               mode=p.mode, depth=p.depth, dedup_key=f"preset:{p.id}:{slot.isoformat()}")
            if new:
                created.append(jid)
                log.info("enqueued %s job %s for preset %s slot %s", "catch-up" if late else "scheduled", jid, p.name, slot)
    return created


_scheduler = None


def start() -> None:
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    if _scheduler:
        return
    _scheduler = BackgroundScheduler(timezone=tz())
    _scheduler.add_job(tick, "interval", seconds=60, id="gpti-tick", max_instances=1, coalesce=True, next_run_time=datetime.now(tz()))
    _scheduler.start()


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
