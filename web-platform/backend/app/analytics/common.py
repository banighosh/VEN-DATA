"""Shared analytics primitives: dataset frames, filters, period windows, measures.

Every analytics module works on a ``Scope``: the dataset frame after dimension
filters, split into the selected (current) window and its comparison window.
Because all modules derive from the same Scope, KPI cards and charts always
agree with each other for a given set of filters.
"""
from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..ingestion.mapping import FIELD_BY_KEY
from ..models import DATE_FIELDS, NUMBER_FIELDS, TEXT_FIELDS, Dataset, FactRecord

DIMENSION_FIELDS = ("region", "country", "state", "city", "category", "subcategory", "product", "brand",
                    "customer_segment", "business_unit", "channel", "customer")
Granularity = Literal["day", "week", "month", "quarter", "year"]


class FilterSpec(BaseModel):
    """Global filters shared by every chart, KPI card, table and export."""

    start_date: date | None = None
    end_date: date | None = None
    region: list[str] = Field(default_factory=list)
    country: list[str] = Field(default_factory=list)
    state: list[str] = Field(default_factory=list)
    city: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    subcategory: list[str] = Field(default_factory=list)
    product: list[str] = Field(default_factory=list)
    brand: list[str] = Field(default_factory=list)
    customer_segment: list[str] = Field(default_factory=list)
    business_unit: list[str] = Field(default_factory=list)
    channel: list[str] = Field(default_factory=list)
    customer: list[str] = Field(default_factory=list)
    comparison: Literal["previous_period", "previous_year", "none"] = "previous_period"

    def active_dimensions(self) -> dict[str, list[str]]:
        return {d: getattr(self, d) for d in DIMENSION_FIELDS if getattr(self, d)}


# --------------------------------------------------------------------------- frames
@dataclass
class DatasetFrame:
    dataset_id: int
    version: int
    name: str
    df: pd.DataFrame
    mapping: dict[str, str]
    derived: set[str]
    available: set[str]
    date_min: pd.Timestamp | None
    date_max: pd.Timestamp | None

    @property
    def customer_key(self) -> str | None:
        if "customer_id" in self.available:
            return "customer_id"
        if "customer_name" in self.available:
            return "customer_name"
        return None

    def has(self, *fields: str) -> bool:
        return all(f in self.available for f in fields)

    def dim_col(self, dimension: str) -> str | None:
        if dimension == "customer":
            return self.customer_key
        return dimension if dimension in self.available else None

    def label(self, key: str) -> str:
        if key == "customer":
            return "Customer"
        if key == "cost" and "cost" in self.derived:
            return "Implied cost"
        if key == "profit":
            src = (self.mapping.get("profit") or "").lower()
            if "operating" in src:
                return "Operating profit"
            if "gross" in src:
                return "Gross profit"
            return "Profit"
        if key == "customer_name" and "retailer" in (self.mapping.get("customer_name") or "").lower():
            return "Retailer"
        fld = FIELD_BY_KEY.get(key)
        return fld.label if fld else key.replace("_", " ").title()

    def source(self, key: str) -> str | None:
        return self.mapping.get(key)


_cache: OrderedDict[tuple[int, int], DatasetFrame] = OrderedDict()
_lock = threading.Lock()


def get_frame(db: Session, dataset: Dataset) -> DatasetFrame:
    key = (dataset.id, dataset.version)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    cols = [FactRecord.id, FactRecord.row_number] + [getattr(FactRecord, f) for f in (*DATE_FIELDS, *TEXT_FIELDS, *NUMBER_FIELDS)]
    stmt = select(*cols).where(FactRecord.dataset_id == dataset.id, FactRecord.is_valid.is_(True))
    with db.get_bind().connect() as conn:
        df = pd.DataFrame(conn.execute(stmt).all(), columns=[c.key for c in cols])
    for f in DATE_FIELDS:
        df[f] = pd.to_datetime(df[f], errors="coerce")
    for f in NUMBER_FIELDS:
        df[f] = pd.to_numeric(df[f], errors="coerce").astype(float)
    available = {c for c in (*DATE_FIELDS, *TEXT_FIELDS, *NUMBER_FIELDS) if c in df and df[c].notna().any()}
    derived = {d["field"] for d in (dataset.processing or {}).get("derived_fields", [])}
    frame = DatasetFrame(
        dataset_id=dataset.id, version=dataset.version, name=dataset.name, df=df,
        mapping=dict(dataset.mapping or {}), derived=derived, available=available,
        date_min=df["txn_date"].min() if not df.empty else None,
        date_max=df["txn_date"].max() if not df.empty else None,
    )
    with _lock:
        _cache[key] = frame
        while len(_cache) > get_settings().frame_cache_size:
            _cache.popitem(last=False)
    return frame


