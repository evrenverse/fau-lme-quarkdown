"""Materialise empty <span class="cross-reference"> elements as real DOM
text content.

PROBLEM
-------
Quarkdown emits cross-references (``.ref {id}``) as empty span placeholders
with attributes that a CSS rule then expands via ``::before`` /
``content: attr(...)``::

    <span class="cross-reference"
          data-location="5.6"
          data-localized-kind="Chapter"></span>

    /* Quarkdown's lib/html/theme/global.css */
    .quarkdown [data-location]::before {
      content: attr(data-localized-kind) " " attr(data-location)
               var(--qd-label-suffix);
    }

Visually this renders fine in a browser, but PagedJS — which paginates the
DOM before paint — measures line widths from the **DOM text** of each
inline element. The CSS-generated ``::before`` content is **invisible to
PagedJS's layout engine**, so the empty span is treated as width 0.
PagedJS then packs more words into the line than will actually fit. When
Chromium subsequently paints, the rendered cross-reference text
("Chapter 5.6", "Section 6.7", …) appears in the page box and pushes the
real text past the page's printable bottom edge, where Chromium's
``page.pdf()`` clips it.

The observable symptom is mid-paragraph text loss in the PDF whenever a
``.ref`` falls on a line that crosses a page boundary: PagedJS thinks
the line has room for many more words, those words render below the page
margin, and the PDF prints them as invisible (white-space) overflow.

FIX
---
This module materialises the cross-reference text **into the DOM** before
PagedJS runs (postprocessor stage), so PagedJS sees the real character
count and breaks the line correctly. A companion CSS rule in
``styles.css`` suppresses the now-redundant ``::before`` pseudo-element
for any ``.cross-reference[data-text-materialised]``.

The materialised text follows Quarkdown's CSS content rule exactly:

    {data-localized-kind} " " {data-location}

so the visible output is unchanged from the user's perspective.

APPENDIX RE-LABELLING
---------------------
Quarkdown numbers headings globally, so the appendices (which follow the
body chapters) are numbered as ordinary chapters: with 11 body chapters an
appendix h1 carries ``data-location="12".."16"`` and
``data-localized-kind="Chapter"``. A cross-reference to an appendix would
therefore materialise as "Chapter 14" rather than "Appendix C".

This module remaps such references. It enumerates the appendix h1s inside
the ``.appendix`` container (set up in ``main.qd``) in document order,
assigns letters A, B, C, … (no hard-coded body-chapter count), and rewrites
any cross-reference whose location's leading chapter-number matches an
appendix:

    "Chapter 14"    -> "Appendix C"   (chapter-word swapped + number -> letter)
    "Section 14.2"  -> "Section C.2"  (kind kept, leading number -> letter)
    "Table 14.1"    -> "Table C.1"

The same remap is applied to appendix **float captions** and the
**List-of-Tables / List-of-Figures** entries (see
:func:`relabel_appendix_floats`), so a caption reads "Table B.4" and its
cross-reference reads "Table B.4" instead of one saying "Table 12.4". The
first float-bearing appendix is what surfaces this: a letter-only appendix
(no tables/figures) never exercised the caption path.

It also tags the matching table-of-contents ``<li>`` entries with
``class="appendix-toc-entry"`` so ``styles.css`` can suppress their
auto-number prefix even when the appendix heading carries a custom id
(e.g. ``{#app:quest-rubric}``) that does not start with ``appendix-``.
"""

from __future__ import annotations

import string

from lxml import etree

# Chapter-kind label -> appendix-kind label, per document language. Quarkdown
# emits "Chapter" (en) / "Kapitel" (de) for h1 targets; appendices read
# "Appendix" / "Anhang". Non-chapter kinds (Section, Table, Figure, …) are
# kept verbatim — only their leading location number is remapped to a letter.
_APPENDIX_KIND = {"Chapter": "Appendix", "Kapitel": "Anhang"}

_APPENDIX_CONTAINER_XPATH = (
    ".//*[contains(concat(' ', normalize-space(@class), ' '), ' appendix ')]"
)

# Cross-reference target id prefix -> rendered label noun. Quarkdown stamps
# every cross-reference span with ``data-localized-kind="Chapter"`` regardless
# of whether the target is an h1, an h2, a figure, or a table, so the label
# alone cannot distinguish them. The link's href, on the other hand, carries
# the source's id prefix (``sec:foo``, ``fig:bar``, …) which is the
# authoritative signal. ``materialise_cross_references`` consults this map
# first, falling back to the span's ``data-localized-kind`` only when the
# target id is missing or its prefix is unknown.
_PREFIX_LABEL = {
    "ch:": "Chapter",
    "sec:": "Section",
    "tab:": "Table",
    "fig:": "Figure",
    "lst:": "Listing",
    "eq:": "Equation",
}


