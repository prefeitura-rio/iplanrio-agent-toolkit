from __future__ import annotations

from pathlib import Path

from iplanrio_agent_toolkit.cache.sqlite_cache import SQLiteCache


def _cache(tmp_path: Path) -> SQLiteCache:
    return SQLiteCache(tmp_path / "cache.db")


def test_get_or_create_input_deduplicates_by_content(tmp_path: Path) -> None:
    cache = _cache(tmp_path)

    id1, is_new1, _, _ = cache.get_or_create_input("page_image", "doc_a", b"same-bytes", sub_key="1")
    id2, is_new2, cached_item, cached_sub = cache.get_or_create_input("page_image", "doc_b", b"same-bytes", sub_key="1")

    assert id1 == id2
    assert is_new1 is True
    assert is_new2 is False
    assert cached_item == "doc_a"
    assert cached_sub == "1"


def test_get_or_create_input_different_content_gets_different_ids(tmp_path: Path) -> None:
    cache = _cache(tmp_path)

    id1, _, _, _ = cache.get_or_create_input("page_image", "doc_a", b"bytes-one", sub_key="1")
    id2, _, _, _ = cache.get_or_create_input("page_image", "doc_a", b"bytes-two", sub_key="2")

    assert id1 != id2


def test_save_and_get_output(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    input_id, _, _, _ = cache.get_or_create_input("page_image", "doc_a", b"bytes", sub_key="1")

    cache.save_output(input_id, model_name="test-model", response_text='{"ok": true}')

    output = cache.get_output(input_id)
    assert output is not None
    assert output["model_name"] == "test-model"
    assert output["response_text"] == '{"ok": true}'
    assert output["cached"] is True


def test_get_output_returns_none_when_missing(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    assert cache.get_output(999) is None


def test_get_cached_output_by_reference(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    input_id, _, _, _ = cache.get_or_create_input("page_image", "doc_a", b"bytes", sub_key="1")
    cache.save_output(input_id, model_name="test-model", response_text='{"ok": true}')

    result = cache.get_cached_output_by_reference("doc_a", "1", "page_image")
    assert result is not None
    assert result["response_text"] == '{"ok": true}'


def test_get_cached_output_by_reference_missing(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    assert cache.get_cached_output_by_reference("doc_x", "1", "page_image") is None


def test_content_hash_override_bypasses_content_hashing(tmp_path: Path) -> None:
    cache = _cache(tmp_path)

    id1, is_new1, _, _ = cache.get_or_create_input(
        "extraction_result", "doc_a", b"placeholder", content_hash_override="custom-key-1"
    )
    id2, is_new2, _, _ = cache.get_or_create_input(
        "extraction_result", "doc_b", b"different-placeholder", content_hash_override="custom-key-1"
    )

    assert id1 == id2
    assert is_new2 is False


def test_get_statistics(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    input_id, _, _, _ = cache.get_or_create_input("page_image", "doc_a", b"bytes", sub_key="1")
    cache.save_output(input_id, model_name="test-model", response_text="{}")

    stats = cache.get_statistics()

    assert stats["total_inputs"] == 1
    assert stats["inputs_by_type"] == {"page_image": 1}
    assert stats["total_outputs"] == 1
    assert stats["cache_hit_rate"] == 1.0


def test_get_statistics_empty_cache_has_zero_hit_rate(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    stats = cache.get_statistics()
    assert stats["cache_hit_rate"] == 0.0


def test_context_manager_closes_connection(tmp_path: Path) -> None:
    with _cache(tmp_path) as cache:
        cache.get_or_create_input("page_image", "doc_a", b"bytes", sub_key="1")

    # Connection is closed; further use should raise.
    import sqlite3

    try:
        cache.conn.execute("SELECT 1")
        raised = False
    except sqlite3.ProgrammingError:
        raised = True
    assert raised
