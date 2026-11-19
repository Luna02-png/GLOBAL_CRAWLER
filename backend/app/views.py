"""Row builders shared by the API grids and the exporters (one canonical database, many views)."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Category, Evidence, Industry, Market, OpportunityScore, Product, ProductCategory, ProductLink, ProductMarket,
    ProductMarketTrend, UpcomingRelease,
)

LINK_TYPE_LABEL = {"OFFICIAL_INFO": "Official", "ARTICLE": "Article", "REVIEW": "Review", "RELEASE_INFO": "Release",
                   "RETAIL_PRODUCT": "Retailer", "MARKETPLACE_PRODUCT": "Retailer", "OTHER": "Other"}

RESEARCH_COLUMNS = [
    ("industry", "Industry"), ("category", "Category"), ("subcategory", "Subcategory"), ("region", "Market / Region"),
    ("country", "Country"), ("brand", "Brand"), ("product_name", "Product Name"), ("model_variant", "Model / Colorway / Version"),
    ("sku", "SKU / Model Number"), ("image_url", "Product Image URL"), ("best_info_url", "Best Product Information URL"),
    ("best_link_type", "Best Link Type"), ("alt_info_url_1", "Alternative Information URL 1"),
    ("alt_info_url_2", "Alternative Information URL 2"), ("purchase_url", "Optional Purchase URL"),
    ("ref_url_1", "Reference URL 1"), ("ref_url_2", "Reference URL 2"), ("ref_url_3", "Reference URL 3"),
    ("source_platforms", "Source Platforms"), ("trend_score", "Trend Score"), ("trend_status", "Trend Status"),
    ("early_score", "Early Signal Score"), ("opportunity_score", "Opportunity Score"), ("confidence", "Evidence Confidence"),
    ("coverage", "Data Coverage"), ("trend_explanation", "Trend Explanation"), ("release_status", "Release Status"),
    ("first_detected", "First Detected"), ("last_seen", "Last Seen / Updated"), ("link_status", "Product Link Verification Status"),
]


def _fmt_dt(d) -> Optional[str]:
    """Stored timestamps are UTC; exported in the configured scheduler timezone (default Asia/Ho_Chi_Minh)."""
    if not d:
        return None
    from datetime import timezone as _tz
    from zoneinfo import ZoneInfo
    from . import config
    return d.replace(tzinfo=_tz.utc).astimezone(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")


def _taxonomy(db: Session):
    cats = {c.id: c for c in db.scalars(select(Category))}
    inds = {i.id: i for i in db.scalars(select(Industry))}
    return cats, inds


def research_rows(db: Session, *, markets: Optional[list[str]] = None, industry_ids: Optional[list[int]] = None,
                  category_ids: Optional[list[int]] = None, status: Optional[list[str]] = None, search: Optional[str] = None,
                  include_fixture: bool = True, expand_categories: bool = False, product_ids: Optional[list[int]] = None,
                  since=None, limit: int = 20000) -> list[dict]:
    cats, inds = _taxonomy(db)
    mk = {m.code: m for m in db.scalars(select(Market))}
    q = select(Product, ProductMarket).join(ProductMarket, ProductMarket.product_id == Product.id)
    if markets:
        q = q.where(ProductMarket.market_code.in_(markets))
    if not include_fixture:
        q = q.where(Product.is_fixture.is_(False))
    if product_ids is not None:  # an empty list means "no products" (e.g. a scan that found nothing)
        q = q.where(Product.id.in_(product_ids))
    if since is not None:
        q = q.where(Product.last_seen >= since)
    if search:
        like = f"%{search.lower()}%"
        from sqlalchemy import func, or_
        q = q.where(or_(func.lower(Product.name).like(like), func.lower(Product.brand).like(like), func.lower(Product.sku).like(like),
                        func.lower(Product.model_variant).like(like)))
    pairs = db.execute(q.order_by(Product.last_seen.desc()).limit(limit)).all()
    if not pairs:
        return []
    pids = list({p.id for p, _ in pairs})
    pcats: dict[int, list[int]] = defaultdict(list)
    for pc in db.scalars(select(ProductCategory).where(ProductCategory.product_id.in_(pids))):
        pcats[pc.product_id].append(pc.category_id)
    trends = {(t.product_id, t.market_code): t for t in db.scalars(select(ProductMarketTrend).where(ProductMarketTrend.product_id.in_(pids)))}
    links: dict[int, list[ProductLink]] = defaultdict(list)
    for l in db.scalars(select(ProductLink).where(ProductLink.product_id.in_(pids))):
        links[l.product_id].append(l)
    evid: dict[int, list[Evidence]] = defaultdict(list)
    for e in db.scalars(select(Evidence).where(Evidence.product_id.in_(pids), Evidence.is_syndicated_copy.is_(False))
                        .order_by(Evidence.published_at.desc())):
        evid[e.product_id].append(e)
    rels = {(r.product_id, r.market_code): r for r in db.scalars(select(UpcomingRelease).where(UpcomingRelease.product_id.in_(pids)))}
    opps: dict[tuple, float] = {}
    for o in db.scalars(select(OpportunityScore).where(OpportunityScore.product_id.in_(pids))):
        key = (o.product_id, o.target_market)
        if o.score is not None and o.score > opps.get(key, -1):
            opps[key] = o.score
    rows = []
    sel_cats = set(category_ids or [])
    for p, pm in pairs:
        cat_list = [cats[c] for c in pcats.get(p.id, []) if c in cats]
        if industry_ids and not any(c.industry_id in industry_ids for c in cat_list):
            continue
        if sel_cats and not any(c.id in sel_cats or c.parent_id in sel_cats for c in cat_list):
            continue
        t = trends.get((p.id, pm.market_code))
        if status and (t.trend_status if t else "INSUFFICIENT DATA") not in status:
            continue
        plinks = sorted(links.get(p.id, []), key=lambda l: l.completeness_score, reverse=True)
        primary = next((l for l in plinks if l.is_primary_information_url), None)
        alts = [l for l in plinks if not l.is_primary_information_url and not l.is_purchase_url
                and l.identity_match in ("EXACT MATCH", "HIGH CONFIDENCE")]
        purchase = next((l for l in plinks if l.is_purchase_url), None)
        evs = evid.get(p.id, [])
        mevs = [e for e in evs if e.market_code == pm.market_code] or evs
        refs, outlets_seen = [], set()
        used = {primary.url if primary else None} | {a.url for a in alts[:2]}
        for e in mevs:
            if e.url in used or e.outlet in outlets_seen:
                continue
            refs.append(e.url)
            outlets_seen.add(e.outlet)
            if len(refs) == 3:
                break
        platforms = sorted({e.platform or e.source_key for e in mevs if e.platform or e.source_key})
        rel = rels.get((p.id, pm.market_code))
        m = mk.get(pm.market_code)
        groups = [[c] for c in cat_list] if (expand_categories and cat_list) else [cat_list]
        for grp in groups:
            top_names, sub_names, ind_names = [], [], []
            for c in grp:
                if c.parent_id and c.parent_id in cats:
                    top_names.append(cats[c.parent_id].name)
                    sub_names.append(c.name)
                else:
                    top_names.append(c.name)
                ind_names.append(inds[c.industry_id].name if c.industry_id in inds else "")
            rows.append({
                "row_id": f"{p.id}:{pm.market_code}" + (f":{grp[0].id}" if expand_categories and grp else ""),
                "product_id": p.id, "market_code": pm.market_code, "is_fixture": p.is_fixture, "needs_review": p.needs_review,
                "industry": "; ".join(dict.fromkeys(ind_names)) or None,
                "category": "; ".join(dict.fromkeys(top_names)) or None,
                "subcategory": "; ".join(dict.fromkeys(sub_names)) or None,
                "region": m.region if m else None, "country": m.name if m else pm.market_code,
                "trends_term": (p.attributes or {}).get("trends_term"),
                "brand": p.brand, "product_name": p.name, "model_variant": p.model_variant, "sku": p.sku,
                "image_url": p.image_url,
                "best_info_url": primary.url if primary else None,
                "best_link_type": LINK_TYPE_LABEL.get(primary.page_type) if primary else None,
                "alt_info_url_1": alts[0].url if len(alts) > 0 else None,
                "alt_info_url_2": alts[1].url if len(alts) > 1 else None,
                "purchase_url": purchase.url if purchase else None,
                "ref_url_1": refs[0] if len(refs) > 0 else None, "ref_url_2": refs[1] if len(refs) > 1 else None,
                "ref_url_3": refs[2] if len(refs) > 2 else None,
                "source_platforms": ", ".join(platforms) or None,
                "trend_score": t.trend_score if t else None, "trend_status": t.trend_status if t else "INSUFFICIENT DATA",
                "early_score": t.early_score if t else None, "lifecycle_stage": t.lifecycle_stage if t else None,
                "opportunity_score": opps.get((p.id, pm.market_code)),
                "confidence": t.confidence if t else "LOW", "coverage": round(t.coverage * 100) if t else 0,
                "trend_explanation": t.explanation if t else None,
                "release_status": rel.release_status if rel else p.release_status,
                "first_detected": _fmt_dt(p.first_detected), "last_seen": _fmt_dt(p.last_seen),
                "link_status": p.link_status, "evidence_count": len(mevs),
            })
    return rows
