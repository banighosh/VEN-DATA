"""Unit tests for cleaning, profiling, mapping and validation primitives."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ingestion.file_validation import FileValidationError, validate_upload
from app.ingestion.mapping import suggest_mapping, validate_mapping
from app.ingestion.profiler import profile_column, profile_frame
from app.ingestion.reader import detect_header_row
from app.processing.cleaning import (
    detect_duplicates,
    harmonize_categories,
    iqr_outliers,
    normalize_dates,
    normalize_numeric,
)
from app.processing.transform import TransformOptions, build_canonical
from app.processing.validation import consistency_checks, detect_key_conflicts


def test_normalize_numeric_handles_business_formats():
    s = pd.Series(["$1,234.50", "(100)", "12%", "€ 3 000", "abc", None, "", "−7"])
    res = normalize_numeric(s)
    assert res.values.iloc[0] == 1234.5
    assert res.values.iloc[1] == -100
    assert abs(res.values.iloc[2] - 0.12) < 1e-12
    assert res.values.iloc[3] == 3000
    assert res.values.iloc[7] == -7
    assert np.isnan(res.values.iloc[4])
    # Unparseable text is flagged invalid; blanks are missing, not invalid.
    assert res.invalid_mask.tolist() == [False, False, False, False, True, False, False, False]


def test_normalize_dates_day_first_and_excel_serial():
    res = normalize_dates(pd.Series(["17/01/2024", "05/02/2024", "garbage", None]))
    assert res.values.iloc[0] == pd.Timestamp("2024-01-17")
    assert res.values.iloc[1] == pd.Timestamp("2024-02-05")  # day-first inferred from 17/01
    assert res.invalid_mask.tolist() == [False, False, True, False]
    serial = normalize_dates(pd.Series([45292, 45293]))
    assert serial.values.iloc[0] == pd.Timestamp("2024-01-01")


def test_harmonize_categories_unifies_case_and_spacing():
    s, variants = harmonize_categories(pd.Series(["In-Store", "In-Store", "in-store", " In-Store ", "Online"]))
    assert set(s) == {"In-Store", "Online"}
    assert "In-Store" in variants


def test_duplicates_and_outliers():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    assert detect_duplicates(df).tolist() == [False, True, False]
    vals = pd.Series(list(range(100)) + [10_000])
    mask, fences = iqr_outliers(vals)
    assert mask.iloc[-1] and mask.sum() == 1 and fences is not None


def test_header_detection_skips_title_rows():
    raw = pd.DataFrame([[None, "Sales Database", None, None], [None] * 4, [None, "Retailer", "Date", "Sales"],
                        [None, "A", "2021-01-01", 5], [None, "B", "2021-01-02", 6]])
    assert detect_header_row(raw) == 2


def test_profiler_type_inference():
    assert profile_column("Total Sales", pd.Series([100.0, 200.0, 300.0]))["inferred_type"] == "currency"
    assert profile_column("Invoice Date", pd.Series(pd.to_datetime(["2021-01-01", "2021-02-01"])))["inferred_type"] == "date"
    assert profile_column("Operating Margin", pd.Series([0.3, 0.5, 0.25]))["inferred_type"] == "percent"
    p = profile_column("Sales Method", pd.Series(["In-store", "In-Store", "Online"] * 10))
    assert p["inferred_type"] == "category" and p["case_variants"]


def test_mapping_suggestion_and_key_conflict():
    df = pd.DataFrame({
        "Retailer": ["Foot Locker", "Walmart", "Amazon", "Kohl's"], "Retailer ID": [1, 1, 1, 2],
        "Invoice Date": pd.to_datetime(["2021-01-01"] * 4), "Total Sales": [10.0, 20.0, 30.0, 40.0],
        "Units Sold": [1, 2, 3, 4], "Price per Unit": [10, 10, 10, 10], "Sales Method": ["Online"] * 4,
    })
    conflicts = detect_key_conflicts(df)
    assert conflicts and conflicts[0]["id_column"] == "Retailer ID"
    sug = suggest_mapping(profile_frame(df), conflicts)
    m = sug["mapping"]
    assert m["txn_date"] == "Invoice Date" and m["revenue"] == "Total Sales" and m["channel"] == "Sales Method"
    assert m["customer_name"] == "Retailer" and "customer_id" not in m
    assert any("Retailer ID" in w for w in sug["warnings"])


def test_validate_mapping_requires_date_and_revenue():
    errors, _ = validate_mapping({"product": "P"}, ["P"])
    assert any("Transaction date" in e for e in errors) and any("Revenue" in e for e in errors)
    errors, _ = validate_mapping({"txn_date": "D", "unit_price": "P", "quantity": "Q"}, ["D", "P", "Q"])
    assert errors == []  # revenue can be derived


def test_transform_never_fabricates_missing_values():
    df = pd.DataFrame({"Date": ["2024-01-01", None, "2024-01-03"], "Sales": ["10", "20", None]})
    canonical, report = build_canonical(df, {"txn_date": "Date", "revenue": "Sales"}, TransformOptions())
    assert canonical["is_valid"].tolist() == [True, False, False]
    assert np.isnan(canonical["revenue"].iloc[2])  # stays missing
    assert report["excluded_rows"] == {"missing_date": 1, "missing_revenue": 1}


def test_revenue_reconciliation_check_reports_ratio():
    df = pd.DataFrame({"Date": ["2024-01-01"] * 4, "Price": [10, 10, 10, 10], "Units": [1, 2, 3, 4],
                       "Sales": [10, 20, 300, 400]})
    mapping = {"txn_date": "Date", "unit_price": "Price", "quantity": "Units", "revenue": "Sales"}
    canonical, _ = build_canonical(df, mapping, TransformOptions())
    check = next(c for c in consistency_checks(canonical, mapping) if c["id"] == "revenue_reconciliation")
    assert check["affected_rows"] == 2 and check["status"] == "fail" and "10×" in check["detail"]
    derived, rep = build_canonical(df, mapping, TransformOptions(revenue_source="derived"))
    assert derived["revenue"].tolist() == [10, 20, 30, 40]
    assert rep["derived_fields"][0]["field"] == "revenue"


def test_file_validation_rejects_bad_files():
    for name, head in (("a.pdf", b"%PDF"), ("a.xls", b"x"), ("a.xlsx", b"not a zip")):
        try:
            validate_upload(name, head, 10, 100)
        except FileValidationError:
            continue
        raise AssertionError(f"{name} should be rejected")
    assert validate_upload("ok.csv", b"a,b\n1,2", 7, 100).file_type == "csv"
