"""Product, regional, customer, financial and operational analytics modules."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .common import (
    PERIOD_FREQ,
    Scope,
    auto_granularity,
    breakdown,
    pct_change,
    period_label,
    pivot_series,
    safe_div,
    timeseries,
    totals,
)

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def unavailable(reason: str, requires: list[str] | None = None) -> dict[str, Any]:
    return {"available": False, "reason": reason, "requires": requires or []}


def matrix(df: pd.DataFrame, frame, row_dim: str, col_dim: str, measure: str = "revenue",
           row_order: list[str] | None = None) -> dict[str, Any]:
    """Row × column heat-map cells. `col_dim` may be a dimension or 'month'/'weekday'."""
    rcol = frame.dim_col(row_dim) if row_dim not in ("weekday",) else None
    if df.empty or (row_dim != "weekday" and rcol is None):
        return {"rows": [], "cols": [], "cells": []}
    work = df.copy()
    if row_dim == "weekday":
        work["_r"] = work["txn_date"].dt.dayofweek.map(lambda d: WEEKDAYS[d])
    else:
        work["_r"] = work[rcol].astype(str)
    if col_dim == "month":
        work["_c"] = work["txn_date"].dt.to_period("M")
        cols_p = sorted(work["_c"].unique())
        col_labels = [p.strftime("%b %Y") for p in cols_p]
        work["_c"] = work["_c"].map(lambda p: p.strftime("%b %Y"))
    elif col_dim == "month_of_year":
        work["_c"] = work["txn_date"].dt.strftime("%b")
        col_labels = [m for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                      if m in set(work["_c"])]
    else:
        ccol = frame.dim_col(col_dim)
        if ccol is None:
            return {"rows": [], "cols": [], "cells": []}
        work["_c"] = work[ccol].astype(str)
        col_labels = list(work.groupby("_c")["revenue"].sum().sort_values(ascending=False).index)
    if measure == "transactions":
        g = work.groupby(["_r", "_c"]).size().rename("value").to_frame()
    elif measure == "margin":
        g = work.groupby(["_r", "_c"]).agg(p=("profit", "sum"), r=("revenue", "sum"))
        g["value"] = g["p"] / g["r"].replace(0, np.nan)
    else:
        mcol = "quantity" if measure == "units" else measure
        g = work.groupby(["_r", "_c"])[mcol].sum().rename("value").to_frame()
    if row_dim == "weekday":
        rows = [d for d in WEEKDAYS if d in set(work["_r"])]
    else:
        rows = row_order or list(work.groupby("_r")["revenue"].sum().sort_values(ascending=False).index)
    cells = [{"row": r, "col": c, "value": None if pd.isna(v) else float(v)}
             for (r, c), v in g["value"].items()]
    return {"rows": rows, "cols": col_labels, "cells": cells, "measure": measure}


def _slope_pct(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    if len(vals) < 4 or np.mean(vals) == 0:
        return None
    x = np.arange(len(vals))
    slope = np.polyfit(x, vals, 1)[0]
    return float(slope / np.mean(vals))


# --------------------------------------------------------------------------- products
def products(scope: Scope, top: int = 5) -> dict[str, Any]:
    frame = scope.frame
    if not frame.dim_col("product"):
        return {"available": False, "reason": "Map a Product column to enable product analytics.", "requires": ["product"]}
    rows = breakdown(scope, "product")
    active = [r for r in rows if r["revenue"] > 0]
    gran = "month" if auto_granularity(scope.start, scope.end) in ("month", "quarter") else auto_granularity(scope.start, scope.end)
    trend = pivot_series(scope.current, frame, "product", gran, scope.start, scope.end, top=8)
    # Product → category lookup for colouring the profitability scatter.
    cat_of: dict[str, str] = {}
    if frame.dim_col("category") and not scope.current.empty:
        cat_of = scope.current.groupby("product")["category"].agg(lambda s: s.mode().iat[0] if not s.mode().empty else None).to_dict()
    for r in rows:
        r["category"] = cat_of.get(r["key"])
        series = [v.get(r["key"]) for v in trend["rows"]] if r["key"] in trend["keys"] else []
        r["trend_slope"] = _slope_pct(series)
    declining = [r for r in rows if (r.get("growth") is not None and r["growth"] < 0) or
                 (r.get("trend_slope") is not None and r["trend_slope"] < -0.03)]
    by_margin = sorted([r for r in active if r["margin"] is not None], key=lambda r: r["margin"], reverse=True)
    return {
        "available": True,
        "products": rows,
        "best": active[:top],
        "worst": sorted(active, key=lambda r: r["revenue"])[:top],
        "most_profitable": by_margin[:top],
        "least_profitable": by_margin[::-1][:top],
        "declining": sorted(declining, key=lambda r: (r.get("growth") if r.get("growth") is not None else 0)),
        "categories": breakdown(scope, "category") if frame.dim_col("category") else [],
        "subcategories": breakdown(scope, "subcategory") if frame.dim_col("subcategory") else [],
        "trend": trend,
        "category_trend": pivot_series(scope.current, frame, "category", gran, scope.start, scope.end)
        if frame.dim_col("category") else {"keys": [], "rows": []},
        "heatmap": matrix(scope.current, frame, "product", "channel" if frame.dim_col("channel") else "region",
                          "margin" if frame.has("profit") else "revenue",
                          row_order=[r["key"] for r in active]),
        "granularity": gran,
    }


# --------------------------------------------------------------------------- regional
def regional(scope: Scope) -> dict[str, Any]:
    frame = scope.frame
    geo = [d for d in ("region", "country", "state", "city") if frame.dim_col(d)]
    if not geo:
        return {"available": False, "reason": "Map a Region, State or City column to enable regional analytics.",
                "requires": ["region", "state", "city"]}
    out: dict[str, Any] = {"available": True, "levels": geo}
    for d in geo:
        out[d] = breakdown(scope, d)
    cur, base = scope.current, scope.base
    if "state" in geo:
        parent = "region" if "region" in geo else None
        if parent and not cur.empty:
            lookup = base.groupby("state")[parent].agg(lambda s: s.mode().iat[0]).to_dict()
            for r in out["state"]:
                r["region"] = lookup.get(r["key"])
    if "city" in geo:
        if "state" in geo and not cur.empty:
            lookup = base.groupby("city")["state"].agg(lambda s: s.mode().iat[0]).to_dict()
            for r in out["city"]:
                r["state"] = lookup.get(r["key"])
        out["top_cities"] = out["city"][:15]
        out["bottom_cities"] = sorted([r for r in out["city"] if r["revenue"] > 0], key=lambda r: r["revenue"])[:5]

    # Market penetration — measured as market coverage and share, because the
    # dataset carries no total-addressable-market figures.
    pen_level = "region" if "region" in geo else geo[0]
    pen = []
    total_rev = float(cur["revenue"].sum()) or None
    for key, grp in base.groupby(pen_level):
        cur_grp = cur[cur[pen_level] == key]
        row = {"key": str(key), "share": safe_div(float(cur_grp["revenue"].sum()), total_rev)}
        for lvl, plural in (("state", "states"), ("city", "cities")):
            if lvl in geo:
                seen = grp[lvl].nunique()
                active = cur_grp[lvl].nunique()
                row[f"active_{plural}"] = int(active)
                row[f"known_{plural}"] = int(seen)
                row[f"{lvl}_coverage"] = safe_div(active, seen)
        if "city" in geo:
            row["revenue_per_city"] = safe_div(float(cur_grp["revenue"].sum()), cur_grp["city"].nunique())
        pen.append(row)
    out["penetration"] = {
        "level": pen_level, "rows": sorted(pen, key=lambda r: -(r["share"] or 0)),
        "active_states": int(cur["state"].nunique()) if "state" in geo else None,
        "known_states": int(base["state"].nunique()) if "state" in geo else None,
        "active_cities": int(cur["city"].nunique()) if "city" in geo else None,
        "known_cities": int(base["city"].nunique()) if "city" in geo else None,
        "revenue_per_active_city": safe_div(float(cur["revenue"].sum()), cur["city"].nunique()) if "city" in geo and not cur.empty else None,
        "note": "Coverage = locations with sales in the period ÷ locations seen anywhere in the dataset. "
                "True market penetration needs market-size data, which this dataset does not include.",
    }
    out["heatmap"] = matrix(cur, frame, pen_level, "month")
    return out


# --------------------------------------------------------------------------- customers
def customers(scope: Scope, min_customers_for_clv: int = 30) -> dict[str, Any]:
    frame = scope.frame
    ck = frame.customer_key
    if ck is None:
        return {"available": False, "reason": "Map a Customer or Customer ID column to enable customer analytics.",
                "requires": ["customer_id", "customer_name"],
                "segments": breakdown(scope, "customer_segment") if frame.dim_col("customer_segment") else []}
    base, cur, prev = scope.base, scope.current, scope.previous
    first = base.groupby(ck)["txn_date"].min()
    last = base.groupby(ck)["txn_date"].max()
    active = set(cur[ck].dropna().unique())
    new = {c for c in active if scope.start is not None and first.get(c) is not None and first[c] >= scope.start}
    returning = active - new
    prev_active = set(prev[ck].dropna().unique()) if scope.has_previous else set()
    retained = prev_active & active
    freq = cur.groupby(ck).size()
    gaps = []
    for _, g in cur.groupby(ck)["txn_date"]:
        days = np.sort(g.dt.normalize().unique())
        if len(days) > 1:
            gaps.append(float(np.diff(days).astype("timedelta64[D]").astype(float).mean()))

    gran = "month" if auto_granularity(scope.start, scope.end) in ("month", "quarter") else auto_granularity(scope.start, scope.end)
    freq_key = PERIOD_FREQ[gran]
    monthly = []
    if not cur.empty:
        per = cur.assign(_p=cur["txn_date"].dt.to_period(freq_key))
        first_p = first.dt.to_period(freq_key)
        for p in pd.period_range(scope.start, scope.end, freq=freq_key):
            members = set(per.loc[per["_p"] == p, ck].unique())
            n_new = sum(1 for c in members if first_p.get(c) == p)
            monthly.append({"label": period_label(p, gran), "period": p.start_time.date().isoformat(),
                            "new": n_new, "returning": len(members) - n_new, "active": len(members)})

    accounts = breakdown(scope, "customer")
    lifetime = base.groupby(ck)["revenue"].sum()
    total = float(sum(r["revenue"] for r in accounts)) or None
    cum = 0.0
    for r in accounts:
        cum += r["revenue"]
        share_cum = safe_div(cum, total) or 0
        r["cumulative_share"] = share_cum
        r["tier"] = "A" if share_cum <= 0.8 or r is accounts[0] else ("B" if share_cum <= 0.95 else "C")
        r["first_purchase"] = first.get(r["key"])
        r["last_purchase"] = last.get(r["key"])
        r["lifetime_revenue"] = float(lifetime.get(r["key"], 0.0))
        r["status"] = "New" if r["key"] in new else ("Returning" if r["key"] in returning else "Lapsed")

    n_customers = int(base[ck].nunique())
    lifespan_days = (last - first).dt.days
    if n_customers >= min_customers_for_clv:
        avg_rev = float(lifetime.mean())
        months = max(((base["txn_date"].max() - base["txn_date"].min()).days / 30.44), 1)
        clv = {"available": True, "method": "Historical CLV",
               "avg_lifetime_revenue": avg_rev,
               "avg_lifetime_profit": float(base.groupby(ck)["profit"].sum().mean()) if frame.has("profit") else None,
               "avg_lifespan_days": float(lifespan_days.mean()),
               "avg_monthly_revenue_per_customer": avg_rev / months,
               "note": "Observed revenue per customer to date. Not a predictive model."}
    else:
        clv = {"available": False, "method": "Per-account lifetime value",
               "reason": f"Only {n_customers} distinct customers, too few for a statistical CLV model "
                         f"(needs at least {min_customers_for_clv}). Lifetime revenue is shown per account instead."}

    pareto = [{"key": r["key"], "cumulative_share": r["cumulative_share"], "share": r["share"]} for r in accounts]
    tiers: dict[str, dict[str, float]] = {}
    for r in accounts:
        t = tiers.setdefault(r["tier"], {"customers": 0, "revenue": 0.0})
        t["customers"] += 1
        t["revenue"] += r["revenue"]
    return {
        "available": True,
        "key": ck,
        "label": frame.label(ck),
        "summary": {
            "total": len(active), "new": len(new), "returning": len(returning),
            "previous_total": len(prev_active) if scope.has_previous else None,
            "retained": len(retained) if scope.has_previous else None,
            "retention_rate": safe_div(len(retained), len(prev_active)) if prev_active else None,
            "churned": len(prev_active - active) if scope.has_previous else None,
            "avg_transactions": float(freq.mean()) if len(freq) else None,
            "avg_days_between_purchases": float(np.mean(gaps)) if gaps else None,
            "avg_revenue_per_customer": safe_div(float(cur["revenue"].sum()), len(active)),
            "top_customer_share": accounts[0]["share"] if accounts else None,
            "known_customers": n_customers,
        },
        "new_vs_returning": monthly,
        "segments": breakdown(scope, "customer_segment") if frame.dim_col("customer_segment") else [],
        "segment_label": frame.label("customer_segment"),
        "accounts": accounts,
        "tiers": [{"tier": k, **v} for k, v in sorted(tiers.items())],
        "pareto": pareto,
        "frequency": [{"key": str(k), "transactions": int(v)} for k, v in freq.sort_values(ascending=False).items()],
        "clv": clv,
        "granularity": gran,
    }


# --------------------------------------------------------------------------- financial
def financial(scope: Scope, bridge_dim: str | None = None) -> dict[str, Any]:
    frame = scope.frame
    cur = totals(scope.current, frame)
    prev = totals(scope.previous, frame) if scope.has_previous else None

    def line(key, label, value, prev_value, kind="amount", note=None):
        if value is None:
            return {"key": key, "label": label, "available": False, "note": note}
        change = (value - prev_value) if (kind == "ratio" and prev_value is not None) else pct_change(value, prev_value)
        return {"key": key, "label": label, "available": True, "value": value, "previous": prev_value,
                "change": change, "kind": kind, "note": note}

    p = (lambda k: prev[k] if prev else None)
    statement = [
        line("revenue", "Revenue", cur["revenue"], p("revenue")),
        line("cost", frame.label("cost"), cur["cost"], p("cost"),
             note="Revenue minus profit; the source has no cost column" if "cost" in frame.derived else None),
        line("profit", frame.label("profit"), cur["profit"], p("profit")),
        line("margin", f"{frame.label('profit')} margin", cur["margin"], p("margin"), kind="ratio"),
        line("net_profit", "Net profit", cur["net_profit"], p("net_profit"),
             note=None if frame.has("net_profit") else "Not in this dataset. Map a Net profit column to enable it."),
    ]
    gran = "month" if auto_granularity(scope.start, scope.end) in ("month", "quarter") else auto_granularity(scope.start, scope.end)
    trend = timeseries(scope.current, frame, gran, scope.start, scope.end)

    expense: dict[str, Any] = {}
    if frame.has("cost"):
        for dim in ("category", "channel", "region", "subcategory"):
            if frame.dim_col(dim):
                rows = breakdown(scope, dim, sort_by="cost")
                tot = sum(r["cost"] or 0 for r in rows) or None
                expense[dim] = {"label": frame.label(dim),
                                "rows": [{"key": r["key"], "cost": r["cost"], "share": safe_div(r["cost"], tot),
                                          "cost_ratio": safe_div(r["cost"], r["revenue"])} for r in rows]}

    waterfall = []
    if frame.has("cost") and frame.has("profit"):
        wf_dim = next((d for d in ("category", "channel", "region") if frame.dim_col(d)), None)
        waterfall.append({"name": "Revenue", "value": cur["revenue"], "kind": "total"})
        if wf_dim:
            for r in breakdown(scope, wf_dim, sort_by="cost"):
                if r["cost"]:
                    waterfall.append({"name": f"{frame.label('cost')} · {r['key']}", "value": -r["cost"], "kind": "delta"})
        else:
            waterfall.append({"name": frame.label("cost"), "value": -(cur["cost"] or 0), "kind": "delta"})
        waterfall.append({"name": frame.label("profit"), "value": cur["profit"], "kind": "total"})

    bridge = None
    bdim = bridge_dim if bridge_dim and frame.dim_col(bridge_dim) else next(
        (d for d in ("category", "channel", "region", "product") if frame.dim_col(d)), None)
    if scope.has_previous and frame.has("profit") and bdim:
        steps = [{"name": f"{frame.label('profit')} · {scope.prev_label}", "value": prev["profit"], "kind": "total"}]
        for r in breakdown(scope, bdim, sort_by="profit"):
            delta = (r["profit"] or 0) - (r.get("prev_profit") or 0)
            steps.append({"name": r["key"], "value": delta, "kind": "delta"})
        steps.append({"name": f"{frame.label('profit')} · {scope.label}", "value": cur["profit"], "kind": "total"})
        bridge = {"dimension": bdim, "label": frame.label(bdim), "steps": steps}

    budget = (unavailable("No budget or target column in this dataset. Map a Budget / target column to compare plan vs actual.",
                          ["budget"]) if not frame.has("budget") else {
        "available": True,
        "total_budget": cur["budget"], "total_actual": cur["revenue"],
        "variance": cur["revenue"] - (cur["budget"] or 0), "attainment": safe_div(cur["revenue"], cur["budget"]),
        "series": [{"label": r["label"], "actual": r.get("revenue"), "budget": r.get("budget")} for r in trend],
    })
    margins = {dim: {"label": frame.label(dim), "rows": breakdown(scope, dim, sort_by="margin")}
               for dim in ("channel", "region", "category", "customer_segment") if frame.dim_col(dim) and frame.has("profit")}
    return {"statement": statement, "trend": trend, "granularity": gran, "expense_breakdown": expense,
            "waterfall": waterfall, "bridge": bridge, "budget": budget, "margins": margins,
            "cost_is_derived": "cost" in frame.derived}


# --------------------------------------------------------------------------- operations
def operations(scope: Scope) -> dict[str, Any]:
    frame = scope.frame
    cur = scope.current
    gran = auto_granularity(scope.start, scope.end)
    series = timeseries(cur, frame, gran, scope.start, scope.end)
    t_cur = totals(cur, frame)
    t_prev = totals(scope.previous, frame) if scope.has_previous else None
    upt = safe_div(t_cur["units"], t_cur["transactions"]) if t_cur["units"] is not None else None
    upt_prev = safe_div(t_prev["units"], t_prev["transactions"]) if t_prev and t_prev["units"] is not None else None
    volume = [{"label": r["label"], "transactions": r.get("transactions"), "units": r.get("units"),
               "units_per_txn": safe_div(r.get("units"), r.get("transactions")) if r.get("transactions") else None}
              for r in series]
    channel = []
    if frame.dim_col("channel"):
        for r in breakdown(scope, "channel"):
            r["units_per_txn"] = safe_div(r.get("units"), r["transactions"]) if r["transactions"] else None
            r["revenue_per_unit"] = safe_div(r["revenue"], r.get("units"))
            r["profit_per_unit"] = safe_div(r.get("profit"), r.get("units"))
            channel.append(r)

    def date_gap(a: str, b: str, label: str) -> dict[str, Any]:
        if not (frame.has(a) and frame.has(b)):
            missing = [f for f in (a, b) if not frame.has(f)]
            return unavailable(f"{label} needs {' and '.join(frame.label(m) for m in missing)}, which this dataset does not have.", missing)
        days = (cur[b] - cur[a]).dt.days.dropna()
        if days.empty:
            return unavailable(f"No rows with both dates in the selected period for {label.lower()}.")
        monthly = cur.assign(_d=(cur[b] - cur[a]).dt.days).groupby(cur["txn_date"].dt.to_period("M"))["_d"].mean()
        return {"available": True, "avg_days": float(days.mean()), "median_days": float(days.median()),
                "p90_days": float(days.quantile(0.9)), "negative": int((days < 0).sum()),
                "trend": [{"label": p.strftime("%b %Y"), "avg_days": float(v)} for p, v in monthly.items()]}

    processing = date_gap("txn_date", "ship_date", "Order processing time")
    delivery = date_gap("ship_date" if frame.has("ship_date") else "txn_date", "delivery_date", "Delivery time")
    if frame.has("order_status"):
        status = cur["order_status"].astype(str).str.lower()
        cancelled = status.str.contains("cancel|void")
        returned = status.str.contains("return|refund")
        by_month = cur.assign(_c=cancelled).groupby(cur["txn_date"].dt.to_period("M"))["_c"].mean()
        cancellations = {"available": True, "cancellation_rate": float(cancelled.mean()), "return_rate": float(returned.mean()),
                         "statuses": cur["order_status"].value_counts().to_dict(),
                         "trend": [{"label": p.strftime("%b %Y"), "rate": float(v)} for p, v in by_month.items()]}
        fulfilment = {"available": True, "fulfilled_rate": float((~cancelled & ~returned).mean())}
    else:
        cancellations = unavailable("Cancellation rate needs an Order status column, which this dataset does not have.", ["order_status"])
        fulfilment = unavailable("Fulfilment performance needs order status or ship/delivery dates, which this dataset does not have.",
                                 ["order_status", "ship_date", "delivery_date"])
    return {
        "granularity": gran,
        "summary": {
            "transactions": t_cur["transactions"], "prev_transactions": t_prev["transactions"] if t_prev else None,
            "orders": t_cur["orders"], "units": t_cur["units"], "prev_units": t_prev["units"] if t_prev else None,
            "units_per_txn": upt, "prev_units_per_txn": upt_prev,
            "revenue_per_unit": safe_div(t_cur["revenue"], t_cur["units"]),
            "prev_revenue_per_unit": safe_div(t_prev["revenue"], t_prev["units"]) if t_prev else None,
            "active_days": int(cur["txn_date"].dt.normalize().nunique()) if not cur.empty else 0,
            "txn_per_active_day": safe_div(t_cur["transactions"], cur["txn_date"].dt.normalize().nunique()) if not cur.empty else None,
        },
        "volume": volume,
        "weekday_heatmap": matrix(cur, frame, "weekday", "month_of_year", "transactions"),
        "channel_efficiency": channel,
        "processing_time": processing,
        "delivery": delivery,
        "cancellations": cancellations,
        "fulfilment": fulfilment,
    }
