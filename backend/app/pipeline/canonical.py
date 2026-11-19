"""Canonical product identity. Similar text alone does not prove identity: automatic merges require
matching SKU, or an identical significant-token set with identical numbers and no conflicting SKU."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

from rapidfuzz import fuzz

FILLER = {"retro", "og", "shoe", "shoes", "sneaker", "sneakers", "the", "edition", "colorway", "wmns", "womens",
          "women's", "mens", "men's", "gs", "kids", "new", "all", "official", "headphones", "earbuds", "smartphone",
          "phone", "set", "figure", "series"}
BRAND_WORDS = {"air jordan": {"air", "jordan", "nike", "aj"}, "new balance": {"new", "balance", "nb"},
               "pop mart": {"pop", "mart"}}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode() or (s or "")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s or "").lower().replace("'", "")
    return [t for t in re.split(r"[^\w]+", s) if t]


def significant_tokens(brand: str, name: str, variant: Optional[str]) -> set[str]:
    bw = BRAND_WORDS.get((brand or "").lower(), set(tokens(brand or "")))
    toks = set(tokens(name)) | set(tokens(variant or ""))
    return {t for t in toks if t not in bw and t not in FILLER}


def numbers(toks: Iterable[str]) -> set[str]:
    return {t for t in toks if any(c.isdigit() for c in t)}


def canonical_key(brand: str, name: str, variant: Optional[str], sku: Optional[str]) -> str:
    b = slug(brand or "unknown")
    if sku:
        return f"{b}|sku|{sku.upper()}"
    sig = sorted(significant_tokens(brand, name, variant))
    return f"{b}|name|{'-'.join(sig)}"


@dataclass
class Candidate:
    id: int
    brand: str
    name: str
    variant: Optional[str]
    sku: Optional[str]


def match(brand: str, name: str, variant: Optional[str], sku: Optional[str],
          candidates: Iterable[Candidate]) -> tuple[Optional[int], str, Optional[int]]:
    """Return (matched_id, verdict, possible_id). verdict: SKU / EXACT / POSSIBLE / NONE."""
    sig = significant_tokens(brand, name, variant)
    best_possible, best_score = None, 0.0
    for c in candidates:
        if (c.brand or "").lower() != (brand or "").lower():
            continue
        if sku and c.sku:
            if sku.upper() == c.sku.upper():
                return c.id, "SKU", None
            continue  # conflicting SKUs are never the same product
        csig = significant_tokens(c.brand, c.name, c.variant)
        if not sig or not csig:
            continue
        if numbers(sig) != numbers(csig):
            continue
        if sig == csig:
            return c.id, "EXACT", None
        score = fuzz.token_sort_ratio(" ".join(sorted(sig)), " ".join(sorted(csig)))
        if score >= 85 and score > best_score:
            best_possible, best_score = c.id, score
    return None, ("POSSIBLE" if best_possible else "NONE"), best_possible
