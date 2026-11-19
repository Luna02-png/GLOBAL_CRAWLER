"""Import Google Trends CSV files that the user downloaded from trends.google.com (the ⬇ export button).
Values are a *relative* 0-100 index for that export's term/geo/period - never an absolute search volume."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Market, Product, ProductAlias, ProductMarket, SearchInterest

DATE_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?")


@dataclass
class Series:
    term: str
    geo_label: Optional[str]
    points: list[tuple[date, float]] = field(default_factory=list)


@dataclass
class ParsedTrends:
    granularity: str
    series: list[Series]


def _parse_date(cell: str) -> Optional[date]:
    m = DATE_RE.match(cell.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _value(cell: str) -> Optional[float]:
    c = cell.strip()
    if c == "":
        return None
    if c.startswith("<"):
        return 0.5  # Google shows "<1" for values below 1
    try:
        return float(c.replace(",", "."))
    except ValueError:
        return None


def parse_trends_csv(text: str) -> ParsedTrends:
    text = text.lstrip("﻿")
    rows = [r for r in csv.reader(io.StringIO(text))]
    first_data = next((i for i, r in enumerate(rows) if r and _parse_date(r[0])), None)
    if first_data is None or first_data == 0:
        raise ValueError("No dated rows found - is this a Google Trends 'Interest over time' CSV?")
    header = rows[first_data - 1]
    series: list[Series] = []
    for label in header[1:]:
        m = re.match(r"^(.*?):\s*\((.*)\)\s*$", label.strip())
        series.append(Series(term=(m.group(1) if m else label).strip(), geo_label=(m.group(2).strip() if m else None)))
    dates: list[date] = []
    for r in rows[first_data:]:
        if not r or not _parse_date(r[0]):
            continue
        d = _parse_date(r[0])
        dates.append(d)
        for i, s in enumerate(series, start=1):
            if i < len(r):
                v = _value(r[i])
                if v is not None:
                    s.points.append((d, v))
    gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
    step = gaps[len(gaps) // 2] if gaps else 7
    gran = "DAY" if step <= 1 else "WEEK" if step <= 8 else "MONTH"
    return ParsedTrends(granularity=gran, series=[s for s in series if s.points])


def guess_market(db: Session, geo_label: Optional[str]) -> Optional[str]:
    if not geo_label:
        return None
    if geo_label.lower() in ("worldwide", "toàn cầu", "global"):
        return "GLOBAL"
    for m in db.scalars(select(Market)):
        if m.name.lower() == geo_label.lower() or m.code.lower() == geo_label.lower():
            return m.code
    return None


def suggest_products(db: Session, term: str, limit: int = 5) -> list[dict]:
    exact = [{"product_id": p.id, "name": p.name, "score": 100} for p in db.scalars(select(Product))
             if str((p.attributes or {}).get("trends_term", "")).strip().lower() == term.strip().lower()]
    if exact:
        return exact[:limit]  # term saved by the "Open Google Trends" button
    names: dict[str, int] = {}
    for pid, name in db.execute(select(Product.id, Product.name)):
        names[name] = pid
    for pid, alias in db.execute(select(ProductAlias.product_id, ProductAlias.alias)):
        names.setdefault(alias, pid)
    out, seen = [], set()
    for name, score, _ in process.extract(term, list(names), scorer=fuzz.WRatio, limit=limit * 2):
        pid = names[name]
        if pid in seen or score < 60:
            continue
        seen.add(pid)
        out.append({"product_id": pid, "name": name, "score": round(score)})
        if len(out) == limit:
            break
    return out


def preview(db: Session, text: str) -> dict:
    parsed = parse_trends_csv(text)
    return {"granularity": parsed.granularity, "series": [
        {"term": s.term, "geo_label": s.geo_label, "market_guess": guess_market(db, s.geo_label), "points": len(s.points),
         "first": s.points[0][0].isoformat(), "last": s.points[-1][0].isoformat(),
         "latest_values": [v for _, v in s.points[-4:]], "suggestions": suggest_products(db, s.term)} for s in parsed.series]}


def import_csv(db: Session, text: str, mapping: list[dict], file_name: Optional[str] = None) -> dict:
    """mapping: [{term, product_id, market_code}] - terms without a product_id are skipped."""
    parsed = parse_trends_csv(text)
    by_term = {s.term: s for s in parsed.series}
    batch_time = utcnow()
    stored, products = 0, set()
    for mp in mapping:
        s = by_term.get(mp.get("term"))
        pid, mc = mp.get("product_id"), mp.get("market_code")
        if not s or not pid or not mc or db.get(Product, pid) is None:
            continue
        if db.get(ProductMarket, (pid, mc)) is None:
            db.add(ProductMarket(product_id=pid, market_code=mc, attribution="SEARCH_IMPORT", confidence="MEDIUM"))
        for d, v in s.points:
            row = db.scalar(select(SearchInterest).where(SearchInterest.product_id == pid, SearchInterest.market_code == mc,
                                                         SearchInterest.term == s.term, SearchInterest.day == d))
            if row is None:
                row = SearchInterest(product_id=pid, market_code=mc, term=s.term, day=d, value=v, granularity=parsed.granularity)
                db.add(row)
            row.value, row.granularity, row.source_file, row.imported_at = v, parsed.granularity, file_name, batch_time
            stored += 1
        products.add(pid)
    db.flush()
    return {"points": stored, "product_ids": sorted(products), "granularity": parsed.granularity}


def search_signal(db: Session, product_id: int, market: str, today: Optional[date] = None) -> Optional[dict]:
    """Level and growth from the most recent import batch (exports are scaled independently, so batches are not mixed)."""
    rows = list(db.scalars(select(SearchInterest).where(SearchInterest.product_id == product_id, SearchInterest.market_code == market)))
    if not rows:
        return None
    latest = max(r.imported_at for r in rows)
    rows = [r for r in rows if r.imported_at == latest]
    per_day: dict[date, list[float]] = {}
    for r in rows:
        per_day.setdefault(r.day, []).append(r.value)
    pts = sorted((d, sum(v) / len(v)) for d, v in per_day.items())
    gran = rows[0].granularity
    n = {"DAY": 7, "WEEK": 4, "MONTH": 3}.get(gran, 4)
    today = today or utcnow().date()
    stale_after = {"DAY": 10, "WEEK": 35, "MONTH": 75}.get(gran, 35)
    last_day = pts[-1][0]
    if (today - last_day).days > stale_after:
        return {"stale": True, "last_day": last_day.isoformat(), "granularity": gran}
    if len(pts) < 2 * n:
        n = max(1, len(pts) // 2)
    recent = [v for _, v in pts[-n:]]
    prev = [v for _, v in pts[-2 * n:-n]] or recent
    lv, pv = sum(recent) / len(recent), sum(prev) / len(prev)
    growth = (lv + 5) / (pv + 5) - 1  # additive smoothing on the 0-100 index
    return {"stale": False, "level": lv, "prev": pv, "growth": growth, "granularity": gran, "n": n,
            "last_day": last_day.isoformat(), "terms": sorted({r.term for r in rows})}
