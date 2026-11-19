from app.pipeline.canonical import Candidate, canonical_key, match

C = [Candidate(1, "Air Jordan", "Air Jordan 4", "Bred Reimagined", "FV5029-006"),
     Candidate(2, "Apple", "Apple iPhone 17 Pro", None, None),
     Candidate(3, "Air Jordan", "Air Jordan 4", None, None)]


def test_same_sku_merges():
    assert match("Air Jordan", "Jordan 4 Retro", "Bred", "FV5029-006", C)[:2] == (1, "SKU")


def test_alias_spelling_merges_without_sku():
    assert match("Air Jordan", "Jordan 4 Retro Bred Reimagined", None, None, C)[:2] == (1, "EXACT")


def test_conflicting_sku_never_merges():
    assert match("Air Jordan", "Air Jordan 4", "Bred Reimagined", "AB1234-001", C)[0] is None


def test_different_model_number_never_merges():
    assert match("Apple", "Apple iPhone 16 Pro", None, None, C)[0] is None
    assert match("Apple", "Apple iPhone 17 Pro Max", None, None, C)[0] is None  # Pro Max is a different product


def test_model_level_vs_colorway_are_distinct():
    mid, verdict, _ = match("Air Jordan", "Air Jordan 4", "Military Black", None, C)
    assert mid is None


def test_key_is_stable():
    assert canonical_key("Nike", "Nike Dunk Low", "Panda", None) == canonical_key("Nike", "NIKE Dunk Low", "panda", None)
