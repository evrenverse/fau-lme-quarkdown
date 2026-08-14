"""Parse acronyms.qd's Markdown table into a {KEY: anchor-slug} map.

Each table row has the form `| **KEY** | Definition |`. Rows without bold
in the first cell are ignored (defensive — a non-bold row is malformed and
must not pollute the link map).
"""

from __future__ import annotations

import re
from pathlib import Path

ROW_PATTERN = re.compile(
    r"^\|\s*\*\*(?P<key>[^\W\d_][\w.\-/]*)\*\*\s*\|",
    flags=re.MULTILINE,
)
ROW_FULL_PATTERN = re.compile(
    r"^\|\s*\*\*(?P<key>[^\W\d_][\w.\-/]*)\*\*\s*\|\s*(?P<long>[^|]+?)\s*\|",
    flags=re.MULTILINE,
)
NON_SLUG = re.compile(r"[^a-z0-9]+")


def parse_acromap(acronyms_path: Path) -> dict[str, str]:
    """Return {KEY: anchor-slug} for every `| **KEY** | ... |` row."""
    text = acronyms_path.read_text(encoding="utf-8")
    return {
        match.group("key"): slugify_acronym(match.group("key"))
        for match in ROW_PATTERN.finditer(text)
    }


def parse_acromap_long_forms(acronyms_path: Path) -> dict[str, str]:
    """Return {KEY: LongForm} for every `| **KEY** | LongForm |` row.

    Used by the Auto-Expansion postprocessor pass to render first-occurrence
    acronyms as "LongForm (KEY)". The Long Form is the table's second cell,
    stripped of leading/trailing whitespace.
    """
    text = acronyms_path.read_text(encoding="utf-8")
    return {
        match.group("key"): match.group("long").strip()
        for match in ROW_FULL_PATTERN.finditer(text)
    }


def slugify_acronym(key: str) -> str:
    """Convert an acronym KEY into its HTML id slug: `HTTP` → `acro-http`.

    Lowercases and replaces every non-[a-z0-9] run with a single hyphen,
    then strips leading/trailing hyphens.
    """
    slug = NON_SLUG.sub("-", key.lower()).strip("-")
    return "acro-" + slug
