"""Tests for the lxml-based text-node walker that respects skip zones."""

import re

from lxml import html as lxml_html

from postprocess_links.dom_rewriter import iter_text_nodes, replace_text_with_anchor


# Default skip set used by the citation rewriter.
CITE_SKIP_TAGS = frozenset({"code", "pre", "kbd", "samp", "a"})
CITE_SKIP_CLASSES = ("katex", "bibliography")


def parse(s: str):
    return lxml_html.fragment_fromstring(s, create_parent="div")


def test_iter_visits_plain_text() -> None:
    doc = parse("<p>hello world</p>")
    texts = [(t.text, t.role) for t in iter_text_nodes(doc, CITE_SKIP_TAGS, CITE_SKIP_CLASSES)]
    assert texts == [("hello world", "text")]


def test_iter_skips_code_block() -> None:
    doc = parse("<p>before <code>HTTP</code> after</p>")
    texts = [t.text for t in iter_text_nodes(doc, CITE_SKIP_TAGS, CITE_SKIP_CLASSES)]
    assert texts == ["before ", " after"]


def test_iter_skips_class_substring() -> None:
    doc = parse(
        '<div><p>outside</p><div class="bibliography-entry">inside</div></div>'
    )
    texts = [t.text for t in iter_text_nodes(doc, CITE_SKIP_TAGS, CITE_SKIP_CLASSES)]
    assert texts == ["outside"]


def test_replace_text_with_anchor_simple() -> None:
    doc = parse("<p>see [Pet07] for details</p>")
    p = doc[0]
    text_node = next(iter_text_nodes(p, CITE_SKIP_TAGS, CITE_SKIP_CLASSES))
    pattern = re.compile(r"\[Pet07\]")
    replace_text_with_anchor(
        text_node,
        pattern,
        lambda match: ("#bib-pet07", "bib-cite", match.group(0)),
    )
    out = lxml_html.tostring(p, encoding="unicode")
    assert 'href="#bib-pet07"' in out
    assert ">[Pet07]<" in out
    assert "see " in out and " for details" in out


def test_replace_preserves_surrounding_tail_text() -> None:
    # tail-position text: <em>x</em>HTTP rest
    doc = parse("<p><em>x</em> HTTP rest</p>")
    p = doc[0]
    tail_node = list(iter_text_nodes(p, CITE_SKIP_TAGS, CITE_SKIP_CLASSES))[-1]
    pattern = re.compile(r"\bHTTP\b")
    replace_text_with_anchor(
        tail_node,
        pattern,
        lambda m: ("#acro-http", "acro-link", m.group(0)),
    )
    out = lxml_html.tostring(p, encoding="unicode")
    assert 'href="#acro-http"' in out
    assert " rest" in out


def test_replace_multiple_matches_in_one_node() -> None:
    doc = parse("<p>HTTP and HTTP again</p>")
    p = doc[0]
    text_node = next(iter_text_nodes(p, CITE_SKIP_TAGS, CITE_SKIP_CLASSES))
    pattern = re.compile(r"\bHTTP\b")
    replace_text_with_anchor(
        text_node,
        pattern,
        lambda m: ("#acro-http", "acro-link", m.group(0)),
    )
    out = lxml_html.tostring(p, encoding="unicode")
    assert out.count('href="#acro-http"') == 2
