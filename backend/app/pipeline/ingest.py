"""Turn raw source items into canonical products + evidence + release events."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.base import RawItem
from ..db import utcnow
from ..models import (
    Brand, Category, ChangeEvent, Evidence, Product, ProductAlias, ProductCategory, ProductMarket, ReleaseHistory,
    UpcomingRelease,
)
from . import canonical
from .extract import BrandEntry, Mention, extract_mentions, normalize_text

CLAIM_TO_STATUS = {
    "OFFICIALLY_CONFIRMED": "OFFICIALLY CONFIRMED", "RETAILER_LISTED": "RETAILER LISTED", "RUMORED": "RUMORED",
    "LEAKED": "LEAKED", "DELAYED": "DELAYED", "CANCELLED": "CANCELLED", "RELEASED": "RELEASED",
}
STATUS_RANK = {"RUMORED": 1, "LEAKED": 1, "REPORTED / EXPECTED": 2, "RETAILER LISTED": 3, "OFFICIALLY CONFIRMED": 4,
               "DELAYED": 4, "RELEASED": 5, "CANCELLED": 5}
PRECISION_RANK = {"TBA": 0, "YEAR": 1, "SEASON": 2, "QUARTER": 2, "MONTH": 3, "DAY": 4}


@dataclass
class IngestStats:
    items: int = 0
    mentions: int = 0
    products_new: int = 0
    products_updated: int = 0
    evidence_new: int = 0
    skipped_out_of_scope: int = 0
    touched_products: set[int] = field(default_factory=set)
    products_with_new_evidence: set[int] = field(default_factory=set)


@dataclass
class ScopeContext:
    categories: list[Category]  # expanded (includes subcategories)
    include_keywords: list[str]
    exclude_keywords: list[str]
    tracking_only: bool = False
    restrict_product_ids: Optional[set[int]] = None
    job_id: Optional[int] = None


def load_brands(db: Session) -> tuple[list[BrandEntry], dict[str, list[int]]]:
    brands = list(db.scalars(select(Brand)))
    return [BrandEntry(b.name, list(b.aliases or [])) for b in brands], {b.name: list(b.industry_ids or []) for b in brands}


def fingerprint(title: str) -> str:
    t = normalize_text(title).lower()
    t = re.sub(r"[^\w]+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()


def _text_has(text: str, kw: str) -> bool:
    """Whole-word keyword match; a trailing '*' makes it a prefix match (e.g. 'galaxy s*')."""
    if not kw:
        return False
    kw = kw.lower()
    if kw.endswith("*"):
        return re.search(r"(?<!\w)" + re.escape(kw[:-1]), text) is not None
    return re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text) is not None


def assign_categories(m: Mention, text: str, scope: ScopeContext, brand_industries: dict[str, list[int]]) -> list[Category]:
    low = text.lower()
    out: list[Category] = []
    for c in scope.categories:
        if any(_text_has(low, x) for x in (c.exclude_keywords or [])):
            continue
        brand_hit = any(b.lower() == m.brand.lower() or _text_has(m.name.lower(), b.lower()) for b in (c.brands or []))
        kws = list(c.keywords or []) + [k for ks in (c.local_keywords or {}).values() for k in ks]
        kw_hit = any(_text_has(low, k) for k in kws)
        if brand_hit or kw_hit:
            out.append(c)
    # a subcategory match implies its parent; keep only the most specific matches per branch
    ids = {c.id for c in out}
    out = [c for c in out if not any(o.parent_id == c.id for o in out)] if ids else out
    return out


def _candidates(db: Session, brand: str) -> list[canonical.Candidate]:
    rows = db.execute(select(Product.id, Product.brand, Product.name, Product.model_variant, Product.sku)
                      .where(Product.brand == brand)).all()
    return [canonical.Candidate(*r) for r in rows]


def upsert_release(db: Session, product: Product, market: str, m: Mention, item: RawItem, credibility: float,
                   job_id: Optional[int]) -> Optional[str]:
    status = CLAIM_TO_STATUS.get(m.claim_type)
    published = item.published_at or utcnow()
    future_date = m.release_date is not None and m.release_date >= published.date()
    if status is None and future_date:
        status = "REPORTED / EXPECTED"
    if status == "RELEASED" and m.release_date and not future_date:
        pass
    rel = db.scalar(select(UpcomingRelease).where(UpcomingRelease.product_id == product.id, UpcomingRelease.market_code == market))
    if rel is None:
        if status is None or (status in ("OFFICIALLY CONFIRMED", "RETAILER LISTED") and not future_date and m.release_date is not None):
            return None
        if status in ("RELEASED", "DELAYED", "CANCELLED") and not future_date:
            return None  # nothing to update yet
        if status in ("OFFICIALLY CONFIRMED", "RETAILER LISTED") and m.release_date is None and m.claim_type != "RETAILER_LISTED":
            # "official images" of an already-released product is not an upcoming launch
            if not re.search(r"\b(upcoming|coming|will release|releas\w* (soon|next)|launch\w* (soon|next))\b", item.title.lower()):
                return None
        rel = UpcomingRelease(product_id=product.id, market_code=market, release_status=status,
                              expected_date=m.release_date, expected_date_text=m.release_date_text or "TBA",
                              date_precision=m.date_precision or "TBA", expected_price=m.price, currency=m.currency,
                              source_type=item.source_type, first_reported=published, last_updated=utcnow(),
                              latest_development=f"{status}: {item.title} ({item.outlet})")
        db.add(rel)
        db.flush()
        db.add(ReleaseHistory(release_id=rel.id, field="release_status", old_value=None, new_value=status, source_url=item.url))
        db.add(ChangeEvent(event_type="NEW_RELEASE_EVENT" if status not in ("RUMORED", "LEAKED") else "NEW_RUMOR",
                           product_id=product.id, market_code=market, detail=rel.latest_development, source_url=item.url,
                           job_id=job_id, is_fixture=item.is_fixture))
        product.release_status = status
        return "created"
    changed = None
    if status and status != rel.release_status:
        allowed = STATUS_RANK.get(status, 0) >= STATUS_RANK.get(rel.release_status, 0) or status in ("DELAYED", "CANCELLED")
        if status in ("RUMORED", "LEAKED") and rel.release_status not in ("RUMORED", "LEAKED"):
            allowed = False  # a new rumor never downgrades a confirmed launch
        if allowed:
            db.add(ReleaseHistory(release_id=rel.id, field="release_status", old_value=rel.release_status, new_value=status, source_url=item.url))
            ev = {"OFFICIALLY CONFIRMED": "RUMOR_CONFIRMED" if rel.release_status in ("RUMORED", "LEAKED") else "RELEASE_CONFIRMED",
                  "DELAYED": "RELEASE_DELAYED", "CANCELLED": "RELEASE_CANCELLED", "RELEASED": "RELEASED"}.get(status, "RELEASE_STATUS_CHANGED")
            db.add(ChangeEvent(event_type=ev, product_id=product.id, market_code=market,
                               detail=f"{rel.release_status} → {status}: {item.title}", source_url=item.url, job_id=job_id,
                               is_fixture=item.is_fixture))
            rel.release_status = status
            product.release_status = status
            changed = "status"
    if m.release_date_text and (m.release_date != rel.expected_date):
        better = PRECISION_RANK.get(m.date_precision or "TBA", 0) >= PRECISION_RANK.get(rel.date_precision, 0)
        if better or status == "DELAYED" or (rel.release_status == "OFFICIALLY CONFIRMED" and status == "OFFICIALLY CONFIRMED"):
            db.add(ReleaseHistory(release_id=rel.id, field="expected_date", old_value=rel.expected_date_text,
                                  new_value=m.release_date_text, source_url=item.url))
            if rel.expected_date is not None:
                db.add(ChangeEvent(event_type="RELEASE_DATE_REVISED", product_id=product.id, market_code=market,
                                   detail=f"{rel.expected_date_text} → {m.release_date_text}", source_url=item.url, job_id=job_id,
                                   is_fixture=item.is_fixture))
            rel.expected_date, rel.expected_date_text, rel.date_precision = m.release_date, m.release_date_text, m.date_precision
            changed = changed or "date"
    if m.price and rel.expected_price is None:
        rel.expected_price, rel.currency = m.price, m.currency
    if changed:
        rel.latest_development = f"{rel.release_status}: {item.title} ({item.outlet})"
    rel.last_updated = utcnow()
    return changed


def ingest_mention(db: Session, source, item: RawItem, m: Mention, cats: list[Category], scope: ScopeContext,
                   stats: IngestStats) -> Optional[Product]:
    """Attach one extracted (or user-supplied) mention to a canonical product with its evidence."""
    stats.mentions += 1
    matched_id, verdict, possible_id = canonical.match(m.brand, m.name, m.model_variant, m.sku, _candidates(db, m.brand))
    if scope.restrict_product_ids is not None and matched_id not in scope.restrict_product_ids:
        return None
    if matched_id is None and scope.tracking_only:
        return None
    now = utcnow()
    if matched_id is None:
        key = canonical.canonical_key(m.brand, m.name, m.model_variant, m.sku)
        product = db.scalar(select(Product).where(Product.canonical_key == key))
    else:
        product = db.get(Product, matched_id)
    created = False
    if product is None:
        product = Product(canonical_key=canonical.canonical_key(m.brand, m.name, m.model_variant, m.sku),
                          brand=m.brand, name=m.name, model_variant=m.model_variant, sku=m.sku,
                          is_fixture=item.is_fixture, first_detected=now, last_seen=now,
                          needs_review=verdict == "POSSIBLE",
                          attributes={"possible_duplicate_of": possible_id} if possible_id else {})
        db.add(product)
        db.flush()
        created = True
        stats.products_new += 1
        db.add(ChangeEvent(event_type="NEW_PRODUCT", product_id=product.id, market_code=item.market_code,
                           detail=f"{product.name}" + (f" \"{product.model_variant}\"" if product.model_variant else ""),
                           source_url=item.url, job_id=scope.job_id, is_fixture=item.is_fixture))
    else:
        if not product.sku and m.sku:
            product.sku = m.sku
        if not product.model_variant and m.model_variant and verdict in ("SKU",):
            product.model_variant = m.model_variant
        product.last_seen = now
        if product.id not in stats.touched_products:
            stats.products_updated += 1
    stats.touched_products.add(product.id)
    if item.image_url and not product.image_url and item.image_url.startswith(("http://", "https://")):
        product.image_url = item.image_url
        product.attributes = {**(product.attributes or {}), "image_source": f"feed media of {item.url}"}
    if m.name != product.name:
        if not db.scalar(select(ProductAlias).where(ProductAlias.product_id == product.id, ProductAlias.alias == m.name)):
            db.add(ProductAlias(product_id=product.id, alias=m.name, lang=item.lang))
    for c in cats:
        if not db.get(ProductCategory, (product.id, c.id)):
            db.add(ProductCategory(product_id=product.id, category_id=c.id))
    market = item.market_code or "GLOBAL"
    pm = db.get(ProductMarket, (product.id, market))
    if pm is None:
        db.add(ProductMarket(product_id=product.id, market_code=market, first_seen=now, last_seen=now,
                             attribution="USER_CAPTURE" if getattr(source, "key", "") == "manual_capture" else "SOURCE_EDITION", confidence="MEDIUM" if market != "GLOBAL" else "LOW"))
    else:
        pm.last_seen = now
    ev = db.scalar(select(Evidence).where(Evidence.product_id == product.id, Evidence.url == item.url))
    fp = fingerprint(item.title)
    if ev is None:
        dup = db.scalar(select(Evidence.id).where(Evidence.product_id == product.id, Evidence.content_fingerprint == fp,
                                                  Evidence.outlet != item.outlet))
        db.add(Evidence(product_id=product.id, source_key=source.key, source_type=item.source_type, platform=item.platform,
                        outlet=item.outlet, url=item.url, url_is_aggregator=item.url_is_aggregator, title=item.title,
                        snippet=normalize_text(item.summary)[:500] or None, author=item.author, lang=item.lang,
                        market_code=market, claim_type=m.claim_type, published_at=item.published_at, observed_at=now,
                        engagement=item.engagement or {}, content_fingerprint=fp, is_syndicated_copy=dup is not None,
                        is_fixture=item.is_fixture, job_id=scope.job_id))
        stats.evidence_new += 1
        stats.products_with_new_evidence.add(product.id)
        if not created:
            db.add(ChangeEvent(event_type="NEW_EVIDENCE", product_id=product.id, market_code=market,
                               detail=item.title, source_url=item.url, job_id=scope.job_id, is_fixture=item.is_fixture))
    else:
        ev.observed_at = now
        if item.engagement:
            ev.engagement = item.engagement
    upsert_release(db, product, market, m, item, getattr(source, "credibility", 0.6), scope.job_id)
    db.flush()
    return product


def ingest_items(db: Session, source, items: list[RawItem], scope: ScopeContext, stats: IngestStats) -> IngestStats:
    brand_entries, brand_industries = load_brands(db)
    excl = [k.lower() for k in scope.exclude_keywords if k]
    incl = [k.lower() for k in scope.include_keywords if k]
    for item in items:
        stats.items += 1
        text = normalize_text(f"{item.title} {item.summary}")
        low = text.lower()
        if any(_text_has(low, k) for k in excl):
            stats.skipped_out_of_scope += 1
            continue
        if incl and not any(_text_has(low, k) for k in incl):
            stats.skipped_out_of_scope += 1
            continue
        mentions = extract_mentions(item.title, item.summary, brand_entries, item.published_at)
        # feed category tags often name the exact products ("Nike Air Force 1 Low", "Nike Kobe 6")
        seen = {frozenset(canonical.significant_tokens(mm.brand, mm.name, None)) for mm in mentions}
        for tag in getattr(item, "tags", None) or []:
            for tm in extract_mentions(tag, "", brand_entries, item.published_at, max_mentions=1):
                key = frozenset(canonical.significant_tokens(tm.brand, tm.name, None))
                if key in seen:
                    continue
                seen.add(key)
                tm.claim_type = "MENTION"  # a tag is a reference, not a release claim
                tm.release_date_text = tm.release_date = tm.date_precision = None
                mentions.append(tm)
        for m in mentions:
            cats = assign_categories(m, text, scope, brand_industries) if scope.categories else []
            if scope.categories and not cats:
                stats.skipped_out_of_scope += 1
                continue
            ingest_mention(db, source, item, m, cats, scope, stats)
    return stats
