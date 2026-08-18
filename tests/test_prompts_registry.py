from __future__ import annotations

from pathlib import Path

import pytest

from iplanrio_agent_toolkit.prompts.registry import PromptRegistry, compute_prompt_hash


def _make_versions(tmp_path: Path, kind: str, versions: dict[str, str]) -> Path:
    kind_dir = tmp_path / kind
    kind_dir.mkdir(parents=True)
    for version, content in versions.items():
        (kind_dir / f"{version}.txt").write_text(content, encoding="utf-8")
    return tmp_path


def test_list_versions_sorts_numerically_not_lexicographically(tmp_path: Path) -> None:
    # Regression test: the original implementation sorted "v*.txt" filenames as
    # plain strings, so "v10" would sort before "v2" ("v10" < "v2" lexicographically).
    root = _make_versions(
        tmp_path,
        "classification",
        {"v1": "one", "v2": "two", "v9": "nine", "v10": "ten"},
    )
    registry = PromptRegistry(root)

    assert registry.list_versions("classification") == ["v1", "v2", "v9", "v10"]


def test_latest_version_picks_the_highest_number(tmp_path: Path) -> None:
    root = _make_versions(tmp_path, "extraction", {"v1": "one", "v9": "nine", "v10": "ten"})
    registry = PromptRegistry(root)

    assert registry.latest_version("extraction") == "v10"


def test_latest_version_is_none_when_kind_missing(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path)
    assert registry.latest_version("nonexistent") is None


def test_load_defaults_to_latest_version(tmp_path: Path) -> None:
    root = _make_versions(tmp_path, "classification", {"v1": "old prompt", "v2": "new prompt"})
    registry = PromptRegistry(root)

    assert registry.load("classification") == "new prompt"


def test_load_specific_version(tmp_path: Path) -> None:
    root = _make_versions(tmp_path, "classification", {"v1": "old prompt", "v2": "new prompt"})
    registry = PromptRegistry(root)

    assert registry.load("classification", version="v1") == "old prompt"


def test_load_raises_when_no_versions_exist(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path)
    with pytest.raises(FileNotFoundError):
        registry.load("classification")


def test_load_raises_when_specific_version_missing(tmp_path: Path) -> None:
    root = _make_versions(tmp_path, "classification", {"v1": "old prompt"})
    registry = PromptRegistry(root)

    with pytest.raises(FileNotFoundError):
        registry.load("classification", version="v99")


def test_info_includes_hash_and_resolved_version(tmp_path: Path) -> None:
    root = _make_versions(tmp_path, "classification", {"v1": "hello world"})
    registry = PromptRegistry(root)

    info = registry.info("classification")

    assert info.content == "hello world"
    assert info.version == "v1"
    assert info.hash == compute_prompt_hash("hello world")


def test_detect_version_matches_by_content_hash(tmp_path: Path) -> None:
    root = _make_versions(tmp_path, "classification", {"v1": "hello", "v2": "world"})
    registry = PromptRegistry(root)

    assert registry.detect_version("classification", "hello") == "v1"
    assert registry.detect_version("classification", "world") == "v2"
    assert registry.detect_version("classification", "unknown text") == "unknown"


def test_compute_prompt_hash_is_deterministic_and_short() -> None:
    hash1 = compute_prompt_hash("some prompt text")
    hash2 = compute_prompt_hash("some prompt text")

    assert hash1 == hash2
    assert len(hash1) == 12
