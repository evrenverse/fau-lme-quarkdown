"""Tests for the cross-reference text materialisation postprocessor step.

Locks in the fix for the PagedJS-zero-width-span bug where empty
``<span class="cross-reference">`` elements (whose text is injected via
CSS ``::before`` ``content: attr(...)``) cause PagedJS to over-pack
lines: PagedJS measures DOM textContent (which is empty), Chromium
later paints the attr()-text inside the span, and overflowing glyphs
get clipped during ``page.pdf()``. The materialisation injects the
rendered text into the span's DOM textContent so PagedJS sees the real
line width.
"""

from lxml import etree
from lxml import html as lxml_html

from postprocess_links.crossrefs import (
    build_appendix_label_map,
    materialise_cross_references,
    relabel_appendix_floats,
)


def parse_fragment(html: str) -> "lxml_html.HtmlElement":
    return lxml_html.fragment_fromstring(html, create_parent="body")


def test_materialises_chapter_cross_reference() -> None:
    root = parse_fragment(
        '<p>see <a href="#ch:foo"><span class="cross-reference" '
        'data-location="6.3" data-localized-kind="Chapter"></span></a>.</p>'
    )
    n = materialise_cross_references(root)
    assert n == 1
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "Chapter 6.3"
    assert span.get("data-text-materialised") == "1"


def test_materialises_figure_and_table_cross_references() -> None:
    root = parse_fragment(
        '<p>'
        '<a href="#fig:x"><span class="cross-reference" '
        'data-location="2.1" data-localized-kind="Figure"></span></a> and '
        '<a href="#tab:y"><span class="cross-reference" '
        'data-location="4.2" data-localized-kind="Table"></span></a>.'
        '</p>'
    )
    n = materialise_cross_references(root)
    assert n == 2
    spans = root.findall(".//span[@class='cross-reference']")
    assert spans[0].text == "Figure 2.1"
    assert spans[1].text == "Table 4.2"


def test_idempotent_on_already_materialised_span() -> None:
    """Running the materialiser twice produces the same DOM (no
    double-injection, no append). Defends against accidental re-runs of
    the postprocessor."""
    root = parse_fragment(
        '<p><span class="cross-reference" data-location="1" '
        'data-localized-kind="Chapter"></span></p>'
    )
    n1 = materialise_cross_references(root)
    n2 = materialise_cross_references(root)
    assert n1 == 1
    assert n2 == 0  # second run injects nothing
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "Chapter 1"
    assert span.get("data-text-materialised") == "1"


def test_skips_span_with_existing_text_content() -> None:
    """A cross-reference span that already carries text (e.g. user
    override in source) must not be overwritten — only flagged so the
    CSS suppresses the now-duplicate ::before."""
    root = parse_fragment(
        '<p><span class="cross-reference" data-location="5.1" '
        'data-localized-kind="Chapter">custom label</span></p>'
    )
    materialise_cross_references(root)
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "custom label"  # preserved
    assert span.get("data-text-materialised") == "1"  # but flagged


def test_skips_span_with_missing_attributes() -> None:
    """A malformed cross-reference (missing data-location or
    data-localized-kind) is left untouched so the build-stage lint can
    flag it. We never invent text content."""
    root = parse_fragment(
        '<p>'
        '<span class="cross-reference" data-location="5.1"></span>'
        '<span class="cross-reference" data-localized-kind="Chapter"></span>'
        '</p>'
    )
    n = materialise_cross_references(root)
    assert n == 0
    for span in root.findall(".//span[@class='cross-reference']"):
        assert span.text in (None, "")
        assert span.get("data-text-materialised") is None


def test_does_not_touch_non_cross_reference_spans() -> None:
    """Class-anchored selector: spans with [data-location] but without
    .cross-reference (e.g. headings, captions, list-item labels) must
    be left alone — their text comes from a different mechanism."""
    root = parse_fragment(
        '<p>'
        '<span class="caption" data-location="2.1"></span>'
        '<h2 data-location="3"></h2>'
        '<li data-location="1.a"></li>'
        '</p>'
    )
    n = materialise_cross_references(root)
    assert n == 0
    for el in root.iter():
        assert el.get("data-text-materialised") is None


def test_class_match_handles_multiple_classes() -> None:
    """The selector must match a span whose class attribute contains
    'cross-reference' alongside other classes (e.g. theme additions
    like 'fau-lme-cross-ref' or PagedJS-injected helper classes)."""
    root = parse_fragment(
        '<p><span class="cross-reference fau-lme-emphasis" '
        'data-location="7" data-localized-kind="Chapter"></span></p>'
    )
    materialise_cross_references(root)
    span = root.find(".//span")
    assert span.text == "Chapter 7"
    assert span.get("data-text-materialised") == "1"


