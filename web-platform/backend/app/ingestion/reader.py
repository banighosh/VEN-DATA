"""Read Excel workbooks (all sheets) and CSV files into pandas.

Handles the messy realities of business spreadsheets: title rows above the
header, blank leading columns, unnamed/duplicate headers, odd CSV encodings and
delimiters. Header detection is automatic but can be overridden by the user.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from ..processing.cleaning import clean_column_names

DETECT_ROWS = 30
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


@dataclass
class SheetInfo:
    name: str
    rows: int | None
    columns: int | None
    header_row: int
    empty: bool = False


@dataclass
class ReadResult:
    frame: pd.DataFrame
    header_row: int
    sampled: bool
    total_rows: int | None
    notes: list[str] = field(default_factory=list)


def list_sheets(path: Path, file_type: str) -> list[SheetInfo]:
    if file_type == "csv":
        raw = _read_csv_raw(path, nrows=DETECT_ROWS)
        total = _count_csv_rows(path)
        header = detect_header_row(raw)
        return [SheetInfo(name="CSV", rows=max(total - header - 1, 0), columns=raw.shape[1], header_row=header, empty=raw.empty)]
    wb = load_workbook(path, read_only=True, data_only=True)
    infos: list[SheetInfo] = []
    try:
        for ws in wb.worksheets:
            rows = ws.max_row
            cols = ws.max_column
            raw = pd.DataFrame(list(ws.iter_rows(min_row=1, max_row=DETECT_ROWS, values_only=True)))
            empty = raw.dropna(how="all").empty
            header = detect_header_row(raw) if not empty else 0
            data_rows = None if rows is None else max(rows - header - 1, 0)
            infos.append(SheetInfo(name=ws.title, rows=data_rows, columns=cols, header_row=header, empty=empty))
    finally:
        wb.close()
    return infos


def detect_header_row(raw: pd.DataFrame) -> int:
    """Pick the first row that looks like a header: >=2 text labels and data beneath it."""
    if raw.empty:
        return 0
    best_row, best_score = 0, -1.0
    limit = min(len(raw), DETECT_ROWS)
    for i in range(limit):
        row = raw.iloc[i]
        values = [v for v in row.tolist() if not _blank(v)]
        if len(values) < 2:
            continue
        texts = [v for v in values if isinstance(v, str) and not _numeric_text(v)]
        if len(texts) < max(2, 0.6 * len(values)):
            continue
        below = raw.iloc[i + 1 : i + 4]
        if below.empty:
            continue
        below_counts = below.notna().sum(axis=1)
        if below_counts.max() < max(2, 0.5 * len(values)):
            continue
        uniqueness = len(set(map(str, texts))) / len(texts)
        score = len(texts) * uniqueness
        if score > best_score + 0.5:  # earliest row wins ties
            best_row, best_score = i, score
    return best_row


def read_table(path: Path, file_type: str, sheet: str | None, header_row: int | None = None,
               nrows: int | None = None) -> ReadResult:
    notes: list[str] = []
    if file_type == "csv":
        raw_head = _read_csv_raw(path, nrows=DETECT_ROWS)
        header = detect_header_row(raw_head) if header_row is None else header_row
        enc, sep = _sniff_csv(path)
        frame = pd.read_csv(path, sep=sep, encoding=enc, header=None, skiprows=header, nrows=None if nrows is None else nrows + 1,
                            dtype=str, keep_default_na=True, skip_blank_lines=True, engine="python" if len(sep) > 1 else "c")
        total = _count_csv_rows(path) - header - 1
        if sep != ",":
            notes.append(f"Detected '{sep}' delimiter")
        if enc not in ("utf-8", "utf-8-sig"):
            notes.append(f"Read with {enc} encoding")
    else:
        if header_row is None:
            raw_head = pd.read_excel(path, sheet_name=sheet, header=None, nrows=DETECT_ROWS, engine="openpyxl")
            header = detect_header_row(raw_head)
        else:
            header = header_row
        frame = pd.read_excel(path, sheet_name=sheet, header=None, skiprows=header,
                              nrows=None if nrows is None else nrows + 1, engine="openpyxl")
        total = None
    if frame.empty:
        return ReadResult(pd.DataFrame(), header, False, 0, notes)

    header_values = frame.iloc[0].tolist()
    body = frame.iloc[1:].reset_index(drop=True)
    body.columns = clean_column_names(header_values)
    # Remember the original spreadsheet row number (1-based) for traceability.
    body.index = pd.RangeIndex(start=header + 2, stop=header + 2 + len(body))

    empty_cols = [c for c in body.columns if body[c].isna().all() and c.startswith("Column ")]
    if empty_cols:
        body = body.drop(columns=empty_cols)
        notes.append(f"Dropped {len(empty_cols)} empty unnamed column(s)")
    empty_rows = body.isna().all(axis=1)
    if empty_rows.any():
        body = body[~empty_rows]
        notes.append(f"Skipped {int(empty_rows.sum())} blank row(s)")
    if header > 0:
        notes.append(f"Header found on row {header + 1}; {header} row(s) above it were ignored")

    body = body.infer_objects()
    sampled = nrows is not None and len(body) >= nrows
    if sampled:
        body = body.iloc[:nrows]
    return ReadResult(body, header, sampled, total if total is not None else (None if sampled else len(body)), notes)


def cache_key(sheet: str | None, header_row: int | None) -> str:
    return hashlib.sha1(f"{sheet}|{header_row}".encode()).hexdigest()[:16]


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and not v.strip())


def _numeric_text(v: str) -> bool:
    try:
        float(v.replace(",", "").replace("$", "").strip())
        return True
    except ValueError:
        return False


def _sniff_csv(path: Path) -> tuple[str, str]:
    data = path.read_bytes()[: 64 * 1024]
    encoding = "utf-8"
    for enc in CSV_ENCODINGS:
        try:
            text = data.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("latin-1", errors="replace")
        encoding = "latin-1"
    try:
        dialect = csv.Sniffer().sniff("\n".join(text.splitlines()[:50]), delimiters=",;\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ","
    return encoding, sep


def _read_csv_raw(path: Path, nrows: int) -> pd.DataFrame:
    """First rows as a ragged grid (title rows above the header have fewer fields)."""
    enc, sep = _sniff_csv(path)
    rows: list[list[str | None]] = []
    with open(path, newline="", encoding=enc, errors="replace") as fh:
        for row in csv.reader(fh, delimiter=sep):
            # Blank lines are kept as empty rows so indices match physical line numbers.
            rows.append([cell if cell.strip() else None for cell in row])
            if len(rows) >= nrows:
                break
    width = max((len(r) for r in rows), default=0)
    return pd.DataFrame([r + [None] * (width - len(r)) for r in rows])


def _count_csv_rows(path: Path) -> int:
    with open(path, "rb") as fh:
        return sum(1 for line in fh if line.strip())


def frame_to_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_pickle(buf)
    return buf.getvalue()
