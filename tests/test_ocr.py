from __future__ import annotations

from pathlib import Path

import pytest

try:
    import fitz  # noqa: F401
except ImportError:
    fitz = None

pytestmark = pytest.mark.skipif(fitz is None, reason="PyMuPDF not installed")

from iplanrio_agent_toolkit.ocr import get_page_count  # noqa: E402


def _make_pdf(tmp_path: Path, pages: int = 3) -> Path:
    import fitz

    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()
    return path


def test_get_page_count(tmp_path: Path) -> None:
    assert get_page_count(_make_pdf(tmp_path, pages=3)) == 3
    assert get_page_count(_make_pdf(tmp_path, pages=1)) == 1