# --- Appendix re-labelling (Quarkdown numbers appendices as chapters 12+) ---

_APPENDIX_CONTAINER = (
    '<div class="container appendix">'
    '<h1 id="appendix-a-prompts" data-location="12">Appendix A: Prompts</h1>'
    '<h1 id="appendix-b-tables" data-location="13">Appendix B: Tables</h1>'
    '<h1 id="app:quest-rubric" data-location="14">Appendix C: Rubric</h1>'
    '</div>'
)


def test_remaps_appendix_chapter_cross_reference() -> None:
    """A `.ref` to an appendix heading materialises as 'Appendix C', not
    'Chapter 14' — even when the appendix carries a custom id that does not
    start with `appendix-` (the real bug)."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<p>see <a href="#app:quest-rubric"><span class="cross-reference" '
        'data-location="14" data-localized-kind="Chapter"></span></a>.</p>'
    )
    materialise_cross_references(root)
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "Appendix C"


def test_remaps_appendix_subsection_keeps_kind() -> None:
    """A `.ref` into an appendix subsection keeps its kind but maps the
    leading chapter-number to the letter: 'Section 14.2' -> 'Section C.2',
    'Table 14.1' -> 'Table C.1'."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<p>'
        '<a href="#s"><span class="cross-reference" '
        'data-location="14.2" data-localized-kind="Section"></span></a> '
        '<a href="#t"><span class="cross-reference" '
        'data-location="14.1" data-localized-kind="Table"></span></a>'
        '</p>'
    )
    materialise_cross_references(root)
    spans = root.findall(".//span[@class='cross-reference']")
    assert spans[0].text == "Section C.2"
    assert spans[1].text == "Table C.1"


def test_non_appendix_reference_unaffected_when_appendix_present() -> None:
    """With an appendix container present, an ordinary chapter reference is
    still 'Chapter 6.3' — the remap fires only for appendix locations."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<p><a href="#sec:x"><span class="cross-reference" '
        'data-location="6.3" data-localized-kind="Chapter"></span></a></p>'
    )
    materialise_cross_references(root)
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "Chapter 6.3"


def test_tags_appendix_toc_entries_not_chapter_entries() -> None:
    """ToC <li>s pointing into an appendix (chapter-level or subsection) get
    `appendix-toc-entry` so the stylesheet suppresses their auto-number
    prefix regardless of the heading id; chapter entries are untouched."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<ul>'
        '<li data-target-id="app:quest-rubric" data-location="14">C</li>'
        '<li data-target-id="quest-sub" data-location="14.2">sub</li>'
        '<li data-target-id="ch:intro" data-location="1">Intro</li>'
        '</ul>'
    )
    materialise_cross_references(root)
    appx = root.xpath(".//li[@data-target-id='app:quest-rubric']")[0]
    appx_sub = root.xpath(".//li[@data-target-id='quest-sub']")[0]
    intro = root.xpath(".//li[@data-target-id='ch:intro']")[0]
    assert "appendix-toc-entry" in (appx.get("class") or "")
    assert "appendix-toc-entry" in (appx_sub.get("class") or "")
    assert "appendix-toc-entry" not in (intro.get("class") or "")


def test_appendix_remap_noop_without_container() -> None:
    """No appendix container -> map is empty -> ordinary behaviour, so a
    location-14 reference stays 'Chapter 14' (defends the body-chapter case
    and keeps the materialiser safe on appendix-free documents)."""
    root = parse_fragment(
        '<p><span class="cross-reference" data-location="14" '
        'data-localized-kind="Chapter"></span></p>'
    )
    materialise_cross_references(root)
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "Chapter 14"


# --- Prefix-based label dispatch (sec: → Section, ch: → Chapter, …) ---


def test_sec_ref_renders_as_section_label() -> None:
    """`.ref {sec:foo}` renders as 'Section X.Y', not 'Chapter X.Y'."""
    html = (
        "<html><body>"
        "<h1 id='ch:bg' data-location='2'>Background</h1>"
        "<h2 id='sec:docspread' data-location='2.6'>Documents</h2>"
        "<p>See <a href='#sec:docspread'>"
        "<span class='cross-reference'></span></a> for openpyxl details.</p>"
        "</body></html>"
    )
    root = etree.fromstring(html)
    materialise_cross_references(root)
    rendered = etree.tostring(root, encoding="unicode")
    assert "Section 2.6" in rendered
    assert "Chapter 2.6" not in rendered

