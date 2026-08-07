"""File validation and filesystem helpers for uploads."""

import re
from pathlib import Path

ALLOWED_EXTENSIONS = {
    ".csv": "csv",
    ".xlsx": "excel",
    ".pdf": "pdf",
}


def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe basename."""
    name = Path(filename).name.strip().replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()]", "_", name, flags=re.UNICODE)
    name = name.strip(" .")
    if not name or name in {".", ".."}:
        raise ValueError("Invalid filename")
    return name


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def detect_dataset_type(filename: str) -> str:
    ext = extension_of(filename)
    dataset_type = ALLOWED_EXTENSIONS.get(ext)
    if dataset_type is None:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {allowed}")
    return dataset_type


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
