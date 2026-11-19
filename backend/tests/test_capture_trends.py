from datetime import date, timedelta

from sqlalchemy import select

from app.db import session_scope, utcnow
from app.models import Brand, Evidence, Product, Setting, Source
from app.pipeline.manual import handle_of, parse_engagement, platform_of
from app.pipeline.trends import parse_trends_csv

OLD_FMT = "Category: All categories\n\nWeek,labubu: (Vietnam),nike dunk: (Vietnam)\n" + "\n".join(
    f"{(date(2026, 8, 2) + timedelta(weeks=i)).isoformat()},{v},{'<1' if i == 0 else 3}" for i, v in enumerate([10, 12, 15, 20, 30, 45, 60, 80]))
NEW_FMT = '"Time","Labubu"\n' + "\n".join(f'"{(date(2026, 11, 1) + timedelta(days=i)).isoformat()}","{v}"' for i, v in enumerate(range(10, 60, 3)))


def test_engagement_platform_and_handle_parsing():
    assert parse_engagement("1,234 likes, 56 comments - nike on Nov 3") == {"likes": 1234, "comments": 56}
    assert parse_engagement("Video 2.5M views 120K likes") == {"views": 2_500_000, "likes": 120_000}
    assert parse_engagement("12 N lượt thích") == {}
    assert platform_of("https://www.tiktok.com/@kicks.vn/video/1")[1] == "SOCIAL"
    assert platform_of("https://shopee.vn/abc-i.1.2")[1] == "RETAIL"
    assert handle_of("https://www.tiktok.com/@kicks.vn/video/1") == "@kicks.vn"
    assert handle_of("https://x.com/sneakernews/status/123") == "@sneakernews"
    assert handle_of("https://www.instagram.com/p/AbC/", "Kicks VN (@kicksvn) • Instagram") == "@kicksvn"


def test_trends_csv_both_formats():
    a = parse_trends_csv(OLD_FMT)
    assert a.granularity == "WEEK" and [s.term for s in a.series] == ["labubu", "nike dunk"]
    assert a.series[0].geo_label == "Vietnam" and a.series[1].points[0][1] == 0.5
    b = parse_trends_csv(NEW_FMT)
    assert b.granularity == "DAY" and b.series[0].term == "Labubu" and b.series[0].geo_label is None


def test_capture_creates_social_evidence_and_rescoring(client):
    items = [{"url": f"https://www.tiktok.com/@creator{i}/video/{i}", "market_code": "VN", "title": "Labubu Big Into Energy unboxing",
              "product_name": "POP MART Labubu Big Into Energy", "likes": 1000 * (i + 1), "views": 20000 * (i + 1)} for i in range(3)]
    items.append({"url": "https://www.instagram.com/p/xyz/", "market_code": "VN", "title": ""})  # no caption, no product
    r = client.post("/api/capture", json=items).json()
    assert r["saved"] == 3
    assert r["results"][3]["status"] == "NEED_TITLE"
    with session_scope() as db:
        p = db.scalar(select(Product).where(Product.name.like("%Labubu%")))
        assert p.brand == "Pop Mart" and not p.is_fixture
        evs = list(db.scalars(select(Evidence).where(Evidence.product_id == p.id)))
        assert {e.outlet for e in evs} == {"TikTok:@creator0", "TikTok:@creator1", "TikTok:@creator2"}
        assert all(e.source_type == "SOCIAL" and e.engagement.get("likes") for e in evs)
    row = next(x for x in client.get("/api/research").json()["rows"] if "Labubu" in x["product_name"])
    assert row["country"] == "Vietnam" and "TikTok" in row["source_platforms"]
    # duplicate capture updates instead of double counting
    r2 = client.post("/api/capture", json=items[:1]).json()
    assert r2["results"][0]["status"] == "DUPLICATE_UPDATED"


