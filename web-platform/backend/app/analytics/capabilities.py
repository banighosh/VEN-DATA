"""Which metrics and filters a dataset can support, based on its mapped fields."""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..ingestion.mapping import FIELDS
from .common import DatasetFrame

METRICS: dict[str, dict[str, Any]] = {
    "revenue": {"label": "Revenue", "requires": ["revenue"]},
    "units": {"label": "Units sold", "requires": ["quantity"]},
    "profit": {"label": "Profit", "requires": ["profit"]},
    "margin": {"label": "Profit margin", "requires": ["profit"]},
    "cost": {"label": "Cost", "requires": ["cost"]},
    "net_profit": {"label": "Net profit", "requires": ["net_profit"]},
    "aov": {"label": "Average order value", "requires": ["revenue"], "better_with": ["order_id"]},
    "customers": {"label": "Customer count", "requires_any": ["customer_id", "customer_name"]},
    "new_vs_returning": {"label": "New vs returning customers", "requires_any": ["customer_id", "customer_name"]},
    "retention": {"label": "Customer retention", "requires_any": ["customer_id", "customer_name"]},
    "clv": {"label": "Customer lifetime value", "requires_any": ["customer_id", "customer_name"]},
    "budget_vs_actual": {"label": "Budget vs actual", "requires": ["budget"]},
    "processing_time": {"label": "Order processing time", "requires": ["ship_date"]},
    "delivery_performance": {"label": "Delivery performance", "requires": ["delivery_date"]},
    "cancellation_rate": {"label": "Cancellation rate", "requires": ["order_status"]},
    "geography_map": {"label": "Geographic map", "requires": ["state"]},
    "forecast": {"label": "Revenue forecast", "requires": ["txn_date", "revenue"], "note": "Needs ≥ 12 months of history"},
}

FILTER_FIELDS = ("region", "state", "city", "category", "subcategory", "product", "customer_segment", "business_unit",
                 "channel", "customer")


def capabilities(frame: DatasetFrame) -> dict[str, Any]:
    fields = {}
    for f in FIELDS:
        fields[f.key] = {"label": frame.label(f.key), "available": f.key in frame.available,
                         "source": frame.source(f.key), "derived": f.key in frame.derived, "group": f.group}
    metrics = {}
    for key, spec in METRICS.items():
        if "requires_any" in spec:
            ok = any(r in frame.available for r in spec["requires_any"])
            missing = [] if ok else spec["requires_any"]
        else:
            missing = [r for r in spec["requires"] if r not in frame.available]
            ok = not missing
        entry = {"label": spec["label"], "available": ok, "missing": missing}
        if ok and spec.get("better_with") and not all(b in frame.available for b in spec["better_with"]):
            entry["basis"] = "per transaction line (no Order ID)"
        if spec.get("note"):
            entry["note"] = spec["note"]
        metrics[key] = entry
    filters = {}
    for f in FILTER_FIELDS:
        col = frame.dim_col(f)
        filters[f] = {"available": col is not None, "label": frame.label(col or f),
                      "source": frame.source(col) if col else None}
    return {"fields": fields, "metrics": metrics, "filters": filters,
            "customer_label": frame.label(frame.customer_key) if frame.customer_key else None}


def filter_options(frame: DatasetFrame) -> dict[str, Any]:
    df = frame.df
    out: dict[str, Any] = {"date_min": frame.date_min, "date_max": frame.date_max, "dimensions": {}}
    for f in FILTER_FIELDS:
        col = frame.dim_col(f)
        if col is None:
            continue
        vc = df.groupby(col)["revenue"].sum().sort_values(ascending=False)
        out["dimensions"][f] = {"label": frame.label(col), "values": [str(v) for v in vc.index[:500]],
                                "truncated": len(vc) > 500}
    # Parent links power cascading filter lists (region → state → city, category → product).
    links = {}
    for child, parent in (("state", "region"), ("city", "state"), ("product", "category"), ("subcategory", "category")):
        if frame.dim_col(child) and frame.dim_col(parent):
            m = df.groupby(child)[parent].agg(lambda s: s.mode().iat[0]).to_dict()
            links[child] = {"parent": parent, "map": {str(k): str(v) for k, v in m.items()}}
    out["links"] = links
    if frame.date_min is not None and frame.date_max is not None:
        years = sorted({d.year for d in (frame.date_min, frame.date_max)} | set(df["txn_date"].dt.year.unique().tolist()))
        out["years"] = [int(y) for y in years]
        last_full = None
        for y in reversed(out["years"]):
            if frame.date_min <= pd.Timestamp(y, 1, 1) and frame.date_max >= pd.Timestamp(y, 12, 31):
                last_full = y
                break
        out["latest_full_year"] = last_full
    return out
