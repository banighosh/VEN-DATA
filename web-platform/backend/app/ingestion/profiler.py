"""Column profiling: type inference, completeness, validity and formatting signals."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from ..processing.cleaning import (
    case_variant_groups,
    date_like_ratio,
    iqr_outliers,
    is_blank,
    looks_like_excel_serial,
    normalize_dates,
    normalize_numeric,
)

_ID_NAME = re.compile(r"(^|\b|_)(id|key|code|sku|no|number|#)($|\b|_)", re.IGNORECASE)
_PCT_NAME = re.compile(r"margin|percent|pct|%|rate|ratio|share", re.IGNORECASE)
_MONEY_NAME = re.compile(r"price|sales|revenue|profit|cost|amount|value|income|spend|budget|discount|total", re.IGNORECASE)
_DATE_NAME = re.compile(r"date|day|time|period|month", re.IGNORECASE)
_BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "1", "0"}


def _py(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, float) and np.isnan(v):
        return None
    return v


def profile_column(name: str, series: pd.Series) -> dict[str, Any]:
    n = len(series)
    blank = is_blank(series)
    non_null = int((~blank).sum())
    values = series[~blank]
    prof: dict[str, Any] = {
        "name": name,
        "inferred_type": "empty",
        "non_null": non_null,
        "missing": int(blank.sum()),
        "missing_pct": round(float(blank.mean() * 100), 2) if n else 0.0,
        "unique": int(values.nunique(dropna=True)) if non_null else 0,
        "invalid": 0,
        "invalid_examples": [],
        "samples": [_py(v) for v in values.drop_duplicates().head(5).tolist()],
        "mixed_types": False,
        "whitespace_issues": 0,
        "case_variants": [],
        "outliers": 0,
        "stats": None,
        "top_values": None,
        "notes": [],
    }
    prof["unique_pct"] = round(prof["unique"] / non_null * 100, 2) if non_null else 0.0
    if non_null == 0:
        return prof

    kind, invalid_mask, parsed = _infer(name, series, values, blank)
    prof["inferred_type"] = kind
    if invalid_mask is not None:
        prof["invalid"] = int(invalid_mask.sum())
        prof["invalid_examples"] = [_py(v) for v in series[invalid_mask].drop_duplicates().head(5).tolist()]

    py_types = {type(v).__name__ for v in values.head(5000).tolist()}
    numeric_types = {"int", "float", "int64", "float64"}
    prof["mixed_types"] = bool(py_types & numeric_types and "str" in py_types)

    if kind in ("number", "integer", "currency", "percent") and parsed is not None:
        num = parsed.dropna()
        if not num.empty:
            prof["stats"] = {
                "min": float(num.min()), "max": float(num.max()), "mean": float(num.mean()),
                "median": float(num.median()), "sum": float(num.sum()), "zeros": int((num == 0).sum()),
                "negatives": int((num < 0).sum()),
            }
            mask, _ = iqr_outliers(parsed)
            prof["outliers"] = int(mask.sum())
    elif kind == "date" and parsed is not None:
        d = parsed.dropna()
        if not d.empty:
            prof["stats"] = {"min": d.min().date().isoformat(), "max": d.max().date().isoformat(),
                             "distinct_days": int(d.dt.normalize().nunique())}
    if kind in ("category", "text", "id", "boolean"):
        text = values[values.map(lambda v: isinstance(v, str))]
        if not text.empty:
            prof["whitespace_issues"] = int((text != text.str.strip().str.replace(r"\s+", " ", regex=True)).sum())
            prof["case_variants"] = case_variant_groups(text)
        if kind in ("category", "boolean"):
            vc = values.astype(str).value_counts().head(12)
            prof["top_values"] = [{"value": str(k), "count": int(c)} for k, c in vc.items()]
    return prof


def _infer(name: str, series: pd.Series, values: pd.Series, blank: pd.Series):
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date", None, pd.to_datetime(series, errors="coerce")
    if pd.api.types.is_bool_dtype(series):
        return "boolean", None, None
    if pd.api.types.is_numeric_dtype(series):
        if _DATE_NAME.search(name) and looks_like_excel_serial(series):
            res = normalize_dates(series)
            return "date", res.invalid_mask, res.values
        num = pd.to_numeric(series, errors="coerce")
        return _numeric_kind(name, num, values), None, num

    # Object / string columns: try numbers, then dates, then booleans, then text.
    res = normalize_numeric(series)
    parsed_ratio = 1 - res.invalid_count / max(len(values), 1)
    if parsed_ratio >= 0.9:
        text_vals = values.astype(str)
        if text_vals.str.contains("%").mean() > 0.5:
            kind = "percent"
        elif text_vals.str.contains(r"[\$€£¥₹]").mean() > 0.3:
            kind = "currency"
        else:
            kind = _numeric_kind(name, res.values, values)
        return kind, res.invalid_mask, res.values

    obj_dates = values.map(lambda v: hasattr(v, "year") and hasattr(v, "month") and not isinstance(v, str)).mean()
    if obj_dates >= 0.8 or date_like_ratio(values) >= 0.8 or (_DATE_NAME.search(name) and date_like_ratio(values) >= 0.5):
        dres = normalize_dates(series)
        if 1 - dres.invalid_count / max(len(values), 1) >= 0.8:
            return "date", dres.invalid_mask, dres.values

    lowered = set(values.astype(str).str.strip().str.lower().unique()[:20])
    if lowered and lowered <= _BOOL_VALUES and len(lowered) <= 4:
        return "boolean", None, None

    unique = values.nunique()
    if _ID_NAME.search(name) and unique / max(len(values), 1) > 0.5:
        return "id", None, None
    if unique <= max(50, int(0.05 * len(values))):
        return "category", None, None
    return "text", None, None


def _numeric_kind(name: str, num: pd.Series, values: pd.Series) -> str:
    clean = num.dropna()
    if clean.empty:
        return "number"
    if _PCT_NAME.search(name) and clean.between(-1.5, 1.5).mean() > 0.95:
        return "percent"
    whole = bool((clean == clean.round()).all())
    if _ID_NAME.search(name) and whole and not _MONEY_NAME.search(name):
        return "id"
    if _MONEY_NAME.search(name):
        return "currency"
    return "integer" if whole else "number"


def profile_frame(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [profile_column(str(c), df[c]) for c in df.columns]


def preview_rows(df: pd.DataFrame, limit: int = 100) -> list[dict[str, Any]]:
    head = df.head(limit)
    rows = []
    for idx, rec in zip(head.index, head.to_dict(orient="records")):
        rows.append({"__row": int(idx), **{k: _py(v) for k, v in rec.items()}})
    return rows