def _split_location(loc: str) -> tuple[str, str]:
    """Split a location into its leading chapter-number and the remainder.

    ``"14"`` -> ``("14", "")``; ``"14.2"`` -> ``("14", ".2")``.
    """
    head, sep, tail = loc.partition(".")
    return head, (sep + tail if sep else "")


def build_appendix_label_map(root: etree._Element) -> dict[str, str]:
    """Map each appendix chapter-number to its letter (``{"14": "C", …}``).

    Enumerates ``h1[data-location]`` inside the ``.appendix`` container in
    document order and assigns A, B, C, … so the mapping survives adding or
    removing body chapters (no hard-coded chapter index). Returns an empty
    map when there is no appendix container, leaving ordinary documents
    (and the existing unit tests) unaffected.
    """
    loc_to_letter: dict[str, str] = {}
    idx = 0
    for container in root.xpath(_APPENDIX_CONTAINER_XPATH):
        for h1 in container.xpath(".//h1[@data-location]"):
            loc = (h1.get("data-location") or "").strip()
            # Chapter-level only (integer location); subsections are h2/h3.
            if not loc or "." in loc or loc in loc_to_letter:
                continue
            if idx >= len(string.ascii_uppercase):
                continue  # >26 appendices: leave unmapped rather than crash
            loc_to_letter[loc] = string.ascii_uppercase[idx]
            idx += 1
    return loc_to_letter


def _relabel(kind: str, loc: str, loc_to_letter: dict[str, str]) -> str:
    """Return the materialised text for a cross-reference, remapping the
    leading number to an appendix letter when it points into an appendix."""
    head, rest = _split_location(loc)
    if head in loc_to_letter:
        new_kind = _APPENDIX_KIND.get(kind, kind)
        return f"{new_kind} {loc_to_letter[head]}{rest}"
    return f"{kind} {loc}"


def _resolve_label_from_anchor(
    span: etree._Element, root: etree._Element
) -> tuple[str, str] | None:
    """Resolve ``(kind, location)`` from the parent ``<a>``'s target id.

    Walks up to the immediate ``<a>`` parent, reads its ``href``, strips the
    leading ``#``, and dispatches the prefix through :data:`_PREFIX_LABEL`. If
    the prefix is known and an element with the matching id carries a
    ``data-location`` attribute, returns ``(label, location)`` from that
    target. Returns ``None`` otherwise so the caller can fall back to the
    span's own ``data-localized-kind``/``data-location`` attributes (the
    pre-fix back-compat path that keeps existing fixtures working).
    """
    parent = span.getparent()
    if parent is None or parent.tag != "a":
        return None
    href = (parent.get("href") or "").strip()
    if not href.startswith("#"):
        return None
    target_id = href[1:]
    if not target_id:
        return None
    for prefix, label in _PREFIX_LABEL.items():
        if not target_id.startswith(prefix):
            continue
        # Lookup via a literal-comparison xpath so ids containing punctuation
        # (e.g. ``sec:doc-spread``) don't need escaping. ``concat`` is the
        # idiomatic way to quote arbitrary strings inside an xpath predicate.
        targets = root.xpath(
            ".//*[@id=$tid]", tid=target_id
        )
        for target in targets:
            loc = (target.get("data-location") or "").strip()
            if loc:
                return label, loc
        # Known prefix but no usable target — let the caller fall back to
        # the span's own attributes rather than guessing the location.
        return None
    return None


def tag_appendix_toc_entries(
    root: etree._Element, loc_to_letter: dict[str, str]
) -> int:
    """Add ``class="appendix-toc-entry"`` to every ToC ``<li>`` whose
    location points into an appendix (chapter-level or subsection), so the
    stylesheet can suppress its auto-number prefix regardless of the
    heading id. Returns the number of entries tagged."""
    if not loc_to_letter:
        return 0
    count = 0
    for li in root.xpath(".//li[@data-target-id and @data-location]"):
        head = _split_location((li.get("data-location") or "").strip())[0]
        if head not in loc_to_letter:
            continue
        classes = (li.get("class") or "").split()
        if "appendix-toc-entry" not in classes:
            classes.append("appendix-toc-entry")
            li.set("class", " ".join(classes))
            count += 1
    return count


