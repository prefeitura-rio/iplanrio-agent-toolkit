"""OCR text extraction from PDF pages, supporting EasyOCR and PaddleOCR engines.

Requires the ``ocr`` extra (``pdf2image``, ``pillow``, ``PyMuPDF``) plus,
separately, whichever OCR engine you choose to use (``easyocr`` or
``paddleocr`` + ``paddlepaddle``), since those are heavy, platform-specific
dependencies not bundled by this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pdf2image import convert_from_path

from iplanrio_agent_toolkit.logging import get_logger

if TYPE_CHECKING:
    from PIL import Image

logger = get_logger(__name__)

OCREngineName = Literal["easyocr", "paddleocr"]


@dataclass(frozen=True)
class PaddleOCRConfig:
    """Configuration for the PaddleOCR engine."""

    lang: str = "en"
    ocr_version: str = "PP-OCRv5"
    use_doc_orientation_classify: bool = True
    use_doc_unwarping: bool = True
    use_textline_orientation: bool = True
    textline_orientation_batch_size: int = 1
    text_recognition_batch_size: int = 1
    gpu: bool = True


class OCRProcessor:
    """OCR processor supporting EasyOCR and PaddleOCR for text extraction from PDFs."""

    def __init__(
        self,
        languages: list[str] | None = None,
        gpu: bool = True,
        dpi: int = 200,
        engine: OCREngineName = "easyocr",
        paddleocr_config: PaddleOCRConfig | None = None,
    ) -> None:
        """Configure an OCR processor; engines are constructed lazily on first use.

        :param languages: Language codes for EasyOCR (default: ``["pt", "en"]``).
        :param gpu: Whether to use GPU acceleration.
        :param dpi: DPI used when converting PDF pages to images.
        :param engine: Which OCR engine to use.
        :param paddleocr_config: PaddleOCR-specific configuration, used only when ``engine="paddleocr"``.
        """
        self.languages = languages or ["pt", "en"]
        self.gpu = gpu
        self.dpi = dpi
        self.engine = engine
        self.paddleocr_config = paddleocr_config or PaddleOCRConfig(gpu=gpu)
        self._reader: object | None = None
        self._paddle_engine: object | None = None

    @property
    def reader(self) -> object:
        """Lazily construct and return the EasyOCR reader instance."""
        if self._reader is None:
            import easyocr  # noqa: PLC0415 - optional heavy dep

            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    @property
    def paddle_engine(self) -> object:
        """Lazily construct and return the PaddleOCR engine instance."""
        if self._paddle_engine is None:
            import paddle  # noqa: PLC0415 - optional heavy dep
            from paddleocr import PaddleOCR  # noqa: PLC0415 - optional heavy dep

            config = self.paddleocr_config
            if not paddle.is_compiled_with_cuda():
                logger.warning("PaddlePaddle was installed WITHOUT GPU support. Using CPU.")
                paddle.set_device("cpu")
            elif config.gpu:
                try:
                    paddle.set_device("gpu")
                except Exception as exc:  # fall back to CPU
                    logger.warning("Could not use GPU, falling back to CPU: %s", exc)
                    paddle.set_device("cpu")
            else:
                paddle.set_device("cpu")

            self._paddle_engine = PaddleOCR(
                use_doc_orientation_classify=config.use_doc_orientation_classify,
                use_doc_unwarping=config.use_doc_unwarping,
                use_textline_orientation=config.use_textline_orientation,
                textline_orientation_batch_size=config.textline_orientation_batch_size,
                text_recognition_batch_size=config.text_recognition_batch_size,
                lang=config.lang,
                ocr_version=config.ocr_version,
            )
        return self._paddle_engine

    def ocr_image(self, image: Image.Image) -> str:
        """Extract text from a PIL Image using the configured engine.

        :param image: Image to process.
        :returns: Extracted text.
        """
        if self.engine == "paddleocr":
            return self._ocr_image_paddle(image)
        return self._ocr_image_easyocr(image)

    def _ocr_image_easyocr(self, image: Image.Image) -> str:
        import numpy as np  # noqa: PLC0415 - optional heavy dep

        results = self.reader.readtext(np.array(image))
        return "\n".join(result[1] for result in results)

    def _ocr_image_paddle(self, image: Image.Image) -> str:
        import numpy as np  # noqa: PLC0415 - optional heavy dep

        result = self.paddle_engine.predict(np.array(image))

        text_parts: list[str] = []
        for page_result in result or []:
            if hasattr(page_result, "rec_texts"):
                text_parts.extend(page_result.rec_texts)
            elif isinstance(page_result, dict) and "rec_texts" in page_result:
                text_parts.extend(page_result["rec_texts"])
            elif isinstance(page_result, list):
                for item in page_result:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:  # noqa: PLR2004 - [text, confidence] pair
                        text_info = item[1]
                        if isinstance(text_info, (list, tuple)) and text_info:
                            text_parts.append(str(text_info[0]))
                        elif isinstance(text_info, str):
                            text_parts.append(text_info)

        return "\n".join(text_parts)

    def ocr_pdf_page(self, pdf_path: Path, page_num: int) -> str:
        """Extract text from a single PDF page.

        :param pdf_path: Path to the PDF file.
        :param page_num: 1-indexed page number.
        :returns: Extracted text, or an empty string if the page couldn't be rendered.
        """
        images = convert_from_path(str(pdf_path), first_page=page_num, last_page=page_num, dpi=self.dpi)
        return self.ocr_image(images[0]) if images else ""

    def ocr_pdf(self, pdf_path: Path) -> list[str]:
        """Extract text from every page of a PDF.

        :param pdf_path: Path to the PDF file.
        :returns: One extracted-text string per page, in page order.
        """
        images = convert_from_path(str(pdf_path), dpi=self.dpi)
        page_texts = []
        for idx, image in enumerate(images):
            logger.debug("OCR page %d/%d", idx + 1, len(images))
            page_texts.append(self.ocr_image(image))
        return page_texts

    def ocr_pdf_pages(self, pdf_path: Path, page_numbers: list[int] | None = None) -> list[tuple[int, str]]:
        """Extract text from specific PDF pages.

        :param pdf_path: Path to the PDF file.
        :param page_numbers: 1-indexed page numbers to process; ``None`` means all pages.
        :returns: List of ``(page_number, text)`` tuples.
        """
        if page_numbers is None:
            return [(i + 1, text) for i, text in enumerate(self.ocr_pdf(pdf_path))]
        return [(page_num, self.ocr_pdf_page(pdf_path, page_num)) for page_num in page_numbers]


def get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF.

    :param pdf_path: Path to the PDF file.
    :returns: Page count.
    """
    import fitz  # noqa: PLC0415 - optional heavy dep

    doc = fitz.open(str(pdf_path))
    try:
        return len(doc)
    finally:
        doc.close()


def extract_page_as_image(pdf_path: Path, page_num: int, dpi: int = 200) -> Image.Image | None:
    """Render a single PDF page as a PIL Image.

    :param pdf_path: Path to the PDF file.
    :param page_num: 1-indexed page number.
    :param dpi: Rendering resolution.
    :returns: The rendered page image, or ``None`` if the page couldn't be rendered.
    """
    images = convert_from_path(str(pdf_path), first_page=page_num, last_page=page_num, dpi=dpi)
    return images[0] if images else None
