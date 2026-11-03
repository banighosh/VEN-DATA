"""Executive KPI cards with previous-period comparison."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .common import Scope, auto_granularity, pct_change, previous_window, safe_div, timeseries, totals

UP_IS_GOOD = {"total_revenue", "total_sales", "total_profit", "profit_margin", "growth_rate", "aov",
              "total_customers", "transaction_volume"}


def _direction(change: float | None, tol: float = 1e-9) -> str:
    if change is None:
        return "flat"
    return "up" if change > tol else "down" if change < -tol else "flat"


def _card(key: str, label: str, value, previous, fmt: str, change_type: str = "relative", **extra) -> dict[str, Any]:
    if value is None:
        return {"key": key, "label": label, "available": False, "format": fmt, **extra}
    if change_type == "absolute":
        change = (value - previous) if previous is not None else None
    else:
        change = pct_change(value, previous)
    direction = _direction(change)
    good = key in UP_IS_GOOD
    sentiment = "neutral" if direction == "flat" else ("positive" if (direction == "up") == good else "negative")
    return {"key": key, "label": label, "available": True, "value": value, "previous": previous, "change": change,
            "change_type": change_type, "direction": direction, "sentiment": sentiment, "format": fmt, **extra}


def compute_kpis(scope: Scope) -> dict[str, Any]:
    frame = scope.frame
    cur = totals(scope.current, frame)
    prev = totals(scope.previous, frame) if scope.has_previous else None
    p = (lambda k: prev[k] if prev else None)

    # Growth rate needs the window before the comparison window as its own baseline.
    prev_growth = None
    growth = pct_change(cur["revenue"], p("revenue"))
    if scope.has_previous and scope.prev_start is not None:
        pp = previous_window(scope.prev_start, scope.prev_end, scope.filters.comparison)
        if pp:
            base = scope.base
            pp_df = base[(base["txn_date"] >= pp[0]) & (base["txn_date"] <= pp[1])]
            if not pp_df.empty:
                prev_growth = pct_change(p("revenue"), float(pp_df["revenue"].sum()))

    gran = auto_granularity(scope.start, scope.end)
    series = timeseries(scope.current, frame, gran, scope.start, scope.end)

    def spark(metric: str) -> list[dict[str, Any]]:
        return [{"label": r["label"], "value": r.get(metric)} for r in series]

    ck = frame.customer_key
    cards = [
        _card("total_revenue", "Total Revenue", cur["revenue"], p("revenue"), "currency", sparkline=spark("revenue"),
              source=frame.source("revenue"), derived="revenue" in frame.derived),
        _card("total_sales", "Total Sales (Units)", cur["units"], p("units"), "number", sparkline=spark("units"),
              source=frame.source("quantity"),
              **({} if cur["units"] is not None else {"reason": "Map a Units / quantity column to enable."})),
        _card("total_profit", f"Total {frame.label('profit')}", cur["profit"], p("profit"), "currency",
              sparkline=spark("profit"), source=frame.source("profit"),
              **({} if cur["profit"] is not None else {"reason": "Map a Profit or Cost column to enable."})),
        _card("profit_margin", "Profit Margin", cur["margin"], p("margin"), "percent", change_type="absolute",
              sparkline=spark("margin"), note=f"{frame.label('profit')} ÷ revenue",
              **({} if cur["margin"] is not None else {"reason": "Requires profit or cost."})),
        _card("growth_rate", "Revenue Growth", growth, prev_growth, "percent", change_type="absolute",
              note="Change in growth rate is shown in percentage points" if prev_growth is not None else None,
              **({} if growth is not None else {"reason": "No revenue in the comparison period to grow from."})),
        _card("aov", "Avg Order Value" if frame.has("order_id") else "Avg Transaction Value", cur["aov"], p("aov"), "currency",
              sparkline=spark("aov"),
              note=None if frame.has("order_id") else "Per transaction line (no Order ID column mapped)"),
        _card("total_customers", "Total Customers", cur["customers"], p("customers"), "number",
              note=f"Distinct {frame.label(ck).lower()}s" if ck else None,
              **({} if cur["customers"] is not None else {"reason": "Map a Customer column to enable."})),
        _card("transaction_volume", "Transaction Volume", cur["transactions"], p("transactions"), "number",
              sparkline=spark("transactions"), note="Rows / invoice lines"),
    ]
    return {"cards": cards, "totals": cur, "previous_totals": prev, "granularity": gran}


def kpi_attention(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """KPIs whose movement crosses an attention threshold."""
    flagged = []
    for c in cards:
        if not c.get("available") or c.get("change") is None:
            continue
        ch = c["change"]
        if c["change_type"] == "absolute":
            hit = abs(ch) >= 0.01  # one percentage point
        else:
            hit = abs(ch) >= 0.10
        if hit and c["sentiment"] == "negative":
            flagged.append(c)
    return flagged


def share_of(series: pd.Series) -> pd.Series:
    total = series.sum()
    return series / total if total else series * 0


__all__ = ["compute_kpis", "kpi_attention", "safe_div"]
