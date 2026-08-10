"""IsolationForest anomaly detection with dataset-adaptive features/plots."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.engines.ml.helpers import (
    MlEngineError,
    coerce_numeric,
    infer_target_column,
    pick_scatter_axes,
    records_from_frame,
    resolve_column,
    resolve_feature_columns,
)

_MAX_PLOT_POINTS = 2500


def run_anomaly(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    features: list[str],
    target: str | None,
    contamination: float,
    limit: int,
    random_state: int = 42,
    plot_x: str | None = None,
    plot_y: str | None = None,
) -> dict[str, Any]:
    if frame.empty:
        raise MlEngineError("Dataset is empty")

    feature_cols = resolve_feature_columns(frame, lookup, features)

    target_col = None
    if target:
        target_col = resolve_column(target, lookup, label="target", required=False)
    if target_col is None:
        try:
            target_col = infer_target_column(frame, lookup)
        except MlEngineError:
            target_col = feature_cols[0] if feature_cols else None

    if target_col and target_col not in feature_cols:
        try:
            coerce_numeric(frame, target_col)
            feature_cols = [target_col, *[c for c in feature_cols if c != target_col]]
        except MlEngineError:
            pass

    if not feature_cols:
        raise MlEngineError("Anomaly detection needs numeric feature columns")

    working = frame.copy()
    for col in feature_cols:
        working[col] = coerce_numeric(working, col)
    working = working.dropna(subset=feature_cols).reset_index(drop=True)
    if len(working) < 10:
        raise MlEngineError("Anomaly detection needs at least 10 rows after cleaning")

    # Keep contamination sane for tiny datasets.
    contamination = float(min(max(contamination, 0.01), 0.25))
    if int(contamination * len(working)) < 1:
        contamination = max(0.01, 1.0 / len(working))

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

    figure, plot_meta = _build_anomaly_figure(
        working,
        scaled=scaled,
        feature_cols=feature_cols,
        target_col=target_col,
        plot_x=plot_x,
        plot_y=plot_y,
        lookup=lookup,
        random_state=random_state,
    )

    preview_cols = list(dict.fromkeys([*feature_cols, "anomaly", "anomaly_score"]))
    for candidate in working.columns:
        name = str(candidate).lower()
        if str(candidate) in preview_cols:
            continue
        if any(token in name for token in ("id", "customer", "name", "region", "order", "category")):
            preview_cols.insert(0, str(candidate))
            if len(preview_cols) >= 8:
                break

    ordered = pd.concat(
        [anomalies[preview_cols], working.loc[~working["anomaly"], preview_cols]],
        axis=0,
    )
    return {
        "task": "anomaly",
        "model": "isolation_forest",
        "summary": {
            "features": feature_cols,
            "target": target_col,
            "row_count": int(len(working)),
            "anomaly_count": int(working["anomaly"].sum()),
            "anomaly_rate": round(float(working["anomaly"].mean()), 4),
            "contamination": contamination,
            "score_min": round(score_min, 4),
            "score_max": round(score_max, 4),
            "plot": plot_meta,
            "random_state": random_state,
        },
        "results": records_from_frame(ordered, limit=limit),
        "result_count": int(len(working)),
        "applied": {
            "features": feature_cols,
            "target": target_col,
            "contamination": contamination,
            "plot": plot_meta,
            "selection": "dataset_adaptive",
        },
        "plotly_figure": json.loads(pio.to_json(figure, engine="json")),
    }


def _build_anomaly_figure(
    working: pd.DataFrame,
    *,
    scaled: np.ndarray,
    feature_cols: list[str],
    target_col: str | None,
    plot_x: str | None,
    plot_y: str | None,
    lookup: dict[str, str],
    random_state: int,
) -> tuple[Any, dict[str, Any]]:
    plot_frame = working
    if len(working) > _MAX_PLOT_POINTS:
        # Keep anomalies, sample normals.
        anomalies = working[working["anomaly"]]
        normals = working[~working["anomaly"]]
        remain = max(0, _MAX_PLOT_POINTS - len(anomalies))
        if len(normals) > remain:
            normals = normals.sample(n=remain, random_state=random_state)
        plot_frame = pd.concat([anomalies, normals], axis=0)

    color = plot_frame["anomaly"].map({True: "anomaly", False: "normal"})
    resolved_x = (
        resolve_column(plot_x, lookup, label="plot_x", required=False) if plot_x else None
    )
    resolved_y = (
        resolve_column(plot_y, lookup, label="plot_y", required=False) if plot_y else None
    )

    axes = pick_scatter_axes(
        plot_frame,
        feature_cols,
        preferred_x=resolved_x,
        preferred_y=resolved_y,
    )
    if axes is not None:
        axis_x, axis_y = axes
        try:
            frame = plot_frame.copy()
            frame[axis_x] = coerce_numeric(frame, axis_x)
            frame[axis_y] = coerce_numeric(frame, axis_y)
            figure = px.scatter(
                frame,
                x=axis_x,
                y=axis_y,
                color=color,
                title=f"Anomaly detection · {axis_x} vs {axis_y}",
                template="plotly_white",
            )
            figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})
            return figure, {"method": "feature_axes", "x": axis_x, "y": axis_y}
        except MlEngineError:
            pass

    if len(feature_cols) >= 2:
        pca = PCA(n_components=2, random_state=random_state)
        coords_full = pca.fit_transform(scaled)
        coords = coords_full[plot_frame.index.to_numpy()]
        frame = plot_frame.copy()
        frame["PC1"] = coords[:, 0]
        frame["PC2"] = coords[:, 1]
        explained = [round(float(v) * 100, 1) for v in pca.explained_variance_ratio_]
        figure = px.scatter(
            frame,
            x="PC1",
            y="PC2",
            color=color,
            title=(
                f"Anomaly detection · PCA of "
                f"{', '.join(feature_cols[:4])}{'…' if len(feature_cols) > 4 else ''}"
            ),
            template="plotly_white",
            labels={
                "PC1": f"PC1 ({explained[0]}%)",
                "PC2": f"PC2 ({explained[1]}%)",
            },
        )
        figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})
        return figure, {
            "method": "pca",
            "x": "PC1",
            "y": "PC2",
            "features": feature_cols,
            "explained_variance_pct": explained,
        }

    y_col = target_col or feature_cols[0]
    frame = plot_frame.reset_index(drop=True).copy()
    frame["row"] = np.arange(1, len(frame) + 1)
    figure = px.scatter(
        frame,
        x="row",
        y=y_col,
        color=frame["anomaly"].map({True: "anomaly", False: "normal"}),
        title=f"Anomaly detection · {y_col}",
        template="plotly_white",
    )
    figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})
    return figure, {"method": "series", "x": "row", "y": y_col}
