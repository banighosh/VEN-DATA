"""Reusable, side-effect-free cleaning primitives.

Design rule: these functions *normalise* values and *report* problems. They never
invent a business value. Anything that cannot be parsed becomes null and is
counted, so it shows up in the data quality report instead of disappearing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_CURRENCY_CHARS = re.compile(r"[\$€£¥₹₩₽¢]|USD|EUR|GBP|INR|JPY", re.IGNORECASE)
_NUMERIC_JUNK = re.compile(r"[\s,'_]")
_PARENS_NEG = re.compile(r"^\((.*)\)$")
_DATE_LIKE = re.compile(r"\d{1,4}[-/.\s]\d{1,2}[-/.\s]\d{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}")
EXCEL_EPOCH = pd.Timestamp("1899-12-30")


@dataclass
class ParseResult:
    values: pd.Series
    invalid_mask: pd.Series          # True where a non-empty input could not be parsed
    notes: list[str] = field(default_factory=list)

    @property
    def invalid_count(self) -> int:
        return int(self.invalid_mask.sum())


def is_blank(series: pd.Series) -> pd.Series:
    """True for NaN/None and for strings that are empty after stripping."""
    blank = series.isna()
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        stripped = series.astype("string").str.strip()
        blank = blank | stripped.isin(["", "nan", "NaN", "None", "null", "NULL", "N/A", "n/a", "NA", "-", "--"]).fillna(False)
    return blank.astype(bool)


def clean_column_names(columns: list) -> list[str]:
    """Trim, collapse whitespace, name unnamed columns, de-duplicate."""
    out: list[str] = []
    seen: dict[str, int] = {}
    for idx, col in enumerate(columns):
        name = "" if col is None or (isinstance(col, float) and np.isnan(col)) else str(col)
        name = re.sub(r"\s+", " ", name).strip()
        if not name or name.lower().startswith("unnamed:"):
            name = f"Column {idx + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out


def trim_strings(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Strip leading/trailing whitespace and collapse inner runs. Returns counts changed per column."""
    changed: dict[str, int] = {}
    df = df.copy()
    for col in df.columns:
        s = df[col]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            mask = s.map(lambda v: isinstance(v, str))
            if not mask.any():
                continue
            original = s[mask]
            cleaned = original.str.replace(r"\s+", " ", regex=True).str.strip()
            diff = int((cleaned != original).sum())
            if diff:
                changed[col] = diff
            df.loc[mask, col] = cleaned
    return df, changed


def normalize_numeric(series: pd.Series) -> ParseResult:
    """Parse numbers written with currency symbols, thousands separators, % or (negatives)."""
    blank = is_blank(series)
    if pd.api.types.is_bool_dtype(series):
        values = series.astype(float)
        return ParseResult(values, pd.Series(False, index=series.index))
    if pd.api.types.is_numeric_dtype(series):
        values = pd.to_numeric(series, errors="coerce").astype(float)
        return ParseResult(values, pd.Series(False, index=series.index))

    def parse(v):
        if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
            return float(v)
        if not isinstance(v, str):
            return np.nan
        t = v.strip().replace("−", "-")
        neg = False
        m = _PARENS_NEG.match(t)
        if m:
            neg, t = True, m.group(1)
        pct = t.endswith("%")
        t = _CURRENCY_CHARS.sub("", t.rstrip("%"))
        t = _NUMERIC_JUNK.sub("", t)
        if t.endswith("-"):
            neg, t = True, t[:-1]
        try:
            num = float(t)
        except ValueError:
            return np.nan
        if pct:
            num /= 100.0
        return -num if neg else num

    values = series.map(parse).astype(float)
    invalid = values.isna() & ~blank
    return ParseResult(values, invalid)


