"""Cascading authentication for the Google Generative AI (Gemini) SDK.

Tries, in order: an explicit service account file, an API key, then
Application Default Credentials (ADC) — which covers Infisical-injected
credentials, GCP VM/pod service accounts, and
``gcloud auth application-default login``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from iplanrio_agent_toolkit.logging import get_logger

if TYPE_CHECKING:
    import google.generativeai as genai

logger = get_logger(__name__)

GENERATIVE_LANGUAGE_SCOPE = "https://www.googleapis.com/auth/generative-language"


def configure_genai(
    service_account_file: str | Path | None = None,
    api_key: str | None = None,
) -> "genai":
    """Configure and return the ``google.generativeai`` module with resolved credentials.

    :param service_account_file: Path to a service account JSON file. Falls back
        to the ``GOOGLE_SERVICE_ACCOUNT_FILE`` env var when omitted.
    :param api_key: Google API key. Falls back to the ``GOOGLE_API_KEY`` or
        ``GEMINI_API_KEY`` env vars when omitted.
    :returns: The configured ``google.generativeai`` module, ready to use.
    :raises ValueError: If no credentials could be resolved by any method.
    """
    import google.generativeai as genai  # noqa: PLC0415 - optional heavy dep

    service_account_path = service_account_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if service_account_path and Path(service_account_path).exists():
        try:
            from google.oauth2 import service_account  # noqa: PLC0415 - lazy auth import

            credentials = service_account.Credentials.from_service_account_file(
                str(service_account_path),
                scopes=[GENERATIVE_LANGUAGE_SCOPE],
            )
            genai.configure(credentials=credentials)
            return genai
        except Exception as exc:  # fall through to next auth method
            logger.warning(
                "Failed to load service account from %s: %s. Falling back to other authentication methods.",
                service_account_path,
                exc,
            )

    resolved_api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if resolved_api_key:
        genai.configure(api_key=resolved_api_key)
        return genai

    try:
        import google.auth  # noqa: PLC0415 - lazy auth import

        credentials, project = google.auth.default(scopes=[GENERATIVE_LANGUAGE_SCOPE])
        genai.configure(credentials=credentials)
        logger.info("Using Application Default Credentials (ADC)")
        if project:
            logger.info("GCP project: %s", project)
        return genai
    except Exception as adc_error:
        raise ValueError(
            "No Gemini credentials found. Provide one of:\n"
            "1. service_account_file parameter or GOOGLE_SERVICE_ACCOUNT_FILE env var\n"
            "2. api_key parameter or GOOGLE_API_KEY/GEMINI_API_KEY env var\n"
            "3. Application Default Credentials (run 'gcloud auth application-default login')\n"
            f"\nADC Error: {adc_error}"
        ) from adc_error
