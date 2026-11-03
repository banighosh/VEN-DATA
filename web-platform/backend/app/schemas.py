"""Pydantic request/response models for the REST API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .analytics.common import FilterSpec


class ProcessingOptions(BaseModel):
    revenue_source: Literal["column", "derived"] = "column"
    drop_duplicates: bool = True
    harmonize_categories: bool = True
    trim_whitespace: bool = True


class SheetSummary(BaseModel):
    name: str
    rows: int | None
    columns: int | None
    header_row: int
    empty: bool = False


class UploadOut(BaseModel):
    upload_id: str
    filename: str
    file_type: str
    size_bytes: int
    sheets: list[SheetSummary]
    recommended_sheet: str | None = None


class CreateDatasetRequest(BaseModel):
    upload_id: str
    sheet: str | None = None
    header_row: int | None = None
    name: str | None = None
    mapping: dict[str, str]
    options: ProcessingOptions = Field(default_factory=ProcessingOptions)
    set_default: bool = True


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_filename: str
    sheet_name: str | None
    header_row: int
    status: str
    error: str | None = None
    row_count: int
    valid_row_count: int
    date_min: date | None
    date_max: date | None
    is_default: bool
    mapping: dict[str, str]
    options: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    quality_score: float | None = None
    quality_grade: str | None = None


class DatasetDetail(DatasetOut):
    quality: dict[str, Any]
    processing: dict[str, Any]
    columns: list[dict[str, Any]]


class DatasetPatch(BaseModel):
    name: str | None = None
    is_default: bool | None = None


class AnalyticsRequest(BaseModel):
    filters: FilterSpec = Field(default_factory=FilterSpec)
    granularity: Literal["day", "week", "month", "quarter", "year"] | None = None
    dimension: str | None = None
    split_by: str | None = None
    sort_by: str = "revenue"
    limit: int | None = None
    ascending: bool = False
    horizon: int = 6
    use_ai: bool = True


class RecordsQuery(BaseModel):
    filters: FilterSpec = Field(default_factory=FilterSpec)
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "asc"
    search: str | None = None
    columns: list[str] | None = None
    include_excluded: bool = False
    issues_only: bool = False


class ExportRequest(BaseModel):
    filters: FilterSpec = Field(default_factory=FilterSpec)
    format: Literal["csv", "xlsx"] = "csv"
    columns: list[str] | None = None
    search: str | None = None
    include_excluded: bool = False
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "asc"


class ReportRequest(BaseModel):
    filters: FilterSpec = Field(default_factory=FilterSpec)
    format: Literal["xlsx", "html"] = "xlsx"


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: int | None = None
    filters: dict[str, Any]
    is_default: bool = False


class PresetOut(PresetIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
