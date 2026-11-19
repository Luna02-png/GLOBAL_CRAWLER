"""Trend, Early Signal, Rumor-confidence, Hype and Opportunity computation.

All scores are recomputed from stored raw observations (evidence). Missing signals are excluded from the
weighted average (never treated as zero) and reduce the reported *coverage* instead."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import (
    ChangeEvent, Evidence, MarketSignalCoverage, OpportunityScore, Product, ProductCategory, ProductDailySignal,
    ProductLink, ProductMarket, ProductMarketTrend, Setting, TrendHistory, UpcomingRelease,
)

RETAIL_CLAIMS = {"RETAILER_LISTED", "RELEASED"}


def get_setting(db: Session, key: str, default=None):
    row = db.get(Setting, key)
    return row.value if row else default


def weights_for(db: Session, kind: str, industry_id: Optional[int]) -> dict:
    if industry_id is not None:
        w = get_setting(db, f"weights.{kind}.{industry_id}")
        if w:
            return w
    return get_setting(db, f"weights.{kind}.default", {})


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def weighted(components: dict[str, Optional[float]], weights: dict[str, float]) -> tuple[Optional[float], float]:
    total_w = sum(weights.values()) or 1
    avail = {k: v for k, v in components.items() if v is not None and weights.get(k, 0) > 0}
    aw = sum(weights[k] for k in avail)
    if aw == 0:
        return None, 0.0
    score = sum(weights[k] * avail[k] for k in avail) / aw * 100
    return round(score, 1), round(aw / total_w, 3)


def smoothed_growth(cur: float, prev: float, k: float = 2.0) -> float:
    """Additive smoothing so 2 -> 6 mentions is +100%, not +200% (small-sample safeguard)."""
    return (cur + k) / (prev + k) - 1


def _day(e: Evidence) -> date:
    return (e.published_at or e.observed_at).date()


def market_window_start(db: Session, market: str) -> Optional[date]:
    """Earliest observation date of *any* evidence in this market: history before it is unknown, not zero."""
    v = db.scalar(select(func.min(func.coalesce(Evidence.published_at, Evidence.observed_at))).where(Evidence.market_code == market))
    return v.date() if v else None


def product_industry(db: Session, product_id: int) -> Optional[int]:
    from ..models import Category
    row = db.execute(select(Category.industry_id).join(ProductCategory, ProductCategory.category_id == Category.id)
                     .where(ProductCategory.product_id == product_id)).first()
    return row[0] if row else None


def rebuild_daily(db: Session, product_id: int, market: str, evs: list[Evidence]) -> dict[date, dict]:
    per: dict[date, dict] = defaultdict(lambda: {"m": 0, "outlets": set(), "eng": None, "retail": 0})
    for e in evs:
        d = per[_day(e)]
        d["m"] += 1
        d["outlets"].add(e.outlet or e.source_key)
        eng = e.engagement or {}
        if eng:
            d["eng"] = (d["eng"] or 0) + sum(float(v) for v in eng.values() if isinstance(v, (int, float)))
        if e.source_type == "RETAIL" or e.claim_type in RETAIL_CLAIMS:
            d["retail"] += 1
    db.execute(delete(ProductDailySignal).where(ProductDailySignal.product_id == product_id, ProductDailySignal.market_code == market))
    for day, d in per.items():
        db.add(ProductDailySignal(product_id=product_id, market_code=market, day=day, mentions=d["m"],
                                  independent_sources=len(d["outlets"]), engagement_total=d["eng"], retail_signals=d["retail"]))
    return per


def _count(evs: Iterable[Evidence], start: date, end: date) -> tuple[int, set]:
    n, outlets = 0, set()
    for e in evs:
        if start <= _day(e) < end:
            n += 1
            outlets.add(e.outlet or e.source_key)
    return n, outlets


def compute_product_market(db: Session, product: Product, market: str, today: Optional[date] = None) -> ProductMarketTrend:
    today = today or utcnow().date()
    th = get_setting(db, "thresholds", {}) or {}
    min_indep = th.get("min_independent_sources", 2)
    min_hist = th.get("early_min_history_days", 7)
    min_mentions = th.get("early_min_mentions", 5)
    ind = product_industry(db, product.id)
    evs_all = list(db.scalars(select(Evidence).where(Evidence.product_id == product.id, Evidence.market_code == market)))
    evs = [e for e in evs_all if not e.is_syndicated_copy]
    rebuild_daily(db, product.id, market, evs)
    tomorrow = today + timedelta(days=1)
    m30, o30 = _count(evs, today - timedelta(days=29), tomorrow)
    ed30 = [e for e in evs if e.source_type in ("EDITORIAL", "OFFICIAL") and _day(e) >= today - timedelta(days=29)]
    soc30 = [e for e in evs if e.source_type == "SOCIAL" and _day(e) >= today - timedelta(days=29)]
    ret30 = [e for e in evs if (e.source_type == "RETAIL" or e.claim_type in RETAIL_CLAIMS) and _day(e) >= today - timedelta(days=29)]
    ws = market_window_start(db, market)
    history_days = (today - ws).days + 1 if ws else 0
    l7, _ = _count(evs, today - timedelta(days=6), tomorrow)
    p7, _ = _count(evs, today - timedelta(days=13), today - timedelta(days=6))
    l3, o3 = _count(evs, today - timedelta(days=2), tomorrow)
    p3, _ = _count(evs, today - timedelta(days=5), today - timedelta(days=2))
    pp3, _ = _count(evs, today - timedelta(days=8), today - timedelta(days=5))
    l14, _ = _count(evs, today - timedelta(days=13), tomorrow)
    p14, _ = _count(evs, today - timedelta(days=27), today - timedelta(days=13))
    _, o7 = _count(evs, today - timedelta(days=6), tomorrow)

    from ..pipeline.trends import search_signal
    ss = search_signal(db, product.id, market, today)
    eng_total = sum(sum(v for v in (e.engagement or {}).values() if isinstance(v, (int, float))) for e in soc30)
    g7 = smoothed_growth(l7, p7) if history_days >= 14 else None
    comp = {
        "social": clamp(math.log10(eng_total + 1) / 7) if soc30 and eng_total > 0 else (clamp(len({e.outlet for e in soc30}) / 10) if soc30 else None),
        "search": (clamp(0.5 * ss["level"] / 100 + 0.5 * clamp((ss["growth"] + 1) / 3)) if ss and not ss.get("stale") else None),
        "editorial": clamp(math.log1p(len({e.outlet for e in ed30})) / math.log1p(8)) if ed30 else None,
        "retail": clamp(len(ret30) / 3) if ret30 else None,
        "velocity": clamp((g7 + 1) / 3) if g7 is not None else None,
        "diversity": clamp(len(o30) / 6) if o30 else None,
    }
    score, coverage = weighted(comp, weights_for(db, "trend", ind))
    if len(o30) >= 4 and coverage >= 0.5:
        conf = "HIGH"
    elif len(o30) >= min_indep and coverage >= 0.3:
        conf = "MEDIUM"
    else:
        conf = "LOW"
    upcoming = db.scalar(select(UpcomingRelease).where(UpcomingRelease.product_id == product.id, UpcomingRelease.market_code == market))
    if len(o30) < min_indep or score is None or coverage < th.get("min_coverage_for_status", 0.2):
        status = "INSUFFICIENT DATA"
    elif upcoming and upcoming.release_status not in ("RELEASED", "CANCELLED") and score >= 50:
        status = "UPCOMING HYPE"
    elif g7 is not None and comp["velocity"] >= 0.75 and score >= 45:
        status = "RISING FAST"
    elif score >= 70:
        status = "HOT NOW"
    elif g7 is not None and comp["velocity"] >= 0.66 and score >= 45:
        status = "RISING FAST"
    elif g7 is not None and g7 <= -0.4:
        status = "DECLINING"
    elif g7 is not None:
        status = "STABLE DEMAND"
    else:
        status = "INSUFFICIENT DATA"
    missing = [k for k, v in comp.items() if v is None]
    expl = [f"{m30} non-syndicated mentions from {len(o30)} independent sources in 30d ({', '.join(sorted(o30)[:5])}{'…' if len(o30) > 5 else ''})"]
    if g7 is not None:
        expl.append(f"7d mentions {l7} vs previous 7d {p7} (smoothed growth {g7:+.0%})")
    else:
        expl.append(f"growth not computed: market observation window {history_days}d < 14d")
    if ss and not ss.get("stale"):
        expl.append(f"Google Trends import (relative index, {ss['granularity'].lower()}): last {ss['n']} avg {ss['level']:.0f} vs previous {ss['prev']:.0f} ({ss['growth']:+.0%})")
    elif ss and ss.get("stale"):
        expl.append(f"Google Trends import is stale (last point {ss['last_day']}) - not used")
    if missing:
        expl.append("not observed / no configured source: " + ", ".join(missing))
    trend = db.scalar(select(ProductMarketTrend).where(ProductMarketTrend.product_id == product.id, ProductMarketTrend.market_code == market))
    if trend is None:
        trend = ProductMarketTrend(product_id=product.id, market_code=market, trend_status=status, confidence=conf)
        db.add(trend)
    trend.trend_score, trend.trend_status, trend.confidence, trend.coverage = score, status, conf, coverage
    trend.breakdown = {k: (round(v, 3) if v is not None else None) for k, v in comp.items()}
    trend.breakdown["search_growth_raw"] = round(ss["growth"], 3) if ss and not ss.get("stale") else None
    trend.explanation = "; ".join(expl)

    # ---------------- Early Signal ----------------
    if history_days < min_hist or m30 < min_mentions:
        trend.early_score = None
        trend.lifecycle_stage = "NEW SIGNAL — INSUFFICIENT HISTORY"
        trend.early_provisional = True
        trend.early_breakdown = {"provisional_mentions_30d": m30, "provisional_independent_sources": len(o30), "history_days": history_days,
                                 "mention_growth_3d": None, "mention_growth_7d": None, "mention_growth_14d": None, "acceleration": None}
        trend.early_explanation = f"Only {m30} mentions / {history_days}d of market history (need ≥{min_mentions} mentions and ≥{min_hist}d). Provisional."
    else:
        g3 = smoothed_growth(l3, p3)
        g3_prev = smoothed_growth(p3, pp3)
        acc = g3 - g3_prev
        g14 = smoothed_growth(l14, p14) if history_days >= 28 else None
        g7e = smoothed_growth(l7, p7) if history_days >= 14 else smoothed_growth(l3, p3)
        soc_recent = [e for e in soc30 if _day(e) >= today - timedelta(days=6)]
        soc_prev = [e for e in soc30 if today - timedelta(days=13) <= _day(e) < today - timedelta(days=6)]
        def _eng(lst):
            return sum(sum(v for v in (e.engagement or {}).values() if isinstance(v, (int, float))) for e in lst)
        ecomp = {
            "velocity": clamp((g7e + 1) / 3),
            "acceleration": clamp((acc + 1) / 2),
            "search_growth": clamp((ss["growth"] + 1) / 3) if ss and not ss.get("stale") else None,
            "diversity": clamp(len(o7) / 5) if o7 else 0.0,
            "engagement": clamp((smoothed_growth(_eng(soc_recent), _eng(soc_prev), 100) + 1) / 3) if soc_recent and soc_prev else None,
            "retail": clamp(len([e for e in ret30 if _day(e) >= today - timedelta(days=13)]) / 3) if ret30 else None,
        }
        escore, ecov = weighted(ecomp, weights_for(db, "early", ind))
        if m30 >= 30 and len(o30) >= 8:
            stage = "SATURATED" if g7e <= 0 else "MAINSTREAM"
        elif g7e <= -0.3:
            stage = "COOLING DOWN"
        elif escore is not None and escore >= 75 and len(o7) >= 3 and l7 >= 5:
            stage = "BREAKOUT"
        elif escore is not None and escore >= 60 and acc > 0:
            stage = "ACCELERATING"
        elif escore is not None and escore >= 45:
            stage = "EARLY RISING"
        else:
            stage = "NEW SIGNAL"
        trend.early_score, trend.lifecycle_stage, trend.early_provisional = escore, stage, False
        trend.early_breakdown = {**{k: (round(v, 3) if v is not None else None) for k, v in ecomp.items()},
                                 "search_growth_raw": trend.breakdown.get("search_growth_raw"),
                                 "mention_growth_3d": round(g3, 3), "mention_growth_7d": round(g7e, 3),
                                 "mention_growth_14d": round(g14, 3) if g14 is not None else None, "acceleration": round(acc, 3),
                                 "independent_sources_7d": len(o7), "history_days": history_days, "coverage": ecov,
                                 "mentions_last3": l3, "mentions_prev3": p3, "mentions_last7": l7, "mentions_prev7": p7}
        trend.early_explanation = (f"Last 3d {l3} vs prior 3d {p3} (growth {g3:+.0%}), acceleration {acc:+.2f}; "
                                   f"{len(o7)} independent sources in 7d; coverage {ecov:.0%}")
    trend.computed_at = utcnow()
    db.flush()
    return trend


def compute_release_confidence(db: Session, rel: UpcomingRelease) -> None:
    evs = list(db.scalars(select(Evidence).where(Evidence.product_id == rel.product_id, Evidence.market_code == rel.market_code,
                                                 Evidence.is_syndicated_copy.is_(False))))
    claims = defaultdict(set)
    for e in evs:
        claims[e.claim_type].add(e.outlet or e.source_key)
    official = claims.get("OFFICIALLY_CONFIRMED", set()) | claims.get("RETAILER_LISTED", set())
    rumorish = claims.get("RUMORED", set()) | claims.get("LEAKED", set())
    contradictions = bool(claims.get("CANCELLED")) and bool(official)
    if rel.release_status in ("OFFICIALLY CONFIRMED", "RETAILER LISTED", "RELEASED") and official:
        conf = "HIGH"
    elif len(rumorish | official) >= 3:
        conf = "MEDIUM"
    elif len(rumorish | official) == 2:
        conf = "LOW"
    else:
        conf = "UNVERIFIED"
    if contradictions and conf == "HIGH":
        conf = "MEDIUM"
    rel.rumor_confidence = conf
    today = utcnow().date()
    recent = [e for e in evs if _day(e) >= today - timedelta(days=13)]
    outlets = {e.outlet for e in recent}
    eng = sum(sum(v for v in (e.engagement or {}).values() if isinstance(v, (int, float))) for e in recent)
    hype_parts = {"mentions": clamp(math.log1p(len(recent)) / math.log1p(20)), "diversity": clamp(len(outlets) / 6),
                  "engagement": clamp(math.log10(eng + 1) / 7) if eng else None}
    rel.hype_score, _ = weighted(hype_parts, {"mentions": 40, "diversity": 40, "engagement": 20})


def record_changes(db: Session, product: Product, market: str, old: Optional[dict], trend: ProductMarketTrend, job_id: Optional[int],
                   had_new_evidence: bool) -> None:
    if not had_new_evidence or old is None:
        return
    fx = product.is_fixture
    if trend.trend_status != old["status"] and trend.trend_status in ("HOT NOW", "RISING FAST"):
        db.add(ChangeEvent(event_type=f"NEWLY_{trend.trend_status.replace(' ', '_')}", product_id=product.id, market_code=market,
                           detail=f"{old['status']} → {trend.trend_status}", job_id=job_id, is_fixture=fx))
    if trend.lifecycle_stage != old["stage"]:
        if trend.lifecycle_stage in ("ACCELERATING", "BREAKOUT", "EARLY RISING"):
            db.add(ChangeEvent(event_type=f"EARLY_{trend.lifecycle_stage.replace(' ', '_')}", product_id=product.id, market_code=market,
                               detail=f"{old['stage']} → {trend.lifecycle_stage}", job_id=job_id, is_fixture=fx))
        elif trend.lifecycle_stage == "COOLING DOWN":
            db.add(ChangeEvent(event_type="COOLING_DOWN", product_id=product.id, market_code=market,
                               detail=f"{old['stage']} → COOLING DOWN", job_id=job_id, is_fixture=fx))
    if old["score"] is not None and trend.trend_score is not None and abs(trend.trend_score - old["score"]) >= 15:
        db.add(ChangeEvent(event_type="SCORE_CHANGE", product_id=product.id, market_code=market,
                           detail=f"Trend score {old['score']:.0f} → {trend.trend_score:.0f}", job_id=job_id, is_fixture=fx))


def recompute_products(db: Session, product_ids: Iterable[int], job_id: Optional[int] = None,
                       new_evidence_ids: Optional[set[int]] = None) -> int:
    n = 0
    new_evidence_ids = new_evidence_ids or set()
    for pid in set(product_ids):
        product = db.get(Product, pid)
        if not product:
            continue
        for pm in db.scalars(select(ProductMarket).where(ProductMarket.product_id == pid)):
            prev = db.scalar(select(ProductMarketTrend).where(ProductMarketTrend.product_id == pid, ProductMarketTrend.market_code == pm.market_code))
            old = {"status": prev.trend_status, "stage": prev.lifecycle_stage, "score": prev.trend_score} if prev else None
            t = compute_product_market(db, product, pm.market_code)
            record_changes(db, product, pm.market_code, old, t, job_id, pid in new_evidence_ids)
            if old is None or old["status"] != t.trend_status or old["stage"] != t.lifecycle_stage or old["score"] != t.trend_score or pid in new_evidence_ids:
                db.add(TrendHistory(product_id=pid, market_code=pm.market_code, trend_score=t.trend_score, trend_status=t.trend_status,
                                    early_score=t.early_score, lifecycle_stage=t.lifecycle_stage, job_id=job_id))
            n += 1
        for rel in db.scalars(select(UpcomingRelease).where(UpcomingRelease.product_id == pid)):
            compute_release_confidence(db, rel)
    db.flush()
    return n


def recompute_all(db: Session) -> int:
    ids = [r[0] for r in db.execute(select(Product.id))]
    n = recompute_products(db, ids)
    compute_opportunities(db)
    return n


# ---------------------------------------------------------------- opportunities
def _covered(db: Session, market: str, cat_ids: list[int]) -> bool:
    q = select(MarketSignalCoverage.id).where(MarketSignalCoverage.market_code == market)
    if cat_ids:
        q = q.where((MarketSignalCoverage.category_id.in_(cat_ids)) | (MarketSignalCoverage.category_id.is_(None)))
    return db.scalar(q.limit(1)) is not None


def compute_opportunities(db: Session) -> int:
    presets = get_setting(db, "opportunity.presets", []) or []
    n = 0
    today = utcnow()
    for p in presets:
        src = [m for m in p.get("source_markets", []) if m]
        tgt = p.get("target_market")
        if not src or not tgt:
            continue
        pkey = f"{'+'.join(sorted(src))}>{tgt}"
        trends = list(db.scalars(select(ProductMarketTrend).where(ProductMarketTrend.market_code.in_(src + [tgt]))))
        by_prod: dict[int, dict[str, ProductMarketTrend]] = defaultdict(dict)
        for t in trends:
            by_prod[t.product_id][t.market_code] = t
        for pid, mk in by_prod.items():
            src_t = [mk[m] for m in src if m in mk]
            if not src_t:
                continue
            product = db.get(Product, pid)
            cat_ids = [r[0] for r in db.execute(select(ProductCategory.category_id).where(ProductCategory.product_id == pid))]
            ind = product_industry(db, pid)
            valid_src = [t for t in src_t if t.trend_status != "INSUFFICIENT DATA" and t.trend_score is not None]
            src_mom = (max(t.trend_score for t in valid_src) / 100) if valid_src else None
            tt = mk.get(tgt)
            if tt is not None:
                state = "OBSERVED"
            elif _covered(db, tgt, cat_ids):
                state = "NOT OBSERVED DESPITE COVERAGE"
            else:
                state = "INSUFFICIENT TARGET DATA"
            tgt_growth = None
            if tt is not None and not tt.early_provisional:
                g = (tt.early_breakdown or {}).get("mention_growth_7d")
                tgt_growth = clamp((g + 1) / 3) if g is not None else None
            if state == "OBSERVED" and tt.trend_score is not None and src_mom is not None:
                gap = clamp(1 - (tt.trend_score / 100) / max(src_mom, 0.01))
            elif state == "NOT OBSERVED DESPITE COVERAGE" and src_mom is not None:
                gap = 0.7  # limited evidence of a gap, never 'verified absent'
            else:
                gap = None
            purchase_in_target = db.scalar(select(ProductLink.id).where(ProductLink.product_id == pid, ProductLink.is_purchase_url.is_(True),
                                                                        ProductLink.market_code == tgt))
            retail_gap = 0.0 if purchase_in_target else None
            validated = [t for t in src_t if t.trend_status != "INSUFFICIENT DATA"]
            age_days = (today - product.first_detected).days
            sg = [(t.breakdown or {}).get("search_growth_raw") for t in src_t]
            sg = [g for g in sg if g is not None]
            comp = {"source_momentum": src_mom, "target_early_growth": tgt_growth, "market_gap": gap,
                    "search_acceleration": clamp((max(sg) + 1) / 3) if sg else None,
                    "retail_gap": retail_gap, "multi_market": len(validated) / len(src) if validated else None,
                    "freshness": 1.0 if age_days <= 14 else 0.6 if age_days <= 30 else 0.3}
            score, cov = weighted(comp, weights_for(db, "opportunity", ind))
            if src_mom is None or cov < 0.25:
                score = None  # too little evidence: never present a score built from 1-2 weak dimensions
            upcoming = db.scalar(select(UpcomingRelease).where(UpcomingRelease.product_id == pid, UpcomingRelease.market_code.in_(src + [tgt]),
                                                               UpcomingRelease.release_status.not_in(["RELEASED", "CANCELLED"])))
            if src_mom is None:
                otype = "EMERGING TREND"
            elif state == "OBSERVED" and tt.trend_score is not None and tt.trend_score >= 70:
                otype = "SATURATED TREND"
            elif upcoming is not None:
                otype = "UPCOMING OPPORTUNITY"
            elif len(validated) >= 2 and src_mom >= 0.6:
                otype = "CROSS-MARKET BREAKOUT"
            elif state == "NOT OBSERVED DESPITE COVERAGE" and src_mom >= 0.5:
                otype = "MARKET GAP"
            elif state == "OBSERVED":
                otype = "EARLY MARKET OPPORTUNITY"
            else:
                otype = "EMERGING TREND"
            conf = "HIGH" if cov >= 0.6 and len(validated) >= 2 else "MEDIUM" if cov >= 0.4 and validated else "LOW"
            risk = "HIGH" if state == "INSUFFICIENT TARGET DATA" or conf == "LOW" else "MEDIUM" if conf == "MEDIUM" else "LOW"
            expl = [f"source markets with data: {', '.join(t.market_code for t in src_t)}",
                    f"target {tgt}: {state.lower()}"]
            if state == "INSUFFICIENT TARGET DATA":
                expl.append("missing target data is NOT treated as low popularity")
            if state == "NOT OBSERVED DESPITE COVERAGE":
                expl.append("target was scanned but product not observed (limited evidence, not verified absence)")
            row = db.scalar(select(OpportunityScore).where(OpportunityScore.product_id == pid, OpportunityScore.preset_key == pkey))
            if row is None:
                row = OpportunityScore(product_id=pid, preset_key=pkey, target_market=tgt, opportunity_type=otype, confidence=conf,
                                       risk_level=risk, target_data_state=state)
                db.add(row)
                if otype in ("CROSS-MARKET BREAKOUT", "MARKET GAP", "EARLY MARKET OPPORTUNITY", "UPCOMING OPPORTUNITY"):
                    db.add(ChangeEvent(event_type="NEW_OPPORTUNITY", product_id=pid, market_code=tgt,
                                       detail=f"{otype} {pkey}", is_fixture=product.is_fixture))
            row.source_markets, row.target_market, row.score, row.opportunity_type = src, tgt, score, otype
            row.breakdown = {k: (round(v, 3) if v is not None else None) for k, v in comp.items()}
            row.confidence, row.coverage, row.risk_level, row.target_data_state = conf, cov, risk, state
            row.explanation = "; ".join(expl)
            row.computed_at = utcnow()
            n += 1
    db.flush()
    return n
