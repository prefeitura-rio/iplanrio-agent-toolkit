from __future__ import annotations

from pathlib import Path

from iplanrio_agent_toolkit.gcs.downloader import GCSDownloader


class FakeBlob:
    def __init__(self, name: str, content: bytes = b"content") -> None:
        self.name = name
        self.content = content

    def exists(self) -> bool:
        return self.content is not None

    def download_to_filename(self, filename: str) -> None:
        Path(filename).write_bytes(self.content)


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: dict[str, FakeBlob] = {}

    def blob(self, name: str) -> FakeBlob:
        return self.blobs[name]

    def list_blobs(self, prefix: str = "") -> list[FakeBlob]:
        return [blob for blob in self.blobs.values() if blob.name.startswith(prefix)]


def _downloader(bucket: FakeBucket) -> GCSDownloader:
    d = GCSDownloader(credentials_path=None, bucket_name="fake-bucket")
    d._bucket = bucket
    return d


def test_download_file(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.blobs["pdfs/doc.pdf"] = FakeBlob("pdfs/doc.pdf", b"pdf-content")

    result = _downloader(bucket).download_file("pdfs/doc.pdf", tmp_path)

    assert result == tmp_path / "doc.pdf"
    assert result.read_bytes() == b"pdf-content"


def test_download_file_missing_blob_raises(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.blobs["pdfs/doc.pdf"] = FakeBlob("pdfs/doc.pdf", None)

    import pytest

    with pytest.raises(FileNotFoundError, match="Blob not found"):
        _downloader(bucket).download_file("pdfs/doc.pdf", tmp_path)


def test_download_file_by_name_uses_base_path(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.blobs["pdfs/doc.pdf"] = FakeBlob("pdfs/doc.pdf", b"pdf-content")

    result = _downloader(bucket).download_file_by_name("doc.pdf", tmp_path, base_path="pdfs")

    assert result == tmp_path / "doc.pdf"


def test_download_files_batch_skips_existing(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.blobs["a.pdf"] = FakeBlob("a.pdf", b"a")
    bucket.blobs["b.pdf"] = FakeBlob("b.pdf", b"b")

    existing = tmp_path / "a.pdf"
    existing.write_bytes(b"already-there")

    results = _downloader(bucket).download_files_batch(["a.pdf", "b.pdf"], tmp_path, base_path="", max_workers=2)

    assert set(results) == {"a.pdf", "b.pdf"}
    assert results["a.pdf"].read_bytes() == b"already-there"
    assert results["b.pdf"].read_bytes() == b"b"


def test_download_files_batch_omits_failures(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.blobs["a.pdf"] = FakeBlob("a.pdf", b"a")

    results = _downloader(bucket).download_files_batch(["a.pdf", "missing.pdf"], tmp_path)

    assert set(results) == {"a.pdf"}
    assert results["a.pdf"].read_bytes() == b"a"


def test_get_available_filenames_strips_prefix(tmp_path: Path) -> None:
    bucket = FakeBucket()
    bucket.blobs["pdfs/a.pdf"] = FakeBlob("pdfs/a.pdf")
    bucket.blobs["pdfs/sub/b.pdf"] = FakeBlob("pdfs/sub/b.pdf")
    bucket.blobs["other/c.pdf"] = FakeBlob("other/c.pdf")

    filenames = _downloader(bucket).get_available_filenames(prefix="pdfs")

    assert "a.pdf" in filenames
    assert "sub/b.pdf" in filenames
    assert "c.pdf" not in filenames


def test_cleanup_local_file_and_dir(tmp_path: Path) -> None:
    downloader = _downloader(FakeBucket())
    file = tmp_path / "f.txt"
    file.write_text("x")
    downloader.cleanup_local_file(file)
    assert not file.exists()

    dir_path = tmp_path / "sub"
    dir_path.mkdir()
    (dir_path / "g.txt").write_text("y")
    downloader.cleanup_local_dir(dir_path, recursive=True)
    assert not dir_path.exists()
