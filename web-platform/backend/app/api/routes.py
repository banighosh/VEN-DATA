"""REST API.

Endpoint groups
  /api/health, /api/system/info                 platform status
  /api/uploads                                   file upload, sheet analysis (preview, profile, quality, mapping suggestion)
  /api/datasets                                  process / list / inspect / delete datasets, capabilities, filter options, search
  /api/datasets/{id}/analytics/<module>          KPI + analytics modules (POST body = global filters)
  /api/datasets/{id}/records                     Data Explorer (paging, search, sort, columns), record detail
  /api/datasets/{id}/export | /report            filtered data export (CSV/XLSX) and dashboard report (XLSX/HTML)
  /api/presets                                   saved filter preferences
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ..analytics import breakdowns, capabilities as caps
from ..analytics.common import (
    DatasetFrame,
    FilterSpec,
    auto_granularity,
    breakdown,
    build_scope,
    invalidate_frame,
    pivot_series,
    scope_meta,
    timeseries,
    to_jsonable,
)
from ..analytics.forecast import forecast
from ..analytics.kpis import compute_kpis, kpi_attention
from ..analytics.performance import performance, trend
from ..config import get_settings
from ..db import get_db
from ..ingestion.file_validation import FileValidationError
from ..ingestion.mapping import FIELDS
from ..insights.engine import generate_insights
from ..insights.narrator import enrich, llm_status
from ..models import Dataset, FilterPreset
from ..schemas import (
    AnalyticsRequest,
    CreateDatasetRequest,
    DatasetPatch,
    ExportRequest,
    PresetIn,
    PresetOut,
    RecordsQuery,
    ReportRequest,
    UploadOut,
)
from ..services import datasets as svc
from ..services import records as rec_svc
from .deps import dataset_frame, get_dataset, get_ready_dataset

router = APIRouter(prefix="/api")


def _pipeline_errors(fn):
    try:
        return fn()
    except FileValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except svc.PipelineError as exc:
        raise HTTPException(422, str(exc)) from exc


# --------------------------------------------------------------------------- system
@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": db.get_bind().dialect.name, "time": datetime.now(timezone.utc).isoformat()}


@router.get("/system/info", tags=["system"])
def system_info() -> dict[str, Any]:
    s = get_settings()
    return {"name": s.app_name, "version": s.version, "environment": s.environment, "max_upload_mb": s.max_upload_mb,
            "ai_insights": llm_status(), "fields": [f.to_dict() for f in FIELDS]}


# --------------------------------------------------------------------------- uploads
@router.post("/uploads", response_model=UploadOut, tags=["ingestion"])
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadOut:
    up = _pipeline_errors(lambda: svc.save_upload(db, file.filename or "upload", file.file))
    return UploadOut(upload_id=up.id, filename=up.filename, file_type=up.file_type, size_bytes=up.size_bytes,
                     sheets=up.sheets, recommended_sheet=svc.recommend_sheet(up.sheets))


@router.get("/uploads/{upload_id}/analysis", tags=["ingestion"])
def analyze(upload_id: str, sheet: str | None = None, header_row: int | None = Query(None, ge=0, le=200),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    up = _pipeline_errors(lambda: svc.get_upload(db, upload_id))
    return to_jsonable(_pipeline_errors(lambda: svc.analyze_sheet(up, sheet, header_row)))


# --------------------------------------------------------------------------- datasets
@router.post("/datasets", tags=["datasets"])
def create_dataset(req: CreateDatasetRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    up = _pipeline_errors(lambda: svc.get_upload(db, req.upload_id))
    ds = _pipeline_errors(lambda: svc.create_dataset(db, up, req.sheet, req.header_row, req.mapping,
                                                     req.options.model_dump(), req.name, req.set_default))
    return to_jsonable({**svc.dataset_summary(ds), "processing": ds.processing, "quality": ds.quality})


@router.get("/datasets", tags=["datasets"])
def list_datasets(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()
    return to_jsonable([svc.dataset_summary(d) for d in rows])


@router.get("/datasets/{dataset_id}", tags=["datasets"])
def get_dataset_detail(ds: Dataset = Depends(get_dataset)) -> dict[str, Any]:
    return to_jsonable({**svc.dataset_summary(ds), "quality": ds.quality, "processing": ds.processing, "columns": ds.columns})


@router.patch("/datasets/{dataset_id}", tags=["datasets"])
def patch_dataset(patch: DatasetPatch, ds: Dataset = Depends(get_dataset), db: Session = Depends(get_db)) -> dict[str, Any]:
    if patch.name is not None:
        ds.name = patch.name.strip()[:200] or ds.name
    if patch.is_default:
        db.execute(update(Dataset).where(Dataset.id != ds.id).values(is_default=False))
        ds.is_default = True
    db.commit()
    return to_jsonable(svc.dataset_summary(ds))


@router.delete("/datasets/{dataset_id}", status_code=204, tags=["datasets"])
def remove_dataset(ds: Dataset = Depends(get_dataset), db: Session = Depends(get_db)) -> Response:
    svc.delete_dataset(db, ds)
    return Response(status_code=204)


@router.get("/datasets/{dataset_id}/quality", tags=["datasets"])
def dataset_quality(ds: Dataset = Depends(get_dataset)) -> dict[str, Any]:
    return to_jsonable({"quality": ds.quality, "processing": ds.processing, "columns": ds.columns})


@router.get("/datasets/{dataset_id}/capabilities", tags=["datasets"])
def dataset_capabilities(frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    return to_jsonable(caps.capabilities(frame))


@router.get("/datasets/{dataset_id}/filter-options", tags=["datasets"])
def dataset_filter_options(frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    return to_jsonable(caps.filter_options(frame))


@router.get("/datasets/{dataset_id}/search", tags=["datasets"])
def search_values(q: str = Query(..., min_length=1, max_length=80), frame: DatasetFrame = Depends(dataset_frame)) -> list[dict[str, Any]]:
    term = q.strip().lower()
    hits: list[dict[str, Any]] = []
    for dim in caps.FILTER_FIELDS:
        col = frame.dim_col(dim)
        if col is None:
            continue
        rev = frame.df.groupby(col)["revenue"].sum()
        for value, revenue in rev.items():
            sv = str(value)
            if term in sv.lower():
                hits.append({"dimension": dim, "label": frame.label(col), "value": sv, "revenue": float(revenue),
                             "exact": sv.lower() == term, "prefix": sv.lower().startswith(term)})
    hits.sort(key=lambda h: (not h["exact"], not h["prefix"], -h["revenue"]))
    return hits[:20]


# --------------------------------------------------------------------------- analytics
def _scope(frame: DatasetFrame, req: AnalyticsRequest):
    return build_scope(frame, req.filters)


@router.post("/datasets/{dataset_id}/analytics/overview", tags=["analytics"])
def analytics_overview(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame),
                       ds: Dataset = Depends(get_ready_dataset)) -> dict[str, Any]:
    scope = _scope(frame, req)
    k = compute_kpis(scope)
    gran = req.granularity or auto_granularity(scope.start, scope.end)
    payload = {
        "meta": scope_meta(scope), "kpis": k["cards"], "attention": [c["key"] for c in kpi_attention(k["cards"])],
        "trend": trend(scope, gran), "granularity": gran,
        "categories": breakdown(scope, "category") if frame.dim_col("category") else [],
        "regions": breakdown(scope, "region") if frame.dim_col("region") else [],
        "states": breakdown(scope, "state") if frame.dim_col("state") else [],
        "channels": breakdown(scope, "channel") if frame.dim_col("channel") else [],
        "products": breakdown(scope, "product", limit=10) if frame.dim_col("product") else [],
        "segments": breakdown(scope, "customer_segment") if frame.dim_col("customer_segment") else [],
        "insights": generate_insights(scope, ds.quality, limit=6),
        "quality": {"score": (ds.quality or {}).get("score"), "grade": (ds.quality or {}).get("grade"),
                    "critical": (ds.quality or {}).get("summary", {}).get("critical", 0),
                    "warnings": (ds.quality or {}).get("summary", {}).get("warnings", 0)},
    }
    return to_jsonable(payload)


@router.post("/datasets/{dataset_id}/analytics/kpis", tags=["analytics"])
def analytics_kpis(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    k = compute_kpis(scope)
    return to_jsonable({"meta": scope_meta(scope), "kpis": k["cards"], "attention": [c["key"] for c in kpi_attention(k["cards"])]})


@router.post("/datasets/{dataset_id}/analytics/performance", tags=["analytics"])
def analytics_performance(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    gran = req.granularity or auto_granularity(scope.start, scope.end)
    return to_jsonable({"meta": scope_meta(scope), **performance(scope, gran, req.split_by)})


@router.post("/datasets/{dataset_id}/analytics/products", tags=["analytics"])
def analytics_products(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), **breakdowns.products(scope)})


@router.post("/datasets/{dataset_id}/analytics/regional", tags=["analytics"])
def analytics_regional(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), **breakdowns.regional(scope)})


@router.post("/datasets/{dataset_id}/analytics/customers", tags=["analytics"])
def analytics_customers(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), **breakdowns.customers(scope)})


@router.post("/datasets/{dataset_id}/analytics/financial", tags=["analytics"])
def analytics_financial(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), **breakdowns.financial(scope, req.dimension)})


@router.post("/datasets/{dataset_id}/analytics/operations", tags=["analytics"])
def analytics_operations(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), **breakdowns.operations(scope)})


@router.post("/datasets/{dataset_id}/analytics/forecast", tags=["analytics"])
def analytics_forecast(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), **forecast(scope, max(1, min(req.horizon, 24)))})


@router.post("/datasets/{dataset_id}/analytics/insights", tags=["analytics"])
def analytics_insights(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame),
                       ds: Dataset = Depends(get_ready_dataset)) -> dict[str, Any]:
    scope = _scope(frame, req)
    items = generate_insights(scope, ds.quality, limit=req.limit or 12)
    ai = llm_status()
    if req.use_ai:
        items, ai = enrich(items)
    return to_jsonable({"meta": scope_meta(scope), "insights": items, "ai": ai})


@router.post("/datasets/{dataset_id}/analytics/breakdown", tags=["analytics"])
def analytics_breakdown(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    if not req.dimension or not frame.dim_col(req.dimension):
        raise HTTPException(422, f"Dimension '{req.dimension}' is not available in this dataset.")
    scope = _scope(frame, req)
    return to_jsonable({"meta": scope_meta(scope), "dimension": req.dimension, "label": frame.label(frame.dim_col(req.dimension)),
                        "rows": breakdown(scope, req.dimension, req.sort_by, req.limit, req.ascending)})


@router.post("/datasets/{dataset_id}/analytics/timeseries", tags=["analytics"])
def analytics_timeseries(req: AnalyticsRequest, frame: DatasetFrame = Depends(dataset_frame)) -> dict[str, Any]:
    scope = _scope(frame, req)
    gran = req.granularity or auto_granularity(scope.start, scope.end)
    out: dict[str, Any] = {"meta": scope_meta(scope), "granularity": gran,
                           "series": timeseries(scope.current, frame, gran, scope.start, scope.end)}
    if req.split_by and frame.dim_col(req.split_by):
        out["split"] = pivot_series(scope.current, frame, req.split_by, gran, scope.start, scope.end)
    return to_jsonable(out)


# --------------------------------------------------------------------------- records / export / report
@router.post("/datasets/{dataset_id}/records/query", tags=["records"])
def records_query(q: RecordsQuery, ds: Dataset = Depends(get_ready_dataset), frame: DatasetFrame = Depends(dataset_frame),
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    return to_jsonable(rec_svc.query_records(db, ds, frame, q))


@router.get("/datasets/{dataset_id}/records/{record_id}", tags=["records"])
def record_detail(record_id: int, ds: Dataset = Depends(get_ready_dataset), frame: DatasetFrame = Depends(dataset_frame),
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    out = rec_svc.get_record(db, ds, frame, record_id)
    if out is None:
        raise HTTPException(404, "Record not found.")
    return to_jsonable(out)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:60] or "dataset"


@router.post("/datasets/{dataset_id}/export", tags=["records"])
def export_records(req: ExportRequest, ds: Dataset = Depends(get_ready_dataset), frame: DatasetFrame = Depends(dataset_frame),
                   db: Session = Depends(get_db)):
    cols, rows = rec_svc.iter_export_rows(db, ds, frame, req)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if req.format == "xlsx":
        data = rec_svc.export_xlsx(cols, rows)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{_slug(ds.name)}-{stamp}.xlsx"'})
    return StreamingResponse(rec_svc.export_csv(cols, rows), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{_slug(ds.name)}-{stamp}.csv"'})


@router.post("/datasets/{dataset_id}/report", tags=["records"])
def dashboard_report(req: ReportRequest, ds: Dataset = Depends(get_ready_dataset), frame: DatasetFrame = Depends(dataset_frame)):
    scope = build_scope(frame, req.filters)
    kp = compute_kpis(scope)
    perf = performance(scope, "month")
    prods = breakdowns.products(scope)
    regs = breakdowns.regional(scope)
    ins = generate_insights(scope, ds.quality)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if req.format == "html":
        return HTMLResponse(rec_svc.build_report_html(ds, scope, kp, perf, prods, regs, ins, ds.quality or {}))
    data = rec_svc.build_report_xlsx(ds, scope, kp, perf, prods, regs, ins, ds.quality or {})
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_slug(ds.name)}-report-{stamp}.xlsx"'})


# --------------------------------------------------------------------------- presets
@router.get("/presets", response_model=list[PresetOut], tags=["presets"])
def list_presets(dataset_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(FilterPreset).order_by(FilterPreset.created_at.desc())
    if dataset_id is not None:
        stmt = stmt.where((FilterPreset.dataset_id == dataset_id) | (FilterPreset.dataset_id.is_(None)))
    return db.scalars(stmt).all()


@router.post("/presets", response_model=PresetOut, status_code=201, tags=["presets"])
def create_preset(p: PresetIn, db: Session = Depends(get_db)):
    FilterSpec.model_validate({k: v for k, v in p.filters.items() if k in FilterSpec.model_fields})
    if p.is_default:
        db.execute(update(FilterPreset).where(FilterPreset.dataset_id == p.dataset_id).values(is_default=False))
    preset = FilterPreset(name=p.name.strip(), dataset_id=p.dataset_id, filters=p.filters, is_default=p.is_default)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return preset


@router.delete("/presets/{preset_id}", status_code=204, tags=["presets"])
def delete_preset(preset_id: int, db: Session = Depends(get_db)) -> Response:
    preset = db.get(FilterPreset, preset_id)
    if preset is None:
        raise HTTPException(404, "Preset not found.")
    db.delete(preset)
    db.commit()
    return Response(status_code=204)


__all__ = ["router", "invalidate_frame"]
