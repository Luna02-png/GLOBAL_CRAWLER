"""Application configuration. Values come from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency). Existing env vars win."""
    for candidate in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
        if candidate.exists():
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


_load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("GPTI_DATA_DIR", BASE_DIR.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("GPTI_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'gpti.sqlite3').as_posix()}")
TIMEZONE = os.environ.get("GPTI_TIMEZONE", "Asia/Ho_Chi_Minh")
ENABLE_SCHEDULER = os.environ.get("GPTI_ENABLE_SCHEDULER", "1") == "1"
ENABLE_WORKER = os.environ.get("GPTI_ENABLE_WORKER", "1") == "1"
HTTP_TIMEOUT = float(os.environ.get("GPTI_HTTP_TIMEOUT", "20"))
USER_AGENT = os.environ.get(
    "GPTI_USER_AGENT",
    "Mozilla/5.0 (compatible; GlobalCrawler/0.9; personal RSS reader for product research; respects robots.txt)",
)
GLOBAL_CONCURRENCY = _int("GPTI_GLOBAL_CONCURRENCY", 4)
DEFAULT_SOURCE_RPM = _int("GPTI_DEFAULT_SOURCE_RPM", 20)
CACHE_TTL_SECONDS = _int("GPTI_CACHE_TTL_SECONDS", 1800)
MAX_RESULTS_PER_TASK = _int("GPTI_MAX_RESULTS_PER_TASK", 100)
STATIC_DIR = Path(os.environ.get("GPTI_STATIC_DIR", BASE_DIR / "static"))
