"""Rule-based product entity & claim extraction (no paid AI dependency).

Extraction is deliberately conservative: a mention needs a known brand plus at least one model token.
Everything returned is what literally appears in the source text; nothing is invented."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from ..db import utcnow as _utcnow
from typing import Iterable, Optional

QUOTE_MAP = {"“": '"', "”": '"', "„": '"', "″": '"', "‘": "'", "’": "'", " ": " ",
             "–": "-", "—": " - ", "«": '"', "»": '"', "「": '"', "」": '"'}

STOP_WORDS = {
    "release", "releases", "released", "releasing", "drop", "drops", "dropping", "restock", "restocks", "restocking",
    "official", "officially", "images", "image", "photos", "first", "look", "looks", "review", "reviewed", "reviews",
    "hands-on", "launch", "launches", "launched", "launching", "unveiled", "unveils", "announced", "announces",
    "arrives", "arriving", "coming", "is", "are", "was", "will", "gets", "get", "got", "leak", "leaks", "leaked",
    "rumor", "rumors", "rumored", "rumour", "rumoured", "reportedly", "in", "on", "at", "for", "with", "and", "or",
    "the", "a", "an", "to", "from", "by", "now", "available", "date", "dates", "info", "details", "price", "pricing",
    "surfaces", "surface", "returns", "return", "debuts", "debut", "teased", "teases", "revealed", "reveals",
    "delayed", "postponed", "cancelled", "canceled", "confirmed", "expected", "could", "may", "might", "deal", "deals",
    "sale", "vs", "versus", "where", "how", "why", "what", "this", "that", "these", "its", "it's", "has", "have",
    "set", "sets", "hits", "shelves", "stock", "listed", "listing", "spotted", "early", "next", "week", "weekend",
    "today", "tomorrow", "drops", "update", "updated", "colorway", "colorways", "pack", "detailed", "closer",
    "출시", "발매", "공개", "예정", "리뷰", "가격", "発売", "発表", "予約", "登場", "新色", "復刻", "レビュー", "価格", "が発売",
    "发布", "发售", "上市", "新品", "评测",
    "apparel", "merch", "merchandise",
    # title-case headline verbs / fillers ("The Air Jordan 1 Becomes A Kitten Heel")
    "becomes", "become", "brings", "bring", "shows", "show", "showcases", "celebrates", "honors", "pays", "takes", "joins",
    "adds", "offers", "receives", "goes", "lands", "makes", "meets", "opens", "rolls", "shares", "starts", "turns", "comes",
    "appears", "emerges", "features", "highlights", "includes", "introduces", "previews", "presents", "says", "sees", "gives",
    "hit", "hits", "inspired", "inspires", "dressed", "covered", "wrapped", "arrive", "unveil", "confirms", "plans", "expands",
    "up", "close", "under", "all", "three", "two", "more", "most", "best", "top", "why", "here's", "here", "every", "our",
    "your", "their", "his", "her", "first", "last", "latest", "official", "exclusive", "limited", "vs.", "ra", "mắt", "lộ", "diện", "chính", "thức", "giá", "mở", "bán", "về", "có",
}
ALLOWED_LOWER = {"x", "of", "de", "ii", "iii", "iv", "mini", "pro", "max", "plus", "ultra", "lite", "se", "og", "sp", "low", "mid", "high"}
MAX_NAME_TOKENS = 9
# model spans made only of these words are not products (apps, events, corporate news)
GENERIC_MODEL_WORDS = {"snkrs", "app", "apps", "store", "stores", "day", "days", "sale", "outlet", "company", "inc", "ceo",
                       "earnings", "stock", "shares", "event", "events", "keynote", "wwdc", "x", "ai", "black", "friday",
                       "cyber", "monday", "collection", "news", "brand", "group", "family", "originals", "running",
                       "basketball", "football", "soccer", "lab", "labs", "community", "fans", "fan", "member", "members", "court",
                       "earnings", "ceo", "ads", "deal", "deals", "sale", "prime", "day", "street", "sport", "retros", "brand",
                       "colorways", "collection", "program", "line", "lineup", "family", "series"}

SKU_PATTERNS = {
    "nike": [r"\b[A-Z]{2}\d{4}-\d{3}\b", r"\b\d{6}-\d{3}\b"],
    "air jordan": [r"\b[A-Z]{2}\d{4}-\d{3}\b", r"\b\d{6}-\d{3}\b"],
    "adidas": [r"\b[A-Z]{1,2}\d{4,5}\b"],
    "new balance": [r"\b[MUWBG][A-Z]{0,2}\d{3,4}[A-Z]{2,4}\d?\b"],
    "asics": [r"\b1[012]\d{2}[A-Z]\d{3}[.\-]\d{3}\b"],
    "lego": [r"\b\d{5}\b"],
    "*": [r"\b[A-Z]{2}\d{4}-\d{3}\b"],
}

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
SEASONS = {"spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12, "holiday": 11}
RELEASE_CONTEXT = r"(?:releas\w*|drop\w*|launch\w*|arriv\w*|available|coming|debut\w*|hits?\s+shelves|on\s+sale|ships?|out)"

CLAIM_RULES = [
    ("CANCELLED", r"\b(cancel+ed|scrapped|no longer releasing)\b"),
    ("DELAYED", r"\b(delayed|postponed|pushed back|new release date)\b"),
    ("LEAKED", r"\b(leak|leaks|leaked|renders?|dummy units?)\b|リーク|유출"),
    ("RUMORED", r"\b(rumou?r\w*|reportedly|tipped|speculat\w*|allegedly|could launch|might|may launch)\b|tin đồn|噂|루머|소문"),
    ("RELEASED", r"\b(out now|available now|now available|released today|hits shelves|on sale now|in stores now)\b"),
    ("RETAILER_LISTED", r"\b(listed (on|at|by)|retailer listing|pre-?order\w*|preorder\w*)\b"),
    ("OFFICIALLY_CONFIRMED", r"\b(official(ly)?|announc\w*|unveil\w*|confirm\w*|release date|launch\w* on|will release|press release)\b|chính thức|公式|공식"),
    ("REVIEW", r"\b(review|reviewed|hands-on|tested)\b"),
]
CURRENCY = {"$": "USD", "us$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW", "₫": "VND", "c$": "CAD", "a$": "AUD"}


@dataclass
class Mention:
    brand: str
    name: str  # includes brand, as written
    model_variant: Optional[str] = None
    sku: Optional[str] = None
    claim_type: str = "MENTION"
    release_date_text: Optional[str] = None
    release_date: Optional[date] = None
    date_precision: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    matched_text: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class BrandEntry:
    name: str
    aliases: list[str]


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for k, v in QUOTE_MAP.items():
        s = s.replace(k, v)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# common English words that are also brands: only matched when capitalised exactly as written
AMBIGUOUS_BRANDS = {"nothing", "on", "google", "apple", "echo", "surface", "legion", "ninja", "stanley", "palace", "brooks",
                    "honor", "beats", "meta", "valve", "marshall", "amazon", "vans", "supreme", "crocs", "patagonia", "essence"}


def _brand_patterns(brands: Iterable[BrandEntry]):
    pats = []
    for b in brands:
        names = list(b.aliases)
        if b.name.lower() not in {"nothing", "on", "google"}:  # too ambiguous alone: only their product-line aliases count
            names.append(b.name)
        for alias in names:
            if not alias:
                continue
            case_sensitive = len(alias) <= 3 or alias.lower() in AMBIGUOUS_BRANDS
            flags = 0 if case_sensitive else re.IGNORECASE
            pats.append((len(alias), re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", flags), b.name, alias))
    pats.sort(key=lambda t: -t[0])
    return pats


_TOKEN_RE = re.compile(r'"[^"]{1,60}"|\'[^\']{2,40}\'(?=\s|$|[,.:;!?)])|[\w][\w\-\.\'\+/&]*|[^\w\s]', re.UNICODE)


def _is_model_token(tok: str) -> bool:
    if any(ch.isdigit() for ch in tok):
        return True
    if tok.lower() in ALLOWED_LOWER:
        return True
    if any(ch.isupper() for ch in tok):
        return True
    # CJK / non-latin scripts: accept (names are often in local script)
    return any(ord(ch) > 0x2E80 for ch in tok)


def find_skus(text: str, brand: str) -> list[str]:
    pats = SKU_PATTERNS.get(brand.lower(), []) + ([] if brand.lower() in SKU_PATTERNS else SKU_PATTERNS["*"])
    out: list[str] = []
    for p in pats:
        for m in re.finditer(p, text):
            if m.group(0) not in out:
                out.append(m.group(0))
    return out


def _parse_span(after: str, sku_set: set[str]) -> tuple[list[str], Optional[str], Optional[str]]:
    tokens, variant, sku = [], None, None
    for m in _TOKEN_RE.finditer(after):
        tok = m.group(0)
        if tok.startswith('"') or (tok.startswith("'") and len(tok) > 3 and tok.endswith("'")):
            if tokens or variant is None:
                variant = tok.strip("\"'").strip()
            # a colorway nickname closes the model name; allow a trailing SKU
            rest = after[m.end():m.end() + 30]
            for s in sku_set:
                if s in rest:
                    sku = s
            break
        if tok in sku_set:
            sku = tok
            if not tokens:  # e.g. "LEGO 10316 Rivendell": set number is part of the name
                tokens.append(tok)
                continue
            break
        low = tok.lower()
        if low in STOP_WORDS or not re.match(r"[\w]", tok):
            if tok in ("'",) or (tok == "-" and tokens and False):
                continue
            break
        if not _is_model_token(tok) or re.search(r"[\u3040-\u309f]", tok):  # hiragana = Japanese grammar, not a model name
            break
        tokens.append(tok.rstrip(".,'"))
        if len(tokens) >= MAX_NAME_TOKENS:
            break
    return tokens, variant, sku


def parse_release_date(text: str, published: Optional[datetime]) -> tuple[Optional[str], Optional[date], Optional[str]]:
    t = text
    ref_year = (published or _utcnow()).year
    ctx = RELEASE_CONTEXT + r"[^.]{0,40}?"
    m = re.search(ctx + r"\b(Q[1-4])\s*(?:of\s*)?(20\d{2})\b", t, re.I)
    if m:
        q = int(m.group(1)[1]); y = int(m.group(2))
        return f"Q{q} {y}", date(y, 3 * q - 2, 1), "QUARTER"
    m = re.search(ctx + r"\b(spring|summer|fall|autumn|winter|holiday)\s+(?:season\s+)?(20\d{2})\b", t, re.I)
    if m:
        y = int(m.group(2)); s = m.group(1).lower()
        return f"{s.title()} {y}", date(y, SEASONS[s], 1), "SEASON"
    month_alt = "|".join(sorted(MONTHS, key=len, reverse=True))
    m = re.search(ctx + r"\b(" + month_alt + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b", t, re.I)
    if m:
        mon = MONTHS[m.group(1).lower()]; d = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else ref_year
        if not m.group(3) and published and mon < published.month - 1:
            y += 1
        try:
            dt = date(y, mon, d)
        except ValueError:
            return None, None, None
        label = f"{dt.isoformat()}" + ("" if m.group(3) else " (year inferred from publication date)")
        return label, dt, "DAY"
    m = re.search(ctx + r"\b(" + month_alt + r")\.?\s+(20\d{2})\b", t, re.I)
    if m:
        mon = MONTHS[m.group(1).lower()]; y = int(m.group(2))
        return f"{y}-{mon:02d}", date(y, mon, 1), "MONTH"
    m = re.search(ctx + r"\bin\s+(20\d{2})\b", t, re.I)
    if m:
        y = int(m.group(1))
        return str(y), date(y, 1, 1), "YEAR"
    if re.search(r"\b(TBA|TBD|to be announced)\b", t):
        return "TBA", None, "TBA"
    return None, None, None


def parse_price(text: str) -> tuple[Optional[float], Optional[str]]:
    m = re.search(r"(US\$|C\$|A\$|\$|€|£|¥|₩|₫)\s?(\d{1,3}(?:[,.]\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)", text)
    if not m:
        return None, None
    raw = m.group(2).replace(",", "")
    try:
        return float(raw), CURRENCY.get(m.group(1).lower(), None)
    except ValueError:
        return None, None


def classify_claim(text: str) -> str:
    low = text.lower()
    for claim, pat in CLAIM_RULES:
        if re.search(pat, low, re.I):
            return claim
    return "MENTION"


def extract_mentions(title: str, summary: str, brands: list[BrandEntry], published: Optional[datetime] = None,
                     max_mentions: int = 3) -> list[Mention]:
    title_n = normalize_text(title)
    body_n = normalize_text(summary)[:1500]
    full = f"{title_n}. {body_n}"
    out: list[Mention] = []
    seen_keys: set[str] = set()
    used_spans: list[tuple[int, int]] = []
    for _, pat, brand, alias in _brand_patterns(brands):
        for source_text in (title_n,):  # product identity comes from the title; body only supports details
            for m in pat.finditer(source_text):
                if any(s <= m.start() < e for s, e in used_spans):
                    continue
                skus = set(find_skus(full, brand))
                tokens, variant, sku = _parse_span(source_text[m.end():], skus)
                if not tokens or all(t.lower() in GENERIC_MODEL_WORDS for t in tokens):
                    continue
                used_spans.append((m.start(), m.end() + len(" ".join(tokens)) + 1))
                name = f"{source_text[m.start():m.end()]} {' '.join(tokens)}".strip()
                if not sku and len(skus) == 1:
                    sku = next(iter(skus))
                key = (brand + name + (variant or "")).lower()
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                claim = classify_claim(full)
                rd_text, rd, prec = parse_release_date(full, published)
                price, cur = parse_price(full)
                out.append(Mention(brand=brand, name=name, model_variant=variant, sku=sku, claim_type=claim,
                                   release_date_text=rd_text, release_date=rd, date_precision=prec,
                                   price=price, currency=cur, matched_text=title_n))
                if len(out) >= max_mentions:
                    return out
    return out
