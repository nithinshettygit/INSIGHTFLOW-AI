"""CSV loading helpers with encoding fallbacks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Try strict Unicode first, then common Windows / Western European encodings.
# latin-1 is last because it accepts every byte sequence.
CSV_ENCODINGS = (
    "utf-8",
    "utf-8-sig",
    "cp1252",
    "latin-1",
)


class CsvReadError(ValueError):
    """Raised when a CSV cannot be decoded/parsed with known encodings."""


def _is_decode_error(exc: Exception) -> bool:
    if isinstance(exc, UnicodeDecodeError):
        return True
    message = str(exc).lower()
    return (
        "codec can't decode" in message
        or "unicode decode" in message
        or "invalid continuation byte" in message
    )


def read_csv_with_encoding(
    path: Path,
    *,
    nrows: int | None = None,
    encoding: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """Read a CSV, detecting a workable text encoding when needed.

    Returns:
        (dataframe, encoding_used)
    """
    if encoding:
        candidates = (encoding, *(e for e in CSV_ENCODINGS if e != encoding))
    else:
        candidates = CSV_ENCODINGS

    errors: list[str] = []

    for candidate in candidates:
        try:
            frame = pd.read_csv(path, nrows=nrows, encoding=candidate)
            return frame, candidate
        except Exception as exc:
            if _is_decode_error(exc):
                errors.append(f"{candidate}: {exc}")
                continue
            raise CsvReadError(f"Invalid CSV file: {exc}") from exc

    detail = "; ".join(errors) if errors else "unknown decode failure"
    raise CsvReadError(
        "Unable to decode CSV with supported encodings "
        f"({', '.join(CSV_ENCODINGS)}). Last errors: {detail}"
    )
