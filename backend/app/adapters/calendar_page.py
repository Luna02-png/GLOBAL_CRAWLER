"""Release-calendar pages (e.g. Sneaker Bar Detroit "Air Jordan Release Dates").

These pages have no feed. Each entry is a product name followed by labelled lines:
    Color: ...   Style Code: ...   Release Date: ...   Price: ...
The page is fetched once (robots.txt honoured by http_get) and every entry becomes one RawItem.
The summary is written in neutral words ("Releasing <date>") so the pipeline files it as
REPORTED / EXPECTED - a calendar listing is not an official brand confirmation.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..db import utcnow
from .base import Adapter, FetchCtx, FetchOutput, RawItem, SourceError, http_get

LABEL_RE = re.compile(r"^(colou?r(?:way)?|style\s*code|sku|release\s*date|retail\s*price|price)\s*:\s*(.*)$", re.I)
NOISE_RE = re.compile(r"^(buy|buy now|shop|shop now|more|read more|advertisement|share|\d+)$", re.I)
TYPO = {"februray": "February", "feburary": "February", "janurary": "January", "septmber": "September"}
BLOCK_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div", "span", "strong", "b", "a", "td", "br"]


def _key(label: str) -> str:
    l = label.lower().replace(" ", "")
    if l.startswith("colo"):
        return "color"
    if l in ("stylecode", "sku"):
        return "style_code"
    if l == "releasedate":
        return "release_date"
    return "price"


def _fix_typos(s: str) -> str:
    for bad, good in TYPO.items():
        s = re.sub(bad, good, s, flags=re.I)
    return s


def parse_calendar(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
        t.decompose()
    links: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        txt = " ".join(a.get_text(" ").split())
        if txt and len(txt) > 6 and txt.lower() not in links:
            links[txt.lower()] = urljoin(page_url, a["href"])
    lines = [" ".join(l.split()) for l in soup.get_text("\n").split("\n")]
    lines = [l for l in lines if l]

    entries: list[dict] = []
    cur: Optional[dict] = None
    last_text: Optional[str] = None
    pending_label: Optional[str] = None
    for line in lines:
        m = LABEL_RE.match(line)
        if m:
            key, val = _key(m.group(1)), m.group(2).strip()
            if cur is None or (key in cur and key != "price"):
                # first label of a new entry: its name is the last plain line before it
                if not last_text:
                    pending_label = None
                    continue
                cur = {"name": last_text}
                entries.append(cur)
            if val:
                cur[key] = val
                pending_label = None
            else:
                pending_label = key
            continue
        if pending_label and cur is not None:
            cur[pending_label] = line
            pending_label = None
            continue
        if NOISE_RE.match(line) or len(line) > 140:
            continue
        if cur is not None and "release_date" in cur:
            cur = None  # this plain line starts the next entry
        last_text = line

    out = []
    for e in entries:
        name = e["name"].strip(" -–:")
        if not e.get("release_date") or len(name) < 4:
            continue
        e["name"] = name
        e["release_date"] = _fix_typos(e["release_date"])
        e["url"] = links.get(name.lower()) or f"{page_url.split('#')[0]}#{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}"
        out.append(e)
    return out


def entry_summary(e: dict) -> str:
    parts = [f"Releasing {e['release_date']}"]
    price = e.get("price")
    if price and not re.match(r"^(tba|tbd|n/?a)$", price.strip(), re.I):
        parts[0] += f" at {price}"
    parts[0] += "."
    if e.get("style_code"):
        parts.append(f"Style code {e['style_code']}.")
    if e.get("color"):
        parts.append(f"Colorway {e['color']}.")
    return " ".join(parts)


class CalendarPageAdapter(Adapter):
    name = "release_calendar"

    def check_configured(self, source):
        if not source.url:
            raise SourceError("NOT_CONFIGURED", "calendar page URL missing")

    def fetch(self, source, ctx: FetchCtx) -> FetchOutput:
        body, cached = http_get(source.url, rate_key=source.key, per_minute=source.rate_per_minute, use_cache=ctx.use_cache)
        entries = parse_calendar(body, source.url)
        if not entries:
            raise SourceError("ERROR", "no release entries found - the page layout may have changed")
        now = utcnow()
        market = source.markets[0] if source.markets else None
        items = [RawItem(url=e["url"], title=e["name"], summary=entry_summary(e), published_at=now,
                         outlet=source.platform or source.name, market_code=market, platform=source.platform,
                         source_type=source.source_type, lang="en")
                 for e in entries[: max(ctx.max_results, 200)]]
        return FetchOutput(items, from_cache=cached)
