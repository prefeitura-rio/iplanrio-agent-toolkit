"""Generic versioned text-prompt registry.

Loads prompt text from files named ``v<N>.txt`` inside per-kind directories
(e.g. ``versions/classification/v1.txt``, ``versions/extraction/v3.txt``),
computes content hashes for traceability, and resolves "the latest version"
on demand rather than as an import-time side effect — callers decide when to
read from disk.

This module knows nothing about what the prompts are used for; the set of
valid "kinds" (e.g. ``"classification"``, ``"extraction"``) and the prompt
content itself belong entirely to the consuming application.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_VERSION_PATTERN = re.compile(r"^v(\d+)$")


def _version_sort_key(version: str) -> int:
    """Extract the numeric ordering key from a version string like ``"v9"`` or ``"v10"``.

    Sorting by this key (rather than lexicographically) is what makes
    ``"v10"`` correctly sort after ``"v9"`` instead of before ``"v2"``.

    :param version: Version string, expected to match ``v<digits>``.
    :returns: The integer suffix, or ``-1`` if the string doesn't match the expected pattern.
    """
    match = _VERSION_PATTERN.match(version)
    return int(match.group(1)) if match else -1


@dataclass(frozen=True)
class PromptInfo:
    """A resolved prompt version: its text, hash, source file and version label."""

    content: str
    hash: str
    file: Path
    version: str


class PromptRegistry:
    """Reads versioned prompt text files from a directory tree.

    Expected layout::

        <root>/
        ├── <kind_a>/
        │   ├── v1.txt
        │   ├── v2.txt
        │   └── CHANGELOG.md   (optional, not read by this class)
        └── <kind_b>/
            └── v1.txt
    """

    def __init__(self, root: Path) -> None:
        """Point the registry at a directory of ``<kind>/v<N>.txt`` prompt files.

        :param root: Root directory containing one subdirectory per prompt kind.
        """
        self.root = Path(root)

    def list_versions(self, kind: str) -> list[str]:
        """List available versions for a prompt kind, sorted oldest to newest.

        :param kind: Prompt kind (subdirectory name under :attr:`root`).
        :returns: Version strings (e.g. ``["v1", "v2", "v10"]``), numerically sorted.
        """
        kind_dir = self.root / kind
        if not kind_dir.exists():
            return []
        versions = [f.stem for f in kind_dir.glob("v*.txt")]
        return sorted(versions, key=_version_sort_key)

    def latest_version(self, kind: str) -> str | None:
        """Return the highest version string available for a prompt kind.

        :param kind: Prompt kind (subdirectory name under :attr:`root`).
        :returns: The latest version string, or ``None`` if no versions exist.
        """
        versions = self.list_versions(kind)
        return versions[-1] if versions else None

    def load(self, kind: str, version: str | None = None) -> str:
        """Load the text of a specific (or latest) prompt version.

        :param kind: Prompt kind (subdirectory name under :attr:`root`).
        :param version: Version to load (e.g. ``"v3"``); loads the latest when omitted.
        :returns: The prompt text, stripped of leading/trailing whitespace.
        :raises FileNotFoundError: If no versions exist for ``kind``, or the
            requested version file is missing.
        """
        resolved_version = version or self.latest_version(kind)
        if resolved_version is None:
            raise FileNotFoundError(f"No prompt versions found for kind '{kind}' under {self.root}")

        version_file = self.root / kind / f"{resolved_version}.txt"
        if not version_file.exists():
            raise FileNotFoundError(f"Prompt version not found: {version_file}")

        return version_file.read_text(encoding="utf-8").strip()

    def info(self, kind: str, version: str | None = None) -> PromptInfo:
        """Load a prompt version along with its hash and source file path.

        :param kind: Prompt kind (subdirectory name under :attr:`root`).
        :param version: Version to load; loads the latest when omitted.
        :returns: A :class:`PromptInfo` with content, hash, file path and resolved version.
        """
        resolved_version = version or self.latest_version(kind) or "v1"
        content = self.load(kind, resolved_version)
        return PromptInfo(
            content=content,
            hash=compute_prompt_hash(content),
            file=self.root / kind / f"{resolved_version}.txt",
            version=resolved_version,
        )

    def detect_version(self, kind: str, content: str) -> str:
        """Identify which stored version's content matches ``content``, by hash.

        :param kind: Prompt kind (subdirectory name under :attr:`root`).
        :param content: Prompt text to identify.
        :returns: The matching version string, or ``"unknown"`` if no version matches.
        """
        target_hash = compute_prompt_hash(content)
        for version in self.list_versions(kind):
            if compute_prompt_hash(self.load(kind, version)) == target_hash:
                return version
        return "unknown"


def compute_prompt_hash(content: str) -> str:
    """Compute a short, stable hash of prompt content for traceability.

    :param content: Prompt text.
    :returns: The first 12 hex characters of the SHA-256 digest of ``content``.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
