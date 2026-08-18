"""Read CSV files directly from a Google Cloud Storage bucket, with SQL-like filters."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import storage
from google.oauth2 import service_account

from iplanrio_agent_toolkit.logging import get_logger

logger = get_logger(__name__)

_FILTER_SUFFIX_OPERATORS: dict[str, str] = {
    "_gte": "ge",
    "_lte": "le",
    "_gt": "gt",
    "_lt": "lt",
    "_in": "in",
    "_not": "ne",
}


class GCSCSVReader:
    """Reads CSV files from a Google Cloud Storage bucket into pandas DataFrames."""

    def __init__(self, credentials_path: Path | None = None, bucket_name: str | None = None) -> None:
        """Initialize the reader and resolve the target bucket.

        :param credentials_path: Path to a GCS service account JSON file, or
            ``None`` to use Application Default Credentials (ADC).
        :param bucket_name: GCS bucket name; falls back to the ``GCS_BUCKET`` env var.
        :raises ValueError: If no bucket name is provided or found in the environment.
        """
        bucket_name = bucket_name or os.getenv("GCS_BUCKET")
        if not bucket_name:
            raise ValueError("bucket_name must be provided or GCS_BUCKET env var must be set")
        self.bucket_name = bucket_name

        if credentials_path and Path(credentials_path).exists():
            credentials = service_account.Credentials.from_service_account_file(str(credentials_path))
            self.client = storage.Client(credentials=credentials, project=credentials.project_id)
        else:
            self.client = storage.Client()

        self.bucket = self.client.bucket(bucket_name)

    def read_csv(
        self,
        gcs_path: str,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        **pandas_kwargs: Any,
    ) -> pd.DataFrame:
        """Download a CSV from GCS into memory and load it as a DataFrame.

        :param gcs_path: Path to the CSV within the bucket (e.g. ``"data/database.csv"``).
        :param filters: Optional dict of column filters. Supported key suffixes:
            ``_gte``, ``_lte``, ``_gt``, ``_lt``, ``_in``, ``_not``; no suffix means
            exact match. Example: ``{"data_envio_gte": "2024-01-01", "status": "ok"}``.
        :param limit: Maximum number of rows to return, applied after filtering.
        :param pandas_kwargs: Extra keyword arguments forwarded to :func:`pandas.read_csv`.
        :returns: The (optionally filtered/limited) DataFrame.
        """
        logger.info("Reading CSV from gs://%s/%s", self.bucket_name, gcs_path)

        content = self.bucket.blob(gcs_path).download_as_bytes()
        df = pd.read_csv(io.BytesIO(content), **pandas_kwargs)
        logger.info("Loaded %d rows from CSV", len(df))

        if filters:
            df = self._apply_filters(df, filters)
            logger.info("After filtering: %d rows", len(df))

        if limit and len(df) > limit:
            df = df.head(limit)
            logger.info("Limited to %d rows", limit)

        return df

    @staticmethod
    def _apply_filters(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        """Apply SQL-like filters to a DataFrame based on suffixed column names.

        :param df: Input DataFrame.
        :param filters: Dict of ``{column[_operator]: value}``.
        :returns: Filtered copy of the DataFrame.
        """
        filtered = df.copy()

        for filter_key, filter_value in filters.items():
            column = filter_key
            operator = "eq"
            for suffix, op in _FILTER_SUFFIX_OPERATORS.items():
                if filter_key.endswith(suffix):
                    column = filter_key[: -len(suffix)]
                    operator = op
                    break

            if column not in filtered.columns:
                continue

            if operator == "ge":
                filtered = filtered[filtered[column] >= filter_value]
            elif operator == "le":
                filtered = filtered[filtered[column] <= filter_value]
            elif operator == "gt":
                filtered = filtered[filtered[column] > filter_value]
            elif operator == "lt":
                filtered = filtered[filtered[column] < filter_value]
            elif operator == "in":
                filtered = filtered[filtered[column].isin(filter_value)]
            elif operator == "ne":
                filtered = filtered[filtered[column] != filter_value]
            else:
                filtered = filtered[filtered[column] == filter_value]

        return filtered

    def list_csvs(self, prefix: str = "") -> list[str]:
        """List all ``.csv`` blobs under a prefix.

        :param prefix: Prefix to filter blobs by (e.g. ``"data/"``).
        :returns: List of matching blob paths.
        """
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        return [blob.name for blob in blobs if blob.name.endswith(".csv")]
