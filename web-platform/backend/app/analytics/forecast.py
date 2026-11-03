"""Monthly revenue forecasting — only when the history supports it.

Method (deliberately simple and explainable for business users):
  * Seasonality: each month's revenue relative to its own calendar year's mean,
    averaged over complete years. Normalising within each year keeps the
    seasonal shape stable even when the overall level jumps between years.
  * Trend: a linear trend fitted to the last 12 de-seasonalised months,
    damped as it is projected forward so it does not run away.
  * Fewer than 12 months: no forecast. No complete calendar year: trend only.
A three-month hold-out back-test reports MAPE, and structural breaks in the
history (e.g. a step change in recorded volume) are flagged as warnings.
"""
from typing import Any

import numpy as np
import pandas as pd

from .common import Scope

MIN_MONTHS = 12
LOCAL_TREND_MONTHS = 12
DAMPING = 0.85


def _monthly(df: pd.DataFrame, end: pd.Timestamp | None) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    d = df if end is None else df[df["txn_date"] <= end]
    s = d.groupby(d["txn_date"].dt.to_period("M"))["revenue"].sum()
    idx = pd.period_range(s.index.min(), s.index.max(), freq="M")
    return s.reindex(idx)  # missing months stay NaN


def _seasonal_profile(y: np.ndarray, months: np.ndarray, years: np.ndarray) -> np.ndarray | None:
    acc: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for yr in np.unique(years):
        mask = years == yr
        if mask.sum() == 12 and y[mask].mean() > 0:
            mu = y[mask].mean()
            for m, v in zip(months[mask], y[mask]):
                acc[int(m)].append(v / mu)
    if not acc[1]:
        return None
    prof = np.array([np.mean(acc[m]) for m in range(1, 13)])
    return prof / prof.mean()


def _fit_predict(y: np.ndarray, months: np.ndarray, years: np.ndarray, horizon: int, future_months: np.ndarray,
                 local: int = LOCAL_TREND_MONTHS, damp: float = DAMPING) -> tuple[np.ndarray, np.ndarray, str]:
    n = len(y)
    seasonal = _seasonal_profile(y, months, years) if n >= 15 else None
    s_hist = seasonal[months - 1] if seasonal is not None else np.ones(n)
    deseason = y / s_hist
    k = min(n, local)
    x = np.arange(n - k, n)
    slope, intercept = np.polyfit(x, deseason[-k:], 1)
    fitted = (intercept + slope * np.arange(n)) * s_hist
    level = intercept + slope * (n - 1)
    preds, drift = [], 0.0
    for i in range(1, horizon + 1):
        drift += slope * damp ** i
        preds.append((level + drift) * (seasonal[future_months[i - 1] - 1] if seasonal is not None else 1.0))
    method = ("Seasonal profile × damped 12-month trend" if seasonal is not None
              else "Damped linear trend (no complete year to estimate seasonality)")
    return fitted, np.array(preds), method


def forecast(scope: Scope, horizon: int = 6) -> dict[str, Any]:
    series = _monthly(scope.base, scope.end)
    n_obs = int(series.notna().sum())
    if n_obs < MIN_MONTHS:
        return {"available": False, "reason": f"Forecasting needs at least {MIN_MONTHS} months of history; "
                                             f"the filtered data has {n_obs}.", "history": []}
    if series.isna().any():
        return {"available": False, "reason": "The monthly history has gaps (months with no transactions); "
                                             "a forecast would rest on fabricated values.", "history": []}
    y = series.to_numpy(dtype=float)
    months = np.array([p.month for p in series.index])
    years = np.array([p.year for p in series.index])
    future_idx = pd.period_range(series.index[-1] + 1, periods=horizon, freq="M")
    future_months = np.array([p.month for p in future_idx])
    fitted, pred, method = _fit_predict(y, months, years, horizon, future_months)
    k = min(len(y), LOCAL_TREND_MONTHS)
    resid = (y - fitted)[-k:]  # residuals over the window the trend was fitted on
    sigma = float(np.std(resid, ddof=1)) if len(resid) > 2 else 0.0

    # Back-test: refit without the last 3 months and score those months.
    mape = None
    if len(y) >= MIN_MONTHS + 3:
        _, bt_pred, _ = _fit_predict(y[:-3], months[:-3], years[:-3], 3, months[-3:])
        actual = y[-3:]
        mask = actual != 0
        if mask.any():
            mape = float(np.mean(np.abs((actual[mask] - bt_pred[mask]) / actual[mask])))

    warnings: list[str] = []
    if len(y) >= 24:
        first, last = y[:12].mean(), y[-12:].mean()
        if first > 0 and (last / first > 2 or last / first < 0.5):
            warnings.append(f"The last 12 months average {last / first:.1f}× the first 12 months. A step change of this size "
                            "may reflect changes in data coverage rather than demand; treat the forecast as indicative only.")
    if mape is not None and mape > 0.25:
        warnings.append(f"Back-test error is high (MAPE {mape:.0%}); forecast reliability is low.")
    if (pred < 0).any():
        warnings.append("The fitted trend projects negative revenue; negative points are floored at zero.")
        pred = np.maximum(pred, 0)

    z = 1.28  # ~80% interval
    out_fc = []
    for i, (p, v) in enumerate(zip(future_idx, pred)):
        width = z * sigma * np.sqrt(1 + (i + 1) / len(y))
        out_fc.append({"label": p.strftime("%b %Y"), "period": p.start_time.date().isoformat(), "forecast": float(v),
                       "lower": float(max(v - width, 0)), "upper": float(v + width)})
    history = [{"label": p.strftime("%b %Y"), "period": p.start_time.date().isoformat(), "actual": float(v),
                "fitted": float(f)} for p, v, f in zip(series.index, y, fitted)]
    return {"available": True, "method": method, "horizon": horizon, "history": history, "forecast": out_fc,
            "mape": mape, "interval": "80% prediction interval", "observations": len(y), "warnings": warnings,
            "label": "Statistical projection, not a business plan"}
