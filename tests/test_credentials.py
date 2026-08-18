from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

from iplanrio_agent_toolkit.credentials import inject_credentials_from_env


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MY_TEST_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)


def test_returns_false_when_env_var_missing() -> None:
    assert inject_credentials_from_env("MY_TEST_CREDENTIALS") is False


def test_decodes_and_writes_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b'{"type": "service_account"}'
    monkeypatch.setenv("MY_TEST_CREDENTIALS", base64.b64encode(payload).decode())

    target = tmp_path / "creds.json"
    result = inject_credentials_from_env("MY_TEST_CREDENTIALS", credentials_path=target)

    assert result is True
    assert target.read_bytes() == payload
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(target)


def test_raises_on_invalid_base64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TEST_CREDENTIALS", "not-valid-base64!!!")

    with pytest.raises(ValueError, match="Failed to decode credentials"):
        inject_credentials_from_env("MY_TEST_CREDENTIALS", credentials_path=tmp_path / "creds.json")
