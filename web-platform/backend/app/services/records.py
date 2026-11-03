"""Data Explorer queries (server-side SQL), exports and dashboard reports."""
from __future__ import annotations

import csv
import html
import io
from datetime import date, datetime
from typing import Any, Iterator

from sqlalchemy import Select, String, asc, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from ..analytics.common import DatasetFrame, FilterSpec, Scope
from ..models import DATE_FIELDS, NUMBER_FIELDS, TEXT_FIELDS, Dataset, FactRecord
from ..processing.cleaning import format_currency, format_number, format_percent

SYSTEM_COLUMNS = ("row_number", "issues", "is_valid")


def explorer_columns(frame: DatasetFrame) -> list[dict[str, Any]]:
    cols = [{"key": "row_number", "label": "Source row", "type": "number", "source": None}]
    order = ("txn_date", "customer_name", "customer_id", "region", "state", "city", "product", "category", "subcategory",
             "channel", "customer_segment", "business_unit", "brand", "country", "order_id", "order_status", "ship_date",
             "delivery_date", "unit_price", "quantity", "revenue", "cost", "profit", "net_profit", "margin_pct", "discount", "budget",
             "product_id")
    for key in order:
        if key in frame.available:
            typ = "date" if key in DATE_FIELDS else "number" if key in NUMBER_FIELDS else "text"
            fmt = ("currency" if key in ("unit_price", "revenue", "cost", "profit", "net_profit", "discount", "budget")
                   else "percent" if key == "margin_pct" else None)
            cols.append({"key": key, "label": frame.label(key), "type": typ, "format": fmt,
                         "source": frame.source(key), "derived": key in frame.derived})
    cols.append({"key": "issues", "label": "Data issues", "type": "text", "source": None})
    return cols


def _apply_filters(stmt: Select, dataset_id: int, filters: FilterSpec, frame: DatasetFrame, search: str | None,
                   include_excluded: bool, issues_only: bool = False) -> Select:
    stmt = stmt.where(FactRecord.dataset_id == dataset_id)
    if not include_excluded:
        stmt = stmt.where(FactRecord.is_valid.is_(True))
    if issues_only:
        stmt = stmt.where(FactRecord.issues.is_not(None))
    if filters.start_date:
        stmt = stmt.where(FactRecord.txn_date >= filters.start_date)
    if filters.end_date:
        stmt = stmt.where(FactRecord.txn_date <= filters.end_date)
    for dim, values in filters.active_dimensions().items():
        col = frame.dim_col(dim)
        if col is None:
            continue
        if dim == "customer" and frame.has("customer_id") and frame.has("customer_name"):
            stmt = stmt.where(or_(FactRecord.customer_id.in_(values), FactRecord.customer_name.in_(values)))
        else:
            stmt = stmt.where(getattr(FactRecord, col).in_(values))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        text_cols = [getattr(FactRecord, c) for c in TEXT_FIELDS if c in frame.available]
        conds = [func.lower(c).like(term) for c in text_cols]
        conds.append(cast(FactRecord.row_number, String).like(term))
        stmt = stmt.where(or_(*conds))
    return stmt


