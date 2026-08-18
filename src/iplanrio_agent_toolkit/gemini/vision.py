"""Extract a single PDF page as image or single-page-PDF bytes, for vision API calls.

Requires the ``pdf`` extra (``PyMuPDF``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from iplanrio_agent_toolkit.logging import get_logger

if TYPE_CHECKING:
    import fitz

logger = get_logger(__name__)


def extract_page_as_bytes(pdf_path: Path, page_num: int, as_pdf: bool = False, zoom: float = 2.0) -> bytes:
    """Render a single PDF page as PNG bytes, or extract it as a single-page PDF.

    :param pdf_path: Path to the source PDF file.
    :param page_num: Page number, 0-indexed.
    :param as_pdf: If ``True``, return single-page PDF bytes; otherwise return PNG bytes.
    :param zoom: Rendering zoom factor applied to both axes when ``as_pdf`` is ``False``
        (2.0 roughly matches 144 DPI at a 72-DPI page size).
    :returns: PNG or PDF bytes, depending on ``as_pdf``.
    :raises ValueError: If ``page_num`` is out of range for the document.
    :raises RuntimeError: If the PDF is corrupted or cannot be processed.
    """
    import fitz  # noqa: PLC0415 - optional heavy dep

    doc: fitz.Document | None = None
    new_doc: fitz.Document | None = None

    try:
        doc = fitz.open(pdf_path)

        if page_num < 0 or page_num >= len(doc):
            raise ValueError(
                f"Page number {page_num} is out of range. PDF has {len(doc)} pages (valid range: 0-{len(doc) - 1})"
            )

        if as_pdf:
            new_doc = fitz.open()
            try:
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            except RuntimeError as exc:
                logger.error(
                    "Failed to insert page %d from %s: %s. PDF may be corrupted or malformed.",
                    page_num,
                    pdf_path.name,
                    exc,
                )
                raise RuntimeError(f"Failed to extract page {page_num} as PDF: {exc}") from exc
            return new_doc.tobytes()

        page = doc[page_num]
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        return pixmap.tobytes("png")

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        logger.error("Unexpected error extracting page %d from %s: %s", page_num, pdf_path.name, exc)
        raise RuntimeError(f"Unexpected error extracting page {page_num}: {exc}") from exc
    finally:
        if new_doc is not None:
            new_doc.close()
        if doc is not None:
            doc.close()
