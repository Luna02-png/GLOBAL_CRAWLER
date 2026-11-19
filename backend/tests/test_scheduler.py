from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import session_scope
from app.models import ScanJob, ScanPreset
from app.scheduler import latest_slot, tick
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _p(**kw):
    d = dict(name="t", priority="P1", schedule_time="07:00", schedule_weekday=0, enabled=True)
    d.update(kw)
    return ScanPreset(**d)


def test_p1_daily_slot_is_0700_vietnam_time_including_weekends():
    sat = datetime(2026, 11, 21, 7, 5, tzinfo=VN)  # Saturday
    assert latest_slot(_p(), sat) == datetime(2026, 11, 21, 7, 0, tzinfo=VN)
    assert latest_slot(_p(), datetime(2026, 11, 21, 6, 59, tzinfo=VN)) == datetime(2026, 11, 20, 7, 0, tzinfo=VN)


def test_p2_weekly_monday_0700():
    wed = datetime(2026, 11, 18, 12, 0, tzinfo=VN)
    assert latest_slot(_p(priority="P2"), wed) == datetime(2026, 11, 16, 7, 0, tzinfo=VN)  # Monday


def test_p3_never_scheduled():
    assert latest_slot(_p(priority="P3"), datetime(2026, 11, 18, 7, 0, tzinfo=VN)) is None


def _utc(local):
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def test_tick_is_idempotent_and_catches_up_once(fresh_db):
    with session_scope() as db:
        for p in db.scalars(select(ScanPreset)):
            p.enabled = False
        db.add(_p(name="daily", schedule_anchor_at=_utc(datetime(2026, 11, 1, 0, 0, tzinfo=VN))))
        db.add(_p(name="ondemand", priority="P3", schedule_anchor_at=_utc(datetime(2026, 11, 1, tzinfo=VN))))
    # service was off for 5 days; restart at 10:00 -> exactly one catch-up job
    now = _utc(datetime(2026, 11, 18, 10, 0, tzinfo=VN))
    first = tick(now)
    second = tick(now + timedelta(minutes=1))
    assert len(first) == 1 and second == []
    with session_scope() as db:
        j = db.get(ScanJob, first[0])
        assert j.trigger == "CATCHUP" and j.preset_name == "daily"
        assert db.scalar(select(ScanJob).where(ScanJob.preset_name == "ondemand")) is None
    # next morning 07:00 -> a normal scheduled job
    nxt = tick(_utc(datetime(2026, 11, 19, 7, 0, 30, tzinfo=VN)))
    with session_scope() as db:
        assert db.get(ScanJob, nxt[0]).trigger == "SCHEDULED"


def test_new_preset_does_not_fire_for_past_slot(fresh_db):
    with session_scope() as db:
        for p in db.scalars(select(ScanPreset)):
            p.enabled = False
        db.add(_p(name="new", schedule_anchor_at=_utc(datetime(2026, 11, 18, 9, 0, tzinfo=VN))))
    assert tick(_utc(datetime(2026, 11, 18, 9, 30, tzinfo=VN))) == []
    assert len(tick(_utc(datetime(2026, 11, 19, 7, 1, tzinfo=VN)))) == 1


def test_manual_scan_does_not_modify_preset(client):
    p = client.get("/api/presets").json()[0]
    client.post("/api/scans", json={"preset_id": p["id"], "depth": "FULL"})
    after = next(x for x in client.get("/api/presets").json() if x["id"] == p["id"])
    assert (after["priority"], after["depth"], after["schedule_time"]) == (p["priority"], p["depth"], p["schedule_time"])
