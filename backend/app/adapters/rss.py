from __future__ import annotations

import calendar
import re
import json
import os
from datetime import datetime, timedelta, timezone

from ..db import utcnow as _utcnow
from pathlib import Path
from typing import Optional

import feedparser

from .base import Adapter, FetchCtx, FetchOutput, RawItem, SourceError, http_get


def _dt(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), timezone.utc).replace(tzinfo=None)
    return None


def _image(entry) -> Optional[str]:
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            u = m.get("url")
            if u and u.startswith("http"):
                return u
    for l in entry.get("links") or []:
        if l.get("type", "").startswith("image/") and l.get("href", "").startswith("http"):
            return l["href"]
    return None


def parse_feed(body: str, *, source, ctx: FetchCtx, aggregator: bool = False) -> list[RawItem]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise SourceError("ERROR", f"unparseable feed: {feed.get('bozo_exception')}")
    items: list[RawItem] = []
    default_market = (source.markets[0] if source.markets else None)
    for e in feed.entries[: ctx.max_results]:
        url = e.get("link")
        title = e.get("title") or ""
        if not url or not title:
            continue
        outlet = source.platform or source.name
        if aggregator:
            src = e.get("source") or {}
            outlet = (src.get("title") if isinstance(src, dict) else None) or outlet
            if outlet and title.endswith(" - " + outlet):
                title = title[: -(len(outlet) + 3)]
        items.append(RawItem(
            url=url, title=title, summary=e.get("summary") or "", published_at=_dt(e),
            author=e.get("author"), outlet=outlet, lang=(ctx.languages[0] if ctx.languages else None),
            market_code=ctx.market_code if aggregator else default_market, platform=source.platform,
            source_type=source.source_type, url_is_aggregator=aggregator, image_url=_image(e),
            tags=[t.get("term") for t in (e.get("tags") or []) if t.get("term")][:30],
        ))
    return items


class RssAdapter(Adapter):
    name = "rss"

    def check_configured(self, source):
        if not source.url:
            raise SourceError("NOT_CONFIGURED", "feed URL missing")

    def fetch(self, source, ctx: FetchCtx) -> FetchOutput:
        body, cached = http_get(source.url, rate_key=source.key, per_minute=source.rate_per_minute, use_cache=ctx.use_cache)
        items = parse_feed(body, source=source, ctx=ctx)
        # Most publisher feeds only list the latest ~10 posts. WordPress feeds expose older pages via ?paged=N.
        if ctx.pages > 1 and re.search(r"/feed/?$", (source.url or "").split("?")[0]):
            seen = {i.url for i in items}
            for page in range(2, ctx.pages + 1):
                sep = "&" if "?" in source.url else "?"
                try:
                    pb, _ = http_get(f"{source.url}{sep}paged={page}", rate_key=source.key, per_minute=source.rate_per_minute,
                                     use_cache=ctx.use_cache)
                    more = [i for i in parse_feed(pb, source=source, ctx=ctx) if i.url not in seen]
                except SourceError:
                    break  # e.g. 404 after the last page - keep what we have
                if not more:
                    break
                seen.update(i.url for i in more)
                items.extend(more)
        return FetchOutput(items, from_cache=cached)


class GoogleNewsAdapter(Adapter):
    """Google News public RSS search, localized per market (hl/gl/ceid)."""
    name = "google_news"

    @property
    def per_query(self) -> bool:
        return True

    def fetch(self, source, ctx: FetchCtx) -> FetchOutput:
        if not ctx.google_news_locale:
            raise SourceError("NOT_CONFIGURED", f"no Google News edition configured for market {ctx.market_code}")
        hl, gl, ceid = ctx.google_news_locale.split("|")
        if (ctx.query or "").startswith("topic:"):
            # section headline feed (used when robots.txt disallows the search feed)
            topic = ctx.query.split(":", 1)[1]
            body, cached = http_get(f"https://news.google.com/rss/headlines/section/topic/{topic}", params={"hl": hl, "gl": gl, "ceid": ceid},
                                    rate_key=source.key, per_minute=source.rate_per_minute, use_cache=ctx.use_cache)
            return FetchOutput(parse_feed(body, source=source, ctx=ctx, aggregator=True), from_cache=cached)
        params = {"q": ctx.query or "", "hl": hl, "gl": gl, "ceid": ceid}
        body, cached = http_get(source.url or "https://news.google.com/rss/search", params=params, rate_key=source.key,
                                per_minute=source.rate_per_minute, use_cache=ctx.use_cache)
        return FetchOutput(parse_feed(body, source=source, ctx=ctx, aggregator=True), from_cache=cached)


