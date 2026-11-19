"""Product Link Finder: best *information* page (article/review/official/retail) + optional purchase URL.

Works on ONE product at a time. Candidates come from the product's own evidence, a product-specific
Google News RSS query, and URLs the user adds manually. Every candidate is verified against the canonical
identity using what is observed on the page (or, if the page cannot be fetched, the feed title only)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.base import FetchCtx, SourceError, http_get
from ..adapters.rss import GoogleNewsAdapter
from ..db import utcnow
from ..models import Brand, ChangeEvent, Evidence, Market, Product, ProductLink, ProductMarket, Source
from .canonical import numbers, significant_tokens, tokens

RETAILERS = {"footlocker.com", "jdsports.com", "jdsports.co.uk", "endclothing.com", "sneakersnstuff.com", "kickscrew.com",
             "zalando.com", "zalando.de", "abc-mart.net", "musinsa.com", "bestbuy.com", "target.com", "walmart.com",
             "sephora.com", "ulta.com", "yesstyle.com", "oliveyoung.co.kr", "global.oliveyoung.com", "bhphotovideo.com",
             "fptshop.com.vn", "thegioididong.com", "cellphones.com.vn", "shopee.vn", "lazada.vn", "tiki.vn", "rakuten.co.jp",
             "yodobashi.com", "biccamera.com", "coupang.com", "atmos-tokyo.com", "kith.com", "size.co.uk", "dtlr.com"}
MARKETPLACES = {"stockx.com", "goat.com", "ebay.com", "amazon.com", "amazon.co.jp", "amazon.co.uk", "amazon.de", "mercari.com",
                "kream.co.kr", "grailed.com", "flightclub.com"}
PAGE_TYPE_PRIORITY = {"OFFICIAL_INFO": 5, "REVIEW": 4, "RELEASE_INFO": 4, "ARTICLE": 3, "RETAIL_PRODUCT": 3, "MARKETPLACE_PRODUCT": 2, "OTHER": 1}
MAX_CANDIDATES = 10


@dataclass
class PageInfo:
    accessible: bool
    error: Optional[str] = None
    title: str = ""
    h1: str = ""
    description: str = ""
    og_image: Optional[str] = None
    text_len: int = 0
    text: str = ""
    jsonld_product: dict = field(default_factory=dict)
    image_count: int = 0
    final_url: Optional[str] = None


def _domain(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def _domain_in(d: str, domains: set[str]) -> bool:
    return any(d == x or d.endswith("." + x) for x in domains)


def parse_page(html: str, url: str) -> PageInfo:
    soup = BeautifulSoup(html, "html.parser")
    def meta(*names):
        for n in names:
            t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if t and t.get("content"):
                return t["content"].strip()
        return ""
    prod = {}
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d and isinstance(d["@graph"], list):
                    stack.extend(d["@graph"])
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    prod = d
                    break
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    og_img = meta("og:image", "twitter:image")
    return PageInfo(accessible=True, title=(soup.title.string.strip() if soup.title and soup.title.string else meta("og:title")),
                    h1=(soup.h1.get_text(" ", strip=True) if soup.h1 else ""), description=meta("og:description", "description"),
                    og_image=og_img if og_img.startswith(("http://", "https://")) else None, text_len=len(text), text=text[:20000],
                    jsonld_product=prod, image_count=len(soup.find_all("img")), final_url=url)


def classify_page(url: str, info: Optional[PageInfo], brand_domains: set[str], title_hint: str = "") -> str:
    d = _domain(url)
    has_offer = bool(info and info.jsonld_product.get("offers"))
    if _domain_in(d, brand_domains):
        return "RETAIL_PRODUCT" if has_offer and re.search(r"/(t|p|product|products)/", url) else "OFFICIAL_INFO"
    if _domain_in(d, MARKETPLACES):
        return "MARKETPLACE_PRODUCT"
    if _domain_in(d, RETAILERS) or has_offer:
        return "RETAIL_PRODUCT"
    hint = (url + " " + title_hint + " " + (info.title if info else "")).lower()
    if re.search(r"\breview\b|/review", hint):
        return "REVIEW"
    if re.search(r"release[- ]date|releas|launch|drop|calendar|specs|specifications", hint):
        return "RELEASE_INFO"
    return "ARTICLE"


def identity_match(product: Product, haystack_title: str, body: str, info: Optional[PageInfo]) -> str:
    hay = f"{haystack_title} {body}".lower()
    if product.sku and product.sku.lower() in hay:
        return "EXACT MATCH"
    if info and info.jsonld_product.get("sku") and product.sku and str(info.jsonld_product["sku"]).lower() == product.sku.lower():
        return "EXACT MATCH"
    sig = significant_tokens(product.brand or "", product.name, product.model_variant)
    if not sig:
        return "REJECTED"
    title_toks = set(tokens(haystack_title))
    page_nums = numbers(set(tokens(hay)))
    if not numbers(sig) <= page_nums:
        return "REJECTED"
    if product.brand and product.brand.lower().split()[0] not in hay:
        return "REJECTED"
    in_title = len(sig & title_toks) / len(sig)
    in_page = len([t for t in sig if t in hay]) / len(sig)
    if in_title == 1.0:
        return "HIGH CONFIDENCE"
    if in_page == 1.0 and in_title >= 0.5:
        return "HIGH CONFIDENCE"
    if in_page >= 0.6:
        return "POSSIBLE MATCH"
    return "REJECTED"


def completeness(product: Product, info: Optional[PageInfo], feed_title: str, feed_image: Optional[str], credibility: float,
                 page_type: str) -> tuple[float, dict]:
    fields: dict[str, object] = {}
    title = (info.title + " " + info.h1) if info and info.accessible else feed_title
    sig = significant_tokens(product.brand or "", product.name, product.model_variant)
    fields["full_name"] = bool(sig) and all(t in title.lower() for t in sig)
    fields["image"] = bool((info and info.og_image) or feed_image)
    desc_len = len(info.description) if info else 0
    fields["description"] = desc_len >= 80 or bool(info and info.text_len >= 1200)
    fields["detailed_content"] = bool(info and (info.text_len >= 3000 or len(info.jsonld_product) >= 5))
    body = (info.text.lower() if info and info.text else "") + " " + feed_title.lower()
    fields["sku"] = bool(product.sku and product.sku.lower() in body)
    fields["variant"] = bool(product.model_variant and product.model_variant.lower() in body)
    fields["release_info"] = bool(re.search(r"release date|releases? on|launch(es|ing)? on|available (on|from)|drops? on", body))
    fields["price"] = bool(info and (info.jsonld_product.get("offers") or re.search(r"(\$|€|£|¥|₩|₫)\s?\d", info.text or "")))
    fields["page_accessible"] = bool(info and info.accessible)
    w = {"full_name": 20, "image": 15, "description": 12, "detailed_content": 15, "sku": 13, "variant": 8, "release_info": 7,
         "price": 3, "page_accessible": 2}
    score = sum(w[k] for k, v in fields.items() if v) + 5 * credibility
    if page_type in ("OFFICIAL_INFO",):
        score += 3
    return round(min(score, 100), 1), fields


@dataclass
class LinkFinderResult:
    product_id: int
    checked: list[dict] = field(default_factory=list)
    primary_url: Optional[str] = None
    purchase_url: Optional[str] = None
    status: str = "NOT_FOUND"
    missing_fields: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _gather_candidates(db: Session, product: Product, purchase_mode: bool, use_search: bool) -> list[dict]:
    cands: dict[str, dict] = {}
    for e in db.scalars(select(Evidence).where(Evidence.product_id == product.id).order_by(Evidence.published_at.desc()).limit(25)):
        cands.setdefault(e.url, {"url": e.url, "title": e.title or "", "source": e.outlet, "market": e.market_code,
                                 "aggregator": e.url_is_aggregator, "via": f"evidence:{e.source_key}", "fixture": e.is_fixture,
                                 "image": None})
    for l in db.scalars(select(ProductLink).where(ProductLink.product_id == product.id)):
        cands.setdefault(l.url, {"url": l.url, "title": (l.info_fields or {}).get("_title", ""), "source": l.source, "market": l.market_code,
                                 "aggregator": False, "via": l.provenance or "existing", "fixture": l.is_fixture, "image": None})
    if use_search:
        src = db.scalar(select(Source).where(Source.key == "google_news"))
        if src and src.enabled:
            markets = [r[0] for r in db.execute(select(ProductMarket.market_code).where(ProductMarket.product_id == product.id))]
            q = f"\"{product.name}\"" + (f" {product.sku}" if product.sku else "") + (" buy" if purchase_mode else "")
            for mc in [m for m in markets if m != "GLOBAL"][:2] or ["US"]:
                mk = db.scalar(select(Market).where(Market.code == mc))
                if not mk or not mk.google_news_ceid:
                    continue
                try:
                    out = GoogleNewsAdapter().fetch(src, FetchCtx(market_code=mc, languages=mk.languages, query=q,
                                                                  google_news_locale=mk.google_news_ceid, max_results=10))
                    for it in out.items:
                        cands.setdefault(it.url, {"url": it.url, "title": it.title, "source": it.outlet, "market": mc,
                                                  "aggregator": True, "via": "search:google_news", "fixture": False, "image": it.image_url})
                except SourceError as e:
                    cands.setdefault("__err__" + mc, {"error": f"google_news {mc}: {e.status} {e.message}"})
    return list(cands.values())


def find_links(db: Session, product_id: int, purchase_mode: bool = False, use_search: bool = True, fetch_pages: bool = True) -> LinkFinderResult:
    product = db.get(Product, product_id)
    res = LinkFinderResult(product_id=product_id)
    if product is None:
        res.status = "ERROR"
        res.failures.append("product not found")
        return res
    brand = db.scalar(select(Brand).where(Brand.name == product.brand)) if product.brand else None
    brand_domains = set(brand.official_domains or []) if brand else set()
    creds = {s.platform: s.credibility for s in db.scalars(select(Source)) if s.platform}
    candidates = _gather_candidates(db, product, purchase_mode, use_search)
    now = utcnow()
    for c in candidates[: MAX_CANDIDATES + 5]:
        if "error" in c:
            res.failures.append(c["error"])
            continue
        url = c["url"]
        existing = db.scalar(select(ProductLink).where(ProductLink.product_id == product.id, ProductLink.url == url))
        if existing is not None and not fetch_pages and (existing.accessible or existing.user_selected):
            continue  # never downgrade a page-verified candidate with a feed-only check
        info: Optional[PageInfo] = None
        if fetch_pages and not c.get("fixture"):
            try:
                body, _ = http_get(url, rate_key="linkfinder:" + _domain(url), per_minute=10)
                info = parse_page(body, url)
            except SourceError as e:
                info = PageInfo(accessible=False, error=f"{e.status}: {e.message}")
                res.failures.append(f"{_domain(url)}: {e.status}")
        page_title = (info.title + " " + info.h1) if info and info.accessible else c["title"]
        body_text = (info.text if info and info.accessible else "") + " " + (info.description if info else "")
        match = identity_match(product, page_title or c["title"], body_text + " " + c["title"], info)
        ptype = classify_page(url, info, brand_domains, c["title"])
        if match in ("EXACT MATCH", "HIGH CONFIDENCE") and info and info.accessible and info.og_image and not product.image_url:
            product.image_url = info.og_image
            product.attributes = {**(product.attributes or {}), "image_source": f"og:image of {url}"}
        cred = creds.get(c.get("source"), 0.6)
        score, fields = completeness(product, info, c["title"], c.get("image"), cred, ptype)
        fields["_title"] = c["title"] or (info.title if info else "")
        fields["_aggregator_url"] = bool(c.get("aggregator"))
        offers = (info.jsonld_product.get("offers") if info else None) or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = currency = stock = None
        if isinstance(offers, dict):
            try:
                price = float(offers.get("price")) if offers.get("price") not in (None, "") else None
            except (TypeError, ValueError):
                price = None
            currency = offers.get("priceCurrency")
            av = str(offers.get("availability") or "")
            stock = av.rsplit("/", 1)[-1] if av else None
        link = db.scalar(select(ProductLink).where(ProductLink.product_id == product.id, ProductLink.url == url))
        if link is None:
            link = ProductLink(product_id=product.id, url=url, page_type=ptype, identity_match=match, first_found_at=now,
                               is_fixture=bool(c.get("fixture")))
            db.add(link)
        link.page_type, link.identity_match, link.source, link.market_code = ptype, match, c.get("source"), c.get("market")
        link.info_fields, link.completeness_score = fields, score
        link.accessible = info.accessible if info else None
        link.fetch_error = info.error if info else None
        link.provenance = c.get("via")
        link.last_verified_at = now
        if ptype in ("RETAIL_PRODUCT", "MARKETPLACE_PRODUCT") and match in ("EXACT MATCH", "HIGH CONFIDENCE") and (price or stock):
            link.price, link.currency, link.stock_state = price, currency, stock
            link.is_purchase_url = True
        else:
            link.is_purchase_url = False
        res.checked.append({"url": url, "page_type": ptype, "identity_match": match, "completeness": score,
                            "accessible": link.accessible, "error": link.fetch_error, "via": c.get("via")})
    db.flush()
    links = list(db.scalars(select(ProductLink).where(ProductLink.product_id == product.id)))
    verified = [l for l in links if l.identity_match in ("EXACT MATCH", "HIGH CONFIDENCE")]
    user_pick = [l for l in links if l.user_selected and l.identity_match != "REJECTED"]
    if user_pick:
        primary = user_pick[0]
    elif verified:
        def rank(l: ProductLink):
            return (l.completeness_score, l.identity_match == "EXACT MATCH", not (l.info_fields or {}).get("_aggregator_url"),
                    PAGE_TYPE_PRIORITY.get(l.page_type, 0), l.last_verified_at or now)
        verified.sort(key=rank, reverse=True)
        top = verified[0]
        close = [l for l in verified if top.completeness_score - l.completeness_score <= 5]
        close.sort(key=lambda l: (PAGE_TYPE_PRIORITY.get(l.page_type, 0), not (l.info_fields or {}).get("_aggregator_url"),
                                  l.completeness_score), reverse=True)
        primary = close[0]
    else:
        primary = None
    had_primary = any(l.is_primary_information_url for l in links)
    for l in links:
        l.is_primary_information_url = primary is not None and l.id == primary.id
    purchase = sorted([l for l in links if l.is_purchase_url], key=lambda l: l.completeness_score, reverse=True)
    if primary:
        res.primary_url = primary.url
        page_checked = primary.accessible is True or primary.user_selected
        res.status = "VERIFIED" if page_checked else "TITLE_MATCH"
        res.missing_fields = [k for k, v in (primary.info_fields or {}).items() if not k.startswith("_") and v is False]
        if not had_primary:
            db.add(ChangeEvent(event_type="NEW_PRIMARY_LINK", product_id=product.id, detail=f"{primary.page_type}: {primary.url}",
                               source_url=primary.url, is_fixture=product.is_fixture))
    elif any(l.identity_match == "POSSIBLE MATCH" for l in links):
        res.status = "NEEDS_REVIEW"
    elif res.failures and not res.checked:
        res.status = "FAILED"
    if purchase:
        res.purchase_url = purchase[0].url
    product.link_status = res.status
    product.link_checked_at = now
    db.flush()
    return res


def add_manual_candidate(db: Session, product_id: int, url: str) -> ProductLink:
    link = db.scalar(select(ProductLink).where(ProductLink.product_id == product_id, ProductLink.url == url))
    if link is None:
        link = ProductLink(product_id=product_id, url=url, page_type="OTHER", identity_match="POSSIBLE MATCH", provenance="manual")
        db.add(link)
        db.flush()
    return link


def set_primary(db: Session, product_id: int, link_id: int) -> ProductLink:
    links = list(db.scalars(select(ProductLink).where(ProductLink.product_id == product_id)))
    target = next((l for l in links if l.id == link_id), None)
    if target is None or target.identity_match == "REJECTED":
        raise ValueError("link not found or rejected")
    for l in links:
        l.user_selected = l.id == link_id
        l.is_primary_information_url = l.id == link_id
    db.get(Product, product_id).link_status = "VERIFIED"
    db.flush()
    return target
