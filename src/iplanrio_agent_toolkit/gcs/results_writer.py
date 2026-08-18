"""Write pipeline results to GCS with Hive-style date partitioning.

Two output formats are supported:

- CSV: ``{base_path}/{partition_column}=YYYY-MM-DD/{filename_prefix}_YYYYMMDD_HHMMSS.csv``
- NDJSON: same layout with a ``.ndjson`` extension. Newline-delimited JSON
  preserves nested fields (lists, dicts) without flattening, and can be loaded
  directly into BigQuery with
  ``LoadJobConfig(source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON, autodetect=True)``.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import storage
from google.oauth2 import service_account

from iplanrio_agent_toolkit.logging import get_logger

logger = get_logger(__name__)


class GCSResultsWriter:
    """Writes result DataFrames/records to GCS, partitioned by date."""

    def __init__(self, bucket_name: str, credentials_path: Path | None = None) -> None:
        """Resolve the target bucket for subsequent writes.

        :param bucket_name: Name of the destination GCS bucket.
        :param credentials_path: Path to a GCS service account JSON file, or
            ``None`` to use Application Default Credentials (ADC).
        """
        if credentials_path and Path(credentials_path).exists():
            credentials = service_account.Credentials.from_service_account_file(str(credentials_path))
            client = storage.Client(credentials=credentials)
        else:
            client = storage.Client()

        self.bucket = client.bucket(bucket_name)
        self.bucket_name = bucket_name

    def write_csv(
        self,
        df: pd.DataFrame,
        base_path: str,
        filename_prefix: str,
        timestamp: datetime | None = None,
        partition_column: str = "data_geracao",
    ) -> str:
        """Write a DataFrame to GCS as a Hive-partitioned CSV.

        :param df: DataFrame to write.
        :param base_path: GCS path prefix (e.g. ``"results/my-pipeline/output"``).
        :param filename_prefix: Prefix for the generated filename.
        :param timestamp: Partition timestamp; defaults to UTC now.
        :param partition_column: Name of the Hive partition column (e.g. ``"data_geracao"``).
        :returns: Full ``gs://bucket/path`` URI of the written file.
        """
        timestamp = timestamp or datetime.now(timezone.utc)
        blob_path = self._partitioned_blob_path(base_path, filename_prefix, "csv", timestamp, partition_column)

        logger.info("Writing %d rows to gs://%s/%s", len(df), self.bucket_name, blob_path)

        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        self.bucket.blob(blob_path).upload_from_string(csv_buffer.getvalue(), content_type="text/csv")

        full_path = f"gs://{self.bucket_name}/{blob_path}"
        logger.info("Written to %s", full_path)
        return full_path

    def write_ndjson(
        self,
        items: list[dict[str, Any]],
        base_path: str,
        filename_prefix: str,
        timestamp: datetime | None = None,
        partition_column: str = "data_geracao",
    ) -> str:
        """Write a list of records to GCS as Hive-partitioned newline-delimited JSON.

        :param items: List of JSON-serializable records, one per line in the output.
        :param base_path: GCS path prefix (e.g. ``"results/my-pipeline/output"``).
        :param filename_prefix: Prefix for the generated filename.
        :param timestamp: Partition timestamp; defaults to UTC now.
        :param partition_column: Name of the Hive partition column (e.g. ``"data_geracao"``).
        :returns: Full ``gs://bucket/path`` URI of the written file.
        """
        timestamp = timestamp or datetime.now(timezone.utc)
        blob_path = self._partitioned_blob_path(base_path, filename_prefix, "ndjson", timestamp, partition_column)

        logger.info("Writing %d records to gs://%s/%s", len(items), self.bucket_name, blob_path)

        ndjson_content = "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in items)
        self.bucket.blob(blob_path).upload_from_string(
            ndjson_content.encode("utf-8"), content_type="application/x-ndjson"
        )

        full_path = f"gs://{self.bucket_name}/{blob_path}"
        logger.info("Written to %s", full_path)
        return full_path

    @staticmethod
    def _partitioned_blob_path(
        base_path: str,
        filename_prefix: str,
        extension: str,
        timestamp: datetime,
        partition_column: str,
    ) -> str:
        date_str = timestamp.strftime("%Y-%m-%d")
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"{base_path}/{partition_column}={date_str}/{filename_prefix}_{ts_str}.{extension}"
