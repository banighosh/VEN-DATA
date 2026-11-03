"""Pipeline orchestration: upload → validate → read → profile → map → clean →
validate → store → reconcile. Each step is a call into its own module so layers
can be maintained or replaced independently."""
from __future__ import annotations

import json
import logging
import math
import pickle
import shutil
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from ..analytics.common import invalidate_frame
from ..config import get_settings
from ..ingestion.file_validation import validate_upload
from ..ingestion.mapping import FIELDS, suggest_mapping, validate_mapping
from ..ingestion.profiler import preview_rows, profile_frame
from ..ingestion.quality import build_quality_report
from ..ingestion.reader import ReadResult, cache_key, list_sheets, read_table
from ..models import DATE_FIELDS, NUMBER_FIELDS, TEXT_FIELDS, Dataset, FactRecord, Upload
from ..processing.transform import TransformOptions, build_canonical
from ..processing.validation import consistency_checks, detect_key_conflicts, reconcile_totals

log = logging.getLogger(__name__)
FACT_COLUMNS = ("dataset_id", "row_number", "is_valid", "issues", *DATE_FIELDS, *TEXT_FIELDS, *NUMBER_FIELDS, "raw")


class PipelineError(ValueError):
    """User-facing processing error (maps to HTTP 422)."""


# --------------------------------------------------------------------------- uploads
def save_upload(db: Session, filename: str, stream: BinaryIO) -> Upload:
    settings = get_settings()
    upload_id = uuid.uuid4().hex
    folder = settings.upload_dir / upload_id
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename or "upload").name.replace("/", "_")
    dest = folder / safe_name
    with open(dest, "wb") as out:
        shutil.copyfileobj(stream, out, length=1024 * 1024)
    size = dest.stat().st_size
    with open(dest, "rb") as fh:
        head = fh.read(8192)
    try:
        checked = validate_upload(safe_name, head, size, settings.max_upload_mb)
        sheets = list_sheets(dest, checked.file_type)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    upload = Upload(id=upload_id, filename=checked.filename, stored_path=str(dest), file_type=checked.file_type,
                    size_bytes=size, sheets=[s.__dict__ for s in sheets])
    db.add(upload)
    db.commit()
    return upload


def recommend_sheet(sheets: list[dict[str, Any]]) -> str | None:
    """Prefer the widest substantial sheet (fact-like), not tiny lookup tables."""
    candidates = [s for s in sheets if not s.get("empty") and (s.get("rows") or 0) > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda s: ((s.get("columns") or 0) >= 6, (s.get("columns") or 0) * min(s.get("rows") or 0, 50_000)))["name"]


def get_upload(db: Session, upload_id: str) -> Upload:
    up = db.get(Upload, upload_id)
    if up is None:
        raise PipelineError("Upload not found or expired. Please upload the file again.")
    return up


def load_sheet(upload: Upload, sheet: str | None, header_row: int | None, row_limit: int | None = None) -> ReadResult:
    """Read (and cache) a sheet as a DataFrame."""
    sheet_name = sheet if upload.file_type == "xlsx" else None
    if upload.file_type == "xlsx" and sheet_name not in {s["name"] for s in upload.sheets}:
        raise PipelineError(f"Sheet '{sheet}' was not found in {upload.filename}.")
    folder = Path(upload.stored_path).parent
    tag = cache_key(sheet_name, header_row) + (f"_{row_limit}" if row_limit else "")
    cache = folder / f"parsed_{tag}.pkl"
    if cache.exists():
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    result = read_table(Path(upload.stored_path), upload.file_type, sheet_name, header_row, nrows=row_limit)
    if result.frame.empty:
        raise PipelineError("The selected sheet has no data rows below the header.")
    with open(cache, "wb") as fh:
        pickle.dump(result, fh)
    return result


def analyze_sheet(upload: Upload, sheet: str | None, header_row: int | None) -> dict[str, Any]:
    t0 = time.perf_counter()
    settings = get_settings()
    result = load_sheet(upload, sheet, header_row, row_limit=settings.profile_row_limit)
    df = result.frame
    profiles = profile_frame(df)
    conflicts = detect_key_conflicts(df)
    suggestion = suggest_mapping(profiles, conflicts)
    mapping = suggestion["mapping"]
    checks: list[dict[str, Any]] = []
    if "txn_date" in mapping and ("revenue" in mapping or {"unit_price", "quantity"} <= mapping.keys()):
        canonical, _ = build_canonical(df, mapping, TransformOptions())
        checks = consistency_checks(canonical, mapping)
    key_cols = {mapping[k] for k in ("txn_date", "revenue") if k in mapping}
    quality = build_quality_report(df, profiles, checks, conflicts, key_cols, sampled=result.sampled)
    return {
        "upload_id": upload.id, "filename": upload.filename, "sheet": sheet, "header_row": result.header_row,
        "rows": int(len(df)), "total_rows": result.total_rows, "columns": list(map(str, df.columns)),
        "sampled": result.sampled, "notes": result.notes, "profiles": profiles, "preview": preview_rows(df, 100),
        "quality": quality, "suggestion": suggestion, "fields": [f.to_dict() for f in FIELDS],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000),
    }


