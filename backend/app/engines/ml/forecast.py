"""Simple time-series forecast (trend + seasonal-naive blend)."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from sklearn.linear_model import LinearRegression

from app.engines.ml.helpers import (
    MlEngineError,
    coerce_numeric,
    detect_time_column,
    records_from_frame,
    resolve_column,
    to_jsonable,
)


def run_forecast(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    target: str | None,
    time_column: str | None,
    horizon: int,
    limit: int,
    random_state: int = 42,
) -> dict[str, Any]:
    if frame.empty:
        raise MlEngineError("Dataset is empty")

    target_col = resolve_column(target, lookup, label="target") if target else None
    if target_col is None:
        # Prefer common business metrics, else first coercible numeric column.
        for candidate in ("sales", "revenue", "profit", "quantity", "amount"):
            resolved = resolve_column(candidate, lookup, label="target", required=False)
            if resolved is not None:
                try:
                    coerce_numeric(frame, resolved)
                    target_col = resolved
                    break
                except MlEngineError:
                    continue
        if target_col is None:
            for column in frame.columns:
                try:
                    coerce_numeric(frame, str(column))
                    target_col = str(column)
                    break
                except MlEngineError:
                    continue
    if target_col is None:
        raise MlEngineError("Could not find a numeric target column for forecasting")

    time_col = (
        resolve_column(time_column, lookup, label="time_column", required=False)
        if time_column
        else detect_time_column(frame)
    )

    working = frame[[c for c in [time_col, target_col] if c]].copy()
    working[target_col] = coerce_numeric(working, target_col)
    working = working.dropna(subset=[target_col])

    if time_col:
        working[time_col] = pd.to_datetime(working[time_col], errors="coerce")
        working = working.dropna(subset=[time_col])
        working = (
            working.groupby(time_col, as_index=False)[target_col]
            .sum()
            .sort_values(time_col)
        )
        time_values = working[time_col]
        freq = pd.infer_freq(time_values) or _guess_freq(time_values)
    else:
        working = working.reset_index(drop=True)
        working.insert(0, "period", np.arange(1, len(working) + 1))
        time_col = "period"
        time_values = working[time_col]
        freq = None

    if len(working) < 3:
        raise MlEngineError("Forecast needs at least 3 aggregated time points")

    y = working[target_col].astype(float).to_numpy()
    x = np.arange(len(y), dtype=float).reshape(-1, 1)
    model = LinearRegression()
    model.fit(x, y)
    fitted = model.predict(x)
    mae = float(np.mean(np.abs(y - fitted)))

    future_x = np.arange(len(y), len(y) + horizon, dtype=float).reshape(-1, 1)
    trend_forecast = model.predict(future_x)

    # Seasonal-naive blend when enough history exists (weekly-ish period of 7).
    season = 7 if len(y) >= 14 else max(1, min(4, len(y) // 2))
    seasonal = np.array([y[-season + (i % season)] for i in range(horizon)], dtype=float)
    alpha = 0.65
    forecast_values = alpha * trend_forecast + (1.0 - alpha) * seasonal
    # Keep non-negative for typical business metrics.
    if float(np.nanmin(y)) >= 0:
        forecast_values = np.maximum(forecast_values, 0.0)

    history_labels = [_label_time(v) for v in time_values.tolist()]
    future_labels = _future_labels(time_values, horizon, freq)

    history_rows = [
        {
            "step": i + 1,
            time_col: history_labels[i],
            target_col: to_jsonable(y[i]),
            "fitted": to_jsonable(fitted[i]),
            "kind": "history",
        }
        for i in range(len(y))
    ]
    forecast_rows = [
        {
            "step": len(y) + i + 1,
            time_col: future_labels[i],
            target_col: to_jsonable(forecast_values[i]),
            "kind": "forecast",
        }
        for i in range(horizon)
    ]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=history_labels,
            y=y.tolist(),
            mode="lines+markers",
            name="history",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=future_labels,
            y=forecast_values.tolist(),
            mode="lines+markers",
            name="forecast",
            line={"dash": "dash"},
        )
    )
    figure.update_layout(
        title=f"Forecast: {target_col}",
        xaxis_title=time_col,
        yaxis_title=target_col,
        template="plotly_white",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )

    preview = pd.DataFrame(history_rows[-min(limit, len(history_rows)) :] + forecast_rows)
    return {
        "task": "forecast",
        "model": "linear_trend_seasonal_blend",
        "summary": {
            "target": target_col,
            "time_column": time_col,
            "history_points": len(y),
            "horizon": horizon,
            "train_mae": round(mae, 4),
            "forecast_mean": round(float(np.mean(forecast_values)), 4),
            "forecast_total": round(float(np.sum(forecast_values)), 4),
            "random_state": random_state,
        },
        "results": records_from_frame(preview, limit=len(preview)),
        "result_count": len(preview),
        "applied": {
            "target": target_col,
            "time_column": time_col,
            "horizon": horizon,
            "freq": freq,
        },
        "plotly_figure": _figure_dict(figure),
    }


def _guess_freq(values: pd.Series) -> str | None:
    if len(values) < 2:
        return None
    delta = (values.iloc[-1] - values.iloc[0]) / max(len(values) - 1, 1)
    days = float(getattr(delta, "days", 0) or 0)
    if days >= 27:
        return "MS"
    if days >= 6:
        return "W"
    if days >= 1:
        return "D"
    return None


def _future_labels(
    time_values: pd.Series,
    horizon: int,
    freq: str | None,
) -> list[str]:
    last = time_values.iloc[-1]
    if isinstance(last, (int, np.integer, float, np.floating)) and not isinstance(
        last,
        (pd.Timestamp,),
    ):
        start = int(last) + 1
        return [str(start + i) for i in range(horizon)]

    last_ts = pd.Timestamp(last)
    if freq:
        try:
            idx = pd.date_range(start=last_ts, periods=horizon + 1, freq=freq)[1:]
            return [_label_time(v) for v in idx]
        except Exception:
            pass
    step = pd.Timedelta(days=1)
    if len(time_values) >= 2:
        delta = pd.Timestamp(time_values.iloc[-1]) - pd.Timestamp(time_values.iloc[-2])
        if delta > pd.Timedelta(0):
            step = delta
    return [_label_time(last_ts + step * (i + 1)) for i in range(horizon)]


def _label_time(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def _figure_dict(figure: go.Figure) -> dict[str, Any]:
    return json.loads(pio.to_json(figure, engine="json"))
