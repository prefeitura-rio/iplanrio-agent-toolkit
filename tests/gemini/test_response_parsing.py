from __future__ import annotations

import json

import pytest

from iplanrio_agent_toolkit.gemini.response_parsing import parse_json_response


def test_parses_plain_json() -> None:
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parses_json_wrapped_in_json_code_fence() -> None:
    raw = '```json\n{"a": 1}\n```'
    assert parse_json_response(raw) == {"a": 1}


def test_parses_json_wrapped_in_generic_code_fence() -> None:
    raw = '```\n{"a": 1}\n```'
    assert parse_json_response(raw) == {"a": 1}


def test_parses_json_with_surrounding_text() -> None:
    raw = 'Here is the result:\n```json\n{"a": 1}\n```'
    assert parse_json_response(raw) == {"a": 1}


def test_parses_json_arrays() -> None:
    assert parse_json_response("[1, 2, 3]") == [1, 2, 3]


def test_raises_on_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_response("this is not json")
