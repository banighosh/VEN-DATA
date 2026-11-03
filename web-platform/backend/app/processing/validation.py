"""Data validation layer: cross-field consistency and reconciliation checks."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .transform import REVENUE_TOLERANCE


def _check(cid: str, name: str, affected: int, total: int, detail: str, warn_at: float = 0.005,
           fail_at: float = 0.05, info: bool = False) -> dict[str, Any]:
    frac = affected / total if total else 0.0
    status = "pass" if affected == 0 else ("info" if info else ("fail" if frac > fail_at else ("warn" if frac > warn_at else "info")))
    return {"id": cid, "name": name, "status": status, "affected_rows": int(affected),
            "affected_pct": round(frac * 100, 2), "detail": detail}


def consistency_checks(canonical: pd.DataFrame, mapping: dict[str, str], revenue_source: str = "column") -> list[dict[str, Any]]:
    """Run calculation consistency checks on a canonical frame."""
    checks: list[dict[str, Any]] = []
    n = len(canonical)
    if n == 0:
        return checks
    rev, qty, price = canonical["revenue"], canonical["quantity"], canonical["unit_price"]

    if {"revenue", "unit_price", "quantity"} <= mapping.keys() and revenue_source != "derived":
        expected = price * qty
        valid = expected.notna() & rev.notna() & (expected != 0)
        rel = ((rev - expected).abs() / expected.abs())[valid]
        bad = rel > REVENUE_TOLERANCE
        ratios = (rev[valid][bad] / expected[valid][bad]).round(4)
        detail = f"{mapping['revenue']} matches {mapping['unit_price']} × {mapping['quantity']} within 1% for all rows."
        if bad.any():
            common = ratios.value_counts().head(3)
            share = common.iloc[0] / bad.sum()
            pattern = (f" {share:.0%} of mismatches are exactly {common.index[0]:g}× the expected value."
                       if share > 0.5 else "")
            detail = (f"{int(bad.sum()):,} rows ({bad.sum() / n * 100:.1f}%) where "
                      f"{mapping['revenue']} ≠ {mapping['unit_price']} × {mapping['quantity']}.{pattern} "
                      f"Revenue figures follow the source column as uploaded; switch the revenue source to "
                      f"'derived' in the mapping if price × units is authoritative.")
        checks.append(_check("revenue_reconciliation", "Revenue = unit price × quantity", int(bad.sum()), n, detail))

    if {"margin_pct", "profit", "revenue"} <= mapping.keys():
        calc = canonical["profit"] / rev.replace(0, np.nan)
        diff = (calc - canonical["margin_pct"]).abs()
        bad = (diff > 0.005).fillna(False)
        checks.append(_check("margin_reconciliation", "Margin % = profit ÷ revenue", int(bad.sum()), n,
                             "Reported margin agrees with profit ÷ revenue." if not bad.any()
                             else f"{int(bad.sum()):,} rows where the reported margin differs from profit ÷ revenue by more than 0.5 pp."))

    if canonical["profit"].notna().any():
        bad = (canonical["profit"] > rev).fillna(False)
        checks.append(_check("profit_le_revenue", "Profit does not exceed revenue", int(bad.sum()), n,
                             "No row reports profit above revenue." if not bad.any() else f"{int(bad.sum()):,} rows report profit above revenue."))

    neg = ((rev < 0) | (qty < 0)).fillna(False)
    checks.append(_check("non_negative", "Revenue and quantity are non-negative", int(neg.sum()), n,
                         "No negative revenue or quantity." if not neg.any()
                         else f"{int(neg.sum()):,} rows have negative revenue or quantity (returns or data errors).", info=False))

    zero = ((rev == 0) | (qty == 0)).fillna(False)
    if zero.any():
        checks.append(_check("zero_value_rows", "Zero-value transactions", int(zero.sum()), n,
                             f"{int(zero.sum()):,} rows record zero revenue or zero units.", info=True))

    d = pd.to_datetime(canonical["txn_date"], errors="coerce")
    if d.notna().any():
        lo, hi = pd.Timestamp("1990-01-01"), pd.Timestamp(date.today() + timedelta(days=366))
        bad = ((d < lo) | (d > hi)).fillna(False)
        checks.append(_check("date_plausible", "Dates fall in a plausible range", int(bad.sum()), n,
                             f"All dates fall between {d.min():%d %b %Y} and {d.max():%d %b %Y}." if not bad.any()
                             else f"{int(bad.sum()):,} rows have dates before 1990 or more than a year in the future."))
    return checks


def detect_key_conflicts(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Find ID columns whose values map to more than one name (e.g. Retailer ID shared by 3 retailers)."""
    conflicts = []
    norm = {c: re.sub(r"[^a-z0-9]+", " ", str(c).lower()).strip() for c in df.columns}
    for col, nc in norm.items():
        tokens = nc.split()
        if not tokens or tokens[-1] not in {"id", "key", "code", "no", "number"}:
            continue
        base = " ".join(tokens[:-1])
        if not base:
            continue
        partner = next((c for c, n2 in norm.items() if c != col and n2 in {base, f"{base} name"}), None)
        if partner is None:
            continue
        pair = df[[col, partner]].dropna()
        if pair.empty:
            continue
        names_per_id = pair.groupby(col)[partner].nunique()
        bad_ids = names_per_id[names_per_id > 1]
        if bad_ids.empty:
            continue
        example_id = bad_ids.index[0]
        names = sorted(map(str, pair.loc[pair[col] == example_id, partner].unique()))[:4]
        rows = int(pair[col].isin(bad_ids.index).sum())
        conflicts.append({
            "id_column": col, "name_column": partner, "ids_affected": int(len(bad_ids)), "rows_affected": rows,
            "example": f"{col} {example_id} → {', '.join(names)}",
        })
    return conflicts


def reconcile_totals(expected: dict[str, float], stored: dict[str, float], tolerance: float = 1e-6) -> list[dict[str, Any]]:
    """Post-load check: totals in the database must equal totals computed in memory."""
    results = []
    for key, exp in expected.items():
        got = stored.get(key)
        ok = got is not None and (abs((got or 0) - exp) <= max(abs(exp) * tolerance, 0.01))
        results.append({"metric": key, "expected": exp, "stored": got, "status": "pass" if ok else "fail"})
    return results