def invalidate_frame(dataset_id: int) -> None:
    with _lock:
        for k in [k for k in _cache if k[0] == dataset_id]:
            _cache.pop(k, None)


# --------------------------------------------------------------------------- scope
@dataclass
class Scope:
    frame: DatasetFrame
    filters: FilterSpec
    base: pd.DataFrame          # dimension-filtered, all dates
    current: pd.DataFrame       # dimension-filtered, selected window
    previous: pd.DataFrame      # dimension-filtered, comparison window (may be empty)
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    prev_start: pd.Timestamp | None
    prev_end: pd.Timestamp | None
    label: str = ""
    prev_label: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def has_previous(self) -> bool:
        return not self.previous.empty


def apply_dimension_filters(df: pd.DataFrame, filters: FilterSpec, frame: DatasetFrame,
                            exclude: set[str] | None = None) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for dim, values in filters.active_dimensions().items():
        if exclude and dim in exclude:
            continue
        col = frame.dim_col(dim)
        if col is None:
            continue
        if dim == "customer" and frame.has("customer_id") and frame.has("customer_name"):
            mask &= df["customer_id"].isin(values) | df["customer_name"].isin(values)
        else:
            mask &= df[col].isin(values)
    return df[mask]


def _month_end(ts: pd.Timestamp) -> bool:
    return ts == ts + pd.offsets.MonthEnd(0)


