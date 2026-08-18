"""Generic string similarity/distance functions, with no domain vocabulary attached."""

from __future__ import annotations


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    The minimum number of single-character insertions, deletions or
    substitutions required to turn ``s1`` into ``s2``.

    :param s1: First string.
    :param s2: Second string.
    :returns: The edit distance between ``s1`` and ``s2``.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def jaccard_length_similarity(s1: str, s2: str) -> float:
    """Score two strings by combining character-set Jaccard similarity and length ratio.

    A cheap, order-insensitive similarity heuristic — useful for fuzzy-matching
    short, typo-prone labels (not full-text/semantic similarity).

    :param s1: First string.
    :param s2: Second string.
    :returns: A score between 0.0 (completely dissimilar) and 1.0 (identical character sets and length).
    """
    if not s1 or not s2:
        return 0.0

    s1_set = set(s1.lower())
    s2_set = set(s2.lower())

    union = len(s1_set | s2_set)
    if union == 0:
        return 0.0

    jaccard = len(s1_set & s2_set) / union
    len_ratio = min(len(s1), len(s2)) / max(len(s1), len(s2))

    return (jaccard + len_ratio) / 2