def _serialize(rec: FactRecord, keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": rec.id}
    for k in keys:
        v = getattr(rec, k)
        out[k] = v.isoformat() if isinstance(v, (date, datetime)) else v
    out["is_valid"] = rec.is_valid
    return out


def query_records(db: Session, dataset: Dataset, frame: DatasetFrame, q) -> dict[str, Any]:
    cols = explorer_columns(frame)
    allowed = {c["key"] for c in cols}
    keys = [c for c in (q.columns or [c["key"] for c in cols]) if c in allowed]
    base = _apply_filters(select(FactRecord), dataset.id, q.filters, frame, q.search, q.include_excluded, q.issues_only)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    sort_key = q.sort_by if q.sort_by in allowed else "row_number"
    col = getattr(FactRecord, sort_key)
    order = (desc(col).nulls_last() if q.sort_dir == "desc" else asc(col).nulls_last())
    rows = db.scalars(base.order_by(order, FactRecord.id).offset((q.page - 1) * q.page_size).limit(q.page_size)).all()
    return {"total": int(total or 0), "page": q.page, "page_size": q.page_size, "columns": cols, "visible": keys,
            "rows": [_serialize(r, keys) for r in rows]}


def get_record(db: Session, dataset: Dataset, frame: DatasetFrame, record_id: int) -> dict[str, Any] | None:
    rec = db.get(FactRecord, record_id)
    if rec is None or rec.dataset_id != dataset.id:
        return None
    fields = []
    for c in explorer_columns(frame):
        if c["key"] in SYSTEM_COLUMNS:
            continue
        v = getattr(rec, c["key"])
        fields.append({**c, "value": v.isoformat() if isinstance(v, (date, datetime)) else v})
    return {"id": rec.id, "row_number": rec.row_number, "is_valid": rec.is_valid,
            "issues": rec.issues.split(",") if rec.issues else [], "fields": fields, "raw": rec.raw}


def iter_export_rows(db: Session, dataset: Dataset, frame: DatasetFrame, req) -> tuple[list[dict[str, Any]], Iterator[list[Any]]]:
    cols = [c for c in explorer_columns(frame) if not req.columns or c["key"] in req.columns]
    stmt = _apply_filters(select(*[getattr(FactRecord, c["key"]) for c in cols]), dataset.id, req.filters, frame,
                          req.search, req.include_excluded)
    sort_key = req.sort_by if req.sort_by in {c["key"] for c in cols} else "row_number"
    col = getattr(FactRecord, sort_key)
    stmt = stmt.order_by(desc(col) if req.sort_dir == "desc" else asc(col))

    def gen():
        for row in db.execute(stmt.execution_options(yield_per=5000)):
            yield [v.isoformat() if isinstance(v, (date, datetime)) else v for v in row]
    return cols, gen()


def export_csv(cols: list[dict[str, Any]], rows: Iterator[list[Any]]) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c["label"] for c in cols])
    yield "﻿" + buf.getvalue()
    buf.seek(0)
    buf.truncate(0)
    for i, row in enumerate(rows):
        writer.writerow(row)
        if i % 1000 == 999:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
    yield buf.getvalue()


def export_xlsx(cols: list[dict[str, Any]], rows: Iterator[list[Any]], sheet_name: str = "Data") -> bytes:
    import xlsxwriter

    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True, "strings_to_numbers": False})
    ws = wb.add_worksheet(sheet_name[:31])
    head = wb.add_format({"bold": True, "bg_color": "#0B1F3A", "font_color": "#FFFFFF", "border": 0})
    money = wb.add_format({"num_format": "$#,##0.00"})
    pct = wb.add_format({"num_format": "0.0%"})
    datef = wb.add_format({"num_format": "yyyy-mm-dd"})
    for j, c in enumerate(cols):
        ws.write(0, j, c["label"], head)
        ws.set_column(j, j, max(12, min(len(c["label"]) + 4, 32)),
                      money if c.get("format") == "currency" else pct if c.get("format") == "percent" else None)
    last = 0
    for i, row in enumerate(rows, start=1):
        last = i
        for j, v in enumerate(row):
            if cols[j]["type"] == "date" and v:
                ws.write_datetime(i, j, datetime.fromisoformat(v), datef)
            elif v is not None:
                ws.write(i, j, v)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(last, 1), len(cols) - 1)
    wb.close()
    return out.getvalue()


# --------------------------------------------------------------------------- reports
def _fmt(v: Any, fmt: str | None) -> str:
    if fmt == "currency":
        return format_currency(v)
    if fmt == "percent":
        return format_percent(v)
    if isinstance(v, (int, float)):
        return format_number(v)
    return "—" if v is None else str(v)


