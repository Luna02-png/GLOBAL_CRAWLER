from datetime import datetime

from app.pipeline.extract import BrandEntry, extract_mentions, parse_release_date
from app.seed import BRANDS

B = [BrandEntry(n, a) for n, a, _, _ in BRANDS]


def one(title, **kw):
    ms = extract_mentions(title, kw.get("summary", ""), B, kw.get("published", datetime(2026, 11, 1)))
    assert ms, f"nothing extracted from {title!r}"
    return ms[0]


def test_sneaker_with_colorway_and_sku():
    m = one('Air Jordan 4 “Bred Reimagined” FV5029-006 Releases February 17th')
    assert (m.brand, m.name, m.model_variant, m.sku) == ("Air Jordan", "Air Jordan 4", "Bred Reimagined", "FV5029-006")
    assert m.date_precision == "DAY" and "inferred" in m.release_date_text  # year was not written: flagged


def test_adidas_and_new_balance_skus():
    assert one('adidas Samba OG "Cream White" IE3439 restocks').sku == "IE3439"
    assert one('New Balance 9060 "Sea Salt" U9060HSA arrives May 2027').sku == "U9060HSA"


def test_electronics_model_and_claims():
    m = one("Samsung Galaxy S26 Ultra leak reveals new design, could launch in Q1 2027")
    assert m.name == "Samsung Galaxy S26 Ultra" and m.claim_type == "LEAKED"
    assert (m.release_date_text, m.date_precision) == ("Q1 2027", "QUARTER")
    m = one("Sony WH-1000XM6 headphones launch at $449")
    assert m.name == "Sony WH-1000XM6" and (m.price, m.currency) == (449.0, "USD")


def test_lego_set_number_kept_in_name():
    m = one("LEGO 10316 Rivendell set review")
    assert m.sku == "10316" and m.name.startswith("LEGO 10316")


def test_generic_brand_mentions_are_not_products():
    assert extract_mentions("This weekend on Nike SNKRS: what to know", "", B) == []
    assert extract_mentions("Nothing beats a good pair of shoes", "", B) == []
    assert extract_mentions("Apple reports record earnings", "", B) == []


def test_uncertain_dates_are_never_turned_into_days():
    assert parse_release_date("expected to release in Spring 2027", None)[2] == "SEASON"
    assert parse_release_date("launching sometime in 2027", None)[:3:2] == ("2027", "YEAR")
    assert parse_release_date("release date TBA", None)[2] == "TBA"
    assert parse_release_date("no date words here 2027", None) == (None, None, None)


def test_rumor_vs_official():
    assert one("Apple iPhone 18 Pro rumored to get 48MP telephoto").claim_type == "RUMORED"
    assert one("Apple iPhone 18 Pro officially announced").claim_type == "OFFICIALLY_CONFIRMED"
