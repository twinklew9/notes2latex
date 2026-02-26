"""Centralized logger factory."""

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name."""
    return logging.getLogger(name)
