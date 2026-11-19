"""Adapter parsing tests use small *recorded-format* samples (synthetic content, real feed structure)."""
from types import SimpleNamespace

from app.adapters.base import FetchCtx
from app.adapters.rss import parse_feed
from app.jobs import build_query

PUBLISHER = """<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Sample</title>
<item><title>Air Jordan 1 High OG "Example" DZ5485-612 Release Date</title><link>https://publisher.example/aj1-example</link>
<pubDate>Tue, 17 Nov 2026 14:00:00 +0000</pubDate><description><![CDATA[<p>Releasing December 5 for $180.</p>]]></description>
<media:content url="https://publisher.example/img/aj1.jpg" medium="image"/></item></channel></rss>"""

GNEWS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Google News</title>
<item><title>Sony WH-1000XM6 review - Example Outlet</title><link>https://news.google.com/rss/articles/CBMiExample?oc=5</link>
<pubDate>Mon, 16 Nov 2026 09:00:00 GMT</pubDate><source url="https://outlet.example">Example Outlet</source></item></channel></rss>"""


def _src(**kw):
    d = dict(key="s", name="Sample", platform="Sample", source_type="EDITORIAL", markets=["US"])
    d.update(kw)
    return SimpleNamespace(**d)


def test_publisher_feed_keeps_original_url_date_and_image():
    items = parse_feed(PUBLISHER, source=_src(), ctx=FetchCtx("US", ["en"], None, None))
    it = items[0]
    assert it.url == "https://publisher.example/aj1-example" and not it.url_is_aggregator
    assert it.published_at.isoformat() == "2026-11-17T14:00:00"
    assert it.image_url == "https://publisher.example/img/aj1.jpg" and it.market_code == "US"


def test_google_news_items_are_flagged_as_aggregator_and_attributed_to_outlet():
    items = parse_feed(GNEWS, source=_src(key="google_news", markets=[]), ctx=FetchCtx("JP", ["ja"], "x", "ja|JP|JP:ja"), aggregator=True)
    it = items[0]
    assert it.url_is_aggregator and it.outlet == "Example Outlet"
    assert it.title == "Sony WH-1000XM6 review"  # " - Outlet" suffix removed
    assert it.market_code == "JP"


def test_query_builder_includes_local_terms_and_exclusions():
    q = build_query(["sneaker", "Air Jordan", "スニーカー"], ["retro"], ["fake", "two words"])
    assert q == '(sneaker OR "Air Jordan" OR スニーカー) retro -fake when:30d'


def test_real_sneakernews_feed_titles_and_tags(fresh_db):
    """Trimmed copy (titles, links, category tags only) of the real Sneaker News feed of 2026-11-18."""
    from pathlib import Path
    from sqlalchemy import select
    from app.db import session_scope
    from app.models import Category, Product, Source
    from app.pipeline.ingest import IngestStats, ScopeContext, ingest_items
    body = (Path(__file__).parent / "sneakernews_feed_sample.xml").read_text(encoding="utf-8")
    with session_scope() as db:
        src = db.scalar(select(Source).where(Source.key == "sneakernews"))
        items = parse_feed(body, source=src, ctx=FetchCtx("US", ["en"], None, None))
        assert len(items) == 7 and "Nike Air Force 1 Low" in items[5].tags
        cats = list(db.scalars(select(Category)))
        st = ingest_items(db, src, items, ScopeContext(categories=cats, include_keywords=[], exclude_keywords=[]), IngestStats())
        names = {p.name for p in db.scalars(select(Product))}
    assert {"Air Jordan 1", "Nike Air Force 1 Low", "Nike Kobe 6", "Nike Kobe 11"} <= names
    assert not any(w in n for n in names for w in ("Becomes", "Street", "Retros"))
    assert len(names) >= 13


def test_wordpress_feed_paging_stops_at_last_page(monkeypatch):
    from app.adapters import rss
    from app.adapters.base import SourceError
    def page(n):
        return ('<?xml version="1.0"?><rss version="2.0"><channel>' +
                "".join(f"<item><title>Nike Dunk Low {n}{i}</title><link>https://x.example/{n}/{i}</link></item>" for i in range(3)) +
                "</channel></rss>")
    calls = []
    def fake_get(url, **kw):
        calls.append(url)
        if url.endswith("/feed/") or url.endswith("rss.xml"):
            return page(1), False
        if url.endswith("paged=2"):
            return page(2), False
        raise SourceError("ERROR", "HTTP 404")
    monkeypatch.setattr(rss, "http_get", fake_get)
    src = _src(url="https://x.example/feed/", rate_per_minute=60)
    out = rss.RssAdapter().fetch(src, FetchCtx("US", ["en"], None, None, pages=5))
    assert len(out.items) == 6 and calls[-1].endswith("paged=3")  # stopped after the 404, kept pages 1-2
    calls.clear()
    out = rss.RssAdapter().fetch(_src(url="https://x.example/rss.xml", rate_per_minute=60), FetchCtx("US", ["en"], None, None, pages=5))
    assert len(calls) == 1  # non-WordPress feeds are read once


def test_release_calendar_page_becomes_upcoming_releases(fresh_db, monkeypatch):
    """Sneaker Bar Detroit style release-date page (no feed): name + Color / Style Code / Release Date / Price."""
    from datetime import datetime
    from pathlib import Path
    from sqlalchemy import select
    from app.adapters import calendar_page
    from app.adapters.rss import get_adapter
    from app.db import session_scope
    from app.models import Category, Product, Source, UpcomingRelease
    from app.pipeline.ingest import IngestStats, ScopeContext, ingest_items
    html = (Path(__file__).parent / "sbd_calendar_sample.html").read_text(encoding="utf-8")
    monkeypatch.setattr(calendar_page, "http_get", lambda url, **kw: (html, False))
    monkeypatch.setattr(calendar_page, "utcnow", lambda: datetime(2026, 11, 1))
    with session_scope() as db:
        src = db.scalar(select(Source).where(Source.key == "sbd_jordan_calendar"))
        assert src is not None and src.adapter == "release_calendar"
        items = get_adapter(src.adapter).fetch(src, FetchCtx("US", ["en"], None, None)).items
        assert [i.title for i in items][:2] == ['Air Jordan 11 MCS Cleat "Space Jam"', 'Air Jordan 6 OG "White Infrared"']
        assert len(items) == 5  # script/footer "Release Date:" noise ignored
        assert items[1].url == "https://sneakerbardetroit.com/air-jordan-6-white-infrared/"
        assert "Februray" not in items[3].summary and "at TBA" not in items[3].summary
        cats = list(db.scalars(select(Category)))
        ingest_items(db, src, items, ScopeContext(categories=cats, include_keywords=[], exclude_keywords=[]), IngestStats())
        prods = {p.sku: p for p in db.scalars(select(Product))}
        assert {"JA7792-400", "CT8529-105", "IZ1694-600", "FV5029-141", "DZ5485-612"} <= set(prods)
        rels = {r.product_id: r for r in db.scalars(select(UpcomingRelease))}
        r6 = rels[prods["CT8529-105"].id]
        assert r6.release_status == "REPORTED / EXPECTED"  # a calendar entry is not an official confirmation
        assert r6.expected_date_text == "2026-11-07" and r6.expected_price == 215
        assert rels[prods["DZ5485-612"].id].date_precision == "SEASON"


def test_new_sneaker_channels_are_seeded(fresh_db):
    from sqlalchemy import select
    from app.db import session_scope
    from app.models import Source
    with session_scope() as db:
        keys = {s.key for s in db.scalars(select(Source))}
    assert {"sneakerbardetroit", "justfreshkicks", "houseofheat", "complex_sneakers", "hypebeast_footwear",
            "sbd_jordan_calendar", "sbd_sneaker_calendar"} <= keys
