"""Minimal logging setup for the engine.

All engine loggers live under the `micro_engine.*` namespace so a single call
to `configure()` controls them without fighting uvicorn's own handlers.
"""
from __future__ import annotations

import logging

_ROOT = "micro_engine"


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_ROOT}.{name}")


def configure(level: str = "INFO") -> None:
    """Attach one stream handler to the engine's root logger (idempotent)."""
    logger = logging.getLogger(_ROOT)
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    logger.propagate = False
