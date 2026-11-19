"""User-captured evidence: pages the user browsed themselves (as a normal visitor) and sent to the app via the
bookmarklet, the capture form or a bulk paste. Nothing here crawls social platforms automatically."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.base import RawItem, SourceError, http_get
from ..db import utcnow
from ..models import Category, Evidence, Product, Source
from .extract import Mention, classify_claim, extract_mentions, normalize_text, parse_price, parse_release_date
from .ingest import IngestStats, ScopeContext, assign_categories, ingest_mention, load_brands
from .links import MARKETPLACES, RETAILERS, _domain, _domain_in

SOCIAL_DOMAINS = {"tiktok.com": "TikTok", "instagram.com": "Instagram", "x.com": "X/Twitter", "twitter.com": "X/Twitter",
                  "facebook.com": "Facebook", "fb.watch": "Facebook", "youtube.com": "YouTube", "youtu.be": "YouTube",
                  "reddit.com": "Reddit", "pinterest.com": "Pinterest", "threads.net": "Threads", "threads.com": "Threads",
                  "xiaohongshu.com": "Xiaohongshu", "douyin.com": "Douyin", "weibo.com": "Weibo", "zalo.me": "Zalo"}
SHOP_DOMAINS = RETAILERS | MARKETPLACES | {"shopee.co.th", "shopee.sg", "lazada.co.th", "tokopedia.com", "aliexpress.com", "temu.com", "etsy.com"}
MANUAL_SOURCE_KEY = "manual_capture"

_NUM = r"(\d[\d.,]*\s?[KkMmBb]?)"
ENGAGEMENT_PATTERNS = {
    "views": [_NUM + r"\s*(?:views?|plays?|lượt xem|回視聴|再生|조회)"],
    "likes": [_NUM + r"\s*(?:likes?|lượt thích|thích|いいね|좋아요)"],
    "comments": [_NUM + r"\s*(?:comments?|bình luận|コメント|댓글)"],
    "shares": [_NUM + r"\s*(?:shares?|reposts?|chia sẻ|シェア|공유)"],
}


def parse_number(s: str) -> Optional[int]:
    s = s.strip().replace(" ", "")
    mult = 1
    if s[-1:].upper() in "KMB":
        mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[s[-1].upper()]
        s = s[:-1]
        s = s.replace(",", ".")
        try:
            return int(float(s) * mult)
        except ValueError:
            return None
    digits = re.sub(r"[.,]", "", s)
    return int(digits) if digits.isdigit() else None


def parse_engagement(text: str) -> dict:
    out: dict[str, int] = {}
    for key, pats in ENGAGEMENT_PATTERNS.items():
        for p in pats:
            m = re.search(p, text or "", re.I)
            if m:
                n = parse_number(m.group(1))
                if n is not None:
                    out[key] = n
                    break
    return out


def platform_of(url: str) -> tuple[str, str]:
    d = _domain(url)
    for dom, name in SOCIAL_DOMAINS.items():
        if d == dom or d.endswith("." + dom):
            return name, "SOCIAL"
    if _domain_in(d, SHOP_DOMAINS) or re.search(r"(^|\.)(shopee|lazada)\.", d):
        return d, "RETAIL"
    return d, "EDITORIAL"


def handle_of(url: str, title: str = "", text: str = "") -> Optional[str]:
    p = urlparse(url)
    path = p.path
    d = _domain(url)
    m = re.search(r"/@([\w.\-]+)", path)
    if m:
        return "@" + m.group(1)
    if d in ("x.com", "twitter.com"):
        m = re.match(r"/([\w]+)/status", path)
        if m:
            return "@" + m.group(1)
    if d.endswith("reddit.com"):
        m = re.search(r"/user/([\w\-]+)", path) or re.search(r"/r/([\w]+)", path)
        if m:
            return ("u/" if "/user/" in path else "r/") + m.group(1)
    m = re.search(r"\(@([\w.]+)\)", title or "") or re.search(r"@([\w.]{3,30})", (title or "") + " " + (text or ""))
    if m:
        return "@" + m.group(1)
    if d.endswith("instagram.com") or d.endswith("facebook.com"):
        m = re.match(r"/([\w.]+)/?$", path) or re.match(r"/([\w.]+)/(?:p|reel|reels|posts|videos)/", path)
        if m and m.group(1) not in ("p", "reel", "reels", "explore", "stories", "watch"):
            return "@" + m.group(1)
    return None


@dataclass
class CaptureIn:
    url: str
    market_code: str
    title: str = ""
    text: str = ""
    product_name: Optional[str] = None
    brand: Optional[str] = None
    model_variant: Optional[str] = None
    sku: Optional[str] = None
    category_id: Optional[int] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    engagement: dict = field(default_factory=dict)


@dataclass
class CaptureResult:
    url: str
    status: str  # SAVED / DUPLICATE_UPDATED / NEED_TITLE / NO_PRODUCT / ERROR
    message: str = ""
    product_id: Optional[int] = None
    product_name: Optional[str] = None


def preview(db: Session, url: str, title: str = "", text: str = "") -> dict:
    brands, _ = load_brands(db)
    platform, stype = platform_of(url)
    mentions = extract_mentions(title, text, brands)
    return {"platform": platform, "source_type": stype, "author": handle_of(url, title, text),
            "engagement": parse_engagement(f"{title} {text}"), "claim_type": classify_claim(f"{title} {text}"),
            "mentions": [{"brand": m.brand, "name": m.name, "model_variant": m.model_variant, "sku": m.sku} for m in mentions]}


def _fetch_title(url: str) -> tuple[str, str, Optional[str]]:
    from .links import parse_page
    body, _ = http_get(url, rate_key="capture:" + _domain(url), per_minute=10)
    info = parse_page(body, url)
    return info.title or info.h1, info.description, info.og_image


def _manual_source(db: Session) -> Source:
    src = db.scalar(select(Source).where(Source.key == MANUAL_SOURCE_KEY))
    if src is None:
        src = Source(key=MANUAL_SOURCE_KEY, name="Manual capture (pages you browsed)", adapter="manual",
                     source_type="SOCIAL", platform="Manual", status="MANUAL", enabled=True, credibility=0.6)
        db.add(src)
        db.flush()
    return src


def capture(db: Session, entries: list[CaptureIn]) -> tuple[list[CaptureResult], IngestStats]:
    src = _manual_source(db)
    brands, brand_inds = load_brands(db)
    all_cats = list(db.scalars(select(Category).where(Category.active.is_(True))))
    stats = IngestStats()
    results: list[CaptureResult] = []
    for e in entries:
        url = (e.url or "").strip()
        if not url.startswith(("http://", "https://")):
            results.append(CaptureResult(url, "ERROR", "not an http(s) URL"))
            continue
        platform, stype = platform_of(url)
        title, text, img = normalize_text(e.title), normalize_text(e.text), e.image_url
        if not title and not e.product_name:
            if stype == "SOCIAL":
                results.append(CaptureResult(url, "NEED_TITLE", "social pages are not fetched automatically - paste the caption or product name"))
                continue
            try:
                title, desc, og = _fetch_title(url)
                text = text or desc
                img = img or og
            except SourceError as err:
                results.append(CaptureResult(url, "NEED_TITLE", f"could not read the page ({err.status}); type the title or product name"))
                continue
        full = f"{title}. {text}"
        if e.product_name:
            found = extract_mentions(e.product_name, "", brands)
            base = found[0] if found else Mention(brand=e.brand or "", name=e.product_name.strip())
            m = Mention(brand=e.brand or base.brand or None, name=base.name if found else e.product_name.strip(),
                        model_variant=e.model_variant or base.model_variant, sku=e.sku or base.sku)
            mentions = [m]
        else:
            mentions = extract_mentions(title, text, brands)
            if not mentions:
                results.append(CaptureResult(url, "NO_PRODUCT", "no known brand + model found in the title - type the product name"))
                continue
        eng = {k: int(v) for k, v in (e.engagement or {}).items() if v not in (None, "") and str(v).isdigit()}
        if not eng:
            eng = parse_engagement(full)
        author = e.author or handle_of(url, title, text)
        outlet = f"{platform}:{author}" if author else (f"{platform}:unknown" if stype == "SOCIAL" else platform)
        item = RawItem(url=url, title=title or (e.product_name or ""), summary=text, published_at=e.published_at or utcnow(),
                       author=author, outlet=outlet, market_code=e.market_code or "GLOBAL", platform=platform, source_type=stype,
                       engagement=eng, image_url=img if img and img.startswith(("http://", "https://")) else None)
        cats = [c for c in all_cats if c.id == e.category_id] if e.category_id else []
        scope = ScopeContext(categories=all_cats, include_keywords=[], exclude_keywords=[])
        for m in mentions:
            m.claim_type = classify_claim(full)
            m.release_date_text, m.release_date, m.date_precision = parse_release_date(full, item.published_at)
            m.price, m.currency = parse_price(full)
            use_cats = cats or assign_categories(m, f"{full} {m.name}", scope, brand_inds)
            existing = None
            before = stats.evidence_new
            prod = ingest_mention(db, src, item, m, use_cats, scope, stats)
            if prod is None:
                results.append(CaptureResult(url, "ERROR", "could not attach to a product"))
                continue
            prod.attributes = {**(prod.attributes or {}), "has_user_capture": True}
            status = "SAVED" if stats.evidence_new > before else "DUPLICATE_UPDATED"
            results.append(CaptureResult(url, status, f"{platform} · {outlet}" + (f" · {eng}" if eng else ""), prod.id, prod.name))
    db.flush()
    return results, stats
