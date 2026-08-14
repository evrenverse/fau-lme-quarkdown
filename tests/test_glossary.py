"""Tests for the dynamic glossary: slug/term mapping, bidirectional anchor
linking, dead-row pruning, the un-glossed-italics hard gate, and the
rewrite_glossary orchestrator."""
from __future__ import annotations

from lxml import html

from postprocess_links.glossary import _slugify, glossary_terms
from postprocess_links.glossary import link_body_occurrences, _find_glossary_table
from postprocess_links.glossary import set_glossary_ids, mark_first_occurrences
from postprocess_links.glossary import remove_dead_glossary_rows
from postprocess_links.glossary import find_unglossed_italics
from postprocess_links.glossary import rewrite_glossary
from postprocess_links.glossary import (
    _row_line_estimate,
    _chunk_glossary_rows,
    paginate_glossary,
    _GLOSS_BUDGET_REST,
)


def _doc(body_html: str) -> html.HtmlElement:
    return html.fromstring(f"<html><body>{body_html}</body></html>")


_GLOSS_TBL = '''
<h1>Appendix C: Glossary</h1>
<table>
  <thead><tr><th>DE term</th><th>EN gloss</th></tr></thead>
  <tbody>
    <tr><td><strong>Zeilenhöhe</strong></td><td>adequacy</td></tr>
    <tr><td><strong>Abkürzungsverzeichnis (LV)</strong></td><td>list of abbreviations</td></tr>
  </tbody>
</table>
'''


def test_slugify_folds_umlauts() -> None:
    assert _slugify("Zeilenhöhe") == "zeilenhoehe"
    assert _slugify("Abkürzungsverzeichnis (LV)") == "abkuerzungsverzeichnis"
    assert _slugify("Sub-agent") == "sub-agent"


def test_glossary_terms_maps_term_to_slug() -> None:
    terms = glossary_terms(_doc(_GLOSS_TBL))
    assert terms == {
        "Zeilenhöhe": "zeilenhoehe",
        "Abkürzungsverzeichnis": "abkuerzungsverzeichnis",
    }


_BODY = '''
<p>The <em>Zeilenhöhe</em> check applies. Later the <em>Zeilenhöhe</em> recurs.</p>
<p>Plain Zeilenhöhe stays plain.</p>
<p>A phrase: <em>Zeilenhöhe der Absätze</em>.</p>
''' + _GLOSS_TBL


def _linked(root):
    return [(a.get("href"), a.text) for a in root.iter("a") if "gloss-link" in (a.get("class") or "")]


def test_links_every_italic_occurrence_not_plain():
    root = _doc(_BODY)
    terms = glossary_terms(root)
    link_body_occurrences(root, terms, _find_glossary_table(root))
    links = _linked(root)
    # 2 standalone + 1 inside the phrase = 3 italic; the plain one and the
    # table <strong> are NOT linked.
    assert links == [
        ("#gloss-zeilenhoehe", "Zeilenhöhe"),
        ("#gloss-zeilenhoehe", "Zeilenhöhe"),
        ("#gloss-zeilenhoehe", "Zeilenhöhe"),
    ]
    # plain text survives verbatim
    assert "Plain Zeilenhöhe stays plain." in root.text_content()


def test_idempotent_linking():
    root = _doc(_BODY)
    terms = glossary_terms(root)
    tbl = _find_glossary_table(root)
    link_body_occurrences(root, terms, tbl)
    link_body_occurrences(root, terms, tbl)  # second pass = no-op
    assert len(_linked(root)) == 3


def test_skip_zone_ancestors_not_linked():
    # <em> inside the bibliography or a heading must NOT be linked, even though
    # the <em> itself carries no skip class (the ANCESTOR does).
    root = _doc(
        '<div class="bibliography"><p><em>Zeilenhöhe</em> in a title.</p></div>'
        '<h2><em>Zeilenhöhe</em> heading</h2>' + _GLOSS_TBL
    )
    terms = glossary_terms(root)
    link_body_occurrences(root, terms, _find_glossary_table(root))
    assert _linked(root) == []


