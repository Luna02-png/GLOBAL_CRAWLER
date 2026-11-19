"""Run Alembic migrations programmatically. Never drops or resets an existing database."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from . import db as dbmod

BACKEND = Path(__file__).resolve().parent.parent


def _cfg() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


def upgrade() -> None:
    cfg = _cfg()
    with dbmod.engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