def test_ch_ref_still_renders_as_chapter_label_regression() -> None:
    """Regression: `.ref {ch:foo}` keeps rendering as 'Chapter X'."""
    html = (
        "<html><body>"
        "<h1 id='ch:bg' data-location='2'>Background</h1>"
        "<p>See <a href='#ch:bg'>"
        "<span class='cross-reference'></span></a> for the LLM stack.</p>"
        "</body></html>"
    )
    root = etree.fromstring(html)
    materialise_cross_references(root)
    rendered = etree.tostring(root, encoding="unicode")
    assert "Chapter 2" in rendered
    assert "Section" not in rendered


# --- Appendix float caption + List-of-Tables/Figures relabelling ---
# (_APPENDIX_CONTAINER maps chapter 12->A, 13->B, 14->C)


def test_relabels_appendix_caption_data_location() -> None:
    """An appendix float caption's data-location is remapped 13.x -> B.x so
    the CSS `[data-location]::before` renders 'Table B.4' / 'Figure B.1',
    matching its cross-reference. A body caption (chapter 8) is untouched."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<table id="tab:r"><caption data-location="13.4" '
        'data-localized-kind="Table">Repeat metrics.</caption></table>'
        + '<figure><figcaption data-location="13.1" '
        'data-localized-kind="Figure">Heatmap.</figcaption></figure>'
        + '<table id="tab:body"><caption data-location="8.1" '
        'data-localized-kind="Table">Body table.</caption></table>'
    )
    loc_to_letter = build_appendix_label_map(root)
    n = relabel_appendix_floats(root, loc_to_letter)
    assert n == 2
    appx_cap = root.xpath(".//table[@id='tab:r']/caption")[0]
    assert appx_cap.get("data-location") == "B.4"
    assert root.find(".//figcaption").get("data-location") == "B.1"
    body_cap = root.xpath(".//table[@id='tab:body']/caption")[0]
    assert body_cap.get("data-location") == "8.1"  # untouched


def test_relabels_list_of_tables_loc_cells() -> None:
    """List-of-Tables / List-of-Figures rows hold the float number as DOM
    text in <td class="loc">; appendix rows are remapped 13.x -> B.x, body
    rows (8.x) stay numeric."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<table class="list-of-tables"><tbody>'
        '<tr><td class="loc">8.1</td><td class="cap">Body</td></tr>'
        '<tr><td class="loc">13.4</td><td class="cap">Appendix</td></tr>'
        '</tbody></table>'
    )
    loc_to_letter = build_appendix_label_map(root)
    relabel_appendix_floats(root, loc_to_letter)
    locs = [td.text for td in root.xpath(".//td[@class='loc']")]
    assert locs == ["8.1", "B.4"]


def test_relabel_appendix_floats_idempotent() -> None:
    """A second pass sees 'B.2' (head 'B' not in the numeric map) and changes
    nothing — safe against accidental re-runs of the postprocessor."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<caption data-location="13.2" data-localized-kind="Table">X</caption>'
    )
    loc_to_letter = build_appendix_label_map(root)
    n1 = relabel_appendix_floats(root, loc_to_letter)
    n2 = relabel_appendix_floats(root, loc_to_letter)
    assert n1 == 1
    assert n2 == 0
    assert root.find(".//caption").get("data-location") == "B.2"


def test_materialise_also_relabels_appendix_caption() -> None:
    """The orchestrating materialise step relabels appendix float captions
    alongside cross-references, so caption and reference agree on 'B.x'."""
    root = parse_fragment(
        _APPENDIX_CONTAINER
        + '<table id="tab:r"><caption data-location="13.3" '
        'data-localized-kind="Table">Repeat.</caption></table>'
        + '<p><a href="#tab:r"><span class="cross-reference" '
        'data-location="13.3" data-localized-kind="Table"></span></a></p>'
    )
    materialise_cross_references(root)
    assert root.find(".//caption").get("data-location") == "B.3"
    span = root.find(".//span[@class='cross-reference']")
    assert span.text == "Table B.3"


def test_relabel_appendix_floats_noop_without_container() -> None:
    """No appendix container -> empty map -> captions left numeric (defends
    the body-only document case)."""
    root = parse_fragment(
        '<caption data-location="13.4" data-localized-kind="Table">X</caption>'
    )
    n = relabel_appendix_floats(root, build_appendix_label_map(root))
    assert n == 0
    assert root.find(".//caption").get("data-location") == "13.4"
