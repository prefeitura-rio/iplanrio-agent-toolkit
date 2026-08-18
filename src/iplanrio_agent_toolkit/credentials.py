"""Inject GCP service account credentials from a base64-encoded environment variable.

Usage (encode credentials for Infisical or any secret manager)::

    cat service-account.json | base64

Store the output as a secret (e.g. ``GCP_CREDENTIALS_BASE64``). At runtime,
call :func:`inject_credentials_from_env` once at startup — all GCP SDKs
(GCS, Vertex AI/Gemini, BigQuery) then pick up credentials automatically via
Application Default Credentials (ADC).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from iplanrio_agent_toolkit.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CREDENTIALS_PATH = Path("/tmp/iplanrio_agent_toolkit_credentials.json")


def inject_credentials_from_env(
    env_var: str = "GCP_CREDENTIALS_BASE64",
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
) -> bool:
    """Decode a base64-encoded service account from an env var and inject it as ADC.

    Writes the decoded JSON to ``credentials_path`` and sets
    ``GOOGLE_APPLICATION_CREDENTIALS`` so all GCP SDKs pick it up automatically.

    :param env_var: Name of the environment variable holding the base64 payload.
    :param credentials_path: Local path to write the decoded service account JSON to.
    :returns: ``True`` if credentials were injected, ``False`` if the env var is not set.
    :raises ValueError: If the env var is set but contains invalid base64.
    """
    value = os.getenv(env_var)
    if not value:
        return False

    try:
        decoded = base64.b64decode(value)
    except Exception as exc:
        raise ValueError(
            f"Failed to decode credentials from env var '{env_var}'. "
            f"Make sure the value is a valid base64-encoded service account JSON.\n"
            f"To encode: cat service-account.json | base64\n"
            f"Error: {exc}"
        ) from exc

    credentials_path.write_bytes(decoded)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)
    logger.info("Credentials injected from %s -> %s", env_var, credentials_path)
    return True
