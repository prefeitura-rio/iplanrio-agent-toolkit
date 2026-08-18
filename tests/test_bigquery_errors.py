from __future__ import annotations

import pytest

from iplanrio_agent_toolkit.bigquery.errors import is_rate_limit_error


@pytest.mark.parametrize(
    "text",
    [
        "429 Too Many Requests",
        "Error: RESOURCE EXHAUSTED",
        "quota exceeded for this project",
        "Some prefix text 429 some suffix",
    ],
)
def test_detects_known_rate_limit_markers(text: str) -> None:
    assert is_rate_limit_error(text) is True


@pytest.mark.parametrize("text", ["500 Internal Server Error", "connection timed out", ""])
def test_does_not_flag_unrelated_errors(text: str) -> None:
    assert is_rate_limit_error(text) is False


def test_none_is_not_a_rate_limit_error() -> None:
    assert is_rate_limit_error(None) is False
