"""lxml-based text-node walker with skip-zone awareness, plus an
in-place replacement helper that splits a text node and inserts anchor
elements between the surviving text fragments.

The walker yields TextNode records, each carrying (a) the text content,
(b) whether it is element.text or element.tail, and (c) the owning
element. Callers mutate text via the element accessors, not via the
TextNode (text nodes in lxml are immutable strings).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterator

from lxml import etree

# A callback returns (href, css_class, displayed_text) for a regex match,
# or None to leave the match untouched.
AnchorSpec = tuple[str, str, str]
AnchorCallback = Callable[[re.Match], AnchorSpec | None]


@dataclass
class TextNode:
    """A text-position handle: either element.text (role='text') or
    element.tail (role='tail'). The element pointer + role uniquely
    identify the mutation site."""

    element: etree._Element
    role: str  # "text" or "tail"

    @property
    def text(self) -> str | None:
        return self.element.text if self.role == "text" else self.element.tail


def _is_skipped(el: etree._Element, skip_tags: frozenset[str], skip_class_substrings: tuple[str, ...]) -> bool:
    if el.tag in skip_tags:
        return True
    cls = el.get("class", "")
    return any(needle in cls for needle in skip_class_substrings)


def iter_text_nodes(
    root: etree._Element,
    skip_tags: frozenset[str],
    skip_class_substrings: tuple[str, ...],
) -> Iterator[TextNode]:
    """Yield every text/tail position in `root`'s subtree, skipping
    elements (and their entire subtree) whose tag is in `skip_tags` or
    whose class attribute contains any of `skip_class_substrings`."""
    if _is_skipped(root, skip_tags, skip_class_substrings):
        return
    if root.text:
        yield TextNode(root, "text")
    for child in list(root):
        # Recurse into the child (its own text + descendants).
        yield from iter_text_nodes(child, skip_tags, skip_class_substrings)
        # The child's tail belongs to the parent's content stream and is
        # rewritable regardless of whether the child itself was skipped:
        # skipping a `<code>` block must NOT also disable rewrites in the
        # text that follows the `</code>`.
        if child.tail:
            yield TextNode(child, "tail")


def replace_text_with_anchor(
    node: TextNode,
    pattern: re.Pattern[str],
    make_anchor: AnchorCallback,
) -> None:
    """Replace every `pattern` match in `node`'s text with an <a> element.

    Splits the text into alternating string/match pieces, then rebuilds
    the parent's child list so that the text fragments and inserted <a>
    elements appear in order. Mutates the element in-place.
    """
    original = node.text or ""
    matches = list(pattern.finditer(original))
    if not matches:
        return

    # Decide which matches we actually rewrite.
    decisions: list[tuple[re.Match, AnchorSpec]] = []
    for m in matches:
        spec = make_anchor(m)
        if spec is not None:
            decisions.append((m, spec))
    if not decisions:
        return

    # Split the original text around the matches we keep.
    parent = node.element
    if node.role == "text":
        # The new pieces become parent.text (first fragment) +
        # a series of <a> children at the FRONT of the existing child list.
        pieces, anchors = _split_with_anchors(original, decisions)
        # Remove old text; we will rebuild via .text + inserted children.
        parent.text = pieces[0]
        # Insert anchors and intermediate text fragments before existing
        # children (in reverse order so insertions stay in the right order).
        cursor_index = 0
        for anchor, follow_text in zip(anchors, pieces[1:]):
            parent.insert(cursor_index, anchor)
            anchor.tail = follow_text
            cursor_index += 1
        # Existing children continue to live AFTER the inserted block —
        # parent.insert(cursor_index, …) above means children at index
        # cursor_index onwards are the originals.
    else:
        # role == "tail": the text lives _after_ parent. We rebuild the
        # tail and insert anchor siblings into parent.getparent() right
        # after parent.
        grandparent = parent.getparent()
        assert grandparent is not None, "tail text requires a grandparent"
        pieces, anchors = _split_with_anchors(original, decisions)
        parent.tail = pieces[0]
        insert_at = list(grandparent).index(parent) + 1
        for anchor, follow_text in zip(anchors, pieces[1:]):
            grandparent.insert(insert_at, anchor)
            anchor.tail = follow_text
            insert_at += 1


def _split_with_anchors(
    text: str, decisions: list[tuple[re.Match, AnchorSpec]]
) -> tuple[list[str], list[etree._Element]]:
    """Return (text_pieces, anchor_elements) where:
    text_pieces[0] is the prefix before the first match, text_pieces[i+1]
    follows anchor_elements[i]. Always len(pieces) == len(anchors) + 1.
    """
    pieces: list[str] = []
    anchors: list[etree._Element] = []
    cursor = 0
    for match, (href, css_class, displayed) in decisions:
        pieces.append(text[cursor : match.start()])
        a = etree.Element("a", attrib={"href": href, "class": css_class})
        a.text = displayed
        anchors.append(a)
        cursor = match.end()
    pieces.append(text[cursor:])
    return pieces, anchors
