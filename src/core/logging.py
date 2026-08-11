"""Small, reusable logging setup for observable pipeline execution."""

import logging

from src.core.settings import settings


def get_logger(name: str) -> logging.Logger:
    """Return a configured project logger without adding duplicate handlers."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        logger.propagate = False
    return logger