class YouTubeAdapter(Adapter):
    """Official YouTube Data API v3 (needs YOUTUBE_API_KEY)."""
    name = "youtube"

    @property
    def per_query(self) -> bool:
        return True

    def check_configured(self, source):
        if not os.environ.get(source.credential_env or "YOUTUBE_API_KEY"):
            raise SourceError("NOT_CONFIGURED", "YOUTUBE_API_KEY not set in .env")

    def fetch(self, source, ctx: FetchCtx) -> FetchOutput:
        self.check_configured(source)
        key = os.environ[source.credential_env or "YOUTUBE_API_KEY"]
        after = (_utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {"part": "snippet", "q": ctx.query or "", "type": "video", "maxResults": min(ctx.max_results, 25),
                  "order": "date", "publishedAfter": after, "key": key}
        if ctx.market_code and len(ctx.market_code) == 2 and ctx.market_code != "GLOBAL":
            params["regionCode"] = ctx.market_code
        if ctx.languages:
            params["relevanceLanguage"] = ctx.languages[0]
        body, cached = http_get(source.url, params=params, rate_key=source.key, per_minute=source.rate_per_minute,
                                use_cache=ctx.use_cache, check_robots=False)
        data = json.loads(body)
        if "error" in data:
            raise SourceError("AUTH_REQUIRED" if data["error"].get("code") in (401, 403) else "ERROR", str(data["error"].get("message")))
        ids = [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]
        stats: dict[str, dict] = {}
        if ids:
            sbody, _ = http_get("https://www.googleapis.com/youtube/v3/videos",
                                params={"part": "statistics", "id": ",".join(ids), "key": key}, rate_key=source.key,
                                per_minute=source.rate_per_minute, use_cache=ctx.use_cache, check_robots=False)
            for v in json.loads(sbody).get("items", []):
                st = v.get("statistics", {})
                stats[v["id"]] = {k: int(st[s]) for k, s in (("views", "viewCount"), ("likes", "likeCount"), ("comments", "commentCount")) if s in st}
        items = []
        for i in data.get("items", []):
            vid = i.get("id", {}).get("videoId")
            sn = i.get("snippet", {})
            if not vid:
                continue
            pub = sn.get("publishedAt")
            items.append(RawItem(url=f"https://www.youtube.com/watch?v={vid}", title=sn.get("title", ""), summary=sn.get("description", ""),
                                 published_at=datetime.strptime(pub, "%Y-%m-%dT%H:%M:%SZ") if pub else None,
                                 author=sn.get("channelTitle"), outlet=f"youtube:{sn.get('channelId')}", lang=(ctx.languages or [None])[0],
                                 market_code=ctx.market_code, platform="YouTube", source_type="SOCIAL", engagement=stats.get(vid, {})))
        return FetchOutput(items, from_cache=cached)


class FixtureAdapter(Adapter):
    """Synthetic DEMO data for tests and UI preview. Never presented as live findings."""
    name = "fixture"
    path = Path(__file__).resolve().parent.parent / "fixtures" / "demo_items.json"

    @property
    def per_query(self) -> bool:
        return True

    def fetch(self, source, ctx: FetchCtx) -> FetchOutput:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        items = []
        now = _utcnow()
        for d in data:
            if ctx.market_code and d.get("market") not in (ctx.market_code, None):
                continue
            items.append(RawItem(url=d["url"], title=d["title"], summary=d.get("summary", ""),
                                 published_at=now - timedelta(days=d.get("days_ago", 0), hours=d.get("hours_ago", 0)),
                                 outlet=d.get("outlet"), lang=d.get("lang"), market_code=d.get("market"),
                                 platform="Fixture", source_type=d.get("source_type", "EDITORIAL"),
                                 engagement=d.get("engagement", {}), image_url=d.get("image_url"), is_fixture=True))
        return FetchOutput(items)


class UnsupportedAdapter(Adapter):
    name = "unsupported"

    def check_configured(self, source):
        raise SourceError("NOT_CONFIGURED", source.notes or "adapter requires credentials/approved API access")

    def fetch(self, source, ctx):
        self.check_configured(source)


from .calendar_page import CalendarPageAdapter  # noqa: E402

ADAPTERS = {a.name: a for a in (RssAdapter(), GoogleNewsAdapter(), YouTubeAdapter(), FixtureAdapter(), UnsupportedAdapter(),
                                 CalendarPageAdapter())}


def get_adapter(name: str) -> Adapter:
    return ADAPTERS.get(name, ADAPTERS["unsupported"])
