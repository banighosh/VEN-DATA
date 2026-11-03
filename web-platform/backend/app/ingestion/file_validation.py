"""First gate of the pipeline: is this file something we can safely read?"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED = {".xlsx": "xlsx", ".xlsm": "xlsx", ".csv": "csv", ".txt": "csv", ".tsv": "csv"}
ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class FileValidationError(ValueError):
    """Raised with a user-facing message when an upload is rejected."""


@dataclass
class ValidatedFile:
    filename: str
    file_type: str  # "xlsx" | "csv"
    size_bytes: int


def validate_upload(filename: str, head: bytes, size_bytes: int, max_mb: int) -> ValidatedFile:
    name = Path(filename or "").name
    if not name:
        raise FileValidationError("The upload has no file name.")
    ext = Path(name).suffix.lower()
    if ext == ".xls":
        raise FileValidationError("Legacy .xls workbooks are not supported. Re-save the file as .xlsx and upload again.")
    if ext not in SUPPORTED:
        raise FileValidationError(f"Unsupported file type '{ext or 'none'}'. Upload an Excel (.xlsx) or CSV file.")
    if size_bytes == 0:
        raise FileValidationError("The file is empty.")
    if size_bytes > max_mb * 1024 * 1024:
        raise FileValidationError(f"The file is {size_bytes / 1048576:.1f} MB; the limit is {max_mb} MB.")
    kind = SUPPORTED[ext]
    if kind == "xlsx":
        if head.startswith(OLE_MAGIC):
            raise FileValidationError("This looks like an encrypted or legacy (.xls) workbook. Save it as a standard .xlsx file.")
        if not head.startswith(ZIP_MAGIC):
            raise FileValidationError("The file has an .xlsx extension but is not a valid Excel workbook.")
    else:
        if b"\x00" in head[:4096]:
            raise FileValidationError("The CSV file contains binary data and cannot be read as text.")
    return ValidatedFile(filename=name, file_type=kind, size_bytes=size_bytes)
