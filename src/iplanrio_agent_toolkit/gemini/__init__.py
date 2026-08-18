"""Generic Gemini API client: authentication, rate-limited calls, response parsing."""

from __future__ import annotations

from iplanrio_agent_toolkit.gemini.auth import configure_genai
from iplanrio_agent_toolkit.gemini.client import (
    GeminiCallResult,
    GeminiClient,
    GenerationConfig,
    build_inline_part,
)
from iplanrio_agent_toolkit.gemini.pricing import TokenPricing, estimate_cost_usd
from iplanrio_agent_toolkit.gemini.response_parsing import parse_json_response

__all__ = [
    "GeminiCallResult",
    "GeminiClient",
    "GenerationConfig",
    "TokenPricing",
    "build_inline_part",
    "configure_genai",
    "estimate_cost_usd",
    "parse_json_response",
]
