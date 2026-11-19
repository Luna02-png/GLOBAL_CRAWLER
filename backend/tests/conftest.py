import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("GPTI_DATA_DIR", tempfile.mkdtemp(prefix="gpti-test-"))
os.environ["GPTI_ENABLE_SCHEDULER"] = "0"
os.environ["GPTI_ENABLE_WORKER"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app import db as dbmod  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path):
    dbmod.configure(f"sqlite:///{(tmp_path / 't.sqlite3').as_posix()}")
    from app.main import init_db
    init_db()
    yield dbmod
    dbmod.engine.dispose()


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def demo_loaded(fresh_db):
    from app.jobs import drain, enqueue
    jid, _ = enqueue("SCAN", {"markets": ["US", "JP", "KR", "VN", "GB"], "source_keys": ["demo_fixture"], "include_fixture": True})
    drain()
    return jid
