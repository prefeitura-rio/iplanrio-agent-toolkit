"""Logging helper for this package.

This package never uses ``print()`` — all diagnostic output goes through the
standard ``logging`` module so that consumers (Prefect flows, scripts,
notebooks) can control formatting, level and destination themselves.
"""

from __future__ import annotations

import logging
from logging import Logger


def get_logger(name: str) -> Logger:
    """Return a logger for the given module name.

    :param name: Usually ``__name__`` of the calling module.
    :returns: A standard library :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
