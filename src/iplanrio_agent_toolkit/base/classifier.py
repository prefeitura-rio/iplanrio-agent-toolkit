"""Generic contract for page/document classifiers.

Any classifier (OCR-based, vision-based, etc.) that implements this interface
can be swapped into a pipeline without it needing to know which
implementation it's using. Unlike the original NF-specific interface this was
extracted from, labels are plain strings chosen by the caller — there is no
built-in notion of "NF" vs "Non-NF".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClassificationResult:
    """Result of classifying a single page/item."""

    label: str
    score: float
    is_positive: bool
    categories: list[str] | None = None


class PageClassifier(ABC):
    """Abstract base class for page/document classifiers."""

    @abstractmethod
    def classify(self, page_input: Any) -> tuple[str, float]:
        """Classify a single page.

        :param page_input: Page data (e.g. OCR text for text-based classifiers,
            or image/PDF bytes for vision-based classifiers).
        :returns: A tuple of ``(label, score)``, where a higher score indicates
            higher confidence in a positive classification.
        """

    @abstractmethod
    def classify_pages(self, inputs: list[Any]) -> list[ClassificationResult]:
        """Classify multiple pages.

        :param inputs: List of page inputs, in the same format expected by :meth:`classify`.
        :returns: One :class:`ClassificationResult` per input, in the same order.
        """

    @abstractmethod
    def get_positive_pages(self, inputs: list[Any]) -> list[int]:
        """Return the 1-indexed page numbers classified as positive.

        :param inputs: List of page inputs, in the same format expected by :meth:`classify`.
        :returns: 1-indexed page numbers whose classification is positive.
        """

    @property
    @abstractmethod
    def requires_preprocessing(self) -> bool:
        """Whether this classifier needs preprocessed input (e.g. OCR text).

        :returns: ``True`` if the classifier needs preprocessed text/data rather
            than raw page bytes.
        """
