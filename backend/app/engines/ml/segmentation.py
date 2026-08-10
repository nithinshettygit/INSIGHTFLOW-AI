"""KMeans segmentation with dataset-adaptive feature selection and plots."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from app.engines.ml.helpers import (
    MlEngineError,
    coerce_numeric,
    pick_scatter_axes,
    records_from_frame,
    resolve_column,
    resolve_feature_columns,
    to_jsonable,
)

_MAX_PLOT_POINTS = 2500


def run_segmentation(
    frame: pd.DataFrame,
    lookup: dict[str, str],
    *,
    features: list[str],
    n_clusters: int,
    limit: int,
    random_state: int = 42,
    plot_x: str | None = None,
    plot_y: str | None = None,
) -> dict[str, Any]:
    if frame.empty:
        raise MlEngineError("Dataset is empty")

    feature_cols = resolve_feature_columns(frame, lookup, features)
    if len(feature_cols) < 1:
        raise MlEngineError("Segmentation needs at least one numeric feature")

    working = frame.copy()
    for col in feature_cols:
        working[col] = coerce_numeric(working, col)
    working = working.dropna(subset=feature_cols).reset_index(drop=True)
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

    figure, plot_meta = _build_cluster_figure(
        working,
        scaled=scaled,
        feature_cols=feature_cols,
        n_clusters=n_clusters,
        plot_x=plot_x,
        plot_y=plot_y,
        lookup=lookup,
        random_state=random_state,
    )

    preview_cols = [c for c in working.columns if c in feature_cols or c == "cluster"]
    for candidate in working.columns:
        name = str(candidate).lower()
        if str(candidate) in preview_cols:
            continue
        if any(token in name for token in ("id", "customer", "name", "region", "segment", "category")):
            preview_cols.insert(0, str(candidate))
            if len(preview_cols) >= 8:
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
            "plot": plot_meta,
            "random_state": random_state,
        },
        "results": records_from_frame(preview, limit=limit),
        "result_count": int(len(working)),
        "applied": {
            "features": feature_cols,
            "n_clusters": n_clusters,
            "plot": plot_meta,
            "selection": "dataset_adaptive",
        },
        "plotly_figure": json.loads(pio.to_json(figure, engine="json")),
    }


def _build_cluster_figure(
    working: pd.DataFrame,
    *,
    scaled: np.ndarray,
    feature_cols: list[str],
    n_clusters: int,
    plot_x: str | None,
    plot_y: str | None,
    lookup: dict[str, str],
    random_state: int,
) -> tuple[Any, dict[str, Any]]:
    plot_frame = working
    if len(working) > _MAX_PLOT_POINTS:
        plot_frame = working.sample(n=_MAX_PLOT_POINTS, random_state=random_state)

    resolved_x = (
        resolve_column(plot_x, lookup, label="plot_x", required=False) if plot_x else None
    )
    resolved_y = (
        resolve_column(plot_y, lookup, label="plot_y", required=False) if plot_y else None
    )

    # 1) Continuous feature axes (reject discrete Quantity-style stripes).
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
                color=frame["cluster"].astype(str),
                title=f"Segmentation ({n_clusters} clusters) · {axis_x} vs {axis_y}",
                template="plotly_white",
                labels={"color": "cluster"},
            )
            figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})
            return figure, {
                "method": "feature_axes",
                "x": axis_x,
                "y": axis_y,
            }
        except MlEngineError:
            pass

    # 2) Two+ features → PCA projection (works for any dataset shape).
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
            color=frame["cluster"].astype(str),
            title=(
                f"Segmentation ({n_clusters} clusters) · PCA of "
                f"{', '.join(feature_cols[:4])}{'…' if len(feature_cols) > 4 else ''}"
            ),
            template="plotly_white",
            labels={
                "color": "cluster",
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

    # 3) Single feature → strip/box style by cluster (never plot cluster on Y as continuous).
    feature = feature_cols[0]
    frame = plot_frame.copy()
    figure = px.strip(
        frame,
        x="cluster",
        y=feature,
        color=frame["cluster"].astype(str),
        title=f"Segmentation ({n_clusters} clusters) · {feature} by cluster",
        template="plotly_white",
        labels={"color": "cluster"},
    )
    figure.update_layout(margin={"l": 40, "r": 20, "t": 50, "b": 40})
    return figure, {
        "method": "strip",
        "x": "cluster",
        "y": feature,
    }