def previous_window(start: pd.Timestamp, end: pd.Timestamp, mode: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    if mode == "none":
        return None
    if mode == "previous_year":
        return start - pd.DateOffset(years=1), end - pd.DateOffset(years=1)
    if start.day == 1 and _month_end(end):
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        p_start = start - pd.DateOffset(months=months)
        return p_start, start - pd.Timedelta(days=1)
    length = (end - start).days + 1
    p_end = start - pd.Timedelta(days=1)
    return p_end - pd.Timedelta(days=length - 1), p_end


def window_label(start: pd.Timestamp | None, end: pd.Timestamp | None) -> str:
    if start is None or end is None:
        return "All time"
    if start.month == 1 and start.day == 1 and end.month == 12 and end.day == 31 and start.year == end.year:
        return str(start.year)
    if start.day == 1 and _month_end(end):
        if start.year == end.year and start.month == end.month:
            return start.strftime("%b %Y")
        if start.year == end.year and start.month in (1, 4, 7, 10) and end.month == start.month + 2:
            return f"Q{(start.month - 1) // 3 + 1} {start.year}"
        return f"{start:%b %Y} – {end:%b %Y}"
    return f"{start:%d %b %Y} – {end:%d %b %Y}"


def build_scope(frame: DatasetFrame, filters: FilterSpec, exclude_dims: set[str] | None = None) -> Scope:
    df = frame.df
    base = apply_dimension_filters(df, filters, frame, exclude_dims)
    start = pd.Timestamp(filters.start_date) if filters.start_date else frame.date_min
    end = pd.Timestamp(filters.end_date) if filters.end_date else frame.date_max
    notes: list[str] = []
    if start is None or end is None:
        empty = base.iloc[0:0]
        return Scope(frame, filters, base, empty, empty, None, None, None, None, "No data", "", ["Dataset has no valid rows"])
    if start > end:
        start, end = end, start
    current = base[(base["txn_date"] >= start) & (base["txn_date"] <= end)]
    prev = previous_window(start, end, filters.comparison)
    if prev:
        ps, pe = prev
        previous = base[(base["txn_date"] >= ps) & (base["txn_date"] <= pe)]
        if previous.empty:
            notes.append(f"No data in the comparison period ({window_label(ps, pe)})")
    else:
        ps = pe = None
        previous = base.iloc[0:0]
    full = filters.start_date is None and filters.end_date is None
    label = "All time" if full else window_label(start, end)
    return Scope(frame, filters, base, current, previous, start, end, ps, pe, label,
                 window_label(ps, pe) if ps is not None else "", notes)


# --------------------------------------------------------------------------- measures
def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0 or (isinstance(b, float) and math.isnan(b)) or (isinstance(a, float) and math.isnan(a)):
        return None
    return a / b


def pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def totals(df: pd.DataFrame, frame: DatasetFrame) -> dict[str, float | None]:
    n = len(df)
    revenue = float(df["revenue"].sum()) if n else 0.0
    profit = float(df["profit"].sum()) if frame.has("profit") and n else None
    cost = float(df["cost"].sum()) if frame.has("cost") and n else None
    units = float(df["quantity"].sum()) if frame.has("quantity") and n else None
    orders = int(df["order_id"].nunique()) if frame.has("order_id") else n
    ck = frame.customer_key
    customers = int(df[ck].nunique()) if ck and n else (0 if ck else None)
    return {
        "revenue": revenue,
        "profit": profit,
        "cost": cost,
        "net_profit": float(df["net_profit"].sum()) if frame.has("net_profit") and n else None,
        "units": units,
        "transactions": n,
        "orders": orders,
        "customers": customers,
        "margin": safe_div(profit, revenue) if profit is not None else None,
        "aov": safe_div(revenue, orders) if orders else None,
        "budget": float(df["budget"].sum()) if frame.has("budget") and n else None,
    }


PERIOD_FREQ = {"day": "D", "week": "W-MON", "month": "M", "quarter": "Q", "year": "Y"}


def period_label(p: pd.Period, granularity: str) -> str:
    if granularity == "month":
        return p.strftime("%b %Y")
    if granularity == "quarter":
        return f"Q{p.quarter} {p.year}"
    if granularity == "year":
        return str(p.year)
    if granularity == "week":
        return f"Wk of {p.start_time:%d %b %Y}"
    return p.strftime("%d %b %Y")


def auto_granularity(start: pd.Timestamp | None, end: pd.Timestamp | None) -> str:
    if start is None or end is None:
        return "month"
    days = (end - start).days
    if days <= 45:
        return "day"
    if days <= 180:
        return "week"
    if days <= 365 * 4:
        return "month"
    return "quarter"


def timeseries(df: pd.DataFrame, frame: DatasetFrame, granularity: str, start: pd.Timestamp | None = None,
               end: pd.Timestamp | None = None) -> list[dict[str, Any]]:
    """Aggregate measures per period. Periods without transactions are returned with null measures
    (shown as gaps), never as fabricated zeros."""
    freq = PERIOD_FREQ[granularity]
    if start is None or end is None:
        if df.empty:
            return []
        start, end = df["txn_date"].min(), df["txn_date"].max()
    periods = pd.period_range(start=start, end=end, freq=freq)
    if df.empty:
        grouped = pd.DataFrame()
    else:
        key = df["txn_date"].dt.to_period(freq)
        agg = {"revenue": "sum"}
        if frame.has("profit"):
            agg["profit"] = "sum"
        if frame.has("cost"):
            agg["cost"] = "sum"
        if frame.has("quantity"):
            agg["quantity"] = "sum"
        if frame.has("budget"):
            agg["budget"] = "sum"
        grouped = df.groupby(key).agg(agg)
        grouped["transactions"] = df.groupby(key).size()
        if frame.has("order_id"):
            grouped["orders"] = df.groupby(key)["order_id"].nunique()
    out = []
    for p in periods:
        row: dict[str, Any] = {"period": p.start_time.date().isoformat(), "label": period_label(p, granularity),
                               "end": p.end_time.date().isoformat()}
        if not grouped.empty and p in grouped.index:
            g = grouped.loc[p]
            rev = float(g["revenue"])
            row.update(revenue=rev, transactions=int(g["transactions"]))
            if "profit" in g:
                row["profit"] = float(g["profit"])
                row["margin"] = safe_div(row["profit"], rev)
            if "cost" in g:
                row["cost"] = float(g["cost"])
            if "quantity" in g:
                row["units"] = float(g["quantity"])
            if "budget" in g:
                row["budget"] = float(g["budget"])
            orders = int(g["orders"]) if "orders" in g else row["transactions"]
            row["aov"] = safe_div(rev, orders)
        else:
            row.update(revenue=None, transactions=0, profit=None, margin=None, units=None, aov=None, no_data=True)
        out.append(row)
    return out


def breakdown(scope: Scope, dimension: str, sort_by: str = "revenue", limit: int | None = None,
              ascending: bool = False) -> list[dict[str, Any]]:
    frame = scope.frame
    col = frame.dim_col(dimension)
    if col is None:
        return []
    cur, prev = scope.current, scope.previous
    total_rev = float(cur["revenue"].sum()) or None

    def agg(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["revenue", "transactions"])
        spec: dict[str, Any] = {"revenue": ("revenue", "sum"), "transactions": ("revenue", "size")}
        if frame.has("profit"):
            spec["profit"] = ("profit", "sum")
        if frame.has("cost"):
            spec["cost"] = ("cost", "sum")
        if frame.has("quantity"):
            spec["units"] = ("quantity", "sum")
        return df.groupby(col, dropna=True).agg(**spec)

    c, p = agg(cur), agg(prev)
    rows = []
    for key, r in c.iterrows():
        rev = float(r["revenue"])
        prof = float(r["profit"]) if "profit" in r else None
        row = {
            "key": str(key), "revenue": rev, "transactions": int(r["transactions"]),
            "profit": prof, "cost": float(r["cost"]) if "cost" in r else None,
            "units": float(r["units"]) if "units" in r else None,
            "margin": safe_div(prof, rev) if prof is not None else None,
            "share": safe_div(rev, total_rev), "aov": safe_div(rev, int(r["transactions"])),
        }
        if scope.has_previous:
            if key in p.index:
                prev_rev = float(p.loc[key, "revenue"])
                prev_prof = float(p.loc[key, "profit"]) if "profit" in p.columns else None
            else:
                prev_rev, prev_prof = 0.0, (0.0 if frame.has("profit") else None)
            row["prev_revenue"] = prev_rev
            row["growth"] = pct_change(rev, prev_rev)
            row["prev_profit"] = prev_prof
            prev_margin = safe_div(prev_prof, prev_rev) if prev_prof is not None else None
            row["prev_margin"] = prev_margin
            row["margin_change"] = (row["margin"] - prev_margin) if row["margin"] is not None and prev_margin is not None else None
        rows.append(row)
    if scope.has_previous:  # members that sold before but not now still matter (lost revenue)
        for key, r in p.iterrows():
            if key not in c.index:
                rows.append({"key": str(key), "revenue": 0.0, "transactions": 0, "profit": 0.0 if frame.has("profit") else None,
                             "units": 0.0 if frame.has("quantity") else None, "margin": None, "share": 0.0, "aov": None,
                             "prev_revenue": float(r["revenue"]), "growth": -1.0,
                             "prev_profit": float(r["profit"]) if "profit" in r else None})
    sign = 1 if ascending else -1
    rows.sort(key=lambda x: (x.get(sort_by) is None, sign * (x.get(sort_by) or 0)))  # nulls always last
    return rows[:limit] if limit else rows


def pivot_series(df: pd.DataFrame, frame: DatasetFrame, dimension: str, granularity: str, start, end,
                 measure: str = "revenue", top: int = 8) -> dict[str, Any]:
    """Wide-format period × member table for stacked/multi-line charts."""
    col = frame.dim_col(dimension)
    if col is None or df.empty:
        return {"keys": [], "rows": []}
    measure_col = "quantity" if measure == "units" else measure
    order = df.groupby(col)[measure_col].sum().sort_values(ascending=False)
    keys = [str(k) for k in order.index[:top]]
    work = df.copy()
    work["_member"] = work[col].astype(str).where(work[col].astype(str).isin(keys), "Other")
    if len(order) > top:
        keys.append("Other")
    freq = PERIOD_FREQ[granularity]
    work["_p"] = work["txn_date"].dt.to_period(freq)
    table = work.pivot_table(index="_p", columns="_member", values=measure_col, aggfunc="sum")
    rows = []
    for p in pd.period_range(start=start, end=end, freq=freq):
        row: dict[str, Any] = {"period": p.start_time.date().isoformat(), "label": period_label(p, granularity)}
        for k in keys:
            v = table.at[p, k] if (p in table.index and k in table.columns) else np.nan
            row[k] = None if pd.isna(v) else float(v)
        rows.append(row)
    return {"keys": keys, "rows": rows}


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return None if pd.isna(obj) else obj.date().isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if obj is pd.NaT:
        return None
    return obj


def scope_meta(scope: Scope) -> dict[str, Any]:
    return {
        "label": scope.label, "start": scope.start, "end": scope.end, "comparison_label": scope.prev_label,
        "comparison_start": scope.prev_start, "comparison_end": scope.prev_end,
        "has_comparison": scope.has_previous, "rows": len(scope.current), "comparison_rows": len(scope.previous),
        "notes": scope.notes,
    }
