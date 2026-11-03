"""API integration tests: messy CSV through the full pipeline, plus Adidas verification."""
from __future__ import annotations

import pandas as pd
import pytest

from app.processing.cleaning import detect_duplicates


def _process(client, name, stream, sheet=None, mapping_override=None, options=None):
    up = client.post("/api/uploads", files={"file": (name, stream, "application/octet-stream")})
    assert up.status_code == 200, up.text
    u = up.json()
    sheet = sheet or u["recommended_sheet"]
    a = client.get(f"/api/uploads/{u['upload_id']}/analysis", params={"sheet": sheet} if sheet != "CSV" else {})
    assert a.status_code == 200, a.text
    analysis = a.json()
    mapping = {**analysis["suggestion"]["mapping"], **(mapping_override or {})}
    r = client.post("/api/datasets", json={"upload_id": u["upload_id"], "sheet": sheet, "mapping": mapping,
                                           "options": options or {}, "name": name})
    assert r.status_code == 200, r.text
    return analysis, r.json()


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_rejects_unsupported_upload(client):
    r = client.post("/api/uploads", files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400


def test_messy_csv_pipeline(client, messy_csv):
    name, stream = messy_csv
    analysis, ds = _process(client, name, stream)
    # Title rows above the header were skipped.
    assert analysis["header_row"] == 3 and "Order Date" in analysis["columns"]
    m = analysis["suggestion"]["mapping"]
    assert m["txn_date"] == "Order Date" and m["revenue"] == "Sales" and m["order_id"] == "Order ID"
    issues = {(i["category"], i.get("column")) for i in analysis["quality"]["issues"]}
    assert ("duplicate", None) in issues
    assert ("invalid_date", "Order Date") in issues
    assert ("missing", "Sales") in issues
    assert ("formatting", "Channel") in issues  # in-store / In-Store

    proc = ds["processing"]
    assert proc["duplicates_removed"] == 1
    assert proc["excluded_rows"] == {"invalid_date": 1, "missing_revenue": 1}
    assert ds["valid_row_count"] == 5

    did = ds["id"]
    k = client.post(f"/api/datasets/{did}/analytics/kpis", json={"filters": {}}).json()
    cards = {c["key"]: c for c in k["kpis"]}
    # Valid rows: 200 + 50 + 300 + 400 + 800 (duplicate dropped, missing/invalid excluded — never filled in).
    assert cards["total_revenue"]["value"] == pytest.approx(1750.0)
    assert cards["total_profit"]["value"] == pytest.approx(50 + 10 + 90 + 200 - 40)
    assert cards["aov"]["label"] == "Avg Order Value"  # order ID mapped → true AOV
    assert cards["aov"]["value"] == pytest.approx(1750.0 / 4)  # orders A-1, A-2, A-3, A-6
    assert cards["total_customers"]["value"] == 3

    ch = client.post(f"/api/datasets/{did}/analytics/breakdown", json={"dimension": "channel"}).json()["rows"]
    assert {r["key"] for r in ch} == {"Online", "In-Store"}  # spelling variants unified

    q = client.post(f"/api/datasets/{did}/records/query", json={"include_excluded": True, "issues_only": True}).json()
    assert q["total"] >= 2
    csv = client.post(f"/api/datasets/{did}/export", json={"format": "csv"})
    assert csv.status_code == 200 and csv.text.count("\n") == 6


def test_filters_drive_every_module_consistently(client, messy_csv):
    name, stream = messy_csv
    _, ds = _process(client, "messy-2.csv", stream)
    did = ds["id"]
    body = {"filters": {"region": ["North"]}}
    total = client.post(f"/api/datasets/{did}/analytics/kpis", json=body).json()
    rev = next(c for c in total["kpis"] if c["key"] == "total_revenue")["value"]
    prods = client.post(f"/api/datasets/{did}/analytics/products", json=body).json()
    assert sum(p["revenue"] for p in prods["products"]) == pytest.approx(rev)
    fin = client.post(f"/api/datasets/{did}/analytics/financial", json=body).json()
    assert fin["statement"][0]["value"] == pytest.approx(rev)
    recs = client.post(f"/api/datasets/{did}/records/query", json={**body, "page_size": 500}).json()
    assert sum(r["revenue"] for r in recs["rows"]) == pytest.approx(rev)


def test_presets_roundtrip(client):
    r = client.post("/api/presets", json={"name": "North only", "filters": {"region": ["North"]}})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert any(p["id"] == pid for p in client.get("/api/presets").json())
    assert client.delete(f"/api/presets/{pid}").status_code == 204


# --------------------------------------------------------------------------- Adidas dataset verification
@pytest.fixture(scope="module")
def adidas(client, adidas_path):
    if adidas_path is None:
        pytest.skip("Set ADIDAS_XLSX to run dataset verification tests")
    with open(adidas_path, "rb") as fh:
        analysis, ds = _process(client, "Adidas US Sales.xlsx", fh, sheet="Cleaned_Table")
    raw = pd.read_excel(adidas_path, sheet_name="Cleaned_Table")
    return analysis, ds, raw


def test_adidas_quality_findings(adidas):
    analysis, ds, raw = adidas
    q = analysis["quality"]
    chk = next(c for c in q["checks"] if c["id"] == "revenue_reconciliation")
    expected_bad = int(((raw["Total Sales"] - raw["Price per Unit"] * raw["Units Sold"]).abs() >
                        0.01 * (raw["Price per Unit"] * raw["Units Sold"])).sum())
    assert chk["affected_rows"] == expected_bad == 3886
    assert any(c["id_column"] == "Retailer ID" for c in q["key_conflicts"])
    assert ds["valid_row_count"] == len(raw) == 9648
    assert all(r["status"] == "pass" for r in ds["processing"]["reconciliation"])


def test_adidas_kpis_match_independent_calculation(client, adidas):
    _, ds, raw = adidas
    did = ds["id"]
    y21 = raw[raw["Invoice Date"].dt.year == 2021]
    y20 = raw[raw["Invoice Date"].dt.year == 2020]
    k = client.post(f"/api/datasets/{did}/analytics/kpis",
                    json={"filters": {"start_date": "2021-01-01", "end_date": "2021-12-31"}}).json()
    c = {x["key"]: x for x in k["kpis"]}
    assert c["total_revenue"]["value"] == pytest.approx(y21["Total Sales"].sum())
    assert c["total_revenue"]["previous"] == pytest.approx(y20["Total Sales"].sum())
    assert c["total_sales"]["value"] == pytest.approx(y21["Units Sold"].sum())
    assert c["total_profit"]["value"] == pytest.approx(y21["Operating Profit"].sum())
    assert c["profit_margin"]["value"] == pytest.approx(y21["Operating Profit"].sum() / y21["Total Sales"].sum())
    assert c["growth_rate"]["value"] == pytest.approx(y21["Total Sales"].sum() / y20["Total Sales"].sum() - 1)
    assert c["aov"]["value"] == pytest.approx(y21["Total Sales"].sum() / len(y21))
    assert c["total_customers"]["value"] == y21["Retailer"].nunique()
    assert c["transaction_volume"]["value"] == len(y21)


def test_adidas_breakdowns_reconcile_to_totals(client, adidas):
    _, ds, raw = adidas
    did = ds["id"]
    body = {"filters": {"channel": ["Online"], "start_date": "2021-07-01", "end_date": "2021-09-30"}}
    sub = raw[(raw["Sales Method"] == "Online") & (raw["Invoice Date"] >= "2021-07-01") & (raw["Invoice Date"] <= "2021-09-30")]
    reg = client.post(f"/api/datasets/{did}/analytics/regional", json=body).json()
    assert sum(r["revenue"] for r in reg["region"]) == pytest.approx(sub["Total Sales"].sum())
    assert sum(r["revenue"] for r in reg["state"]) == pytest.approx(sub["Total Sales"].sum())
    by_state = sub.groupby("State")["Total Sales"].sum()
    for r in reg["state"]:
        assert r["revenue"] == pytest.approx(by_state.get(r["key"], 0.0))  # 0 = sold last quarter, not this one
    perf = client.post(f"/api/datasets/{did}/analytics/performance", json={**body, "granularity": "month"}).json()
    monthly = sub.groupby(sub["Invoice Date"].dt.to_period("M"))["Total Sales"].sum()
    assert [r["revenue"] for r in perf["trend"]["series"]] == pytest.approx(monthly.tolist())
    assert perf["meta"]["comparison_label"] == "Q2 2021"


def test_adidas_insights_are_grounded(client, adidas):
    _, ds, raw = adidas
    ins = client.post(f"/api/datasets/{ds['id']}/analytics/insights",
                      json={"filters": {"start_date": "2021-01-01", "end_date": "2021-12-31"}}).json()
    ids = {i["id"] for i in ins["insights"]}
    assert {"revenue_change", "coverage_shift", "data_quality"} <= ids
    for i in ins["insights"]:
        assert i["observation"] and i["implication"] and i["recommendation"]
        assert i["interpretation_source"] == "rule"
    assert ins["ai"]["enabled"] is False


def test_adidas_forecast_flags_level_shift(client, adidas):
    _, ds, _ = adidas
    fc = client.post(f"/api/datasets/{ds['id']}/analytics/forecast", json={"filters": {}}).json()
    assert fc["available"] and len(fc["forecast"]) == 6
    assert any("coverage" in w for w in fc["warnings"])


def test_adidas_explorer_and_exports(client, adidas):
    _, ds, raw = adidas
    did = ds["id"]
    q = client.post(f"/api/datasets/{did}/records/query",
                    json={"search": "west gear", "sort_by": "revenue", "sort_dir": "desc", "page_size": 10}).json()
    assert q["total"] == int((raw["Retailer"] == "West Gear").sum())
    assert q["rows"][0]["revenue"] == raw.loc[raw["Retailer"] == "West Gear", "Total Sales"].max()
    detail = client.get(f"/api/datasets/{did}/records/{q['rows'][0]['id']}").json()
    assert detail["raw"]["Retailer"] == "West Gear"
    rep = client.post(f"/api/datasets/{did}/report", json={"format": "xlsx"})
    assert rep.status_code == 200 and rep.content[:2] == b"PK"
    assert detect_duplicates(raw).sum() == 0
