"""Thin BigQuery client wrapper: load a DataFrame, query results, insert a row.

Deliberately does not contain anything about *what* is being loaded — no table
schemas, no status/control-table upsert logic. That kind of domain-specific
logic (e.g. "how do I mark a document as processed") belongs in the pipeline
that consumes this client, built on top of :attr:`BigQueryClient.client`.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

from iplanrio_agent_toolkit.logging import get_logger

logger = get_logger(__name__)


class BigQueryClient:
    """Thin wrapper around :class:`google.cloud.bigquery.Client` for common read/write tasks."""

    def __init__(
        self,
        credentials_path: Path | None = None,
        project_id: str | None = None,
        dataset_id: str | None = None,
    ) -> None:
        """Authenticate and resolve the target project/dataset.

        :param credentials_path: Path to a BigQuery service account JSON file, or
            ``None`` to use Application Default Credentials (ADC).
        :param project_id: GCP project ID; auto-detected from credentials when omitted.
        :param dataset_id: Default BigQuery dataset ID; falls back to the
            ``BIGQUERY_DATASET_ID`` env var.
        :raises ValueError: If no dataset ID is provided or found in the environment.
        """
        if credentials_path and Path(credentials_path).exists():
            credentials = service_account.Credentials.from_service_account_file(str(credentials_path))
            self.client = bigquery.Client(credentials=credentials, project=credentials.project_id)
            self.project_id = credentials.project_id
        else:
            self.client = bigquery.Client(project=project_id)
            self.project_id = project_id or self.client.project

        self.dataset_id = dataset_id or os.getenv("BIGQUERY_DATASET_ID")
        if not self.dataset_id:
            raise ValueError("dataset_id must be provided or BIGQUERY_DATASET_ID env var must be set")

        logger.info("Initialized BigQuery client - project=%s, dataset=%s", self.project_id, self.dataset_id)

    def table_ref(self, table_id: str) -> str:
        """Build a fully-qualified ``project.dataset.table`` reference.

        :param table_id: Bare table name within the client's default dataset.
        :returns: Fully-qualified table reference string.
        """
        return f"{self.project_id}.{self.dataset_id}.{table_id}"

    def write_dataframe(
        self,
        df: pd.DataFrame,
        table_id: str,
        write_mode: str = "WRITE_APPEND",
        add_timestamp_column: str | None = "processed_at",
    ) -> dict[str, Any]:
        """Load a DataFrame into a BigQuery table, auto-detecting its schema.

        :param df: DataFrame to load.
        :param table_id: Target table (bare name, resolved against the default dataset).
        :param write_mode: One of ``"WRITE_APPEND"``, ``"WRITE_TRUNCATE"``, ``"WRITE_EMPTY"``.
        :param add_timestamp_column: If given and not already present in ``df``,
            add a column with this name set to the current UTC timestamp before loading.
            Pass ``None`` to skip this behavior entirely.
        :returns: Dict with ``table``, ``rows_written``, ``bytes_processed``, ``job_id``.
        """
        if add_timestamp_column and add_timestamp_column not in df.columns:
            df = df.copy()
            df[add_timestamp_column] = datetime.now(timezone.utc)

        table_ref = self.table_ref(table_id)
        logger.info("Writing %d rows to %s", len(df), table_ref)

        job_config = bigquery.LoadJobConfig(
            write_disposition=write_mode,
            autodetect=True,
            create_disposition="CREATE_IF_NEEDED",
        )
        load_job = self.client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        load_job.result()

        logger.info("Loaded %d rows into %s", load_job.output_rows, table_ref)
        return {
            "table": table_ref,
            "rows_written": load_job.output_rows,
            "bytes_processed": load_job.total_bytes_processed,
            "job_id": load_job.job_id,
        }

    def query_dataframe(
        self,
        table_id: str,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Query a table with simple equality filters, returning a DataFrame.

        :param table_id: Source table (bare name, resolved against the default dataset).
        :param filters: Optional dict of ``{column: value}`` equality filters.
        :param limit: Maximum number of rows to return.
        :returns: Query result as a DataFrame.
        """
        table_ref = self.table_ref(table_id)
        query = f"SELECT * FROM `{table_ref}`"

        if filters:
            clauses = [
                f"{key} = '{value}'" if isinstance(value, str) else f"{key} = {value}" for key, value in filters.items()
            ]
            query += " WHERE " + " AND ".join(clauses)
        if limit:
            query += f" LIMIT {limit}"

        logger.info("Running query: %s", query)
        df = self.client.query(query).to_dataframe()
        logger.info("Retrieved %d rows", len(df))
        return df

    def insert_row(self, table_id: str, row: dict[str, Any]) -> None:
        """Stream-insert a single row into an existing table.

        :param table_id: Fully-qualified or bare target table id.
        :param row: Row values as a dict; datetime-like values are ISO-serialized automatically.
        """
        serialised = {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in row.items()}
        errors = self.client.insert_rows_json(table_id, [serialised])
        if errors:
            logger.warning("Failed to insert row into %s: %s", table_id, errors)
        else:
            logger.info("Row inserted into %s", table_id)

    def create_partitioned_table(
        self,
        table_id: str,
        schema: list[bigquery.SchemaField],
        partition_field: str,
        partition_type: str = "DAY",
        clustering_fields: list[str] | None = None,
    ) -> bigquery.Table:
        """Create a time-partitioned (and optionally clustered) table if it doesn't exist.

        :param table_id: Target table (bare name, resolved against the default dataset).
        :param schema: Explicit column schema for the new table.
        :param partition_field: Column to partition by; must be ``DATE``/``TIMESTAMP``.
        :param partition_type: Partition granularity (``DAY``, ``HOUR``, ``MONTH``, ``YEAR``).
        :param clustering_fields: Optional list of columns to cluster by.
        :returns: The created (or pre-existing) :class:`bigquery.Table`.
        """
        table_ref = self.table_ref(table_id)
        table = bigquery.Table(table_ref, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=getattr(bigquery.TimePartitioningType, partition_type),
            field=partition_field,
        )
        if clustering_fields:
            table.clustering_fields = clustering_fields

        table = self.client.create_table(table, exists_ok=True)
        logger.info("Table ready: %s (partitioned by %s/%s)", table_ref, partition_field, partition_type)
        return table
