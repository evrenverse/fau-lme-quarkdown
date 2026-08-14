"""Integration tests for citation rewriting: body citations get anchors,
bibliography entries get IDs, skip zones are respected."""

from lxml import html as lxml_html

from postprocess_links.citations import (
    rewrite_citations,
    drop_uncited_bib_entries,
    find_unused_bib_labels,
)


BIBMAP = {"Pet07": "peffers2007dsr", "TED24": "ted2024statistics"}


def parse(s: str):
    return lxml_html.fragment_fromstring(s, create_parent="div")


def test_body_citation_becomes_anchor() -> None:
    doc = parse(
        '<div>'
        '<p>see [Pet07] for details</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">Peffers, K. ...</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Forward link to the bibliography entry; the first occurrence also
    # carries the back-reference target id (id="cite-pet07").
    assert 'href="#bib-pet07"' in out
    assert 'class="bib-cite"' in out
    assert '>[Pet07]</a>' in out


def test_bibliography_entry_gets_id() -> None:
    doc = parse(
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">...</span>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="bib-pet07"' in out


def test_citation_inside_code_skipped() -> None:
    doc = parse(
        '<div>'
        '<p>see [Pet07] here</p>'
        '<pre><code>[Pet07]</code></pre>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Exactly one body anchor; the <code> occurrence remains plain text.
    assert out.count('href="#bib-pet07"') == 1
    assert '<code>[Pet07]</code>' in out


def test_unknown_label_left_untouched() -> None:
    doc = parse('<div><p>see [fill] later</p></div>')
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "[fill]" in out
    assert "<a " not in out


def test_citation_inside_bibliography_skipped() -> None:
    # The body label inside the bibliography (the one that gets the `id`)
    # must NOT also be wrapped as a body-style link.
    doc = parse(
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">...</span>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "<a " not in out
    assert 'id="bib-pet07"' in out


def test_multiple_citations_one_paragraph() -> None:
    doc = parse(
        '<div>'
        '<p>see [Pet07] and [TED24] together</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-label">[TED24]</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'href="#bib-pet07"' in out
    assert 'href="#bib-ted24"' in out


def test_idempotent() -> None:
    """Running twice produces byte-identical HTML — pre-existing anchors
    are skipped (no double-wrap)."""
    doc = parse(
        '<div>'
        '<p>see [Pet07] here</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    first = lxml_html.tostring(doc, encoding="unicode")
    rewrite_citations(doc, BIBMAP)
    second = lxml_html.tostring(doc, encoding="unicode")
    assert first == second


# --- Back-references: bibliography label -> first body occurrence ----------


def test_bib_label_links_back_to_first_occurrence() -> None:
    doc = parse(
        '<div>'
        '<p>first [Pet07] use</p>'
        '<p>second [Pet07] use</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">Peffers ...</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Only the first occurrence is the back-reference target.
    assert out.count('id="cite-pet07"') == 1
    # The bibliography label is wrapped in a link to that target.
    assert '<a href="#cite-pet07" class="bib-backref">[Pet07]</a>' in out
    # The entry id is preserved on the span (forward-link target intact).
    assert 'id="bib-pet07"' in out


def test_uncited_label_has_no_backref() -> None:
    # TED24 is in the bibliography but never cited -> no back-link target,
    # so the label is left as plain text (no <a>).
    doc = parse(
        '<div>'
        '<p>only [Pet07] is cited</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-label">[TED24]</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'href="#cite-ted24"' not in out
    # TED24 label survives rewrite_citations untouched (dropping happens later).
    assert '>[TED24]</span>' in out


# --- Dynamic reference list: drop entries the body never cites -------------


def test_drop_uncited_entry_removes_label_and_content() -> None:
    doc = parse(
        '<div>'
        '<p>see [Pet07] here</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">Peffers ...</span>'
        '<span class="bibliography-entry-label">[TED24]</span>'
        '<span class="bibliography-entry-content">DOI statistics ...</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    dropped = drop_uncited_bib_entries(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert dropped == {"bib-ted24"}
    assert "DOI statistics" not in out          # uncited content gone
    assert ">[TED24]</" not in out              # uncited label gone
    assert "Peffers" in out                     # cited entry kept
    assert 'id="bib-pet07"' in out


def test_drop_keeps_all_cited() -> None:
    doc = parse(
        '<div>'
        '<p>see [Pet07] and [TED24]</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">Peffers ...</span>'
        '<span class="bibliography-entry-label">[TED24]</span>'
        '<span class="bibliography-entry-content">DOI statistics ...</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    dropped = drop_uncited_bib_entries(doc)
    assert dropped == set()


def test_find_unused_bib_labels_flags_orphans() -> None:
    doc = parse('<div><p>see [Pet07] only</p></div>')
    rewrite_citations(doc, BIBMAP)
    assert find_unused_bib_labels(doc, BIBMAP) == {"TED24"}


def test_find_unused_bib_labels_empty_when_all_cited() -> None:
    doc = parse('<div><p>see [Pet07] and [TED24]</p></div>')
    rewrite_citations(doc, BIBMAP)
    assert find_unused_bib_labels(doc, BIBMAP) == set()


def test_drop_idempotent() -> None:
    doc = parse(
        '<div>'
        '<p>see [Pet07] here</p>'
        '<div class="bibliography">'
        '<span class="bibliography-entry-label">[Pet07]</span>'
        '<span class="bibliography-entry-content">Peffers ...</span>'
        '<span class="bibliography-entry-label">[TED24]</span>'
        '<span class="bibliography-entry-content">DOI statistics ...</span>'
        '</div>'
        '</div>'
    )
    rewrite_citations(doc, BIBMAP)
    drop_uncited_bib_entries(doc)
    first = lxml_html.tostring(doc, encoding="unicode")
    drop_uncited_bib_entries(doc)
    second = lxml_html.tostring(doc, encoding="unicode")
    assert first == second
