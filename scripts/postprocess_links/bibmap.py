"""Parse a BibTeX file's `note` field into an alpha-label → bibtex-key map.

The thesis hijacks the BibTeX `note` field to carry the citation label that
the custom CSL style emits (e.g., `note = {Pet07}` on
`@article{peffers2007dsr, ...}`). See refs.bib's header comment.
"""

from __future__ import annotations

import re
from pathlib import Path

ENTRY_PATTERN = re.compile(
    r"@\w+\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)\}(?=\s*\n|\s*\Z|\s*@)",
    flags=re.DOTALL,
)
NOTE_FIELD = re.compile(
    r"\bnote\s*=\s*\{(?P<value>[^{}]*)\}",
    flags=re.IGNORECASE,
)


def parse_bibmap(bib_path: Path) -> dict[str, str]:
    """Return {alpha-label: bibtex-key} for every entry whose `note` field
    holds a non-empty alpha label."""
    text = bib_path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for match in ENTRY_PATTERN.finditer(text):
        key = match.group("key").strip()
        body = match.group("body")
        note_match = NOTE_FIELD.search(body)
        if not note_match:
            continue
        label = note_match.group("value").strip()
        if label:
            out[label] = key
    return out


def slugify_label(label: str) -> str:
    """Convert an alpha-label to its HTML id slug: `Pet07` → `bib-pet07`."""
    return "bib-" + label.lower()
