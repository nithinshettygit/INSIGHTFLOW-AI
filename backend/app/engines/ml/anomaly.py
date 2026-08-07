"""IsolationForest anomaly detection."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.engines.ml.helpers import (
    MlEngineError,
    coerce_numeric,
    infer_numeric_features,
    records_from_frame,
    resolve_column,
    resolve_columns,
)


def run_anomaly(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    features: list[str],
    target: str | None,
    contamination: float,
    limit: int,
    random_state: int = 42,
) -> dict[str, Any]:
    if frame.empty:
        raise MlEngineError("Dataset is empty")

    feature_cols = (
        resolve_columns(features, lookup, label="feature")
        if features
        else infer_numeric_features(frame)
    )
    target_col = (
        resolve_column(target, lookup, label="target", required=False) if target else None
    )
    if target_col and target_col not in feature_cols:
        try:
            coerce_numeric(frame, target_col)
            feature_cols = [target_col, *[c for c in feature_cols if c != target_col]]
        except MlEngineError:
            pass

    working = frame.copy()
    for col in feature_cols:
        working[col] = coerce_numeric(working, col)
    working = working.dropna(subset=feature_cols)
    if len(working) < 10:
        raise MlEngineError("Anomaly detection needs at least 10 rows after cleaning")

    matrix = working[feature_cols].to_numpy(dtype=float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=200,
    )
    pred = model.fit_predict(scaled)
    scores = model.decision_function(scaled)
    working = working.copy()
    working["anomaly"] = pred == -1
    working["anomaly_score"] = scores

    anomalies = working[working["anomaly"]].sort_values("anomaly_score")
    score_min = float(np.min(scores))
    score_max = float(np.max(scores))

    y_col = target_col or feature_cols[0]
    x_col = feature_cols[1] if len(feature_cols) > 1 else feature_cols[0]
    if x_col == y_col and len(feature_cols) == 1:
        plot_frame = working.reset_index(drop=True).copy()
        plot_frame["row"] = np.arange(1, len(plot_frame) + 1)
        figure = px.scatter(
            plot_frame,
            x="row",
            y=y_col,
            color=plot_frame["anomaly"].map({True: "anomaly", False: "normal"}),
            title=f"Anomaly detection: {y_col}",
            template="plotly_white",
        )
    else:
        figure = px.scatter(
            working,
            x=x_col,
            y=y_col,
            color=working["anomaly"].map({True: "anomaly", False: "normal"}),
            title=f"Anomaly detection ({len(feature_cols)} features)",
            template="plotly_white",
        )
    figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})

    preview_cols = list(dict.fromkeys([*feature_cols, "anomaly", "anomaly_score"]))
    for candidate in working.columns:
        name = str(candidate).lower()
        if candidate in preview_cols:
            continue
        if any(token in name for token in ("id", "customer", "name", "region", "order")):
            preview_cols.insert(0, str(candidate))
            if len(preview_cols) >= 8:
                break

    # Prefer showing anomalies first in the preview.
    ordered = pd.concat(
        [anomalies[preview_cols], working.loc[~working["anomaly"], preview_cols]],
        axis=0,
    )
    return {
        "task": "anomaly",
        "model": "isolation_forest",
        "summary": {
            "features": feature_cols,
            "row_count": int(len(working)),
            "anomaly_count": int(working["anomaly"].sum()),
            "anomaly_rate": round(float(working["anomaly"].mean()), 4),
            "contamination": contamination,
            "score_min": round(score_min, 4),
            "score_max": round(score_max, 4),
            "random_state": random_state,
        },
        "results": records_from_frame(ordered, limit=limit),
        "result_count": int(len(working)),
        "applied": {
            "features": feature_cols,
            "target": target_col,
            "contamination": contamination,
        },
        "plotly_figure": json.loads(pio.to_json(figure, engine="json")),
    }
