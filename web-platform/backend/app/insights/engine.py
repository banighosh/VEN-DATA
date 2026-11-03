"""Automated insights.

Each insight has two clearly separated layers:

* ``observation`` + ``metrics`` — statistical facts computed deterministically
  from the filtered data. These are always present and always reproducible.
* ``implication`` + ``recommendation`` — interpretation. By default this comes
  from transparent rules in this module (``interpretation_source = "rule"``).
  When an LLM is configured, ``narrator.py`` may rewrite it
  (``interpretation_source = "ai"``). Interpretations describe what the numbers
  mean for the business; they never assert causes the data cannot show.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..analytics.common import Scope, breakdown, pct_change, safe_div, timeseries, totals
from ..analytics.kpis import compute_kpis, kpi_attention
from ..processing.cleaning import format_currency, format_number, format_percent

SEVERITY_RANK = {"critical": 0, "warning": 1, "positive": 2, "info": 3}


def _m(label: str, value: float | None, fmt: str) -> dict[str, Any]:
    return {"label": label, "value": value, "format": fmt}


def _confidence(n_cur: int, n_prev: int | None = None) -> str:
    n = min(n_cur, n_prev) if n_prev is not None else n_cur
    return "high" if n >= 500 else "medium" if n >= 50 else "low"


def _pct(v: float | None, signed: bool = True) -> str:
    return format_percent(v, 1, signed=signed)


def _pp(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:+.1f} pp"


def generate_insights(scope: Scope, quality: dict[str, Any] | None = None, limit: int = 12) -> list[dict[str, Any]]:
    frame = scope.frame
    cur, prev = scope.current, scope.previous
    out: list[dict[str, Any]] = []
    if cur.empty:
        return out
    t = totals(cur, frame)
    tp = totals(prev, frame) if scope.has_previous else None
    period, pperiod = scope.label, scope.prev_label

    # 1 — Revenue movement, decomposed into volume vs value.
    if tp and tp["revenue"]:
        g = pct_change(t["revenue"], tp["revenue"])
        tx_g = pct_change(t["transactions"], tp["transactions"])
        av_g = pct_change(t["aov"], tp["aov"])
        up = g is not None and g >= 0
        vol_share = None
        if g is not None and t["revenue"] > 0 and tp["revenue"] > 0 and abs(math.log(t["revenue"] / tp["revenue"])) > 1e-9:
            vol_share = math.log(t["transactions"] / tp["transactions"]) / math.log(t["revenue"] / tp["revenue"]) if tp["transactions"] and t["transactions"] else None
        driver = ""
        if vol_share is not None:
            driver = ("mostly from transaction volume" if vol_share > 0.6 else
                      "mostly from value per transaction" if vol_share < 0.4 else "from both volume and value per transaction")
        out.append({
            "id": "revenue_change", "category": "revenue", "severity": "positive" if up else "warning",
            "title": f"Revenue {'up' if up else 'down'} {_pct(abs(g) if g is not None else None, False)} vs {pperiod}",
            "observation": (f"Revenue {'increased' if up else 'decreased'} from {format_currency(tp['revenue'])} in {pperiod} to "
                            f"{format_currency(t['revenue'])} in {period} ({_pct(g)}). Transactions changed {_pct(tx_g)} and "
                            f"average value per transaction changed {_pct(av_g)}."),
            "metrics": [_m("Revenue", t["revenue"], "currency"), _m(f"Revenue {pperiod}", tp["revenue"], "currency"),
                        _m("Change", g, "percent"), _m("Transactions change", tx_g, "percent"), _m("Avg value change", av_g, "percent")],
            "implication": (f"The {'gain' if up else 'decline'} came {driver}." if driver else
                            "Revenue moved without a clear split between volume and value.")
                           + (" Growth that rests on volume depends on sustaining transaction counts." if vol_share and vol_share > 0.6 and up else ""),
            "recommendation": ("Check that the transaction growth reflects real demand (not changes in what was recorded) before "
                               "using this growth rate for targets." if up and vol_share and vol_share > 0.6 else
                               "Review the segments with the largest declines (see regional and product insights) and confirm whether "
                               "the drop is concentrated or broad-based." if not up else
                               "Protect the drivers of value per transaction (pricing, mix) while monitoring volume."),
            "confidence": _confidence(len(cur), len(prev)), "drill": {"page": "performance"},
        })

        # 2 — Data coverage caution when recorded activity changes drastically.
        if tx_g is not None and (tx_g > 1.0 or tx_g < -0.5):
            out.append({
                "id": "coverage_shift", "category": "data", "severity": "warning",
                "title": "Large change in recorded transaction volume",
                "observation": (f"{t['transactions']:,} transactions were recorded in {period} versus {tp['transactions']:,} in "
                                f"{pperiod} ({_pct(tx_g)}). Active selling days: {cur['txn_date'].dt.normalize().nunique()} vs "
                                f"{prev['txn_date'].dt.normalize().nunique()}."),
                "metrics": [_m("Transactions", t["transactions"], "number"), _m(f"Transactions {pperiod}", tp["transactions"], "number"),
                            _m("Change", tx_g, "percent")],
                "implication": "A shift this large can come from business change or from differences in how much activity the "
                               "source system captured. The data alone cannot tell these apart, so growth rates between these "
                               "periods should be read with caution.",
                "recommendation": f"Confirm with the data owner that {pperiod} is complete before using period-over-period growth in plans.",
                "confidence": "high", "drill": {"page": "data-management"},
            })

    # 3 — Category contribution / concentration.
    if frame.dim_col("category"):
        cats = breakdown(scope, "category")
        if cats:
            top = cats[0]
            second = cats[1] if len(cats) > 1 else None
            concentrated = (top["share"] or 0) >= 0.5
            out.append({
                "id": "category_contribution", "category": "category", "severity": "info",
                "title": f"{top['key']} drives {_pct(top['share'], False)} of revenue",
                "observation": (f"{top['key']} generated {format_currency(top['revenue'])} ({_pct(top['share'], False)} of revenue)"
                                + (f"; {second['key']} contributed {_pct(second['share'], False)}." if second else ".")
                                + (f" {top['key']} margin: {_pct(top['margin'], False)}." if top.get("margin") is not None else "")),
                "metrics": [_m(f"{top['key']} share", top["share"], "percent"), _m(f"{top['key']} revenue", top["revenue"], "currency")]
                           + ([_m(f"{top['key']} growth", top.get("growth"), "percent")] if top.get("growth") is not None else []),
                "implication": ("Revenue is concentrated in one category, so the total is sensitive to its performance."
                                if concentrated else "Revenue is spread across categories, limiting dependence on any one of them."),
                "recommendation": (f"Track {top['key']} performance closely and review growth options for "
                                   f"{second['key'] if second else 'other categories'} to reduce concentration."
                                   if concentrated else f"Prioritise investment by margin as well as size: compare {top['key']}'s "
                                   f"margin with the others before reallocating."),
                "confidence": _confidence(len(cur)), "drill": {"page": "products", "filter": {"category": [top["key"]]}},
            })

    # 4 — Underperforming regions (growth gap or margin gap vs the total).
    if frame.dim_col("region"):
        regs = breakdown(scope, "region")
        overall_g = pct_change(t["revenue"], tp["revenue"]) if tp else None
        flagged = []
        for r in regs:
            reasons = []
            if overall_g is not None and r.get("growth") is not None and r["growth"] < overall_g - 0.10:
                reasons.append(("growth", r["growth"] - overall_g))
            if t["margin"] is not None and r.get("margin") is not None and r["margin"] < t["margin"] - 0.02:
                reasons.append(("margin", r["margin"] - t["margin"]))
            if reasons:
                flagged.append((r, reasons))
        if flagged:
            flagged.sort(key=lambda x: min(v for _, v in x[1]))
            r, reasons = flagged[0]
            parts = []
            if any(k == "growth" for k, _ in reasons):
                parts.append(f"grew {_pct(r['growth'])} against {_pct(overall_g)} overall")
            if any(k == "margin" for k, _ in reasons):
                parts.append(f"earned a {_pct(r['margin'], False)} margin against {_pct(t['margin'], False)} overall")
            others = ", ".join(x[0]["key"] for x in flagged[1:3])
            out.append({
                "id": "underperforming_region", "category": "region", "severity": "warning",
                "title": f"{r['key']} is underperforming",
                "observation": f"{r['key']} {' and '.join(parts)} in {period}." + (f" Also below benchmark: {others}." if others else ""),
                "metrics": [_m(f"{r['key']} revenue", r["revenue"], "currency"), _m(f"{r['key']} growth", r.get("growth"), "percent"),
                            _m(f"{r['key']} margin", r.get("margin"), "percent"), _m("Overall margin", t["margin"], "percent")],
                "implication": f"{r['key']} is contributing less to growth or profitability than the business average.",
                "recommendation": f"Drill into {r['key']} by state, channel and product to locate where the gap sits before acting.",
                "confidence": _confidence(int(r["transactions"])), "drill": {"page": "regional", "filter": {"region": [r["key"]]}},
            })

    # 5 — Declining products.
    if frame.dim_col("product") and scope.has_previous:
        prods = breakdown(scope, "product")
        declining = [p for p in prods if p.get("growth") is not None and p["growth"] < 0]
        if declining:
            declining.sort(key=lambda p: p["growth"])
            names = ", ".join(f"{p['key']} ({_pct(p['growth'])})" for p in declining[:3])
            out.append({
                "id": "declining_products", "category": "product", "severity": "warning",
                "title": f"{len(declining)} product(s) declined vs {pperiod}",
                "observation": f"Revenue fell for {len(declining)} of {len(prods)} products: {names}.",
                "metrics": [_m(f"{p['key']} growth", p["growth"], "percent") for p in declining[:3]],
                "implication": "Declining lines reduce mix quality and may need intervention or rationalisation.",
                "recommendation": "Review pricing, availability and channel mix for these products; compare with their margin before deciding to invest or exit.",
                "confidence": _confidence(len(cur), len(prev)), "drill": {"page": "products"},
            })
        else:
            out.append({
                "id": "declining_products", "category": "product", "severity": "positive",
                "title": f"No product declined vs {pperiod}",
                "observation": f"All {len(prods)} products grew revenue compared with {pperiod}.",
                "metrics": [_m("Lowest product growth", min((p['growth'] for p in prods if p.get('growth') is not None), default=None), "percent")],
                "implication": "Growth is broad-based across the product range.",
                "recommendation": "Use margin, not growth, to prioritise where to invest next.",
                "confidence": _confidence(len(cur), len(prev)), "drill": {"page": "products"},
            })

    # 6 — Customer segment profitability.
    if frame.dim_col("customer_segment") and frame.has("profit"):
        segs = breakdown(scope, "customer_segment", sort_by="profit")
        if len(segs) >= 2:
            total_p = sum(s["profit"] or 0 for s in segs) or None
            a, b = segs[0], segs[1]
            out.append({
                "id": "segment_profitability", "category": "segment", "severity": "info",
                "title": f"{a['key']} segment leads profit",
                "observation": (f"{a['key']} produced {_pct(safe_div(a['profit'], total_p), False)} of {frame.label('profit').lower()} "
                                f"at a {_pct(a['margin'], False)} margin; {b['key']} produced {_pct(safe_div(b['profit'], total_p), False)} "
                                f"at {_pct(b['margin'], False)}."),
                "metrics": [_m(f"{a['key']} profit", a["profit"], "currency"), _m(f"{a['key']} margin", a["margin"], "percent"),
                            _m(f"{b['key']} margin", b["margin"], "percent")],
                "implication": ("The two segments are similarly profitable, so mix shifts between them have little margin effect."
                                if abs((a["margin"] or 0) - (b["margin"] or 0)) < 0.01 else
                                f"Shifting mix toward {a['key'] if (a['margin'] or 0) > (b['margin'] or 0) else b['key']} would raise blended margin."),
                "recommendation": "Compare segment margins within each product category to see whether the gap is a mix effect or a pricing effect.",
                "confidence": _confidence(len(cur)), "drill": {"page": "customers"},
            })

    # 7 — Channel: revenue leader vs margin leader.
    if frame.dim_col("channel") and frame.has("profit"):
        ch = breakdown(scope, "channel")
        if len(ch) >= 2:
            by_margin = sorted([c for c in ch if c["margin"] is not None], key=lambda c: c["margin"], reverse=True)
            lead, best_m = ch[0], by_margin[0]
            same = lead["key"] == best_m["key"]
            out.append({
                "id": "channel_mix", "category": "channel", "severity": "info",
                "title": f"{lead['key']} leads revenue" + ("" if same else f"; {best_m['key']} leads margin"),
                "observation": (f"{lead['key']} accounts for {_pct(lead['share'], False)} of revenue at a {_pct(lead['margin'], False)} margin. "
                                + ("It also has the highest margin." if same else
                                   f"{best_m['key']} has the highest margin ({_pct(best_m['margin'], False)}) on {_pct(best_m['share'], False)} of revenue.")),
                "metrics": [_m(f"{c['key']} margin", c["margin"], "percent") for c in by_margin[:3]],
                "implication": "Channel mix affects blended margin; growth in the higher-margin channel lifts profitability.",
                "recommendation": "Review channel-level pricing and cost-to-serve before shifting volume between channels.",
                "confidence": _confidence(len(cur)), "drill": {"page": "operations"},
            })

    # 8 — KPIs requiring management attention.
    kpis = compute_kpis(scope)["cards"]
    attention = kpi_attention(kpis)
    margin_card = next((c for c in kpis if c["key"] == "profit_margin" and c.get("available")), None)
    if attention:
        desc = "; ".join(
            f"{c['label']} {_pp(c['change']) if c['change_type'] == 'absolute' else _pct(c['change'])}" for c in attention)
        out.append({
            "id": "kpi_attention", "category": "kpi", "severity": "critical" if len(attention) >= 2 else "warning",
            "title": f"{len(attention)} KPI(s) need management attention",
            "observation": f"Adverse movement beyond threshold (±10% or ±1 pp) vs {pperiod}: {desc}.",
            "metrics": [_m(c["label"], c["change"], "pp" if c["change_type"] == "absolute" else "percent") for c in attention],
            "implication": "These measures moved against the business by more than the attention threshold.",
            "recommendation": "Assign owners to each flagged KPI and review them at the next performance meeting.",
            "confidence": _confidence(len(cur), len(prev)), "drill": {"page": "executive"},
        })
    elif margin_card and margin_card.get("change") is not None:
        out.append({
            "id": "kpi_attention", "category": "kpi", "severity": "positive",
            "title": "No KPI crossed an attention threshold",
            "observation": f"No KPI moved adversely by more than 10% (or 1 pp for ratios) vs {pperiod}. "
                           f"Profit margin changed {_pp(margin_card['change'])}.",
            "metrics": [_m("Margin change", margin_card["change"], "pp")],
            "implication": "Headline performance is stable or improving on every tracked KPI.",
            "recommendation": "Maintain the current review cadence; revisit thresholds if they are too loose for your business.",
            "confidence": _confidence(len(cur), len(prev)), "drill": {"page": "executive"},
        })

    # 9 — Anomalous months inside the window.
    series = [r for r in timeseries(cur, frame, "month", scope.start, scope.end) if r.get("revenue") is not None]
    if len(series) >= 6:
        vals = np.array([r["revenue"] for r in series])
        mu, sd = vals.mean(), vals.std(ddof=1)
        if sd > 0:
            z = (vals - mu) / sd
            idx = int(np.argmax(np.abs(z)))
            if abs(z[idx]) >= 2:
                r = series[idx]
                out.append({
                    "id": "revenue_anomaly", "category": "anomaly", "severity": "info",
                    "title": f"{r['label']} is an outlier month",
                    "observation": f"Revenue in {r['label']} was {format_currency(r['revenue'])}, {abs(z[idx]):.1f} standard deviations "
                                   f"{'above' if z[idx] > 0 else 'below'} the {period} monthly average of {format_currency(mu)}.",
                    "metrics": [_m(r["label"], r["revenue"], "currency"), _m("Monthly average", mu, "currency"), _m("Z-score", float(z[idx]), "number")],
                    "implication": "An unusual month distorts averages and run-rates built on this period.",
                    "recommendation": f"Check {r['label']} for one-off events or data issues before using it as a baseline.",
                    "confidence": "medium", "drill": {"page": "performance"},
                })

    # 10 — Customer concentration.
    ck = frame.customer_key
    if ck:
        accts = breakdown(scope, "customer")
        if len(accts) >= 2 and (accts[0]["share"] or 0) >= 0.25:
            top3 = sum(a["share"] or 0 for a in accts[:3])
            out.append({
                "id": "customer_concentration", "category": "customer", "severity": "warning" if accts[0]["share"] >= 0.35 else "info",
                "title": f"Top {frame.label(ck).lower()} holds {_pct(accts[0]['share'], False)} of revenue",
                "observation": f"{accts[0]['key']} accounts for {_pct(accts[0]['share'], False)} of revenue; the top three account for "
                               f"{_pct(top3, False)} across {len(accts)} {frame.label(ck).lower()}s.",
                "metrics": [_m(f"{a['key']} share", a["share"], "percent") for a in accts[:3]],
                "implication": "Revenue depends on a small number of accounts, which raises exposure to any single relationship.",
                "recommendation": "Review terms and health of the largest accounts and set a target for diversification.",
                "confidence": "high", "drill": {"page": "customers"},
            })

    # 11 — Data quality issues that affect the numbers above.
    for issue in (quality or {}).get("issues", []):
        if issue["severity"] == "critical" and issue["category"] == "consistency":
            out.append({
                "id": "data_quality", "category": "data", "severity": "critical",
                "title": "Revenue figures fail a consistency check",
                "observation": issue["message"],
                "metrics": [_m("Rows affected", issue["count"], "number"), _m("Share of rows", issue["pct"] / 100, "percent")],
                "implication": "Revenue-based KPIs inherit this inconsistency; totals differ depending on which figure is authoritative.",
                "recommendation": "Confirm the authoritative revenue definition with the data owner; switch the revenue source in Data Management if needed.",
                "confidence": "high", "drill": {"page": "data-management"},
            })
            break

    out.sort(key=lambda i: SEVERITY_RANK[i["severity"]])
    for i in out:
        i["interpretation_source"] = "rule"
        i.setdefault("period", period)
    return out[:limit]


def _fmt_metric(m: dict[str, Any]) -> str:
    v, f = m["value"], m["format"]
    if f == "currency":
        return format_currency(v)
    if f == "percent":
        return format_percent(v, 1)
    if f == "pp":
        return _pp(v)
    return format_number(v)