def test_table_row_and_term_anchor():
    # New contract: a term is only made clickable when an exact body occurrence
    # exists (a #gloss-ref-SLUG target). So link + mark BEFORE set_glossary_ids.
    root = _doc('<p>The <em>Zeilenhöhe</em> check.</p>' + _GLOSS_TBL)
    terms = glossary_terms(root)
    tbl = _find_glossary_table(root)
    link_body_occurrences(root, terms, tbl)
    mark_first_occurrences(root, terms)
    set_glossary_ids(root, terms, tbl)
    # Zeilenhöhe has an exact body occurrence -> row id set AND clickable.
    tr = root.xpath('//tr[@id="gloss-zeilenhoehe"]')
    assert len(tr) == 1
    term_link = tr[0].xpath('.//strong/a')
    assert term_link[0].get("href") == "#gloss-ref-zeilenhoehe"
    assert term_link[0].text == "Zeilenhöhe"
    # Abkürzungsverzeichnis has NO body occurrence -> row id set but NOT clickable
    # (its <strong> stays plain text, no wrapping <a>; the cell keeps its raw
    # "(LV)" parenthetical, which is stripped only for the term *key*).
    lv = root.xpath('//tr[@id="gloss-abkuerzungsverzeichnis"]')
    assert len(lv) == 1
    assert lv[0].xpath('.//strong/a') == []
    assert lv[0].xpath('.//strong')[0].text == "Abkürzungsverzeichnis (LV)"


def test_only_first_italic_gets_jump_id():
    root = _doc(_BODY)
    terms = glossary_terms(root)
    tbl = _find_glossary_table(root)
    link_body_occurrences(root, terms, tbl)
    mark_first_occurrences(root, terms)
    ids = [a.get("id") for a in root.iter("a") if "gloss-link" in (a.get("class") or "")]
    # first carries the jump id, the rest don't
    assert ids == ["gloss-ref-zeilenhoehe", None, None]


def test_dead_row_dropped_when_no_italic_use():
    # Zeilenhöhe is italic in body; Abkürzungsverzeichnis never appears.
    root = _doc('<p>The <em>Zeilenhöhe</em> check.</p>' + _GLOSS_TBL)
    terms = glossary_terms(root)
    tbl = _find_glossary_table(root)
    set_glossary_ids(root, terms, tbl)
    link_body_occurrences(root, terms, tbl)
    dropped = remove_dead_glossary_rows(root, terms, tbl)
    assert dropped == {"Abkürzungsverzeichnis"}
    remaining = [s.text_content() for s in root.xpath('//tbody//strong')]
    # the surviving row's <strong> now wraps an <a>, so check via text
    assert "Zeilenhöhe" in " ".join(remaining)
    assert "Abkürzungsverzeichnis" not in " ".join(remaining)


def test_plain_only_term_is_dead():
    # term occurs ONLY plain (never italic) -> no anchor -> dropped.
    root = _doc('<p>Zeilenhöhe plain only.</p>' + _GLOSS_TBL)
    terms = glossary_terms(root)
    tbl = _find_glossary_table(root)
    set_glossary_ids(root, terms, tbl)
    link_body_occurrences(root, terms, tbl)
    dropped = remove_dead_glossary_rows(root, terms, tbl)
    assert "Zeilenhöhe" in dropped


def test_gate_flags_only_unbucketed_german_single_word():
    body = (
        '<p><em>Zwischenspeicher</em> here.</p>'        # german, not glossed -> FLAG
        '<p><em>Zeilenhöhe</em> here.</p>'       # glossed -> ok
        '<p><em>Strategy</em> here.</p>'              # in extra_ignore (--lint-ignore) -> ok
        '<p><em>RAG</em> here.</p>'                   # acronym-shape -> ok
        '<p><em>Modular RAG</em> here.</p>'           # multi-word -> ok
        '<p><em>Qualitäts-</em> here.</p>'            # hyphen fragment -> ok
        '<p><em>workflows</em> here.</p>'             # lowercase English -> ok (not a German noun)
        '<p><em>industry</em> here.</p>'              # lowercase code id -> ok
        '<div class="bibliography"><em>Auslastungsstatistik</em></div>'  # skip-zone ancestor -> ok
        + _GLOSS_TBL
    )
    root = _doc(body)
    terms = glossary_terms(root)
    flagged = find_unglossed_italics(
        root, terms, {"RAG": "rag"}, _find_glossary_table(root),
        extra_ignore=frozenset({"Strategy"}),
    )
    assert flagged == {"Zwischenspeicher"}


def test_rewrite_glossary_end_to_end():
    root = _doc(_BODY)
    dropped = rewrite_glossary(root)
    assert dropped == {"Abkürzungsverzeichnis"}            # never used -> dropped
    first = root.xpath('//a[@id="gloss-ref-zeilenhoehe"]')
    assert len(first) == 1 and first[0].get("href") == "#gloss-zeilenhoehe"
    row = root.xpath('//tr[@id="gloss-zeilenhoehe"]//strong/a')
    assert row[0].get("href") == "#gloss-ref-zeilenhoehe"  # table -> first occ
    assert rewrite_glossary(root) == set()                # idempotent second pass