# --------------------------------------------------------------------------- datasets
def _py(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.date()
    if v is pd.NaT:
        return None
    return v


def _records(dataset_id: int, canonical: pd.DataFrame):
    cols = {c: canonical[c].tolist() for c in FACT_COLUMNS if c in canonical}
    for f in DATE_FIELDS:
        cols[f] = [None if pd.isna(v) else v.date() for v in canonical[f]]
    n = len(canonical)
    for i in range(n):
        yield {c: (dataset_id if c == "dataset_id" else _py(cols[c][i])) for c in FACT_COLUMNS}


def store_records(db: Session, dataset_id: int, canonical: pd.DataFrame) -> None:
    conn = db.connection()
    if conn.dialect.name == "postgresql":
        raw = conn.connection.driver_connection
        with raw.cursor() as cur:
            with cur.copy(f"COPY fact_records ({', '.join(FACT_COLUMNS)}) FROM STDIN") as copy:
                for rec in _records(dataset_id, canonical):
                    rec["raw"] = json.dumps(rec["raw"], default=str)
                    copy.write_row([rec[c] for c in FACT_COLUMNS])
    else:
        batch: list[dict[str, Any]] = []
        for rec in _records(dataset_id, canonical):
            batch.append(rec)
            if len(batch) >= 5000:
                db.execute(insert(FactRecord), batch)
                batch = []
        if batch:
            db.execute(insert(FactRecord), batch)


def create_dataset(db: Session, upload: Upload, sheet: str | None, header_row: int | None, mapping: dict[str, str],
                   options: dict[str, Any], name: str | None, set_default: bool = True) -> Dataset:
    timings: dict[str, int] = {}
    t = time.perf_counter()

    def lap(step: str) -> None:
        nonlocal t
        now = time.perf_counter()
        timings[step] = round((now - t) * 1000)
        t = now

    result = load_sheet(upload, sheet, header_row)
    df = result.frame
    lap("read")
    opts = TransformOptions.from_dict(options)
    errors, warnings = validate_mapping(mapping, list(map(str, df.columns)), opts.revenue_source)
    if errors:
        raise PipelineError(" ".join(errors))

    canonical, report = build_canonical(df, mapping, opts)
    lap("transform")
    checks = consistency_checks(canonical, mapping, opts.revenue_source)
    profiles = profile_frame(df)
    conflicts = detect_key_conflicts(df)
    key_cols = {mapping[k] for k in ("txn_date", "revenue") if k in mapping}
    quality = build_quality_report(df, profiles, checks, conflicts, key_cols)
    lap("validate")

    valid = canonical[canonical["is_valid"]]
    dataset = Dataset(
        name=(name or (f"{Path(upload.filename).stem}: {sheet}" if sheet else Path(upload.filename).stem))[:200],
        upload_id=upload.id, source_filename=upload.filename, sheet_name=sheet, header_row=result.header_row,
        mapping=mapping, options=opts.__dict__, status="processing", row_count=int(len(canonical)),
        valid_row_count=int(len(valid)), columns=profiles, quality=quality,
        date_min=valid["txn_date"].min().date() if not valid.empty else None,
        date_max=valid["txn_date"].max().date() if not valid.empty else None,
    )
    db.add(dataset)
    db.flush()
    store_records(db, dataset.id, canonical)
    lap("store")

    stored = db.execute(
        select(func.count(FactRecord.id), func.coalesce(func.sum(FactRecord.revenue), 0.0),
               func.coalesce(func.sum(FactRecord.profit), 0.0))
        .where(FactRecord.dataset_id == dataset.id, FactRecord.is_valid.is_(True))
    ).one()
    recon = reconcile_totals(
        {"valid_rows": float(len(valid)), "revenue": float(valid["revenue"].sum()),
         "profit": float(valid["profit"].sum()) if valid["profit"].notna().any() else 0.0},
        {"valid_rows": float(stored[0]), "revenue": float(stored[1]), "profit": float(stored[2])},
    )
    if any(r["status"] == "fail" for r in recon):
        db.rollback()
        raise PipelineError("Post-load reconciliation failed: stored totals do not match the processed file.")
    lap("reconcile")

    report.update({"timings_ms": timings, "reconciliation": recon, "mapping_warnings": warnings,
                   "source_notes": result.notes, "header_row": result.header_row})
    dataset.processing = report
    dataset.status = "ready"
    if set_default:
        db.execute(update(Dataset).where(Dataset.id != dataset.id).values(is_default=False))
        dataset.is_default = True
    db.commit()
    db.refresh(dataset)
    return dataset


def delete_dataset(db: Session, dataset: Dataset) -> None:
    was_default = dataset.is_default
    db.delete(dataset)
    db.commit()
    invalidate_frame(dataset.id)
    if was_default:
        nxt = db.scalars(select(Dataset).where(Dataset.status == "ready").order_by(Dataset.created_at.desc())).first()
        if nxt:
            nxt.is_default = True
            db.commit()


def dataset_summary(ds: Dataset) -> dict[str, Any]:
    q = ds.quality or {}
    return {
        "id": ds.id, "name": ds.name, "source_filename": ds.source_filename, "sheet_name": ds.sheet_name,
        "header_row": ds.header_row, "status": ds.status, "error": ds.error, "row_count": ds.row_count,
        "valid_row_count": ds.valid_row_count, "date_min": ds.date_min, "date_max": ds.date_max,
        "is_default": ds.is_default, "mapping": ds.mapping, "options": ds.options, "created_at": ds.created_at,
        "updated_at": ds.updated_at, "quality_score": q.get("score"), "quality_grade": q.get("grade"),
    }


def json_default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)
