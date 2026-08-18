from __future__ import annotations

import pytest

from iplanrio_agent_toolkit.matching.text_similarity import jaccard_length_similarity, levenshtein_distance


@pytest.mark.parametrize(
    ("s1", "s2", "expected"),
    [
        ("", "", 0),
        ("abc", "abc", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
    ],
)
def test_levenshtein_distance(s1: str, s2: str, expected: int) -> None:
    assert levenshtein_distance(s1, s2) == expected


def test_levenshtein_distance_is_symmetric() -> None:
    assert levenshtein_distance("abc", "xyz") == levenshtein_distance("xyz", "abc")


def test_jaccard_length_similarity_identical_strings_is_one() -> None:
    assert jaccard_length_similarity("hello", "hello") == 1.0


def test_jaccard_length_similarity_empty_string_is_zero() -> None:
    assert jaccard_length_similarity("", "hello") == 0.0
    assert jaccard_length_similarity("hello", "") == 0.0


def test_jaccard_length_similarity_is_case_insensitive() -> None:
    assert jaccard_length_similarity("HELLO", "hello") == 1.0


def test_jaccard_length_similarity_completely_different_strings() -> None:
    # Same-length strings with no shared characters still score 0.5 because the
    # length-ratio component is 1.0 — this is intrinsic to the metric.
    assert jaccard_length_similarity("abc", "xyz") == 0.5