def test_trends_import_feeds_search_component(client):
    client.post("/api/capture", json=[{"url": "https://news.example/labubu", "market_code": "VN", "title": "POP MART Labubu Big Into Energy restock"}])
    today = utcnow().date()
    csv_text = "Week,labubu: (Vietnam)\n" + "\n".join(f"{(today - timedelta(weeks=7 - i)).isoformat()},{v}" for i, v in enumerate([10, 12, 15, 20, 30, 45, 60, 80]))
    pv = client.post("/api/trends/preview", json={"csv": csv_text}).json()
    s = pv["series"][0]
    assert s["market_guess"] == "VN" and s["suggestions"], pv
    pid = s["suggestions"][0]["product_id"]
    r = client.post("/api/trends/import", json={"csv": csv_text, "mapping": [{"term": "labubu", "product_id": pid, "market_code": "VN"}]}).json()
    assert r["points"] == 8
    with session_scope() as db:
        from app.models import ProductMarketTrend
        t = db.scalar(select(ProductMarketTrend).where(ProductMarketTrend.product_id == pid, ProductMarketTrend.market_code == "VN"))
        assert t.breakdown["search"] is not None and t.breakdown["search_growth_raw"] > 1
        assert "Google Trends import" in t.explanation


def test_stale_trends_are_ignored(client):
    client.post("/api/capture", json=[{"url": "https://news.example/x", "market_code": "US", "title": "Sony WH-1000XM6 headphones review"}])
    pid = client.get("/api/products-lookup", params={"q": "WH-1000XM6"}).json()[0]["product_id"]
    old = "Week,wh1000xm6: (United States)\n2024-01-07,50\n2024-01-14,60\n"
    client.post("/api/trends/import", json={"csv": old, "mapping": [{"term": "wh1000xm6", "product_id": pid, "market_code": "US"}]})
    t = next(x for x in client.get(f"/api/products/{pid}").json()["trends"] if x["market_code"] == "US")
    assert t["breakdown"]["search"] is None and "stale" in t["explanation"]


def test_seed_upgrade_adds_aliases_and_sources_once(fresh_db):
    with session_scope() as db:
        apple = db.scalar(select(Brand).where(Brand.name == "Apple"))
        assert "iPhone" in apple.aliases
        assert db.scalar(select(Source).where(Source.key == "manual_capture")).adapter == "manual"
        assert db.scalar(select(Source).where(Source.key == "google_trends")).status == "MANUAL_IMPORT"
        assert db.get(Setting, "seed.version").value == 5
        apple.aliases = ["iPhone"]  # user edits are kept on later starts
    from app.seed import seed
    with session_scope() as db:
        seed(db)
        assert db.scalar(select(Brand).where(Brand.name == "Apple")).aliases == ["iPhone"]


def test_vietnamese_and_ambiguous_brand_headlines():
    from datetime import datetime
    from app.pipeline.extract import BrandEntry, extract_mentions
    from app.seed import BRANDS, EXTRA_ALIASES
    B = [BrandEntry(n, a + EXTRA_ALIASES.get(n, [])) for n, a, _, _ in BRANDS]
    m = extract_mentions("iPhone 18 Pro Max lộ diện với camera mới", "", B, datetime(2026, 11, 1))
    assert m and m[0].brand == "Apple" and m[0].name == "iPhone 18 Pro Max"
    assert extract_mentions("Google Play Console adds new policy", "", B) == []
    m = extract_mentions("Nike Air Force 1 Low Plus Apparel Merch drop", "", B)
    assert m[0].name == "Nike Air Force 1 Low Plus"


def test_saved_trends_term_maps_import_automatically(client):
    client.post("/api/capture", json=[{"url": "https://news.example/s", "market_code": "US", "title": "adidas Samba OG \"Cream White\" IE3439 restock"}])
    pid = client.get("/api/products-lookup", params={"q": "Samba"}).json()[0]["product_id"]
    client.put(f"/api/products/{pid}/trends-term", json={"term": "samba og"})
    assert next(r for r in client.get("/api/research").json()["rows"] if r["product_id"] == pid)["trends_term"] == "samba og"
    pv = client.post("/api/trends/preview", json={"csv": "Week,samba og: (United States)\n2026-11-01,40\n2026-11-08,50\n"}).json()
    assert pv["series"][0]["suggestions"][0] == {"product_id": pid, "name": client.get(f"/api/products/{pid}").json()["product"]["name"], "score": 100}
