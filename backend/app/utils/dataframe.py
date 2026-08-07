"""DataFrame helpers for typed column coercion."""

from __future__ import annotations

import pandas as pd


def ensure_numeric_series(series: pd.Series, *, column_name: str) -> pd.Series:
    """Return a numeric series, coercing digit-like object columns when possible.

    Raises:
        ValueError: if the column cannot be interpreted as numeric.
    """
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return series

    cleaned = (
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
    )
    numeric = pd.to_numeric(cleaned, errors="coerce")
    non_null = int(series.notna().sum())
    converted = int(numeric.notna().sum())
    if non_null == 0 or converted == 0 or converted / non_null < 0.8:
        raise ValueError(
            f"Column '{column_name}' is not numeric and could not be coerced "
            f"(converted {converted}/{non_null} non-null values)"
        )
    return numeric