def relabel_appendix_floats(
    root: etree._Element, loc_to_letter: dict[str, str]
) -> int:
    """Remap appendix float numbering from the global chapter number to the
    appendix letter, so a caption renders "Table B.4" / "Figure B.1" instead
    of "Table 12.4" / "Figure 12.1".

    Two carriers hold the rendered number, both keyed off the same
    chapter->letter map as the cross-references:

    * **Float captions** — ``<caption>`` / ``<figcaption>`` carry
      ``data-location="12.4"`` and the global stylesheet paints the visible
      number from ``attr(data-location)`` (the ``[data-location]::before``
      rule). Rewriting the attribute to ``"B.4"`` flips the rendered label
      without disturbing the cross-reference path: the float id lives on the
      ``<table>`` / ``<figure>``, and the inline cross-ref span is relabelled
      separately, so caption and reference independently land on the letter.
    * **List-of-Tables / List-of-Figures rows** — ``<td class="loc">12.4</td>``
      holds the number as DOM text; rewrite the text in place.

    Idempotent: a second pass sees ``"B.4"`` whose head ``"B"`` is absent from
    the numeric map, so nothing changes. No-op without an appendix container.

    Returns the number of carriers rewritten.
    """
    if not loc_to_letter:
        return 0
    count = 0
    captions = root.xpath(
        ".//caption[@data-location] | .//figcaption[@data-location]"
    )
    for cap in captions:
        head, rest = _split_location((cap.get("data-location") or "").strip())
        if head in loc_to_letter:
            cap.set("data-location", f"{loc_to_letter[head]}{rest}")
            count += 1
    loc_cells = root.xpath(
        ".//td[contains(concat(' ', normalize-space(@class), ' '), ' loc ')]"
    )
    for td in loc_cells:
        text = (td.text or "").strip()
        if not text:
            continue
        head, rest = _split_location(text)
        if head in loc_to_letter:
            td.text = f"{loc_to_letter[head]}{rest}"
            count += 1
    return count


def materialise_cross_references(root: etree._Element) -> int:
    """Inject the data-attribute-derived text into every empty
    ``<span class="cross-reference">`` descendant of ``root``.

    Cross-references into an appendix are relabelled ("Chapter 14" ->
    "Appendix C", see module docstring), and appendix ToC entries are
    tagged for stylesheet number-suppression.

    Idempotent: a span already carrying ``data-text-materialised="1"`` is
    skipped, so running the postprocessor twice produces the same output.

    Returns the number of spans materialised.
    """
    loc_to_letter = build_appendix_label_map(root)
    count = 0
    # Quarkdown's CSS targets `[data-location]::before` rather than
    # `.cross-reference::before`, but in practice every Quarkdown-emitted
    # cross-reference *also* carries class="cross-reference", and other
    # `[data-location]` carriers (h1, h2, li with custom labels) are
    # styled by chapter-prefix rules not by the inline cross-ref rule.
    # Anchoring on the class is therefore the safer, narrower selector
    # and matches the CSS suppression rule we ship alongside this fix.
    xpath = ".//span[contains(concat(' ', normalize-space(@class), ' '), ' cross-reference ')]"
    for span in root.xpath(xpath):
        if span.get("data-text-materialised") == "1":
            continue
        if (span.text or "").strip():
            # Already carries real text (e.g. user-overridden in source).
            # Mark it materialised so the CSS rule suppresses the
            # ::before duplication, but don't overwrite.
            span.set("data-text-materialised", "1")
            continue
        # Prefer the parent-anchor prefix dispatch: Quarkdown stamps every
        # cross-ref span with ``data-localized-kind="Chapter"``, regardless
        # of whether the target is a chapter heading, a section heading, a
        # figure, or a table. The link's href encodes the target's id
        # prefix (``sec:``, ``fig:``, …) which is the authoritative signal
        # for the rendered label noun. Falls back to the span's own
        # attributes when the parent is absent, the prefix is unknown, or
        # the target element cannot be located (back-compat with fixtures
        # that wire ``data-localized-kind`` directly on the span).
        resolved = _resolve_label_from_anchor(span, root)
        if resolved is not None:
            kind, loc = resolved
        else:
            kind = (span.get("data-localized-kind") or "").strip()
            loc = (span.get("data-location") or "").strip()
        if not (kind and loc):
            # Malformed cross-ref (missing attributes) — leave it for
            # the build/lint step to surface; do not invent text.
            continue
        # The Quarkdown CSS rule joins kind+loc with a literal space and
        # optionally appends `var(--qd-label-suffix)`. The suffix is "."
        # for headings + list items only and "" (empty) for inline
        # cross-references. Our class-anchored selector targets only
        # inline cross-refs, so the suffix is always empty here. Appendix
        # targets are relabelled ("Chapter 14" -> "Appendix C").
        span.text = _relabel(kind, loc, loc_to_letter)
        span.set("data-text-materialised", "1")
        count += 1
    relabel_appendix_floats(root, loc_to_letter)
    tag_appendix_toc_entries(root, loc_to_letter)
    return count