# Finding #1 regression: after a rewrite pass the glossary <strong> wraps an
# <a> (<strong><a href="#gloss-ref-…">Term</a></strong>). The --check-only pass
# re-parses that ALREADY-rewritten HTML; reading strong.text would give "" and
# park every term. _strong_text/itertext must still recover the term.
def test_glossary_terms_robust_to_wrapped_anchor():
    rewritten_tbl = '''
<h1>Appendix C: Glossary</h1>
<table>
  <thead><tr><th>DE term</th><th>EN gloss</th></tr></thead>
  <tbody>
    <tr id="gloss-zeilenhoehe"><td><strong><a href="#gloss-ref-zeilenhoehe">Zeilenhöhe</a></strong></td><td>adequacy</td></tr>
    <tr><td><strong>Abkürzungsverzeichnis (LV)</strong></td><td>list of abbreviations</td></tr>
  </tbody>
</table>
'''
    terms = glossary_terms(_doc(rewritten_tbl))
    # The wrapped-<a> term is still recovered (not lost to an empty strong.text).
    assert terms == {
        "Zeilenhöhe": "zeilenhoehe",
        "Abkürzungsverzeichnis": "abkuerzungsverzeichnis",
    }


# Finding #2 regression: a term that occurs in the body ONLY as a compound /
# inflection (Zeilenhöhe inside Zeilenhöhenprüfung) must SURVIVE the
# dead-row filter (word-start match) but stay un-clickable (no exact target),
# while a term with an exact italic occurrence IS clickable.
def test_composite_only_term_survives_but_unlinked():
    body = (
        '<p>The <em>Zeilenhöhenprüfung</em> applies.</p>'   # compound only
        '<p>The <em>Abkürzungsverzeichnis</em> lists items.</p>'  # exact occurrence
        + _GLOSS_TBL
    )
    root = _doc(body)
    dropped = rewrite_glossary(root)
    # Zeilenhöhe appears only inside Zeilenhöhenprüfung -> NOT dropped.
    assert dropped == set()
    # Row survives and is listed...
    ausk_row = root.xpath('//tr[@id="gloss-zeilenhoehe"]')
    assert len(ausk_row) == 1
    # ...but its term is NOT a link (no exact jump target exists).
    assert ausk_row[0].xpath('.//strong/a') == []
    assert ausk_row[0].xpath('.//strong')[0].text == "Zeilenhöhe"
    # Abkürzungsverzeichnis has an exact italic occurrence -> IS clickable.
    lv_row = root.xpath('//tr[@id="gloss-abkuerzungsverzeichnis"]//strong/a')
    assert len(lv_row) == 1
    assert lv_row[0].get("href") == "#gloss-ref-abkuerzungsverzeichnis"


def test_dead_row_drops_ref_prefixed_slug():
    # Regression (final review): a term whose slug starts "ref-" (Ref-Objekt ->
    # gloss-ref-objekt) must still be prunable when unused. The old
    # `tid.startswith("gloss-ref-")` guard wrongly skipped such a row, so an
    # unused term stayed in the table.
    tbl = (
        '<h1>Glossary</h1><table><tbody>'
        '<tr><td><strong>Ref-Objekt</strong></td><td>reference object</td></tr>'
        '</tbody></table>'
    )
    root = _doc('<p>No italic use anywhere.</p>' + tbl)
    terms = glossary_terms(root)
    t = _find_glossary_table(root)
    set_glossary_ids(root, terms, t)
    link_body_occurrences(root, terms, t)
    dropped = remove_dead_glossary_rows(root, terms, t)
    assert "Ref-Objekt" in dropped
    assert root.xpath('//tbody/tr') == []


# --- auto-pagination (paginate_glossary) ----------------------------------

def _row(de: str, en: str = "x", desc: str = "y") -> str:
    return f"<tr><td><strong>{de}</strong></td><td>{en}</td><td>{desc}</td></tr>"


def _gloss_table(rows_html: str) -> html.HtmlElement:
    doc = _doc(
        "<h1>Appendix C: Glossary</h1>"
        "<div class='appendix'><table id='glossary'>"
        "<thead><tr><th>DE</th><th>EN</th><th>Desc</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>"
    )
    return doc


def test_row_line_estimate_counts_longest_cell():
    # short row -> 1 line; long description -> multiple lines.
    short = html.fromstring(_row("A"))
    assert _row_line_estimate(short) == 1
    long_desc = html.fromstring(_row("A", "b", "z" * 200))  # 200 / 48 -> 5 lines
    assert _row_line_estimate(long_desc) >= 4


def test_chunk_respects_per_page_budget():
    # 120 one-line rows must split into several chunks, none over the REST budget.
    rows = [html.fromstring(_row(f"T{i}")) for i in range(120)]
    chunks = _chunk_glossary_rows(rows)
    assert len(chunks) >= 3
    assert sum(len(c) for c in chunks) == 120  # no row lost
    for c in chunks:
        assert sum(_row_line_estimate(r) for r in c) <= _GLOSS_BUDGET_REST


