"""Tests for the caption-period validator (postprocess_links.captions)."""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import html as lxml_html

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from postprocess_links.captions import find_caption_period_violations


def parse(snippet: str):
    return lxml_html.fragment_fromstring(snippet, create_parent="body")


def test_period_caption_passes() -> None:
    doc = parse('<figure><figcaption>A figure that ends right.</figcaption></figure>')
    assert find_caption_period_violations(doc) == []


def test_missing_period_caption_flagged() -> None:
    doc = parse('<figure><figcaption>This one forgot the period</figcaption></figure>')
    out = find_caption_period_violations(doc)
    assert len(out) == 1
    assert out[0][0] == "figcaption"


def test_table_caption_checked() -> None:
    doc = parse('<table><caption>Table caption no dot</caption></table>')
    out = find_caption_period_violations(doc)
    assert len(out) == 1
    assert out[0][0] == "caption"


def test_style_block_ignored() -> None:
    """CSS comments referencing 'caption' must not be parsed as captions."""
    doc = parse(
        '<head><style>/* caption: behaviour quirk */ table { color: red; }</style></head>'
    )
    assert find_caption_period_violations(doc) == []


def test_whitespace_only_caption_skipped() -> None:
    """Empty / whitespace-only captions are not flagged — they are a stub
    state, separately handled by the build pipeline."""
    doc = parse('<figure><figcaption>   </figcaption></figure>')
    assert find_caption_period_violations(doc) == []


def test_caption_with_inline_elements() -> None:
    """Caption ending in a period inside an inline element (italic, em, etc.)
    is still considered correct."""
    doc = parse('<figure><figcaption>See <em>fig:x</em>.</figcaption></figure>')
    assert find_caption_period_violations(doc) == []
