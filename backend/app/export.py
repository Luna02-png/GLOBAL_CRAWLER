"""Google-Sheets-safe TSV, CSV and XLSX export. URLs are always plain strings."""
from __future__ import annotations

import csv
import io
import re
from typing import Iterable, Optional
from urllib.parse import urlparse

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp)(\?|#|$)", re.I)
FORMULA_START = ("=", "+", "-", "@")


def is_valid_image_url(url: Optional[str]) -> bool:
    if not url or any(ch.isspace() for ch in url):
        return False
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    return bool(IMAGE_EXT.search(p.path)) or bool(re.search(r"(^|&)(format|fm|ext)=(jpe?g|png|webp|gif|avif)\b", p.query, re.I))


def image_formula(url: str) -> str:
    return '=IMAGE("' + url.replace('"', '""') + '")'


def cell_text(v, *, allow_formula: bool = False) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return ("%.2f" % v).rstrip("0").rstrip(".")
    s = str(v)
    if not allow_formula and s.startswith(FORMULA_START) and not re.fullmatch(r"-?\d+(\.\d+)?", s):
        s = "'" + s  # stop accidental formula interpretation
    return s


def tsv_field(s: str) -> str:
    if any(ch in s for ch in ("\t", "\n", "\r", '"')):
        return '"' + s.replace('"', '""') + '"'
    return s


def prepare(rows: Iterable[dict], columns: list[tuple[str, str]], image_mode: str = "url") -> list[list]:
    out = []
    for r in rows:
        line = []
        for key, _ in columns:
            v = r.get(key)
            if key == "image_url" and image_mode == "formula" and is_valid_image_url(v):
                line.append(("__formula__", image_formula(v)))
            else:
                line.append(v)
        out.append(line)
    return out


def to_tsv(rows: Iterable[dict], columns: list[tuple[str, str]], headers: bool = True, image_mode: str = "url") -> str:
    lines = []
    if headers:
        lines.append("\t".join(tsv_field(label) for _, label in columns))
    for line in prepare(rows, columns, image_mode):
        cells = []
        for v in line:
            if isinstance(v, tuple):
                cells.append(tsv_field(v[1]))
            else:
                cells.append(tsv_field(cell_text(v)))
        lines.append("\t".join(cells))
    return "\r\n".join(lines) + "\r\n"


def to_csv(rows: Iterable[dict], columns: list[tuple[str, str]], headers: bool = True, image_mode: str = "url") -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    if headers:
        w.writerow([label for _, label in columns])
    for line in prepare(rows, columns, image_mode):
        w.writerow([v[1] if isinstance(v, tuple) else cell_text(v) for v in line])
    return "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 (Vietnamese/Japanese) correctly


def to_xlsx(rows: Iterable[dict], columns: list[tuple[str, str]], headers: bool = True, image_mode: str = "url") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    r0 = 1
    if headers:
        for i, (_, label) in enumerate(columns, 1):
            ws.cell(row=1, column=i, value=label).font = Font(bold=True)
        ws.freeze_panes = "A2"
        r0 = 2
    for ri, line in enumerate(prepare(rows, columns, image_mode), r0):
        for ci, v in enumerate(line, 1):
            if isinstance(v, tuple):
                ws.cell(row=ri, column=ci, value=v[1])
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                ws.cell(row=ri, column=ci, value=v)
            else:
                c = ws.cell(row=ri, column=ci)
                c.value = cell_text(v) if v is not None else None
                c.data_type = "s" if v is not None else c.data_type
    for i, (key, label) in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = 48 if "url" in key else max(12, min(40, len(label) + 2))
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def columns_for(keys: Optional[list[str]], catalog: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not keys:
        return catalog
    lookup = dict(catalog)
    return [(k, lookup.get(k, k)) for k in keys if k in lookup]