def test_paginate_splits_long_glossary_into_sub_tables():
    rows = "".join(_row(f"Term{i}", "en", "d" * 60) for i in range(60))
    root = _gloss_table(rows)
    table = _find_glossary_table(root)
    n = paginate_glossary(table)
    tables = root.xpath('//table[contains(@class,"glossary")]')
    assert n == len(tables) >= 2
    # every sub-table carries class="glossary" and repeats the header
    for t in tables:
        assert "glossary" in t.get("class", "")
        assert t.xpath("./thead/tr/th")
    # first keeps the canonical id, the rest get glossary-N
    assert tables[0].get("id") == "glossary"
    assert tables[1].get("id") == "glossary-2"
    # no row is lost across the split
    assert len(root.xpath('//tbody/tr')) == 60


def test_paginate_preserves_row_ids_and_links():
    rows = (
        '<tr id="gloss-aaa"><td><strong><a href="#gloss-ref-aaa">Aaa</a>'
        '</strong></td><td>en</td><td>' + "d" * 60 + "</td></tr>"
    ) + "".join(_row(f"Term{i}", "en", "d" * 60) for i in range(50))
    root = _gloss_table(rows)
    paginate_glossary(_find_glossary_table(root))
    # the linked row survived the move with its id and anchor intact
    kept = root.xpath('//tr[@id="gloss-aaa"]')
    assert len(kept) == 1
    assert kept[0].xpath('.//a[@href="#gloss-ref-aaa"]')


def test_paginate_keeps_short_glossary_single():
    root = _gloss_table("".join(_row(f"T{i}") for i in range(4)))
    n = paginate_glossary(_find_glossary_table(root))
    assert n == 1
    tables = root.xpath('//table')
    assert len(tables) == 1
    assert "glossary" in tables[0].get("class", "")  # class still applied


def test_rewrite_glossary_paginates_and_keeps_links():
    # long glossary whose terms all occur italic in the body (so none are pruned)
    # -> after rewrite, the table is split AND a body link + back-anchor still
    # resolve across the split.
    terms = ["Zeta"] + [f"Term{i}" for i in range(55)]
    body = "".join(f"<p>The <em>{t}</em> applies.</p>" for t in terms)
    rows = "".join(_row(t, "en", "d" * 60) for t in terms)
    root = _doc(
        body
        + "<h1>Appendix C: Glossary</h1><table id='glossary'>"
        + "<thead><tr><th>DE</th><th>EN</th><th>Desc</th></tr></thead>"
        + f"<tbody>{rows}</tbody></table>"
    )
    rewrite_glossary(root)
    assert len(root.xpath('//table[contains(@class,"glossary")]')) >= 2
    # Zeta row still present with its id, and its body em became a gloss-link.
    assert root.xpath('//tr[@id="gloss-zeta"]')
    assert root.xpath('//a[contains(@class,"gloss-link") and @href="#gloss-zeta"]')
    # a term that landed in a later sub-table is still linked too (links survive
    # the row move across the split).
    assert root.xpath('//tr[@id="gloss-term54"]')
    assert root.xpath('//a[contains(@class,"gloss-link") and @href="#gloss-term54"]')


def test_glossary_terms_spans_paginated_subtables():
    # After pagination the glossary is several class="glossary" tables; terms
    # must be collected from ALL of them (regression: the --check-only gate
    # otherwise flags terms in continuation sub-tables as un-glossed).
    root = _doc(
        '<table class="glossary" id="glossary"><tbody>'
        '<tr><td><strong>Alpha</strong></td><td>a</td></tr></tbody></table>'
        '<table class="glossary" id="glossary-2"><tbody>'
        '<tr><td><strong>Beta</strong></td><td>b</td></tr></tbody></table>'
    )
    assert glossary_terms(root) == {"Alpha": "alpha", "Beta": "beta"}


def test_gate_ignores_terms_in_continuation_subtable():
    # A term living only in a continuation sub-table must NOT be flagged as an
    # un-glossed body italic (it is glossed, just on a later page).
    root = _doc(
        '<p>The <em>Beta</em> term.</p>'
        '<table class="glossary" id="glossary"><tbody>'
        '<tr><td><strong>Alpha</strong></td><td>a</td></tr></tbody></table>'
        '<table class="glossary" id="glossary-2"><tbody>'
        '<tr><td><strong>Beta</strong></td><td>b</td></tr></tbody></table>'
    )
    terms = glossary_terms(root)
    flagged = find_unglossed_italics(root, terms, {}, _find_glossary_table(root))
    assert "Beta" not in flagged
