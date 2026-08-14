"""Definition-marker rewrite: body `RQ1`, `G2`, `C1`, `H2.4` etc. become <a>
links pointing at the paragraph or table cell where the marker is first defined.

Recognised marker prefixes (common academic-thesis conventions):

* `RQ`     — research questions  (`**RQ1** — *...*` paragraph form)
* `G`      — research goals      (`**G1 (Optional label).** ...`)
* `C`      — contributions       (`**C1 (Optional label, own).** *...*`)
* `H<n>.<m>[<a-z>]` — hypotheses (`**H2.4** ...` paragraph OR table-cell form,
  with optional lowercase leg suffix `**H2.3a**` / `**H2.3b**` for split
  hypothesis legs; hypotheses are typically defined in the first column of
  a hypotheses table)
* `R<n>[<a-z>]` — functional requirements    (`**R3**`, `**R4a**`, `**R4b**`;
  typically defined in a requirements table)
* `R-NF<n>` — non-functional requirements    (`**R-NF1**`, `**R-NF2**`;
  same table)

A definition counts when its containing element (`<p>` or `<td>`) begins with
`<strong>PREFIX-N…</strong>` and has no text before that first child. The first
matching paragraph or cell per (prefix, N) receives `id="<prefix-lower>-<n>"`
(dots in `n` are replaced with hyphens for valid HTML id syntax: H2.4 → h-2-4,
H2.3a → h-2-3a, R-NF1 → r-nf-1). Body occurrences whose (prefix, N) has an
anchor are wrapped in `<a href="#<slug>" class="marker-link">PREFIX-N</a>`.
Unknown (prefix, N) combinations (e.g. a typo like `RQ99` or a `G7` summit
reference) are left untouched.
"""

from __future__ import annotations

import re
from lxml import etree

from .dom_rewriter import iter_text_nodes, replace_text_with_anchor

# Skip zones identical to acronyms: <strong> is included so the
# definition's own strong tag is never self-linked.
BODY_SKIP_TAGS = frozenset(
    {"code", "pre", "kbd", "samp", "a", "h1", "h2", "h3", "h4", "h5", "h6",
     "figcaption", "caption", "strong",
     "head", "title", "style", "script", "meta", "link"}
)
BODY_SKIP_CLASS_SUBSTRINGS = ("katex", "bibliography")

# Match a definition marker at the start of <strong> text. Trailing content
# after the digits is permitted (e.g. "G1 (Optional label)." or "C1 (...own)."
# or "H2.4 — On the champion..."). Number form is either a bare integer
# (RQ/G/C/R convention), a dotted decimal (H1.1 hypothesis convention), or
# either followed by an optional lowercase letter for split legs / sub-IDs
# (H2.3a, R4b).
# Alternation order is longest-prefix-first: `RQ` before `R` so `RQ1` is not
# misread as `R1`; `R-NF` before `R` so `R-NF1` is not misread as `R` with a
# stray suffix.
DEF_PATTERN = re.compile(
    r"^(?P<prefix>RQ|G|C|H|R-NF|R)(?P<n>\d+(?:\.\d+)?[a-z]?)\b"
)

# Match a definition marker in body text — full word, including prefix.
BODY_PATTERN = re.compile(r"\b(RQ|G|C|H|R-NF|R)(\d+(?:\.\d+)?[a-z]?)\b")

# Elements that may carry a definition. Paragraphs are the canonical home for
# RQ/G/C; table cells additionally host H<n>.<m> hypothesis definitions
# whenever a hypotheses table such as `tab:hypotheses` is used.
DEF_HOST_TAGS = ("p", "td")


def _slug(prefix: str, n: str) -> str:
    """Stable HTML id for a marker. `H2.4` → `h-2-4`; `RQ1` → `rq-1`."""
    return f"{prefix.lower()}-{n.replace('.', '-')}"


def rewrite_markers(root: etree._Element) -> None:
    """Two-step in-place rewrite:
    1. Tag the first element (`<p>` or `<td>`) that opens with
       `<strong>PREFIX-N…</strong>` for each (prefix, N) with
       `id="<prefix-lower>-<n>"`.
    2. Wrap every body occurrence of `(RQ|G|C|H)\\d+(\\.\\d+)?` (known)
       with an <a>.
    """
    anchors = set_marker_paragraph_ids(root)
    if not anchors:
        return
    add_body_links(root, anchors)


def set_marker_paragraph_ids(root: etree._Element) -> set[tuple[str, str]]:
    """Tag the first element that opens with <strong>PREFIX-N…</strong>
    for each (prefix, N). Walks both <p> and <td> so that hypothesis
    tables can host H<n>.<m> definitions. Returns the set of recognised
    (prefix, N) keys (N kept as the original string form, e.g. ``"2.4"``)."""
    seen: set[tuple[str, str]] = set()
    for host_tag in DEF_HOST_TAGS:
        for elem in root.iter(host_tag):
            # Reject hosts with text before the first child — those are
            # not a canonical definition line.
            if elem.text and elem.text.strip():
                continue
            children = list(elem)
            if not children:
                continue
            first = children[0]
            if first.tag != "strong" or first.text is None:
                continue
            match = DEF_PATTERN.match(first.text.strip())
            if not match:
                continue
            prefix = match.group("prefix")
            n = match.group("n")
            key = (prefix, n)
            if key in seen:
                continue
            slug = _slug(prefix, n)
            if elem.get("id") != slug:
                elem.set("id", slug)
            seen.add(key)
    return seen


def add_body_links(
    root: etree._Element, anchors: set[tuple[str, str]]
) -> None:
    """Wrap every body occurrence of `PREFIX-N` (known) with an <a>
    pointing to `#<prefix-lower>-<n>`. Unknown (prefix, N) is left alone."""

    def make_anchor(match: re.Match) -> tuple[str, str, str] | None:
        prefix = match.group(1)
        n = match.group(2)
        if (prefix, n) not in anchors:
            return None
        return (f"#{_slug(prefix, n)}", "marker-link", match.group(0))

    for text_node in list(
        iter_text_nodes(root, BODY_SKIP_TAGS, BODY_SKIP_CLASS_SUBSTRINGS)
    ):
        replace_text_with_anchor(text_node, BODY_PATTERN, make_anchor)
