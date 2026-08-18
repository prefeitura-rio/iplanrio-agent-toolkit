"""Token-based cost estimation for Gemini API calls.

Pricing changes over time and varies per model; callers should pass the
current per-million-token rates for whichever model they're using rather than
relying on a hardcoded default.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPricing:
    """Price per 1,000,000 tokens, in USD."""

    input_per_million: float
    output_per_million: float


def estimate_cost_usd(input_tokens: int, output_tokens: int, pricing: TokenPricing) -> float:
    """Estimate the USD cost of an API call from its token counts.

    :param input_tokens: Number of input (prompt) tokens.
    :param output_tokens: Number of output (completion) tokens.
    :param pricing: Per-million-token rates to apply.
    :returns: Estimated cost in USD.
    """
    input_cost = (input_tokens / 1_000_000) * pricing.input_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_per_million
    return input_cost + output_cost
