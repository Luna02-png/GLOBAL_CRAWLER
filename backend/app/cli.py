"""Command line entry points.

  python -m app.cli serve            run API + UI + worker + scheduler (http://127.0.0.1:8765)
  python -m app.cli run-due          enqueue due P1/P2 scans (one catch-up max) and process the queue, then exit
                                     -> use this from Windows Task Scheduler at 07:00 if the server is not always running
  python -m app.cli scan --preset 3 [--full]   run one preset now (manual; preset is not modified)
  python -m app.cli demo             load clearly-labelled DEMO fixture data (never presented as live)
  python -m app.cli recompute        recompute all scores from stored observations
  python -m app.cli status           print queue / source status
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gpti")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default=os.environ.get("GPTI_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("GPTI_PORT", "8765")))
    sub.add_parser("run-due")
    sc = sub.add_parser("scan")
    sc.add_argument("--preset", type=int, required=True)
    sc.add_argument("--full", action="store_true")
    sub.add_parser("demo")
    sub.add_parser("recompute")
    sub.add_parser("status")
    sub.add_parser("init")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("app.main:app", host=a.host, port=a.port, log_level="info")
        return 0

    from .main import init_db
    init_db()
    from .db import session_scope
    from .jobs import drain, enqueue, preset_scope, recover_stale
    from .models import ScanJob, ScanPreset, Source
    from sqlalchemy import select

    if a.cmd == "init":
        print("database ready")
    elif a.cmd == "run-due":
        from .scheduler import tick
        recover_stale()
        created = tick()
        print(f"enqueued {len(created)} scheduled job(s): {created}")
        n = drain()
        print(f"processed {n} job(s)")
    elif a.cmd == "scan":
        with session_scope() as db:
            p = db.get(ScanPreset, a.preset)
            if p is None:
                print("preset not found"); return 1
            jid, _ = enqueue("SCAN", preset_scope(p), trigger="MANUAL", preset=p, mode=p.mode, depth="FULL" if a.full else "QUICK")
        drain()
        with session_scope() as db:
            j = db.get(ScanJob, jid)
            print(j.status, j.stats)
    elif a.cmd == "demo":
        jid, _ = enqueue("SCAN", {"markets": ["US", "JP", "KR", "VN", "GB"], "source_keys": ["demo_fixture"], "include_fixture": True})
        drain()
        print("DEMO fixture data loaded (flagged is_fixture=true; hide it with the 'Hide demo data' toggle).")
    elif a.cmd == "recompute":
        from .scoring.engine import recompute_all
        with session_scope() as db:
            print("rows:", recompute_all(db))
    elif a.cmd == "status":
        with session_scope() as db:
            for s in db.scalars(select(Source).order_by(Source.key)):
                print(f"{s.key:18} {'on ' if s.enabled else 'off'} {s.status:15} {s.last_error or ''}"[:160])
            for j in db.scalars(select(ScanJob).order_by(ScanJob.id.desc()).limit(10)):
                print(j.id, j.kind, j.trigger, j.status, j.preset_name, j.created_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
