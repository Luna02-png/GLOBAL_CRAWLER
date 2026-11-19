from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from .. import config
from ..db import session_scope, utcnow
from ..models import FetchCache


class SourceError(Exception):
    """Structured adapter failure. status is one of RATE_LIMITED / AUTH_REQUIRED / BLOCKED / ERROR / NOT_CONFIGURED."""

    def __init__(self, status: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.message = message
        self.retryable = retryable


@dataclass
class RawItem:
    url: str
    title: str
    summary: str = ""
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    outlet: Optional[str] = None
    lang: Optional[str] = None
    market_code: Optional[str] = None
    platform: Optional[str] = None
    source_type: str = "EDITORIAL"
    engagement: dict = field(default_factory=dict)
    url_is_aggregator: bool = False
    image_url: Optional[str] = None
    tags: list = field(default_factory=list)  # feed categories, e.g. "Nike Air Force 1 Low"
    is_fixture: bool = False


@dataclass
class FetchCtx:
    market_code: Optional[str]
    languages: list[str]
    query: Optional[str]
    google_news_locale: Optional[str]  # "hl|gl|ceid"
    max_results: int = 50
    use_cache: bool = True
    pages: int = 1  # WordPress-style feeds: also read ?paged=2..pages


@dataclass
class FetchOutput:
    items: list[RawItem]
    from_cache: bool = False


# ---------------------------------------------------------------- rate limiting
class _RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def wait(self, key: str, per_minute: int) -> None:
        interval = 60.0 / max(per_minute, 1)
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next.get(key, now))
            self._next[key] = slot + interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, 30))


rate_limiter = _RateLimiter()
_robots_cache: dict[str, tuple[float, Optional[robotparser.RobotFileParser]]] = {}


def _client() -> httpx.Client:
    return httpx.Client(timeout=config.HTTP_TIMEOUT, follow_redirects=True,
                        headers={"User-Agent": config.USER_AGENT, "Accept-Language": "en;q=0.8,*;q=0.5"})


def robots_allowed(url: str) -> bool:
    """Honour robots.txt. If robots.txt cannot be fetched, allow (standard crawler behaviour)."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    cached = _robots_cache.get(base)
    if not cached or time.time() - cached[0] > 3600:
        rp: Optional[robotparser.RobotFileParser] = robotparser.RobotFileParser()
        try:
            with _client() as c:
                r = c.get(base + "/robots.txt")
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None
        except httpx.HTTPError:
            rp = None
        _robots_cache[base] = (time.time(), rp)
        cached = _robots_cache[base]
    rp = cached[1]
    return True if rp is None else rp.can_fetch(config.USER_AGENT, url)


def http_get(url: str, *, rate_key: str, per_minute: int, use_cache: bool = True, params: Optional[dict] = None,
             check_robots: bool = True) -> tuple[str, bool]:
    """GET with rate limit, robots.txt, cache TTL and conditional requests. Returns (body, from_cache)."""
    full_url = str(httpx.URL(url, params=params)) if params else url
    cached: Optional[FetchCache] = None
    with session_scope() as s:
        cached = s.scalar(select(FetchCache).where(FetchCache.url == full_url))
        if cached is not None:
            s.expunge(cached)
    if use_cache and cached and cached.body is not None and utcnow() - cached.fetched_at < timedelta(seconds=config.CACHE_TTL_SECONDS):
        return cached.body, True
    if check_robots and not robots_allowed(full_url):
        raise SourceError("BLOCKED", f"robots.txt disallows {full_url}")
    headers = {}
    if cached and cached.body is not None:
        if cached.etag:
            headers["If-None-Match"] = cached.etag
        if cached.last_modified:
            headers["If-Modified-Since"] = cached.last_modified
    rate_limiter.wait(rate_key, per_minute)
    try:
        with _client() as c:
            r = c.get(full_url, headers=headers)
    except httpx.TimeoutException as e:
        raise SourceError("ERROR", f"timeout: {e}", retryable=True)
    except httpx.HTTPError as e:
        raise SourceError("ERROR", f"network error: {e}", retryable=True)
    if r.status_code == 304 and cached and cached.body is not None:
        with session_scope() as s:
            row = s.get(FetchCache, cached.id)
            row.fetched_at = utcnow()
        return cached.body, True
    if r.status_code == 429:
        raise SourceError("RATE_LIMITED", "HTTP 429 Too Many Requests", retryable=True)
    if r.status_code in (401, 407):
        raise SourceError("AUTH_REQUIRED", f"HTTP {r.status_code}")
    if r.status_code == 403:
        raise SourceError("BLOCKED", "HTTP 403 Forbidden (access refused; not bypassed)")
    if r.status_code >= 500:
        raise SourceError("ERROR", f"HTTP {r.status_code}", retryable=True)
    if r.status_code >= 400:
        raise SourceError("ERROR", f"HTTP {r.status_code}")
    body = r.text
    low = body[:4000].lower()
    if "captcha" in low and ("g-recaptcha" in low or "hcaptcha" in low or "cf-challenge" in low):
        raise SourceError("BLOCKED", "CAPTCHA / anti-bot challenge returned (not bypassed)")
    with session_scope() as s:
        row = s.scalar(select(FetchCache).where(FetchCache.url == full_url))
        if row is None:
            row = FetchCache(url=full_url, status_code=r.status_code)
            s.add(row)
        row.body = body
        row.status_code = r.status_code
        row.etag = r.headers.get("ETag")
        row.last_modified = r.headers.get("Last-Modified")
        row.fetched_at = utcnow()
    return body, False


class Adapter:
    name = "base"

    def check_configured(self, source) -> None:  # raise SourceError if not usable
        return None

    def fetch(self, source, ctx: FetchCtx) -> FetchOutput:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def per_query(self) -> bool:
        """True if the adapter is queried per (market, keyword); False if it is a single feed."""
        return False
