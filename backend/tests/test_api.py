import csv
import io


def test_core_endpoints(client, demo_loaded):
    assert client.get("/api/health").json()["ok"]
    d = client.get("/api/dashboard").json()
    assert d["total"] >= 5 and d["sources"]
    up = client.get("/api/upcoming").json()
    assert any(u["release_status"] == "OFFICIALLY CONFIRMED" and u["rumor_confidence"] == "HIGH" for u in up)
    ea = client.get("/api/early").json()
    assert any(e["lifecycle_stage"] == "NEW SIGNAL — INSUFFICIENT HISTORY" and e["early_score"] is None for e in ea)
    opp = client.get("/api/opportunities").json()
    assert opp and all(o["target_market"] == "US" for o in opp)
    assert all(o["opportunity_score"] is None or o["coverage"] >= 25 for o in opp)
    ch = client.get("/api/changes", params={"days": 7}).json()
    assert any(c["event_type"] == "NEW_PRODUCT" for c in ch)


def test_hide_demo_data(client, demo_loaded):
    assert client.get("/api/research", params={"include_fixture": False}).json()["rows"] == []


def test_export_selected_rows_in_given_order(client, demo_loaded):
    rows = client.get("/api/research").json()["rows"]
    ids = [rows[2]["row_id"], rows[0]["row_id"]]
    r = client.post("/api/export", json={"format": "tsv", "row_ids": ids, "columns": ["product_name", "best_info_url", "ref_url_1"]})
    grid = list(csv.reader(io.StringIO(r.text), delimiter="\t"))
    assert grid[0] == ["Product Name", "Best Product Information URL", "Reference URL 1"]
    assert [g[0] for g in grid[1:]] == [rows[2]["product_name"], rows[0]["product_name"]]
    x = client.post("/api/export", json={"format": "xlsx"})
    assert x.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_shortlist_survives_rank_change(client, demo_loaded):
    pid = client.get("/api/opportunities").json()[0]["product_id"]
    s = client.post("/api/shortlists", json={"list_type": "OPPORTUNITY", "product_id": pid, "target_market": "US",
                                             "research_status": "Supplier Check"}).json()
    client.post("/api/recompute")
    assert any(x["id"] == s["id"] for x in client.get("/api/shortlists").json())


def test_weights_change_recomputes_from_observations(client, demo_loaded):
    before = {r["row_id"]: r["trend_score"] for r in client.get("/api/research").json()["rows"]}
    client.put("/api/settings/weights.trend.default", json={"social": 0, "search": 0, "editorial": 100, "retail": 0, "velocity": 0, "diversity": 0})
    client.post("/api/recompute")
    after = {r["row_id"]: r["trend_score"] for r in client.get("/api/research").json()["rows"]}
    assert before != after


def test_results_of_one_scan_job(client, demo_loaded):
    from app.jobs import drain, enqueue
    all_rows = client.get("/api/research").json()["rows"]
    # a second scan limited to Japan only touches the products it saw there
    jid, _ = enqueue("SCAN", {"markets": ["JP"], "source_keys": ["demo_fixture"], "include_fixture": True})
    drain()
    rows = client.get("/api/research", params={"job_id": jid}).json()["rows"]
    assert rows and len(rows) < len(all_rows)
    assert {r["market_code"] for r in rows} <= {"JP", "GLOBAL"}
    # a scan that found nothing shows nothing (not everything)
    empty, _ = enqueue("SCAN", {"markets": ["JP"], "source_keys": ["demo_fixture"], "include_fixture": True, "include_keywords": ["zzzz-none"]})
    drain()
    assert client.get("/api/research", params={"job_id": empty}).json()["rows"] == []
    r = client.post("/api/export", json={"format": "tsv", "filters": {"job_id": empty}})
    assert r.text.count("\n") == 1  # header only


def test_dashboard_drilldown_counts_match_bars(client, demo_loaded):
    d = client.get("/api/dashboard").json()
    for by, pairs in (("status", list(d["status_counts"].items())), ("brand", d["brands"]), ("category", d["categories"]),
                      ("market", d["markets"]), ("industry", d["industries"])):
        for value, count in pairs[:3]:
            rows = client.get("/api/dashboard/products", params={"by": by, "value": value}).json()
            assert len(rows) == count, (by, value)
    rising = client.get("/api/dashboard/products", params={"by": "status", "value": "RISING FAST"}).json()
    assert all(r["trend_status"] == "RISING FAST" for r in rising)
    every = client.get("/api/dashboard/products").json()
    assert len({r["product_id"] for r in every}) == d["total"]
    assert client.get("/api/dashboard/products", params={"by": "nope", "value": "x"}).status_code == 400
