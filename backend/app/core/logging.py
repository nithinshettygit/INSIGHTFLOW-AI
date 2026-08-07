"""Logging setup for the InsightFlow AI backend."""

import logging
import sys
from typing import Optional

from app.core.config import Settings


def setup_logging(settings: Optional[Settings] = None) -> None:
    """Configure root logging once for the process.

    Uses stdout so container/EC2 deployments can capture logs without
    local file dependencies. Level follows DEBUG / LOG_LEVEL settings.
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    level_name = settings.log_level.upper()
    if settings.debug and level_name == "INFO":
        level_name = "DEBUG"

    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        # Avoid duplicate handlers when reload creates the app again.
        root.setLevel(level)
        for handler in root.handlers:
            handler.setLevel(level)
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(handler)

    # Quiet noisy third-party loggers in development noise control.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for application modules."""
    return logging.getLogger(name)
