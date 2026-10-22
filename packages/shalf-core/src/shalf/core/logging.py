from __future__ import annotations

import logging
import os

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once; level defaults to ``$SHALF_LOG_LEVEL`` or INFO."""
    logging.basicConfig(
        level=(level or os.getenv("SHALF_LOG_LEVEL") or "INFO").upper(), format=_FORMAT
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
