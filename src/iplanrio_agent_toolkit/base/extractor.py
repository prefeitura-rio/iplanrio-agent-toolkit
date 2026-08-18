"""Generic contract for structured-data extractors.

Deliberately returns a plain ``dict`` rather than a fixed schema — the shape
of extracted data (what fields a document has) is entirely up to the
consuming application's domain model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class DocumentExtractor(Protocol):
    """Protocol for extractors that pull structured data out of documents."""

    def extract_from_pdf(self, pdf_path: Path, pages: list[int] | None = None) -> dict[str, Any]:
        """Extract structured data from specific pages of a PDF.

        :param pdf_path: Path to the source PDF file.
        :param pages: 1-indexed page numbers to extract from; ``None`` means all pages.
        :returns: Application-defined dict of extracted data.
        """
        ...

    def extract_from_images(self, images: list[Any]) -> dict[str, Any]:
        """Extract structured data from a list of page images.

        :param images: Page images (e.g. PIL Images), in reading order.
        :returns: Application-defined dict of extracted data.
        """
        ...
