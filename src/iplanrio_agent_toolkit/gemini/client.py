"""Thin, generic client around the Gemini Generative AI SDK.

Wraps authentication, rate limiting, API metrics tracking, and JSON response
parsing behind a single call. Contains no knowledge of any particular prompt,
document type, or business retry policy — callers own their own prompt text,
generation config, and retry strategy (e.g. "retry once if zero results
found" is a business decision, not something this client should hardcode).
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iplanrio_agent_toolkit.gemini.auth import configure_genai
from iplanrio_agent_toolkit.gemini.response_parsing import parse_json_response
from iplanrio_agent_toolkit.logging import get_logger
from iplanrio_agent_toolkit.metrics_tracker import get_tracker
from iplanrio_agent_toolkit.rate_limiter import get_rate_limiter

logger = get_logger(__name__)


@dataclass(frozen=True)
class GenerationConfig:
    """Gemini ``generate_content`` sampling parameters."""

    temperature: float = 0.1
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 8192

    def as_dict(self) -> dict[str, Any]:
        """Return the config as the plain dict expected by the Gemini SDK."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens,
        }


@dataclass
class GeminiCallResult:
    """Outcome of a single ``generate_content`` call."""

    success: bool
    text: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    error_message: str | None = None
    elapsed_seconds: float = 0.0

    def parse_json(self) -> Any:
        """Parse :attr:`text` as JSON, stripping Markdown code fences if present.

        :returns: The parsed JSON value.
        :raises ValueError: If the call failed or has no text to parse.
        :raises json.JSONDecodeError: If the text is not valid JSON.
        """
        if not self.success or self.text is None:
            raise ValueError(f"Cannot parse JSON from a failed call: {self.error_message}")
        return parse_json_response(self.text)


def build_inline_part(data: bytes, mime_type: str) -> dict[str, Any]:
    """Build a base64-encoded inline content part for a ``generate_content`` call.

    :param data: Raw bytes to embed (e.g. a PNG image or a PDF file).
    :param mime_type: MIME type of ``data`` (e.g. ``"image/png"``, ``"application/pdf"``).
    :returns: A dict in the shape expected by the Gemini SDK's content parts list.
    """
    return {"mime_type": mime_type, "data": base64.b64encode(data).decode("utf-8")}


class GeminiClient:
    """Authenticated Gemini client with integrated rate limiting and metrics."""

    def __init__(
        self,
        model_name: str,
        service_account_file: str | Path | None = None,
        api_key: str | None = None,
    ) -> None:
        """Configure a lazily-authenticated Gemini client.

        :param model_name: Name of the Gemini model to use (e.g. ``"gemini-2.0-flash"``).
        :param service_account_file: Path to a service account JSON file for authentication.
        :param api_key: Google API key, used if no service account is provided/valid.
        """
        self.model_name = model_name
        self._service_account_file = service_account_file
        self._api_key = api_key
        self._model: Any = None

    @property
    def model(self) -> Any:
        """Lazily authenticate and construct the underlying ``GenerativeModel``."""
        if self._model is None:
            genai = configure_genai(self._service_account_file, self._api_key)
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

    def generate_content(
        self,
        parts: list[Any],
        generation_config: GenerationConfig | None = None,
        metrics_label: str = "gemini",
    ) -> GeminiCallResult:
        """Call ``generate_content``, guarded by the global rate limiter.

        :param parts: Content parts to send (prompt strings, inline parts from
            :func:`build_inline_part`, or PIL images).
        :param generation_config: Sampling parameters; defaults to :class:`GenerationConfig` defaults.
        :param metrics_label: Label used when recording this call in the global
            :class:`~iplanrio_agent_toolkit.metrics_tracker.APIMetricsTracker`
            (e.g. ``"classification"`` vs ``"extraction"``).
        :returns: A :class:`GeminiCallResult` describing the outcome.
        """
        generation_config = generation_config or GenerationConfig()
        tracker = get_tracker()
        rate_limiter = get_rate_limiter()

        start_time = time.time()
        rate_limiter.acquire()
        try:
            response = self.model.generate_content(parts, generation_config=generation_config.as_dict())
            duration_ms = (time.time() - start_time) * 1000

            tracker.record_call(api_type=metrics_label, duration_ms=duration_ms, success=True)

            usage = response.usage_metadata
            return GeminiCallResult(
                success=True,
                text=response.text,
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                total_tokens=getattr(usage, "total_token_count", 0) or 0,
                elapsed_seconds=duration_ms / 1000,
            )
        except Exception as exc:  # reported in the result, not raised
            duration_ms = (time.time() - start_time) * 1000
            tracker.record_call(api_type=metrics_label, duration_ms=duration_ms, success=False, error_type=str(exc))
            logger.warning("Gemini call failed: %s", exc)
            return GeminiCallResult(success=False, error_message=str(exc), elapsed_seconds=duration_ms / 1000)
        finally:
            rate_limiter.release()
