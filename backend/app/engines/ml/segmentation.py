"""KMeans customer / row segmentation."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.io as pio
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from app.engines.ml.helpers import (
    MlEngineError,
    coerce_numeric,
    infer_numeric_features,
    records_from_frame,
    resolve_columns,
    to_jsonable,
)


def run_segmentation(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    features: list[str],
    n_clusters: int,
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
    if len(feature_cols) < 1:
        raise MlEngineError("Segmentation needs at least one numeric feature")

    working = frame.copy()
    for col in feature_cols:
        working[col] = coerce_numeric(working, col)
    working = working.dropna(subset=feature_cols)
    if len(working) < n_clusters:
        raise MlEngineError(
            f"Need at least {n_clusters} rows for {n_clusters} clusters "
            f"(have {len(working)} after dropping nulls)",
        )

    matrix = working[feature_cols].to_numpy(dtype=float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    kmeans = KMeans(n_clusters=n_clusters, n_init=10, random_state=random_state)
    labels = kmeans.fit_predict(scaled)
    working = working.copy()
    working["cluster"] = labels.astype(int)

    sizes = (
        working.groupby("cluster")
        .size()
        .rename("size")
        .reset_index()
        .sort_values("cluster")
    )
    centroids = []
    for cluster_id in range(n_clusters):
        center = {
            "cluster": int(cluster_id),
            "size": int((labels == cluster_id).sum()),
        }
        inverted = scaler.inverse_transform(
            kmeans.cluster_centers_[cluster_id].reshape(1, -1)
        )[0]
        for i, col in enumerate(feature_cols):
            center[col] = to_jsonable(float(inverted[i]))
        centroids.append(center)

    plot_frame = working.copy()
    if len(feature_cols) >= 2:
        x_col, y_col = feature_cols[0], feature_cols[1]
    else:
        x_col = feature_cols[0]
        y_col = "cluster"
    figure = px.scatter(
        plot_frame,
        x=x_col,
        y=y_col,
        color=plot_frame["cluster"].astype(str),
        title=f"Customer segmentation ({n_clusters} clusters)",
        template="plotly_white",
    )
    figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})

    preview_cols = [c for c in working.columns if c in feature_cols or c == "cluster"]
    for candidate in working.columns:
        name = str(candidate).lower()
        if candidate in preview_cols:
            continue
        if any(token in name for token in ("id", "customer", "name", "region", "segment")):
            preview_cols.insert(0, str(candidate))
            if len(preview_cols) >= 6:
                break

    preview = working[preview_cols]
    return {
        "task": "segmentation",
        "model": "kmeans",
        "summary": {
            "n_clusters": n_clusters,
            "features": feature_cols,
            "row_count": int(len(working)),
            "cluster_sizes": {
                str(int(row.cluster)): int(row.size) for row in sizes.itertuples()
            },
            "centroids": centroids,
            "inertia": round(float(kmeans.inertia_), 4),
            "random_state": random_state,
        },
        "results": records_from_frame(preview, limit=limit),
        "result_count": int(len(working)),
        "applied": {
            "features": feature_cols,
            "n_clusters": n_clusters,
        },
        "plotly_figure": json.loads(pio.to_json(figure, engine="json")),
    }
