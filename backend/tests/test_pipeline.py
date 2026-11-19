from sqlalchemy import func, select

from app.adapters.base import RawItem
from app.db import session_scope
from app.jobs import drain, enqueue, expand_categories
from app.models import (
    Category, ChangeEvent, Evidence, Product, ProductCategory, ReleaseHistory, ScanJob, ScanPreset, Source, UpcomingRelease,
)
from app.pipeline.ingest import IngestStats, ScopeContext, ingest_items


def _src(db, key="sneakernews"):
    return db.scalar(select(Source).where(Source.key == key))


def _ingest(db, items, cat_names=None, **kw):
    cats = list(db.scalars(select(Category))) if not cat_names else expand_categories(
        db, [c.id for c in db.scalars(select(Category).where(Category.name.in_(cat_names)))], [])
    sc = ScopeContext(categories=cats, include_keywords=kw.get("include", []), exclude_keywords=kw.get("exclude", []),
                      tracking_only=kw.get("tracking", False))
    return ingest_items(db, _src(db), items, sc, IngestStats())


def test_demo_scan_end_to_end_flags_fixtures(demo_loaded):
    with session_scope() as db:
        j = db.get(ScanJob, demo_loaded)
        assert j.status == "COMPLETED" and j.stats["products_new"] >= 5
        assert db.scalar(select(func.count(Product.id)).where(Product.is_fixture.is_(False))) == 0
        assert db.scalar(select(func.count(Evidence.id)).where(Evidence.is_fixture.is_(False))) == 0


def test_overlapping_categories_do_not_duplicate_products(fresh_db):
    with session_scope() as db:
        items = [RawItem(url="https://sn.example/1", title='Nike Air Max 1 "Big Bubble" sneaker DQ3989-100 releases March 26, 2027',
                         market_code="US", outlet="Sneaker News")]
        _ingest(db, items, ["Sneakers", "Nike"])
        _ingest(db, items, ["Nike"])
        assert db.scalar(select(func.count(Product.id))) == 1
        assert db.scalar(select(func.count(Evidence.id))) == 1
        pc = db.scalar(select(func.count()).select_from(ProductCategory))
        assert pc >= 1


def test_scope_and_exclude_keywords(fresh_db):
    with session_scope() as db:
        items = [RawItem(url="https://e/1", title="Sony WH-1000XM6 headphones review", market_code="US", outlet="E"),
                 RawItem(url="https://e/2", title="Nike Dunk Low Panda sneaker restock", market_code="US", outlet="E")]
        st = _ingest(db, items, ["Headphones & Earbuds"])
        assert [p.name for p in db.scalars(select(Product))] == ["Sony WH-1000XM6"]
        st = _ingest(db, [RawItem(url="https://e/3", title="Sony WH-1000XM6 headphones deal", market_code="US", outlet="E")],
                     ["Headphones & Earbuds"], exclude=["deal"])
        assert st.skipped_out_of_scope == 1


def test_tracking_mode_never_creates_products(fresh_db):
    with session_scope() as db:
        _ingest(db, [RawItem(url="https://e/9", title="Sony WH-1000XM6 headphones review", market_code="US", outlet="E")], tracking=True)
        assert db.scalar(select(func.count(Product.id))) == 0


def test_rumor_to_confirmed_to_delay_history(fresh_db):
    with session_scope() as db:
        mk = lambda i, t: RawItem(url=f"https://t/{i}", title=t, market_code="US", outlet=f"O{i}")
        _ingest(db, [mk(1, "Apple iPhone 18 Pro smartphone rumored to launch in Q3 2027")])
        rel = db.scalar(select(UpcomingRelease))
        assert rel.release_status == "RUMORED" and rel.date_precision == "QUARTER"
        _ingest(db, [mk(2, "Apple iPhone 18 Pro smartphone officially announced, releases September 18, 2027")])
        _ingest(db, [mk(3, "Apple iPhone 18 Pro smartphone rumored to slip")])  # weaker rumor must not downgrade
        _ingest(db, [mk(4, "Apple iPhone 18 Pro smartphone delayed, new release date October 2, 2027")])
        rel = db.scalar(select(UpcomingRelease))
        assert rel.release_status == "DELAYED" and rel.expected_date_text == "2027-10-02"
        hist = [(h.field, h.old_value, h.new_value) for h in db.scalars(select(ReleaseHistory).order_by(ReleaseHistory.id))]
        assert ("release_status", "RUMORED", "OFFICIALLY CONFIRMED") in hist
        assert ("release_status", "OFFICIALLY CONFIRMED", "DELAYED") in hist
        types = {e.event_type for e in db.scalars(select(ChangeEvent))}
        assert {"NEW_RUMOR", "RUMOR_CONFIRMED", "RELEASE_DELAYED", "RELEASE_DATE_REVISED"} <= types


def test_deleting_preset_keeps_products_and_history(client, demo_loaded):
    pid = client.get("/api/presets").json()[0]["id"]
    before = client.get("/api/research").json()["rows"]
    assert client.delete(f"/api/presets/{pid}").json() == {"deleted": True}
    assert len(client.get("/api/research").json()["rows"]) == len(before)
    assert all(p["id"] != pid for p in client.get("/api/presets").json())


def test_table_filter_does_not_start_scan(client, demo_loaded):
    n = len(client.get("/api/jobs").json())
    client.get("/api/research", params={"categories": "1,2", "markets": "US"})
    assert len(client.get("/api/jobs").json()) == n


def test_custom_industry_category_and_multi_selection(client):
    ind = client.post("/api/industries", json={"name": "Garden Tools"}).json()
    cat = client.post("/api/categories", json={"industry_id": ind["id"], "name": "Robot Mowers", "keywords": ["robot mower"],
                                               "local_keywords": {"vi": ["máy cắt cỏ robot"]}}).json()
    sub = client.post("/api/categories", json={"industry_id": ind["id"], "parent_id": cat["id"], "name": "Husqvarna", "brands": ["Husqvarna"]}).json()
    tree = client.get("/api/taxonomy").json()
    g = next(i for i in tree if i["name"] == "Garden Tools")
    assert g["categories"][0]["children"][0]["name"] == "Husqvarna"
    p = client.post("/api/presets", json={"name": "Mowers VN+US", "markets": ["VN", "US"], "category_ids": [cat["id"]],
                                           "priority": "P2"}).json()
    assert p["markets"] == ["VN", "US"] and p["priority"] == "P2"
    # renaming a category keeps its id and associations
    assert client.put(f"/api/categories/{sub['id']}", json={"name": "Husqvarna Automower"}).json()["id"] == sub["id"]