def looks_like_excel_serial(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return False
    return bool(((s > 20000) & (s < 60000) & (s == s.round())).mean() > 0.95)


def normalize_dates(series: pd.Series, allow_excel_serial: bool = True) -> ParseResult:
    """Parse dates from datetimes, ISO/locale strings and Excel serial numbers."""
    blank = is_blank(series)
    notes: list[str] = []
    if pd.api.types.is_datetime64_any_dtype(series):
        values = pd.to_datetime(series, errors="coerce")
        return ParseResult(values.dt.tz_localize(None) if values.dt.tz is not None else values,
                           pd.Series(False, index=series.index))
    if pd.api.types.is_numeric_dtype(series):
        if allow_excel_serial and looks_like_excel_serial(series):
            values = EXCEL_EPOCH + pd.to_timedelta(pd.to_numeric(series, errors="coerce"), unit="D")
            notes.append("Converted Excel serial numbers to dates")
            return ParseResult(values, values.isna() & ~blank, notes)
        values = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
        return ParseResult(values, ~blank, ["Numeric values are not dates"])

    def _one(v):
        if isinstance(v, pd.Timestamp):
            return v
        if hasattr(v, "year") and hasattr(v, "month"):
            return pd.Timestamp(v)
        return pd.NaT

    as_obj = series.astype(object)
    direct = as_obj.map(_one)
    text_mask = as_obj.map(lambda v: isinstance(v, str)) & ~blank
    if text_mask.any():
        texts = as_obj[text_mask].astype(str).str.strip()
        dayfirst = _guess_dayfirst(texts)
        parsed = pd.to_datetime(texts, errors="coerce", format="mixed", dayfirst=dayfirst)
        direct.loc[text_mask] = parsed
        if dayfirst:
            notes.append("Day-first date format detected (DD/MM/YYYY)")
    values = pd.to_datetime(direct, errors="coerce")
    invalid = values.isna() & ~blank
    return ParseResult(values, invalid, notes)


def _guess_dayfirst(texts: pd.Series) -> bool:
    """If any slash/dash date has a first component > 12, the format is day-first."""
    parts = texts.str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
    if parts.dropna().empty:
        return False
    first = pd.to_numeric(parts[0], errors="coerce")
    second = pd.to_numeric(parts[1], errors="coerce")
    return bool((first > 12).any() and not (second > 12).any())


def date_like_ratio(series: pd.Series) -> float:
    s = series.dropna()
    s = s[s.map(lambda v: isinstance(v, str))]
    if s.empty:
        return 0.0
    return float(s.astype(str).str.contains(_DATE_LIKE).mean())


def harmonize_categories(series: pd.Series) -> tuple[pd.Series, dict[str, list[str]]]:
    """Unify values that differ only by case/whitespace (e.g. 'In-store' vs 'In-Store').

    The most frequent spelling wins. Returns the new series and {canonical: [variants]}.
    """
    s = series.copy()
    mask = s.map(lambda v: isinstance(v, str))
    if not mask.any():
        return s, {}
    text = s[mask]
    keys = text.str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()
    variants: dict[str, list[str]] = {}
    replace: dict[str, str] = {}
    for key, group in text.groupby(keys):
        counts = group.value_counts()
        if len(counts) > 1:
            # Most frequent spelling wins; ties prefer conventional casing (not all-lower / all-upper).
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].islower() or kv[0].isupper(), kv[0]))
            canonical = str(ranked[0][0])
            others = [str(v) for v, _ in ranked[1:]]
            variants[canonical] = others
            for o in others:
                replace[o] = canonical
    if replace:
        s.loc[mask] = text.replace(replace)
    return s, variants


def case_variant_groups(series: pd.Series, limit: int = 10) -> list[list[str]]:
    """Report groups of spellings that collapse to the same value (inconsistent formatting)."""
    s = series.dropna()
    s = s[s.map(lambda v: isinstance(v, str))]
    if s.empty:
        return []
    uniques = pd.Series(s.unique())
    if len(uniques) > 5000:
        uniques = uniques.head(5000)
    keys = uniques.str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()
    groups = [sorted(g.tolist()) for _, g in uniques.groupby(keys) if len(g) > 1]
    return groups[:limit]


def detect_duplicates(df: pd.DataFrame, subset: list[str] | None = None) -> pd.Series:
    """Mask of rows that repeat an earlier row exactly (first occurrence is kept)."""
    if df.empty:
        return pd.Series(False, index=df.index)
    hashed = pd.util.hash_pandas_object(df[subset] if subset else df, index=False)
    return hashed.duplicated(keep="first")


def missing_value_summary(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    out = {}
    n = max(len(df), 1)
    for col in df.columns:
        missing = int(is_blank(df[col]).sum())
        out[col] = {"missing": missing, "missing_pct": round(missing / n * 100, 2)}
    return out


def iqr_outliers(values: pd.Series, k: float = 3.0) -> tuple[pd.Series, tuple[float, float] | None]:
    """Extreme outliers using Tukey fences (k=3 flags only far-out values)."""
    v = pd.to_numeric(values, errors="coerce")
    clean = v.dropna()
    if len(clean) < 20:
        return pd.Series(False, index=values.index), None
    q1, q3 = np.percentile(clean, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=values.index), None
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return ((v < lo) | (v > hi)).fillna(False), (float(lo), float(hi))


def format_currency(value: float | None, currency: str = "USD", compact: bool = True) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    symbol = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(currency, "")
    sign = "-" if value < 0 else ""
    v = abs(value)
    if compact:
        for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if v >= div:
                return f"{sign}{symbol}{v / div:,.2f}{suffix}"
    return f"{sign}{symbol}{v:,.0f}"


def format_number(value: float | None, compact: bool = True, decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    sign = "-" if value < 0 else ""
    v = abs(value)
    if compact:
        for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if v >= div:
                return f"{sign}{v / div:,.2f}{suffix}"
    return f"{sign}{v:,.{decimals}f}"


def format_percent(value: float | None, decimals: int = 1, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value * 100:+.{decimals}f}%" if signed else f"{value * 100:.{decimals}f}%"