def build_report_xlsx(dataset: Dataset, scope: Scope, kpis: dict, perf: dict, prods: dict, regs: dict,
                      insights: list[dict], quality: dict) -> bytes:
    import xlsxwriter

    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})
    title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#0B1F3A"})
    sub = wb.add_format({"italic": True, "font_color": "#5B6B82"})
    head = wb.add_format({"bold": True, "bg_color": "#0B1F3A", "font_color": "#FFFFFF"})
    money = wb.add_format({"num_format": "$#,##0"})
    pct = wb.add_format({"num_format": "0.0%"})
    num = wb.add_format({"num_format": "#,##0"})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})

    ws = wb.add_worksheet("Executive summary")
    ws.write(0, 0, f"{dataset.name}: executive summary", title)
    ws.write(1, 0, f"Period: {scope.label}" + (f"  ·  Compared with: {scope.prev_label}" if scope.prev_label else "")
             + f"  ·  Generated {datetime.now():%d %b %Y %H:%M}", sub)
    active = {k: v for k, v in scope.filters.active_dimensions().items()}
    ws.write(2, 0, "Filters: " + ("; ".join(f"{k}: {', '.join(v)}" for k, v in active.items()) if active else "none"), sub)
    for j, h in enumerate(["KPI", "Current", "Previous", "Change", "Note"]):
        ws.write(4, j, h, head)
    r = 5
    for c in kpis["cards"]:
        ws.write(r, 0, c["label"])
        if c.get("available"):
            f = money if c["format"] == "currency" else pct if c["format"] == "percent" else num
            ws.write_number(r, 1, c["value"], f)
            if c.get("previous") is not None:
                ws.write_number(r, 2, c["previous"], f)
            if c.get("change") is not None:
                ws.write_number(r, 3, c["change"], pct)
            ws.write(r, 4, c.get("note") or "")
        else:
            ws.write(r, 1, "Not available")
            ws.write(r, 4, c.get("reason") or "")
        r += 1
    ws.set_column(0, 0, 28)
    ws.set_column(1, 3, 16)
    ws.set_column(4, 4, 50)

    ws2 = wb.add_worksheet("Insights")
    for j, h in enumerate(["Severity", "Insight", "Observation (statistical)", "Business implication", "Recommended action", "Interpretation source"]):
        ws2.write(0, j, h, head)
    for i, ins in enumerate(insights, start=1):
        for j, v in enumerate([ins["severity"], ins["title"], ins["observation"], ins["implication"], ins["recommendation"],
                               "AI-generated" if ins["interpretation_source"] == "ai" else "Rule-based"]):
            ws2.write(i, j, v, wrap)
    ws2.set_column(0, 0, 10)
    ws2.set_column(1, 1, 34)
    ws2.set_column(2, 4, 60)
    ws2.set_column(5, 5, 18)

    def table(name: str, rows: list[dict], columns: list[tuple[str, str, Any]]):
        sh = wb.add_worksheet(name[:31])
        for j, (_, label, _) in enumerate(columns):
            sh.write(0, j, label, head)
            sh.set_column(j, j, 18 if j else 28)
        for i, row in enumerate(rows, start=1):
            for j, (key, _, f) in enumerate(columns):
                v = row.get(key)
                if isinstance(v, (int, float)) and v is not None:
                    sh.write_number(i, j, v, f)
                elif v is not None:
                    sh.write(i, j, str(v))

    table("Monthly trend", perf["trend"]["series"], [("label", "Period", None), ("revenue", "Revenue", money),
          ("profit", "Profit", money), ("margin", "Margin", pct), ("units", "Units", num), ("transactions", "Transactions", num)])
    for key, label in (("annual", "Annual"), ("quarterly", "Quarterly")):
        table(f"{label} summary", perf[key], [("label", "Period", None), ("revenue", "Revenue", money), ("profit", "Profit", money),
              ("margin", "Margin", pct), ("pop_growth", "Growth vs prior", pct), ("yoy_growth", "YoY growth", pct)])
    cols = [("key", "Name", None), ("revenue", "Revenue", money), ("share", "Share", pct), ("profit", "Profit", money),
            ("margin", "Margin", pct), ("units", "Units", num), ("growth", "Growth", pct)]
    if prods.get("available"):
        table("Products", prods["products"], cols)
        if prods.get("categories"):
            table("Categories", prods["categories"], cols)
    if regs.get("available"):
        for lvl in regs["levels"]:
            table(lvl.title(), regs[lvl], cols)

    ws3 = wb.add_worksheet("Data quality")
    ws3.write(0, 0, f"Quality score: {quality.get('score')} ({quality.get('grade')})", title)
    for j, h in enumerate(["Severity", "Category", "Column", "Rows", "Message"]):
        ws3.write(2, j, h, head)
    for i, iss in enumerate(quality.get("issues", []), start=3):
        for j, v in enumerate([iss["severity"], iss["category"], iss.get("column") or "", iss["count"], iss["message"]]):
            ws3.write(i, j, v, wrap)
    ws3.set_column(0, 3, 14)
    ws3.set_column(4, 4, 100)
    wb.close()
    return out.getvalue()


