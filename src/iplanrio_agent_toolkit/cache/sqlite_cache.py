"""SQLite-backed two-tier cache for expensive, content-addressable API calls.

Designed for pipelines that repeatedly send the same (or byte-identical)
inputs to a costly API (e.g. an LLM) and want to avoid paying for it twice.

Schema (three tables):

- ``api_inputs``: unique preprocessed inputs, deduplicated by SHA-256 content hash.
- ``item_references``: maps an arbitrary ``(item_key, sub_key, input_type)``
  tuple (e.g. a PDF name + page number) to the content hash that represents it,
  so multiple items with identical content share one ``api_inputs`` row.
- ``api_outputs``: API responses, linked to ``api_inputs`` by foreign key.

There is nothing document- or LLM-specific baked into the schema: ``item_key``,
``sub_key`` and ``input_type`` are opaque strings chosen by the caller.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import time
from pathlib import Path
from typing import Any

_MAX_RETRIES = 10
_BASE_RETRY_DELAY_SECONDS = 0.1


class SQLiteCache:
    """Manages a SQLite database used as a two-tier, content-addressable cache."""

    def __init__(self, db_path: Path) -> None:
        """Open (creating if needed) the cache database and ensure its schema exists.

        :param db_path: Path to the SQLite database file. Parent directories are created.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: callers that need thread safety should use
        # one SQLiteCache instance per thread, since sqlite3 connections are
        # not safe to share across threads even with this flag.
        self.conn = sqlite3.connect(str(self.db_path), timeout=120.0, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=120000")
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_type TEXT NOT NULL,
                item_key TEXT NOT NULL,
                sub_key TEXT,
                content_hash TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_inputs_lookup
            ON api_inputs(item_key, sub_key, input_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_inputs_hash
            ON api_inputs(content_hash)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL,
                sub_key TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                input_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (item_key, sub_key, input_type),
                FOREIGN KEY (content_hash) REFERENCES api_inputs(content_hash)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_refs_lookup
            ON item_references(item_key, sub_key, input_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_refs_hash
            ON item_references(content_hash)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                response_text TEXT NOT NULL,
                usage_metadata TEXT,
                elapsed_seconds REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (input_id) REFERENCES api_inputs(id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_outputs_input
            ON api_outputs(input_id)
        """)

        self.conn.commit()

    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        """Compute the SHA-256 hash of ``content``, used as the deduplication key.

        :param content: Binary content to hash.
        :returns: Hexadecimal digest string.
        """
        return hashlib.sha256(content).hexdigest()

    def get_or_create_input(  # noqa: PLR0913, PLR0917 - public cache API
        self,
        input_type: str,
        item_key: str,
        content: bytes,
        sub_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        content_hash_override: str | None = None,
    ) -> tuple[int, bool, str | None, str | None]:
        """Get the existing cached input matching this content, or create a new one.

        Implements a two-tier strategy: ``api_inputs`` stores each unique
        content blob's hash once; ``item_references`` maps
        ``(item_key, sub_key, input_type)`` to that hash. This means two
        different items with byte-identical content share one cache entry.

        :param input_type: Caller-defined category of input (e.g. ``"page_image"``).
        :param item_key: Identifier of the parent item (e.g. a file name).
        :param content: Preprocessed input content to hash and deduplicate on.
        :param sub_key: Identifier of the sub-item within ``item_key`` (e.g. a page number),
            or ``None`` if the input has no sub-items.
        :param metadata: Arbitrary JSON-serializable metadata to store alongside the input.
        :param content_hash_override: Use this hash instead of hashing ``content``.
            Useful when the cache key is conceptually derived from something other
            than raw bytes (e.g. a composite key), and ``content`` is just a placeholder.
        :returns: A tuple ``(input_id, is_new_blob, cached_item_key, cached_sub_key)``:
            ``input_id`` is the ``api_inputs`` row id; ``is_new_blob`` is ``True`` when
            this content hash was not seen before; ``cached_item_key``/``cached_sub_key``
            identify which other item first cached this exact content, or ``(None, None)``
            if this is the first (or only) reference.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                return self._get_or_create_input_impl(
                    input_type, item_key, content, sub_key, metadata, content_hash_override
                )
            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc) and attempt < _MAX_RETRIES - 1:
                    delay = _BASE_RETRY_DELAY_SECONDS * (2**attempt) + random.uniform(0, 0.1)
                    time.sleep(delay)
                    continue
                raise
        raise AssertionError("unreachable")  # loop always returns or raises

    def _get_or_create_input_impl(  # noqa: PLR0913, PLR0917 - mirrors public API
        self,
        input_type: str,
        item_key: str,
        content: bytes,
        sub_key: str | None,
        metadata: dict[str, Any] | None,
        content_hash_override: str | None,
    ) -> tuple[int, bool, str | None, str | None]:
        content_hash = content_hash_override or self.compute_content_hash(content)
        cursor = self.conn.cursor()

        cursor.execute("SELECT id FROM api_inputs WHERE content_hash = ?", (content_hash,))
        row = cursor.fetchone()

        if row:
            input_id = row["id"]
            is_new_blob = False
        else:
            metadata_json = json.dumps(metadata) if metadata else None
            try:
                cursor.execute(
                    """
                    INSERT INTO api_inputs (input_type, item_key, sub_key, content_hash, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (input_type, item_key, sub_key, content_hash, metadata_json),
                )
                input_id = cursor.lastrowid
                is_new_blob = True
            except sqlite3.IntegrityError:
                # Race: another thread inserted the same hash between our SELECT and INSERT.
                cursor.execute("SELECT id FROM api_inputs WHERE content_hash = ?", (content_hash,))
                row = cursor.fetchone()
                input_id = row["id"]
                is_new_blob = False

        cached_item_key: str | None = None
        cached_sub_key: str | None = None

        if sub_key is not None:
            cursor.execute(
                "SELECT id FROM item_references WHERE item_key = ? AND sub_key = ? AND input_type = ?",
                (item_key, sub_key, input_type),
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO item_references (item_key, sub_key, content_hash, input_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item_key, sub_key, content_hash, input_type),
                )

            cursor.execute(
                """
                SELECT item_key, sub_key FROM item_references
                WHERE content_hash = ? AND NOT (item_key = ? AND sub_key = ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (content_hash, item_key, sub_key),
            )
            cached_source = cursor.fetchone()
            if cached_source:
                cached_item_key = cached_source["item_key"]
                cached_sub_key = cached_source["sub_key"]

        self.conn.commit()
        return (input_id, is_new_blob, cached_item_key, cached_sub_key)

    def get_output(self, input_id: int) -> dict[str, Any] | None:
        """Get the most recent cached output for a given input.

        :param input_id: ``api_inputs`` row id.
        :returns: Dict with ``model_name``, ``response_text``, ``usage_metadata``,
            ``elapsed_seconds``, ``created_at``, ``cached=True``; or ``None`` if not found.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT model_name, response_text, usage_metadata, elapsed_seconds, created_at
            FROM api_outputs
            WHERE input_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (input_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "model_name": row["model_name"],
            "response_text": row["response_text"],
            "usage_metadata": json.loads(row["usage_metadata"]) if row["usage_metadata"] else None,
            "elapsed_seconds": row["elapsed_seconds"],
            "created_at": row["created_at"],
            "cached": True,
        }

    def get_cached_output_by_reference(self, item_key: str, sub_key: str, input_type: str) -> dict[str, Any] | None:
        """Look up a cached API response directly by ``(item_key, sub_key, input_type)``.

        Faster than :meth:`get_output` when the caller doesn't already have an
        ``input_id`` (e.g. on a fresh run before recomputing the content bytes),
        since it avoids needing to hash the content to find the cache entry.

        :param item_key: Identifier of the parent item (e.g. a file name).
        :param sub_key: Identifier of the sub-item (e.g. a page number).
        :param input_type: Category of input this reference was stored under.
        :returns: Dict with ``response_text``, ``usage_metadata``, ``cached_item_key``,
            ``cached_sub_key``; or ``None`` if no cached output exists yet.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT o.response_text, o.usage_metadata, ir.item_key AS cached_item_key,
                   ir.sub_key AS cached_sub_key
            FROM item_references ir
            JOIN api_inputs i ON ir.content_hash = i.content_hash
            JOIN api_outputs o ON i.id = o.input_id
            WHERE ir.item_key = ? AND ir.sub_key = ? AND ir.input_type = ?
            LIMIT 1
            """,
            (item_key, sub_key, input_type),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "response_text": row["response_text"],
            "usage_metadata": json.loads(row["usage_metadata"]) if row["usage_metadata"] else None,
            "cached_item_key": row["cached_item_key"],
            "cached_sub_key": row["cached_sub_key"],
        }

    def save_output(
        self,
        input_id: int,
        model_name: str,
        response_text: str,
        usage_metadata: dict[str, Any] | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        """Persist an API response linked to a previously created input.

        :param input_id: ``api_inputs`` row id returned by :meth:`get_or_create_input`.
        :param model_name: Name/identifier of the model or API that produced the response.
        :param response_text: Raw response payload (typically JSON) as text.
        :param usage_metadata: Arbitrary JSON-serializable usage/cost metadata.
        :param elapsed_seconds: Wall-clock duration of the API call.
        """
        cursor = self.conn.cursor()
        usage_json = json.dumps(usage_metadata) if usage_metadata else None
        cursor.execute(
            """
            INSERT INTO api_outputs (input_id, model_name, response_text, usage_metadata, elapsed_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (input_id, model_name, response_text, usage_json, elapsed_seconds),
        )
        self.conn.commit()

    def get_statistics(self) -> dict[str, Any]:
        """Return cache statistics.

        :returns: Dict with ``total_inputs`` (int), ``inputs_by_type`` (dict[str, int]),
            ``total_outputs`` (int), and ``cache_hit_rate`` (float, 0.0-1.0 — the ratio
            of outputs to inputs, since every cached input eventually gets exactly one
            output on a fully-processed run).
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT input_type, COUNT(*) as count FROM api_inputs GROUP BY input_type")
        inputs_by_type = {row["input_type"]: row["count"] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) as count FROM api_outputs")
        total_outputs = cursor.fetchone()["count"]

        total_inputs = sum(inputs_by_type.values())
        return {
            "total_inputs": total_inputs,
            "inputs_by_type": inputs_by_type,
            "total_outputs": total_outputs,
            "cache_hit_rate": total_outputs / total_inputs if total_inputs > 0 else 0.0,
        }

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> SQLiteCache:
        """Support use as a context manager."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Close the connection on context manager exit."""
        self.close()
