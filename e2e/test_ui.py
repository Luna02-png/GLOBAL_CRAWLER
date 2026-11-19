"""Browser end-to-end checks (Playwright). Start the app first:  python -m app.cli demo && python -m app.cli serve
Run:  python -m pytest e2e -q   (env GPTI_URL overrides http://127.0.0.1:8765)"""
import csv
import io
import os

import pytest

pw = pytest.importorskip("playwright.sync_api")
URL = os.environ.get("GPTI_URL", "http://127.0.0.1:8765")
SHOTS = os.environ.get("GPTI_SHOTS", "")
PAGES = ["dashboard", "sheet", "upcoming", "opportunity", "early", "new", "links", "lists", "scans", "taxonomy", "sources", "settings"]


@pytest.fixture(scope="module")
def page():
    with pw.sync_playwright() as p:
        exe = os.environ.get("CHROME") or ("/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None)
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1500, "height": 950}, permissions=["clipboard-read", "clipboard-write"])
        pg = ctx.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        yield pg
        b.close()


def test_every_page_renders_without_errors(page):
    for name in PAGES:
        page.goto(f"{URL}/#{name}")
        page.wait_for_timeout(900)
        assert page.locator("main h2").count() >= 1, name
        if SHOTS:
            page.screenshot(path=os.path.join(SHOTS, f"{name}.png"))
    assert page.errors == []


def test_copy_selected_rows_to_google_sheets_tsv(page):
    page.goto(f"{URL}/#sheet")
    page.wait_for_selector(".ag-row")
    checks = page.locator(".ag-center-cols-container .ag-row .ag-selection-checkbox input, .ag-pinned-left-cols-container .ag-row .ag-selection-checkbox input")
    if checks.count() == 0:
        checks = page.locator(".ag-row input[type=checkbox]")
    checks.nth(0).check()
    checks.nth(1).check()
    page.locator("select[title='Copy / export scope']").select_option("selected")
    page.get_by_role("button", name="COPY TO GOOGLE SHEETS").click()
    page.wait_for_selector(".flash")
    text = page.evaluate("navigator.clipboard.readText()")
    grid = list(csv.reader(io.StringIO(text), delimiter="\t"))
    assert len(grid) == 3, grid  # header + 2 selected rows
    assert len({len(r) for r in grid}) == 1  # aligned columns
    assert "Product Name" in grid[0] and "Best Product Information URL" in grid[0]
    i = grid[0].index("Best Product Information URL")
    assert all(r[i] == "" or r[i].startswith("http") for r in grid[1:])  # plain URL strings


def test_product_drawer_and_single_product_link_search(page):
    page.goto(f"{URL}/#sheet")
    page.wait_for_selector(".ag-row")
    page.get_by_role("button", name="Details").first.click()
    page.wait_for_selector(".drawer h3")
    is_demo = page.locator(".drawer .demo").count() == 1
    assert is_demo == ("DEMO" in page.locator(".drawer").inner_text())  # demo rows are always labelled
    page.get_by_role("button", name="Find Product Information Links").click()
    page.wait_for_selector("text=Link finder result", timeout=120000)  # live products also query Google News (slow when offline)


def test_bookmarklet_capture_flow(page):
    """Simulates: user browses a social post themselves, clicks the bookmark, checks the form, saves."""
    page.goto(f"{URL}/#capture")
    page.wait_for_selector("a.bookmarklet")
    code = page.get_attribute("a.bookmarklet", "href")
    assert code.startswith("javascript:")
    post = "https://www.tiktok.com/@e2e.creator/video/777"
    page.route(post, lambda r: r.fulfill(content_type="text/html", body="""<html><head><title>TikTok</title>
      <meta property="og:title" content="POP MART Labubu Big Into Energy unboxing">
      <meta property="og:description" content="12.5K likes, 340 comments. Labubu restock haul"></head><body>video</body></html>"""))
    page.goto(post)
    with page.context.expect_page() as pop:
        page.evaluate(code[len("javascript:"):])
    cap = pop.value
    cap.wait_for_selector("text=Capture one page")
    cap.wait_for_timeout(1200)
    assert cap.get_by_label("Page URL *").input_value() == post
    assert cap.get_by_label("Likes", exact=True).input_value() == "12500"
    assert cap.get_by_label("Account / author").input_value() == "@e2e.creator"
    cap.get_by_role("button", name="Save as evidence").click()
    cap.wait_for_selector("text=SAVED")
    cap.close()


def test_open_google_trends_button(page):
    page.goto(f"{URL}/#sheet")
    page.wait_for_selector(".ag-row")
    page.get_by_role("button", name="Details").first.click()
    page.wait_for_selector(".drawer h3")
    page.context.route("https://trends.google.com/**", lambda r: r.fulfill(content_type="text/html", body="<html>trends</html>"))
    with page.context.expect_page() as pop:
        page.locator(".drawer").get_by_role("button", name="Mở Google Trends").click()
    url = pop.value.url
    pop.value.close()
    assert url.startswith("https://trends.google.com/trends/explore?") and "hl=en-US" in url and "date=today+3-m" in url


def test_drag_select_cells_and_ctrl_c(page):
    page.goto(f"{URL}/#sheet")
    page.wait_for_selector(".ag-row")
    hdr = page.locator(".ag-header-cell-text").all_inner_texts()
    assert hdr[0] == "Product Name" and hdr[1].startswith("Link")  # name first, link right after
    start = page.locator(".ag-pinned-left-cols-container [row-index='0'] [col-id='product_name']")
    end = page.locator(".ag-pinned-left-cols-container [row-index='2'] [col-id='best_info_url']")
    a, b = start.bounding_box(), end.bounding_box()
    page.mouse.move(a["x"] + 20, a["y"] + 10)
    page.mouse.down()
    page.mouse.move(b["x"] + 120, b["y"] + 10, steps=8)
    page.mouse.up()
    assert page.locator(".cell-sel").count() == 6
    page.keyboard.press("Control+c")
    page.wait_for_selector(".flash")
    grid = list(csv.reader(io.StringIO(page.evaluate("navigator.clipboard.readText()")), delimiter="\t"))
    assert len(grid) == 3 and all(len(r) == 2 for r in grid)
    assert all(r[1] == "" or r[1].startswith("http") for r in grid)


def test_dashboard_click_shows_products(page):
    page.goto(f"{URL}/#dashboard")
    page.reload()  # earlier tests leave the product drawer open in the same SPA session
    page.wait_for_selector(".kpi")
    rising = int(page.locator(".kpi.rise b").inner_text())
    page.locator(".kpi.rise").click()
    page.wait_for_selector(".modal.drill")
    page.wait_for_timeout(600)
    assert f"{rising} dòng" in page.locator(".drillhead h3").inner_text()
    if rising:
        assert page.locator(".modal.drill .ag-center-cols-container .ag-row").count() == rising
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, "drill_rising.png"))
    page.keyboard.press("Escape")
    assert page.locator(".modal.drill").count() == 0
    # a bar row (Brands card) opens the products of that brand; Details opens the drawer on top
    bar = page.locator(".card:has(h4:has-text('Brands')) .bar.click").first
    n = int(bar.locator(".bval").inner_text())
    bar.click()
    page.wait_for_timeout(700)
    assert f"{n} dòng" in page.locator(".drillhead h3").inner_text()
    page.locator(".modal.drill").get_by_role("button", name="Details").first.click()
    page.wait_for_selector(".drawer h3")
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, "drill_drawer.png"))
    assert page.errors == []
