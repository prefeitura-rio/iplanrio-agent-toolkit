"""Generic base contracts (Protocols/ABCs) for pipeline building blocks.

Note: the original codebase this was extracted from also had a
``BasePipeline`` Protocol whose methods (``classify_pdf``, ``classify_batch``)
did not match any real implementation. It was not ported here — see
``MIGRATION_PLAN.md`` for the rationale. Define a new pipeline contract here
once a second concrete pipeline actually needs one.
"""

from __future__ import annotations

from iplanrio_agent_toolkit.base.classifier import ClassificationResult, PageClassifier
from iplanrio_agent_toolkit.base.extractor import DocumentExtractor

__all__ = ["ClassificationResult", "DocumentExtractor", "PageClassifier"]
