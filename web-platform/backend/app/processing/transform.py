"""Map source columns onto the canonical business schema.

Input: a cleaned-header DataFrame read from the upload plus the user's mapping.
Output: a canonical frame (one row per source row) ready to persist, and a
processing report describing every transformation that was applied.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..ingestion.mapping import FIELD_BY_KEY
from .cleaning import (
    detect_duplicates,
    harmonize_categories,
    iqr_outliers,
    is_blank,
    normalize_dates,
    normalize_numeric,
    trim_strings,
)

CANONICAL_TEXT = ("order_id", "customer_id", "customer_name", "customer_segment", "product", "product_id", "category",
                  "subcategory", "brand", "region", "country", "state", "city", "channel", "business_unit", "order_status")
CANONICAL_NUM = ("revenue", "quantity", "unit_price", "cost", "profit", "net_profit", "margin_pct", "discount", "budget")
CANONICAL_DATE = ("txn_date", "ship_date", "delivery_date")
REVENUE_TOLERANCE = 0.01  # 1% relative tolerance for price × qty reconciliation


@dataclass
class TransformOptions:
    revenue_source: str = "column"      # "column" | "derived"
    drop_duplicates: bool = True
    harmonize_categories: bool = True
    trim_whitespace: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> TransformOptions:
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _text(series: pd.Series) -> pd.Series:
    def conv(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        if isinstance(v, (float, np.floating)) and float(v).is_integer():
            return str(int(v))
        if isinstance(v, (pd.Timestamp, datetime, date)):
            return v.isoformat()[:10]
        s = str(v).strip()
        return s or None
    return series.map(conv).astype(object)


def _json_safe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if np.isnan(f) or np.isinf(f) else f
    if isinstance(v, (pd.Timestamp, datetime)):
        return None if pd.isna(v) else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def build_canonical(df: pd.DataFrame, mapping: dict[str, str], options: TransformOptions) -> tuple[pd.DataFrame, dict[str, Any]]:
    report: dict[str, Any] = {
        "input_rows": int(len(df)), "steps": [], "field_parsing": {}, "harmonized": {}, "trimmed": {},
        "duplicates_found": 0, "duplicates_removed": 0, "derived_fields": [], "excluded_rows": {}, "row_flags": {},
    }
    work = df
    if options.trim_whitespace:
        work, trimmed = trim_strings(work)
        report["trimmed"] = trimmed
        if trimmed:
            report["steps"].append(f"Trimmed stray whitespace in {sum(trimmed.values()):,} cell(s)")

    dup_mask = detect_duplicates(work)
    report["duplicates_found"] = int(dup_mask.sum())
    if options.drop_duplicates and dup_mask.any():
        work = work[~dup_mask]
        report["duplicates_removed"] = int(dup_mask.sum())
        report["steps"].append(f"Removed {int(dup_mask.sum()):,} exact duplicate row(s)")

    out = pd.DataFrame(index=work.index)
    out["row_number"] = work.index.astype(int)
    invalid_flags: dict[str, pd.Series] = {}
    source_blank: dict[str, pd.Series] = {}

    for key, col in mapping.items():
        fld = FIELD_BY_KEY[key]
        src = work[col]
        source_blank[key] = is_blank(src)
        if fld.dtype == "date":
            res = normalize_dates(src)
            out[key] = res.values.dt.normalize()
            invalid_flags[key] = res.invalid_mask
            report["field_parsing"][key] = {"column": col, "invalid": res.invalid_count, "notes": res.notes}
        elif fld.dtype == "number":
            res = normalize_numeric(src)
            vals = res.values
            if key == "margin_pct" and vals.dropna().abs().gt(1.5).mean() > 0.5:
                vals = vals / 100.0
                res.notes.append("Margin values looked like whole percentages and were divided by 100")
            out[key] = vals
            invalid_flags[key] = res.invalid_mask
            report["field_parsing"][key] = {"column": col, "invalid": res.invalid_count, "notes": res.notes}
        else:
            vals = _text(src)
            if options.harmonize_categories and key not in ("order_id", "customer_id", "product_id"):
                vals, variants = harmonize_categories(vals)
                if variants:
                    report["harmonized"][key] = variants
                    n = sum(int((src.astype(str).str.strip().isin(v)).sum()) for v in variants.values())
                    report["steps"].append(f"Unified {n:,} inconsistent spelling(s) in {fld.label} ({col})")
            out[key] = vals
            report["field_parsing"][key] = {"column": col, "invalid": 0, "notes": []}

    for k in CANONICAL_DATE:
        if k not in out:
            out[k] = pd.NaT
    for k in CANONICAL_NUM:
        if k not in out:
            out[k] = np.nan
    for k in CANONICAL_TEXT:
        if k not in out:
            out[k] = None

    # Derived measures — always labelled as derived, never silently substituted.
    if options.revenue_source == "derived" or "revenue" not in mapping:
        if "unit_price" in mapping and "quantity" in mapping:
            out["revenue"] = out["unit_price"] * out["quantity"]
            report["derived_fields"].append({"field": "revenue", "formula": "unit_price × quantity"})
            report["steps"].append("Derived revenue as unit price × quantity")
    if "cost" not in mapping and "profit" in mapping:
        out["cost"] = out["revenue"] - out["profit"]
        report["derived_fields"].append({"field": "cost", "formula": "revenue − profit", "label": "Implied cost"})
        report["steps"].append("Derived implied cost as revenue − profit")
    elif "profit" not in mapping and "cost" in mapping:
        out["profit"] = out["revenue"] - out["cost"]
        report["derived_fields"].append({"field": "profit", "formula": "revenue − cost"})
        report["steps"].append("Derived profit as revenue − cost")

    # Row-level validation flags.
    flags: dict[str, pd.Series] = {}
    flags["missing_date"] = out["txn_date"].isna() & source_blank.get("txn_date", pd.Series(True, index=out.index))
    flags["invalid_date"] = invalid_flags.get("txn_date", pd.Series(False, index=out.index))
    flags["missing_revenue"] = out["revenue"].isna() & ~invalid_flags.get("revenue", pd.Series(False, index=out.index))
    flags["invalid_revenue"] = invalid_flags.get("revenue", pd.Series(False, index=out.index))
    for key, mask in invalid_flags.items():
        if key not in ("txn_date", "revenue") and mask.any():
            flags[f"invalid_{key}"] = mask
    if {"unit_price", "quantity"} <= mapping.keys() and "revenue" in mapping and options.revenue_source != "derived":
        expected = out["unit_price"] * out["quantity"]
        rel = (out["revenue"] - expected).abs() / expected.abs().replace(0, np.nan)
        flags["revenue_mismatch"] = (rel > REVENUE_TOLERANCE).fillna(False)
    flags["negative_revenue"] = (out["revenue"] < 0).fillna(False)
    mask, _ = iqr_outliers(out["revenue"])
    flags["revenue_outlier"] = mask

    issues = pd.Series([[] for _ in range(len(out))], index=out.index, dtype=object)
    for name, mask in flags.items():
        mask = mask.reindex(out.index).fillna(False).astype(bool)
        if mask.any():
            report["row_flags"][name] = int(mask.sum())
            for idx in out.index[mask]:
                issues.at[idx].append(name)
    out["issues"] = issues.map(lambda lst: ",".join(lst) if lst else None)
    out["is_valid"] = out["txn_date"].notna() & out["revenue"].notna()
    excluded = ~out["is_valid"]
    if excluded.any():
        reasons = {}
        for name in ("missing_date", "invalid_date", "missing_revenue", "invalid_revenue"):
            m = flags[name].reindex(out.index).fillna(False) & excluded
            if m.any():
                reasons[name] = int(m.sum())
        report["excluded_rows"] = reasons
        report["steps"].append(f"Excluded {int(excluded.sum()):,} row(s) from analytics (missing or invalid date or revenue); they stay in storage for review")

    raw_records = work.to_dict(orient="records")
    out["raw"] = [{str(k): _json_safe(v) for k, v in rec.items()} for rec in raw_records]
    report["output_rows"] = int(len(out))
    report["valid_rows"] = int(out["is_valid"].sum())
    return out, report
