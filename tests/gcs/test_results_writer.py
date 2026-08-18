from __future__ import annotations

from datetime import datetime

from iplanrio_agent_toolkit.gcs.results_writer import GCSResultsWriter


class FakeUploadingBlob:
    def __init__(self) -> None:
        self.uploaded: str | bytes | None = None
        self.content_type: str | None = None

    def upload_from_string(self, data: str | bytes, content_type: str | None = None) -> None:
        self.uploaded = data
        self.content_type = content_type


class FakeUploadingBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeUploadingBlob] = {}

    def blob(self, name: str) -> FakeUploadingBlob:
        blob = FakeUploadingBlob()
        self.blobs[name] = blob
        return blob


def _writer(bucket: FakeUploadingBucket) -> GCSResultsWriter:
    w = GCSResultsWriter(bucket_name="fake-bucket")
    w.bucket = bucket
    return w


def test_partitioned_blob_path_uses_utc_timestamp() -> None:
    ts = datetime(2024, 5, 3, 10, 15, 30)

    path = GCSResultsWriter._partitioned_blob_path("base", "results", "csv", ts, "data_geracao")

    assert path == "base/data_geracao=2024-05-03/results_20240503_101530.csv"


def test_write_csv_builds_partitioned_path_and_returns_uri() -> None:
    import pandas as pd

    bucket = FakeUploadingBucket()
    writer = _writer(bucket)
    ts = datetime(2024, 5, 3, 10, 15, 30)

    uri = writer.write_csv(pd.DataFrame({"a": [1, 2]}), "results/out", "batch", timestamp=ts)

    assert uri == "gs://fake-bucket/results/out/data_geracao=2024-05-03/batch_20240503_101530.csv"
    blob_path = "results/out/data_geracao=2024-05-03/batch_20240503_101530.csv"
    assert bucket.blobs[blob_path].content_type == "text/csv"


def test_write_ndjson_writes_one_record_per_line() -> None:
    bucket = FakeUploadingBucket()
    writer = _writer(bucket)
    ts = datetime(2024, 5, 3, 10, 15, 30)

    uri = writer.write_ndjson([{"a": 1, "b": {"nested": [1, 2]}}, {"a": 2}], "results/out", "batch", timestamp=ts)

    assert uri.startswith("gs://fake-bucket/results/out/data_geracao=2024-05-03/")
    blob_path = "results/out/data_geracao=2024-05-03/batch_20240503_101530.ndjson"
    uploaded = bucket.blobs[blob_path].uploaded
    assert isinstance(uploaded, bytes)
    lines = uploaded.decode("utf-8").split("\n")
    assert lines[0] == '{"a": 1, "b": {"nested": [1, 2]}}'
    assert lines[1] == '{"a": 2}'


def test_write_ndjson_serializes_non_json_safe_values() -> None:
    bucket = FakeUploadingBucket()
    writer = _writer(bucket)
    ts = datetime(2024, 5, 3, 10, 15, 30)

    writer.write_ndjson([{"ts": datetime(2024, 1, 1)}], "results/out", "batch", timestamp=ts)

    blob_path = "results/out/data_geracao=2024-05-03/batch_20240503_101530.ndjson"
    uploaded = bucket.blobs[blob_path].uploaded
    assert isinstance(uploaded, bytes)
    assert '"ts": "2024-01-01 00:00:00"' in uploaded.decode("utf-8")
