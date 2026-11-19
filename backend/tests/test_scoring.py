from datetime import timedelta

from sqlalchemy import select

from app.db import session_scope, utcnow
from app.models import Evidence, Product, ProductMarket, ProductMarketTrend
from app.scoring.engine import compute_product_market, smoothed_growth, weighted


def test_missing_signals_are_excluded_not_zero():
    score, cov = weighted({"a": 0.8, "b": None}, {"a": 50, "b": 50})
    assert score == 80.0 and cov == 0.5
    assert weighted({"a": None}, {"a": 10}) == (None, 0.0)


def test_small_sample_growth_is_damped():
    assert smoothed_growth(6, 2) == 1.0  # not +200%
    assert smoothed_growth(0, 0) == 0.0


def _product(db, name="Nike Test 1"):
    p = Product(canonical_key=name, brand="Nike", name=name)
    db.add(p)
    db.flush()
    db.add(ProductMarket(product_id=p.id, market_code="US"))
    return p


def test_single_mention_is_insufficient_data(fresh_db):
    with session_scope() as db:
        p = _product(db)
        db.add(Evidence(product_id=p.id, source_key="x", source_type="EDITORIAL", outlet="A", url="https://a/1",
                        market_code="US", content_fingerprint="f1", published_at=utcnow()))
        db.flush()
        t = compute_product_market(db, p, "US")
        assert t.trend_status == "INSUFFICIENT DATA"
        assert t.lifecycle_stage == "NEW SIGNAL — INSUFFICIENT HISTORY" and t.early_score is None and t.early_provisional


def test_syndicated_copies_do_not_count(fresh_db):
    with session_scope() as db:
        p = _product(db)
        for i in range(5):
            db.add(Evidence(product_id=p.id, source_key="x", source_type="EDITORIAL", outlet=f"O{i}", url=f"https://a/{i}",
                            market_code="US", content_fingerprint="same", is_syndicated_copy=i > 0, published_at=utcnow()))
        db.flush()
        t = compute_product_market(db, p, "US")
        assert "from 1 independent sources" in t.explanation


def test_growth_requires_observation_window(fresh_db):
    with session_scope() as db:
        p = _product(db)
        for i in range(6):
            db.add(Evidence(product_id=p.id, source_key="x", source_type="EDITORIAL", outlet=f"O{i}", url=f"https://a/{i}",
                            market_code="US", content_fingerprint=f"f{i}", published_at=utcnow() - timedelta(days=i % 3)))
        db.flush()
        t = compute_product_market(db, p, "US")
        assert t.breakdown["velocity"] is None and "window" in t.explanation
