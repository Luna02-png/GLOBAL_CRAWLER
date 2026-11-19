import csv
import io

from openpyxl import load_workbook

from app.export import image_formula, is_valid_image_url, to_csv, to_tsv, to_xlsx

COLS = [("name", "Product Name"), ("image_url", "Image"), ("url", "Best URL"), ("note", "Note"), ("score", "Score")]
ROWS = [
    {"name": 'Air Jordan 4 "Bred"', "image_url": "https://cdn.example.com/aj4.jpg", "url": "https://a.example/x?y=1&z=2",
     "note": "line1\nline2\twith tab", "score": 71.25},
    {"name": "=HYPERLINK(\"evil\")", "image_url": "not a url", "url": None, "note": None, "score": None},
]


def parse_tsv(text):
    """Parse TSV the way Google Sheets does (quoted fields may contain tabs/newlines)."""
    return list(csv.reader(io.StringIO(text), delimiter="\t"))


def test_tsv_alignment_quotes_newlines_nulls():
    t = to_tsv(ROWS, COLS, headers=True)
    grid = parse_tsv(t)
    assert grid[0] == [l for _, l in COLS]
    assert len(grid) == 3 and all(len(r) == len(COLS) for r in grid)
    assert grid[1][0] == 'Air Jordan 4 "Bred"'
    assert grid[1][3] == "line1\nline2\twith tab"
    assert grid[1][2] == "https://a.example/x?y=1&z=2"  # URL stays a plain copyable string
    assert grid[2][2] == "" and grid[2][4] == ""  # null cells keep column boundaries


def test_formula_injection_neutralised_but_image_formula_allowed():
    grid = parse_tsv(to_tsv(ROWS, COLS, headers=False, image_mode="formula"))
    assert grid[1][0].startswith("'=")
    assert grid[0][1] == '=IMAGE("https://cdn.example.com/aj4.jpg")'
    assert grid[1][1] == "not a url"  # invalid image URL never becomes a formula


def test_image_url_validation():
    assert is_valid_image_url("https://x.com/a/b.webp?w=300")
    assert is_valid_image_url("https://x.com/img?id=3&format=png")
    assert not is_valid_image_url("https://x.com/product/123")
    assert not is_valid_image_url("javascript:alert(1).png")
    assert image_formula('https://x.com/a"b.jpg') == '=IMAGE("https://x.com/a""b.jpg")'


def test_csv_and_xlsx_roundtrip(tmp_path):
    c = to_csv(ROWS, COLS)
    assert c.startswith("﻿")
    grid = list(csv.reader(io.StringIO(c.lstrip("﻿"))))
    assert grid[1][3] == "line1\nline2\twith tab"
    data = to_xlsx(ROWS, COLS, image_mode="formula")
    p = tmp_path / "x.xlsx"
    p.write_bytes(data)
    ws = load_workbook(p).active
    assert ws["A1"].value == "Product Name"
    assert ws["B2"].value == '=IMAGE("https://cdn.example.com/aj4.jpg")'
    assert ws["C2"].value == "https://a.example/x?y=1&z=2"
    assert ws["E2"].value == 71.25
    assert ws["C3"].value is None
