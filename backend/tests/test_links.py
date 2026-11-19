from sqlalchemy import select

from app.adapters import base
from app.db import session_scope
from app.models import Evidence, Product, ProductLink, ProductMarket
from app.pipeline import links as L

ARTICLE = """<html><head><title>Air Jordan 4 "Bred Reimagined" FV5029-006 Release Date</title>
<meta property="og:image" content="https://img.news.example/aj4-bred.jpg">
<meta name="description" content="The Air Jordan 4 Bred Reimagined swaps nubuck for full-grain leather and releases on February 17, 2024 for $215.">
</head><body><h1>Air Jordan 4 "Bred Reimagined"</h1><p>""" + ("Detailed history, materials, sizing and release info. " * 80) + """
Style code FV5029-006. Release date: February 17. Price $215.</p></body></html>"""
THIN_SHOP = """<html><head><title>Jordan 4 Retro Bred Reimagined | Shop</title>
<script type="application/ld+json">{"@type":"Product","name":"Jordan 4 Retro Bred Reimagined","sku":"FV5029-006",
"offers":{"@type":"Offer","price":"215.00","priceCurrency":"USD","availability":"https://schema.org/InStock"}}</script>
</head><body><h1>Jordan 4 Retro</h1><button>Add to cart</button></body></html>"""
WRONG = """<html><head><title>Air Jordan 4 "Military Black" DH6927-111</title></head><body><h1>Air Jordan 4 Military Black</h1>
<p>Style code DH6927-111</p></body></html>"""
PAGES = {"https://news.example/aj4-bred": ARTICLE, "https://www.footlocker.com/product/aj4": THIN_SHOP,
         "https://news.example/aj4-military": WRONG}


def _setup(db):
    p = Product(canonical_key="k", brand="Air Jordan", name="Air Jordan 4", model_variant="Bred Reimagined", sku="FV5029-006")
    db.add(p)
    db.flush()
    db.add(ProductMarket(product_id=p.id, market_code="US"))
    for u, t in (("https://news.example/aj4-bred", 'Air Jordan 4 "Bred Reimagined" FV5029-006'),
                 ("https://www.footlocker.com/product/aj4", "Jordan 4 Retro Bred Reimagined"),
                 ("https://news.example/aj4-military", 'Air Jordan 4 "Military Black"')):
        db.add(Evidence(product_id=p.id, source_key="x", source_type="EDITORIAL", outlet=u, url=u, title=t, market_code="US",
                        content_fingerprint=u))
    db.flush()
    return p


def test_article_beats_thin_shop_and_purchase_kept_separate(fresh_db, monkeypatch):
    monkeypatch.setattr(L, "http_get", lambda url, **kw: (PAGES[url], False))
    with session_scope() as db:
        p = _setup(db)
        r = L.find_links(db, p.id, use_search=False)
        assert r.status == "VERIFIED"
        assert r.primary_url == "https://news.example/aj4-bred"
        assert r.purchase_url == "https://www.footlocker.com/product/aj4"
        links = {l.url: l for l in db.scalars(select(ProductLink))}
        assert links["https://news.example/aj4-military"].identity_match == "REJECTED"
        assert links["https://www.footlocker.com/product/aj4"].page_type == "RETAIL_PRODUCT"
        assert links["https://www.footlocker.com/product/aj4"].price == 215.0
        assert not links["https://news.example/aj4-bred"].is_purchase_url
        assert db.get(Product, p.id).image_url == "https://img.news.example/aj4-bred.jpg"


def test_article_only_is_a_success_without_purchase_url(fresh_db, monkeypatch):
    monkeypatch.setattr(L, "http_get", lambda url, **kw: (PAGES[url], False))
    with session_scope() as db:
        p = _setup(db)
        db.query(Evidence).filter(Evidence.url.contains("footlocker")).delete()
        r = L.find_links(db, p.id, use_search=False)
        assert r.status == "VERIFIED" and r.purchase_url is None
        assert db.get(Product, p.id).link_status == "VERIFIED"


def test_blocked_pages_fall_back_to_title_match_honestly(fresh_db, monkeypatch):
    def blocked(url, **kw):
        raise base.SourceError("BLOCKED", "HTTP 403")
    monkeypatch.setattr(L, "http_get", blocked)
    with session_scope() as db:
        p = _setup(db)
        r = L.find_links(db, p.id, use_search=False)
        assert r.status == "TITLE_MATCH" and r.failures
        assert all(l.accessible is False for l in db.scalars(select(ProductLink)))


def test_user_can_override_primary(fresh_db, monkeypatch):
    monkeypatch.setattr(L, "http_get", lambda url, **kw: (PAGES[url], False))
    with session_scope() as db:
        p = _setup(db)
        L.find_links(db, p.id, use_search=False)
        shop = db.scalar(select(ProductLink).where(ProductLink.url.contains("footlocker")))
        L.set_primary(db, p.id, shop.id)
        r = L.find_links(db, p.id, use_search=False)
        assert r.primary_url == shop.url  # re-running does not override the user's choice


def test_single_product_lookup_does_not_touch_others(client, demo_loaded, monkeypatch):
    monkeypatch.setattr(L, "http_get", lambda url, **kw: (_ for _ in ()).throw(base.SourceError("ERROR", "offline")))
    rows = client.get("/api/research").json()["rows"]
    target = rows[0]["product_id"]
    before = {r["product_id"]: r["link_status"] for r in rows}
    with session_scope() as db:
        stamp = {p.id: p.link_checked_at for p in db.scalars(select(Product))}
    jobs_before = len(client.get("/api/jobs").json())
    client.post(f"/api/products/{target}/find-links")
    assert len(client.get("/api/jobs").json()) == jobs_before  # no scan job was created
    with session_scope() as db:
        for p in db.scalars(select(Product)):
            if p.id != target:
                assert p.link_checked_at == stamp[p.id]
