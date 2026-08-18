"""Download files from a Google Cloud Storage bucket, with batch/parallel support."""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from google.cloud import storage
from google.oauth2 import service_account

from iplanrio_agent_toolkit.logging import get_logger

logger = get_logger(__name__)

_MAX_FAILED_DOWNLOADS_TO_LOG = 5


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of downloading a single blob."""

    name: str
    local_path: Path | None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the download completed without error."""
        return self.local_path is not None


class GCSDownloader:
    """Downloads files from a Google Cloud Storage bucket."""

    def __init__(self, credentials_path: Path | None, bucket_name: str | None = None) -> None:
        """Initialize the GCS client lazily.

        :param credentials_path: Path to a GCS service account JSON file, or
            ``None`` to use Application Default Credentials (ADC).
        :param bucket_name: Name of the target GCS bucket.
        """
        self.credentials_path = Path(credentials_path) if credentials_path else None
        self.bucket_name = bucket_name
        self.default_base_path = ""
        self._client: storage.Client | None = None
        self._bucket: storage.Bucket | None = None

    @property
    def client(self) -> storage.Client:
        """Lazily construct and return the underlying GCS client."""
        if self._client is None:
            if self.credentials_path is not None:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"GCS credentials not found at: {self.credentials_path}\n"
                        f"Please fill in the service account credentials."
                    )
                credentials = service_account.Credentials.from_service_account_file(str(self.credentials_path))
                self._client = storage.Client(credentials=credentials)
            else:
                self._client = storage.Client()
        return self._client

    @property
    def bucket(self) -> storage.Bucket:
        """Lazily resolve and return the target bucket."""
        if self._bucket is None:
            self._bucket = self.client.bucket(self.bucket_name)
        return self._bucket

    def download_file(self, blob_path: str, local_dir: Path, filename: str | None = None) -> Path:
        """Download a single blob to a local directory.

        :param blob_path: Path to the blob within the bucket (e.g. ``"pdfs/file.pdf"``).
        :param local_dir: Local directory to save the file into.
        :param filename: Local filename to use; defaults to the blob's basename.
        :returns: Path to the downloaded local file.
        :raises FileNotFoundError: If the blob does not exist in the bucket.
        """
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        blob = self.bucket.blob(blob_path)
        if not blob.exists():
            raise FileNotFoundError(f"Blob not found in GCS: {blob_path}")

        local_path = local_dir / (filename or Path(blob_path).name)
        blob.download_to_filename(str(local_path))
        return local_path

    def download_file_by_name(self, name: str, local_dir: Path, base_path: str | None = None) -> Path:
        """Download a blob identified only by its filename, under a base path.

        :param name: Filename exactly as stored in GCS, without the base path.
        :param local_dir: Local directory to save the file into.
        :param base_path: Prefix within the bucket; defaults to :attr:`default_base_path`.
        :returns: Path to the downloaded local file.
        """
        base_path = self.default_base_path if base_path is None else base_path
        blob_path = f"{base_path}/{name}" if base_path else name
        return self.download_file(blob_path, local_dir, filename=name)

    def download_files_batch(
        self,
        names: list[str],
        local_dir: Path,
        base_path: str | None = None,
        max_workers: int = 20,
        skip_existing: bool = True,
    ) -> dict[str, Path]:
        """Download multiple blobs concurrently.

        :param names: Filenames to download (without base path).
        :param local_dir: Local directory to save files into.
        :param base_path: Prefix within the bucket; defaults to :attr:`default_base_path`.
        :param max_workers: Maximum number of concurrent downloads.
        :param skip_existing: Skip files that already exist locally with non-zero size.
        :returns: Dict mapping each successfully-downloaded name to its local path.
            Failed downloads are omitted; check the logs for details.
        """
        base_path = self.default_base_path if base_path is None else base_path
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Path] = {}
        to_download: list[str] = []
        for name in names:
            local_path = local_dir / name
            if skip_existing and local_path.exists() and local_path.stat().st_size > 0:
                results[name] = local_path
            else:
                to_download.append(name)

        if skip_existing and results:
            logger.info("Skipped %d already-downloaded files", len(results))
        if not to_download:
            logger.info("All files already exist locally, skipping download")
            return results

        logger.info("Downloading %d new files", len(to_download))

        def _download_single(name: str) -> DownloadResult:
            try:
                blob_path = f"{base_path}/{name}" if base_path else name
                local_path = local_dir / name
                self.bucket.blob(blob_path).download_to_filename(str(local_path))
                return DownloadResult(name=name, local_path=local_path)
            except Exception as exc:  # reported to caller via DownloadResult, not raised
                return DownloadResult(name=name, local_path=None, error=str(exc))

        failed: list[DownloadResult] = []
        completed = 0
        with ThreadPoolExecutor(max_workers=min(max_workers, len(to_download))) as executor:
            futures = {executor.submit(_download_single, name): name for name in to_download}
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                if result.succeeded:
                    results[result.name] = result.local_path
                else:
                    failed.append(result)

                if completed % max_workers == 0 or completed == len(to_download):
                    logger.info("Downloaded %d/%d files", completed, len(to_download))

        if failed:
            logger.warning("%d downloads failed", len(failed))
            for result in failed[:_MAX_FAILED_DOWNLOADS_TO_LOG]:
                logger.warning("  - %s: %s", result.name, result.error)
            if len(failed) > _MAX_FAILED_DOWNLOADS_TO_LOG:
                logger.warning("  ... and %d more failures", len(failed) - _MAX_FAILED_DOWNLOADS_TO_LOG)

        return results

    def cleanup_local_file(self, file_path: Path) -> None:
        """Delete a local file if it exists.

        :param file_path: Path to the file to remove.
        """
        file_path = Path(file_path)
        if file_path.exists():
            file_path.unlink()

    def cleanup_local_dir(self, dir_path: Path, recursive: bool = False, pattern: str = "*") -> None:
        """Remove files from a local directory.

        :param dir_path: Directory to clean up.
        :param recursive: If ``True``, remove the directory and all its contents.
        :param pattern: Glob pattern of files to remove when ``recursive`` is ``False``.
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            return

        if recursive:
            shutil.rmtree(dir_path)
        else:
            for file_path in dir_path.glob(pattern):
                file_path.unlink()

    def blob_exists(self, blob_path: str) -> bool:
        """Check whether a blob exists in the bucket.

        :param blob_path: Path to the blob within the bucket.
        :returns: ``True`` if the blob exists.
        """
        return self.bucket.blob(blob_path).exists()

    def list_blobs(self, prefix: str = "") -> list[str]:
        """List all blob names under a prefix.

        :param prefix: Prefix to filter blobs by (e.g. ``"pdfs/"``).
        :returns: List of blob names.
        """
        return [blob.name for blob in self.bucket.list_blobs(prefix=prefix)]

    def get_available_filenames(self, prefix: str = "") -> set[str]:
        """List blobs under a prefix and return just their filenames (prefix stripped).

        Prefer this over repeated :meth:`blob_exists` calls for bulk availability
        checks — it costs a single GCS API call.

        :param prefix: Prefix to filter blobs by (e.g. ``"pdfs/"``).
        :returns: Set of filenames with the prefix removed.
        """
        prefix_normalized = prefix.rstrip("/") + "/" if prefix else ""
        filenames = set()
        for blob_name in self.list_blobs(prefix=prefix):
            if prefix_normalized and blob_name.startswith(prefix_normalized):
                filename = blob_name[len(prefix_normalized) :]
            elif prefix and blob_name.startswith(prefix):
                filename = blob_name[len(prefix) :]
            else:
                filename = blob_name
            if filename:
                filenames.add(filename)
        return filenames

    def get_available_filenames_from_csv(self, csv_path: Path, filename_column: str = "filename") -> set[str]:
        """Read a pre-generated CSV of known filenames instead of listing the bucket.

        Useful when a full bucket listing is expensive and a snapshot CSV is
        refreshed out-of-band. Falls back to :meth:`get_available_filenames`
        (an actual bucket listing) when the CSV is missing.

        :param csv_path: Path to a CSV file with a column of filenames.
        :param filename_column: Name of the column containing filenames.
        :returns: Set of filenames.
        """
        if not Path(csv_path).exists():
            logger.warning("%s not found - falling back to GCS API listing", csv_path)
            return self.get_available_filenames()

        df = pd.read_csv(csv_path)
        return set(df[filename_column].dropna().unique())
