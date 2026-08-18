"""Heuristics for recognizing common transient API error messages."""

from __future__ import annotations

_RATE_LIMIT_MARKERS = ("429", "resource exhausted", "quota exceeded")


def is_rate_limit_error(text: str | None) -> bool:
    """Return whether ``text`` looks like a rate-limit / quota-exceeded error message.

    This is a plain string-matching heuristic against common phrasing used by
    Google APIs (Gemini, BigQuery, etc.) for HTTP 429 responses. It knows
    nothing about where the text came from — callers are responsible for
    extracting the relevant error message from their own domain-specific data
    structures before calling this function.

    :param text: Error message (or any free text) to inspect, or ``None``.
    :returns: ``True`` if any known rate-limit marker is found (case-insensitive).
    """
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)
