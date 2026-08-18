"""Parse JSON out of a raw Gemini text response.

Gemini frequently wraps JSON answers in Markdown code fences (```` ```json ... ``` ````)
even when explicitly asked for raw JSON. This single implementation replaces
what used to be three near-identical copies across the original codebase.
"""

from __future__ import annotations

import json
from typing import Any


def parse_json_response(response_text: str) -> Any:
    """Strip Markdown code fences (if present) and parse the remaining text as JSON.

    Gemini frequently wraps JSON answers in Markdown code fences
    (`` ```json ... ``` ``) even when explicitly asked for raw JSON, and may
    prefix the block with natural-language text (e.g. ``"Here is the result:"``).
    This single implementation replaces what used to be three near-identical
    copies across the original codebase.

    :param response_text: Raw text returned by the model.
    :returns: The parsed JSON value (usually a dict).
    :raises json.JSONDecodeError: If the cleaned text is not valid JSON.
    """
    text = response_text.strip()

    first_fence = text.find("```")
    if first_fence != -1:
        text = text[first_fence:]
        if text.startswith("```json"):
            text = text[len("```json") :]
        elif text.startswith("```"):
            text = text[len("```") :]
        if text.endswith("```"):
            text = text[: -len("```")]

    return json.loads(text.strip())
