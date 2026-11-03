"""Data quality report: completeness, uniqueness, validity, formatting and consistency."""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..processing.cleaning import detect_duplicates

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def build_quality_report(df: pd.DataFrame, profiles: list[dict[str, Any]], checks: list[dict[str, Any]] | None = None,
                         conflicts: list[dict[str, Any]] | None = None, key_columns: set[str] | None = None,
                         sampled: bool = False) -> dict[str, Any]:
    rows, cols = df.shape
    cells = rows * cols
    key_columns = key_columns or set()
    missing_cells = sum(p["missing"] for p in profiles)
    invalid_cells = sum(p["invalid"] for p in profiles)
    non_null_cells = max(sum(p["non_null"] for p in profiles), 1)
    dup_mask = detect_duplicates(df)
    dup_rows = int(dup_mask.sum())
    issues: list[dict[str, Any]] = []

    def add(severity, category, message, column=None, count=0, examples=None):
        issues.append({"severity": severity, "category": category, "column": column, "count": int(count),
                       "pct": round(count / rows * 100, 2) if rows else 0.0, "message": message,
                       "examples": examples or []})

    for p in profiles:
        col = p["name"]
        if p["inferred_type"] == "empty":
            add("warning", "missing", f"Column '{col}' is completely empty.", col, rows)
            continue
        if p["missing"]:
            sev = "critical" if col in key_columns else ("warning" if p["missing_pct"] >= 5 else "info")
            add(sev, "missing", f"{p['missing']:,} missing value(s) in '{col}' ({p['missing_pct']}%).", col, p["missing"])
        if p["invalid"]:
            cat = "invalid_date" if p["inferred_type"] == "date" else "invalid_number"
            kind = "date" if cat == "invalid_date" else "numeric"
            sev = "critical" if col in key_columns and p["invalid"] / max(p["non_null"], 1) > 0.05 else "warning"
            add(sev, cat, f"{p['invalid']:,} value(s) in '{col}' are not valid {kind} values.", col, p["invalid"], p["invalid_examples"])
        if p["mixed_types"] and not p["invalid"]:
            add("info", "formatting", f"'{col}' mixes numbers and text.", col, 0, p["samples"][:3])
        if p["whitespace_issues"]:
            add("info", "formatting", f"{p['whitespace_issues']:,} value(s) in '{col}' have leading, trailing or repeated spaces.",
                col, p["whitespace_issues"])
        if p["case_variants"]:
            groups = p["case_variants"]
            ex = [" / ".join(g) for g in groups[:3]]
            add("warning", "formatting", f"'{col}' has {len(groups)} value(s) spelled inconsistently (case or spacing).", col,
                len(groups), ex)
        if p["outliers"]:
            add("info", "outlier", f"{p['outliers']:,} extreme outlier(s) in '{col}' (beyond 3× IQR).", col, p["outliers"])

    if dup_rows:
        add("warning", "duplicate", f"{dup_rows:,} row(s) exactly duplicate an earlier row.", None, dup_rows)

    for c in conflicts or []:
        add("warning", "key_conflict",
            f"'{c['id_column']}' is not a unique key for '{c['name_column']}': {c['ids_affected']} ID(s) are shared by "
            f"different names ({c['example']}).", c["id_column"], c["rows_affected"])

    for chk in checks or []:
        if chk["status"] in ("fail", "warn"):
            sev = "critical" if chk["status"] == "fail" else "warning"
            add(sev, "consistency", f"{chk['name']}: {chk['detail']}", None, chk["affected_rows"])
        elif chk["status"] == "info" and chk["affected_rows"]:
            add("info", "consistency", f"{chk['name']}: {chk['detail']}", None, chk["affected_rows"])

    issues.sort(key=lambda i: (SEVERITY_ORDER[i["severity"]], -i["count"]))

    completeness = 1 - missing_cells / cells if cells else 1.0
    uniqueness = 1 - dup_rows / rows if rows else 1.0
    validity = 1 - invalid_cells / non_null_cells
    # Consistency = average pass rate across every cross-field check that ran.
    rates = [1 - (c["affected_pct"] / 100 if c["status"] in ("fail", "warn") else 0.0) for c in (checks or [])]
    rates += [1 - c["rows_affected"] / rows for c in (conflicts or []) if rows]
    consistency = sum(rates) / len(rates) if rates else 1.0
    score = 100 * (0.35 * completeness + 0.2 * uniqueness + 0.25 * validity + 0.2 * consistency)
    n_crit = sum(1 for i in issues if i["severity"] == "critical")
    n_warn = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0.0, score - min(5 * n_crit, 15) - min(n_warn, 5))  # open issues cap the headline score
    grade = "A" if score >= 95 else "B" if score >= 85 else "C" if score >= 70 else "D"
    return {
        "summary": {
            "rows": int(rows), "columns": int(cols), "cells": int(cells), "missing_cells": int(missing_cells),
            "missing_pct": round(missing_cells / cells * 100, 2) if cells else 0.0, "duplicate_rows": dup_rows,
            "duplicate_pct": round(dup_rows / rows * 100, 2) if rows else 0.0, "invalid_values": int(invalid_cells),
            "critical": sum(1 for i in issues if i["severity"] == "critical"),
            "warnings": sum(1 for i in issues if i["severity"] == "warning"),
            "sampled": sampled,
        },
        "dimensions": {
            "completeness": round(completeness * 100, 1), "uniqueness": round(uniqueness * 100, 1),
            "validity": round(validity * 100, 1), "consistency": round(consistency * 100, 1),
        },
        "score": round(score, 1),
        "grade": grade,
        "issues": issues,
        "checks": checks or [],
        "key_conflicts": conflicts or [],
    }
