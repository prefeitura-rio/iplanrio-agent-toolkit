from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
from iplanrio_agent_toolkit.gemini.vision import extract_page_as_bytes  # noqa: E402


def _make_pdf(tmp_path: Path, pages: int = 2) -> Path:
    path = tmp_path / "sample.pdf"
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), "Hello")
    doc.save(path)
    doc.close()
    return path


def test_extracts_page_as_png(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)

    png_bytes = extract_page_as_bytes(pdf, page_num=0, as_pdf=False)

    assert png_bytes.startswith(b"\x89PNG")


def test_extracts_page_as_pdf(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path)

    pdf_bytes = extract_page_as_bytes(pdf, page_num=1, as_pdf=True)

    reopened = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert reopened.page_count == 1
    reopened.close()


def test_page_out_of_range_raises(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, pages=1)

    with pytest.raises(ValueError, match="out of range"):
        extract_page_as_bytes(pdf, page_num=5)