def build_report_html(dataset: Dataset, scope: Scope, kpis: dict, perf: dict, prods: dict, regs: dict,
                      insights: list[dict], quality: dict) -> str:
    e = html.escape
    def change(c: dict) -> str:
        if c.get("change") is None:
            return ""
        val = f"{c['change'] * 100:+.1f} pp" if c["change_type"] == "absolute" else f"{c['change'] * 100:+.1f}%"
        return f"{val} vs {e(scope.prev_label)}"

    cards = "".join(
        f"<div class='kpi'><div class='l'>{e(c['label'])}</div>"
        f"<div class='v'>{e(_fmt(c.get('value'), c['format'])) if c.get('available') else 'n/a'}</div>"
        f"<div class='c {c.get('sentiment', '')}'>{change(c)}</div></div>"
        for c in kpis["cards"])
    ins = "".join(
        f"<div class='ins {i['severity']}'><h4>{e(i['title'])}</h4><p><b>Observation (statistical):</b> {e(i['observation'])}</p>"
        f"<p><b>Implication ({'AI-generated' if i['interpretation_source'] == 'ai' else 'rule-based'}):</b> {e(i['implication'])}</p>"
        f"<p><b>Recommended action:</b> {e(i['recommendation'])}</p></div>" for i in insights)

    def tbl(rows: list[dict], cols: list[tuple[str, str, str | None]]) -> str:
        head = "".join(f"<th>{e(lbl)}</th>" for _, lbl, _ in cols)
        body = "".join("<tr>" + "".join(f"<td>{e(_fmt(r.get(k), f) if f else str(r.get(k, '')))}</td>" for k, _, f in cols) + "</tr>"
                       for r in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    std = [("key", "Name", None), ("revenue", "Revenue", "currency"), ("share", "Share", "percent"),
           ("margin", "Margin", "percent"), ("growth", "Growth", "percent")]
    sections = [f"<h3>Annual summary</h3>{tbl(perf['annual'], [('label', 'Year', None), ('revenue', 'Revenue', 'currency'), ('profit', 'Profit', 'currency'), ('margin', 'Margin', 'percent'), ('pop_growth', 'Growth', 'percent')])}"]
    if prods.get("available"):
        sections.append(f"<h3>Products</h3>{tbl(prods['products'], std)}")
    if regs.get("available") and "region" in regs:
        sections.append(f"<h3>Regions</h3>{tbl(regs['region'], std)}")
    issues = "".join(f"<li><b>{e(i['severity'])}</b>: {e(i['message'])}</li>" for i in quality.get("issues", [])[:10])
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{e(dataset.name)} — BI report</title>
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;color:#1d2433;margin:32px;max-width:1100px}}h1{{color:#0b1f3a;margin:0}}
.meta{{color:#5b6b82;margin:4px 0 24px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.kpi{{border:1px solid #dde3ec;border-radius:10px;padding:12px}}.l{{font-size:12px;color:#5b6b82}}.v{{font-size:22px;font-weight:600;margin:4px 0}}
.c{{font-size:12px;color:#5b6b82}}.positive{{color:#0f7b5f}}.negative{{color:#b42318}}
.ins{{border-left:4px solid #8a9bb4;padding:4px 14px;margin:12px 0;break-inside:avoid}}.ins.critical{{border-color:#b42318}}.ins.warning{{border-color:#c47f00}}.ins.positive{{border-color:#0f7b5f}}
.ins h4{{margin:6px 0}}.ins p{{margin:4px 0;font-size:13px}}table{{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:16px}}
th{{background:#0b1f3a;color:#fff;text-align:left;padding:6px 8px}}td{{border-bottom:1px solid #e6eaf0;padding:5px 8px}}
@media print{{body{{margin:12mm}}}}</style></head><body>
<h1>{e(dataset.name)}</h1><div class='meta'>Period: {e(scope.label)}{(' · compared with ' + e(scope.prev_label)) if scope.prev_label else ''} · generated {datetime.now():%d %b %Y %H:%M}</div>
<div class='grid'>{cards}</div><h2>Insights</h2>{ins}<h2>Detail</h2>{''.join(sections)}
<h2>Data quality — score {quality.get('score')} ({e(str(quality.get('grade')))})</h2><ul>{issues}</ul></body></html>"""
