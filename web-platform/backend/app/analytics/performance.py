"""Business performance: monthly / quarterly / annual trends, growth, contribution."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .common import (
    PERIOD_FREQ,
    Scope,
    breakdown,
    pct_change,
    period_label,
    pivot_series,
    safe_div,
    timeseries,
)

SEGMENT_DIMENSIONS = ("business_unit", "channel", "customer_segment", "category", "region")


def trend(scope: Scope, granularity: str) -> dict[str, Any]:
    frame = scope.frame
    current = timeseries(scope.current, frame, granularity, scope.start, scope.end)
    previous = (timeseries(scope.previous, frame, granularity, scope.prev_start, scope.prev_end)
                if scope.has_previous else [])
    overlay = []
    for i, row in enumerate(current):
        prev = previous[i] if i < len(previous) else None
        overlay.append({
            "label": row["label"], "period": row["period"],
            "current": row.get("revenue"), "previous": prev.get("revenue") if prev else None,
            "previous_label": prev["label"] if prev else None,
            "current_profit": row.get("profit"), "previous_profit": prev.get("profit") if prev else None,
        })

    # Period-over-period and year-over-year growth using full history for the baseline.
    full = timeseries(scope.base, frame, granularity)
    by_period = {r["period"]: r for r in full}
    lag = {"month": 12, "quarter": 4, "year": 1, "week": 52, "day": 365}[granularity]
    full_keys = [r["period"] for r in full]
    growth = []
    for row in current:
        idx = full_keys.index(row["period"]) if row["period"] in full_keys else None
        pop = yoy = None
        if idx is not None and idx > 0:
            pop = pct_change(row.get("revenue"), full[idx - 1].get("revenue"))
        if idx is not None and idx >= lag:
            yoy = pct_change(row.get("revenue"), full[idx - lag].get("revenue"))
        growth.append({"label": row["label"], "period": row["period"], "pop": pop, "yoy": yoy,
                       "revenue": row.get("revenue"), "margin": row.get("margin")})
        _ = by_period

    cumulative, run_c, run_p = [], 0.0, 0.0
    for o in overlay:
        run_c += o["current"] or 0.0
        run_p += o["previous"] or 0.0
        cumulative.append({"label": o["label"], "current": run_c if o["current"] is not None or run_c else None,
                           "previous": run_p if scope.has_previous else None})
    return {"granularity": granularity, "series": current, "previous_series": previous, "overlay": overlay,
            "growth": growth, "cumulative": cumulative}


def period_summary(scope: Scope, granularity: str) -> list[dict[str, Any]]:
    """Quarterly / annual summary table with growth vs the prior period in full history."""
    frame = scope.frame
    full = timeseries(scope.base, frame, granularity)
    lag = {"quarter": 4, "year": 1, "month": 12}.get(granularity, 1)
    rows = []
    start_key = scope.start.to_period(PERIOD_FREQ[granularity]).start_time.date().isoformat() if scope.start is not None else None
    for i, r in enumerate(full):
        if start_key and r["period"] < start_key:
            continue
        if scope.end is not None and r["period"] > scope.end.date().isoformat():
            continue
        prev = full[i - 1] if i > 0 else None
        yago = full[i - lag] if i >= lag else None
        rows.append({**r, "pop_growth": pct_change(r.get("revenue"), prev.get("revenue") if prev else None),
                     "yoy_growth": pct_change(r.get("revenue"), yago.get("revenue") if yago else None)})
    return rows


def performance(scope: Scope, granularity: str = "month", split_by: str | None = None) -> dict[str, Any]:
    frame = scope.frame
    split = split_by if split_by and frame.dim_col(split_by) else next(
        (d for d in ("channel", "category", "region") if frame.dim_col(d)), None)
    contribution = (pivot_series(scope.current, frame, split, granularity, scope.start, scope.end)
                    if split else {"keys": [], "rows": []})
    segments = {}
    for dim in SEGMENT_DIMENSIONS:
        if frame.dim_col(dim):
            segments[dim] = {"label": frame.label(dim), "rows": breakdown(scope, dim)}
    return {
        "trend": trend(scope, granularity),
        "quarterly": period_summary(scope, "quarter"),
        "annual": period_summary(scope, "year"),
        "contribution": {"dimension": split, "label": frame.label(split) if split else None, **contribution},
        "segments": segments,
    }


def drill_time(scope: Scope, level: str) -> list[dict[str, Any]]:
    """Year → quarter → month drill rows inside the current window."""
    return timeseries(scope.current, scope.frame, level, scope.start, scope.end)


def margin_by_period(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"label": r["label"], "margin": safe_div(r.get("profit"), r.get("revenue"))} for r in series]


def period_of(ts: pd.Timestamp, granularity: str) -> str:
    return period_label(ts.to_period(PERIOD_FREQ[granularity]), granularity)
