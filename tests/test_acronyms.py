"""Integration tests for acronym linking."""

from lxml import etree
from lxml import html as lxml_html

from postprocess_links.acronyms import expand_first_occurrences, rewrite_acronyms


ACROMAP = {
    "HTTP": "acro-http",
    "DOI": "acro-doi",
    "BFCL": "acro-bfcl",
    "BF": "acro-bf",
}


def parse(s: str):
    return lxml_html.fragment_fromstring(s, create_parent="div")


def test_body_acronym_becomes_link() -> None:
    doc = parse("<div><p>The HTTP service publishes notices.</p></div>")
    rewrite_acronyms(doc, ACROMAP)
    links = doc.xpath('//a[@class="acro-link"]')
    assert len(links) == 1
    assert links[0].get("href") == "#acro-http"
    assert links[0].text == "HTTP"
    # First (here: only) occurrence carries the back-link target id.
    assert links[0].get("id") == "acro-http-first"


def test_acronym_in_code_skipped() -> None:
    doc = parse("<div><p>use <code>HTTP</code> here</p></div>")
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "<a " not in out
    assert "<code>HTTP</code>" in out


def test_acronym_in_heading_skipped() -> None:
    doc = parse("<div><h2>HTTP overview</h2><p>HTTP works.</p></div>")
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Heading occurrence untouched; body occurrence linked.
    assert "<h2>HTTP overview</h2>" in out
    assert out.count('href="#acro-http"') == 1


def test_acronym_in_figcaption_linked() -> None:
    """Figure captions (and table captions) get acronym links, same as body
    prose. Headings remain unlinked (kept short / display-clean)."""
    doc = parse(
        "<div><figure><figcaption>HTTP workflow</figcaption></figure><p>HTTP now.</p></div>"
    )
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert out.count('href="#acro-http"') == 2


def test_word_boundary_no_false_positive() -> None:
    doc = parse("<div><p>DOI watches TEDdy bears.</p></div>")
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Only the standalone DOI should match.
    assert out.count('href="#acro-doi"') == 1
    assert "TEDdy" in out


def test_longest_match_wins() -> None:
    doc = parse("<div><p>The BFCL benchmark is standard.</p></div>")
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Must match BFCL (longest), not BF + CL.
    assert 'href="#acro-bfcl"' in out
    assert 'href="#acro-bf"' not in out


def test_table_row_gets_id() -> None:
    # Body text must reference the acronyms so the rows are not removed as dead.
    doc = parse(
        '<div>'
        '<table><tbody>'
        '<tr><td><strong>HTTP</strong></td><td>Hypertext Transfer Protocol</td></tr>'
        '<tr><td><strong>DOI</strong></td><td>Digital Object Identifier</td></tr>'
        '</tbody></table>'
        '<p>HTTP and DOI are used here.</p>'
        '</div>'
    )
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="acro-http"' in out
    assert 'id="acro-doi"' in out


def test_acronym_inside_acronym_table_not_linked() -> None:
    """The KEY cell of the acronyms table itself must not become a self-link."""
    doc = parse(
        '<div>'
        '<table><tbody>'
        '<tr><td><strong>HTTP</strong></td><td>def</td></tr>'
        '</tbody></table>'
        '<p>HTTP is used elsewhere.</p>'
        '</div>'
    )
    rewrite_acronyms(doc, ACROMAP)
    out = lxml_html.tostring(doc, encoding="unicode")
    # The <strong>HTTP</strong> inside the table is not wrapped:
    assert "<strong>HTTP</strong>" in out
    # But the body occurrence IS linked:
    assert out.count('href="#acro-http"') == 1


def test_plural_acronym_links_to_singular_anchor() -> None:
    # "LLMs" / "APIs" plurals must link to the same anchor as the singular
    # KEY and keep the original surface form as the link text.
    acromap = {"LLM": "acro-llm"}
    doc = parse("<div><p>The capability of LLMs improved.</p></div>")
    rewrite_acronyms(doc, acromap)
    links = doc.xpath('//a[@class="acro-link"]')
    assert len(links) == 1
    assert links[0].get("href") == "#acro-llm"  # plural links to singular anchor
    assert links[0].text == "LLMs"  # original surface form preserved


def test_idempotent() -> None:
    doc = parse("<div><p>HTTP works. HTTP works again.</p></div>")
    rewrite_acronyms(doc, ACROMAP)
    first = lxml_html.tostring(doc, encoding="unicode")
    rewrite_acronyms(doc, ACROMAP)
    second = lxml_html.tostring(doc, encoding="unicode")
    assert first == second


def test_head_title_style_script_skipped() -> None:
    """Regression: real Quarkdown output has <title>, <style>, <script> in
    <head>. Without head-tag skipping, a second pass wraps title text and
    re-escapes entities in <style>, breaking idempotence on real HTML."""
    full = lxml_html.fromstring(
        "<html>"
        "<head>"
        "<title>HTTP overview</title>"
        "<style>.foo { content: 'HTTP &gt; 1'; }</style>"
        "<script>const x = 'HTTP';</script>"
        "</head>"
        "<body><p>HTTP in body.</p></body>"
        "</html>"
    )
    rewrite_acronyms(full, ACROMAP)
    first = lxml_html.tostring(full, encoding="unicode")
    rewrite_acronyms(full, ACROMAP)
    second = lxml_html.tostring(full, encoding="unicode")
    # Idempotent even with a full <head> present
    assert first == second
    # <title>, <style>, <script> contents must remain untouched
    assert "<title>HTTP overview</title>" in first
    assert "<style>.foo" in first
    assert "<script>const x = 'HTTP';</script>" in first
    # Body occurrence IS linked
    assert first.count('href="#acro-http"') == 1


def test_rewrite_removes_dead_rows():
    """Acronyms not used in body are removed from the rendered table."""
    from postprocess_links.acronyms import rewrite_acronyms

    doc = parse(
        '<div>'
        '<table class="acronyms-table"><tbody>'
        '<tr><td><strong>ALIVE</strong></td><td>used</td></tr>'
        '<tr><td><strong>DEAD</strong></td><td>unused</td></tr>'
        '</tbody></table>'
        '<p>The ALIVE flag is set.</p>'
        '</div>'
    )
    acromap = {"ALIVE": "used", "DEAD": "unused"}
    rewrite_acronyms(doc, acromap)
    rows = doc.xpath('.//table[@class="acronyms-table"]//tbody/tr')
    keys = [r.xpath('.//strong/text()')[0] for r in rows]
    assert keys == ["ALIVE"], f"DEAD should be removed; got {keys}"


def test_body_acronym_diff():
    """Body tokens like 'XYZ' that aren't in acromap show up in the diff set."""
    from postprocess_links.acronyms import find_undefined_body_acronyms

    doc = parse('<div><p>Use the XYZ tool and the ALIVE flag.</p></div>')
    acromap = {"ALIVE": "used"}
    undefined = find_undefined_body_acronyms(doc, acromap)
    assert "XYZ" in undefined
    assert "ALIVE" not in undefined


def test_acronym_used_only_in_heading_kept():
    """An acronym whose only body occurrence is in a heading or figure caption
    (both in BODY_SKIP_TAGS) must NOT be falsely dropped — add_body_links
    cannot insert an <a class=acro-link> there, so _remove_dead_rows needs
    a fallback plain-text scan over those skip zones."""
    doc = parse(
        '<div>'
        '<h2>The PDF Stack</h2>'
        '<figure id="fig:x"><figcaption>The API used in this work.</figcaption></figure>'
        '<table class="acronyms-table"><tbody>'
        '<tr><td><strong>PDF</strong></td><td>Portable Document Format</td></tr>'
        '<tr><td><strong>API</strong></td><td>Application Programming Interface</td></tr>'
        '<tr><td><strong>DEAD</strong></td><td>not used anywhere</td></tr>'
        '</tbody></table>'
        '<p>Some prose without acronyms.</p>'
        '</div>'
    )
    acromap = {"PDF": "acro-pdf", "API": "acro-api", "DEAD": "acro-dead"}
    rewrite_acronyms(doc, acromap)
    rows = doc.xpath('.//table[@class="acronyms-table"]//tbody/tr')
    keys = [r.xpath('.//strong/text()')[0] for r in rows]
    assert keys == ["PDF", "API"], (
        f"PDF (heading) and API (caption) should survive; DEAD should drop. Got {keys}"
    )


# ---------------------------------------------------------------------------
# Auto-Expansion: expand_first_occurrences
# ---------------------------------------------------------------------------


LONG_FORMS = {
    "LLM": "Large Language Model",
    "EU": "European Union",
    "CLI": "Command-Line Interface",
    "KFZ-HU": "Kraftfahrzeug-Hauptuntersuchung nach Norm",
    "TCP/IP": "Transmission Control Protocol / Internet Protocol",
}


def test_first_occurrence_expanded_singular() -> None:
    doc = parse("<div><p>The LLM is fast. The LLM is great. The LLM rules.</p></div>")
    expand_first_occurrences(doc, LONG_FORMS)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert out.count("Large Language Model (LLM)") == 1
    # All three originals: 1 expanded + 2 untouched
    assert out.count("LLM") == 3


def test_first_occurrence_expanded_plural() -> None:
    doc = parse("<div><p>LLMs are common. LLMs scale.</p></div>")
    expand_first_occurrences(doc, LONG_FORMS)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "Large Language Models (LLMs)" in out
    assert out.count("LLMs") == 2  # 1 expanded + 1 untouched


def test_disabled_flag_skips_expansion() -> None:
    doc = parse("<div><p>The LLM is fast.</p></div>")
    expand_first_occurrences(doc, LONG_FORMS, enabled=False)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "Large Language Model" not in out
    assert "LLM" in out


def test_manual_spellout_collision_avoided() -> None:
    """If 'Long Form (KEY)' already manually appears, skip auto-expansion to
    avoid double 'Long Form (Long Form (KEY))'."""
    doc = parse("<div><p>The European Union (EU) is large. The EU rules.</p></div>")
    expand_first_occurrences(doc, LONG_FORMS)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert out.count("European Union (EU)") == 1  # manual one survives, no second one added


def test_composite_acronym_expanded() -> None:
    """Slash-containing keys (TCP/IP) and hyphen-containing keys (KFZ-HU) work."""
    doc = parse("<div><p>TCP/IP applies. KFZ-HU also.</p></div>")
    expand_first_occurrences(doc, LONG_FORMS)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "Transmission Control Protocol / Internet Protocol (TCP/IP)" in out
    assert "Kraftfahrzeug-Hauptuntersuchung nach Norm (KFZ-HU)" in out


def test_skip_zones_respected() -> None:
    """Expansion ignores text in <code>, <h1-h6>, <strong> (acronyms table)."""
    doc = parse(
        "<div><h2>LLM Section</h2><code>LLM</code><p>The LLM in body.</p></div>"
    )
    expand_first_occurrences(doc, LONG_FORMS)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Heading + code untouched; first body occurrence expanded
    assert "<h2>LLM Section</h2>" in out
    assert "<code>LLM</code>" in out
    assert "Large Language Model (LLM)" in out


def test_only_first_body_occurrence_expanded() -> None:
    """Across multiple paragraphs, only the first chronological hit expands."""
    doc = parse(
        "<div><p>First: LLM here.</p><p>Second: LLM here.</p>"
        "<p>Third: LLM here.</p></div>"
    )
    expand_first_occurrences(doc, LONG_FORMS)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert out.count("Large Language Model (LLM)") == 1
    assert "First: Large Language Model (LLM) here" in out


def test_no_long_form_no_expansion() -> None:
    """If a key has no Long Form (empty value in acronyms.qd), it's skipped."""
    doc = parse("<div><p>Some XYZ here.</p></div>")
    expand_first_occurrences(doc, {"XYZ": ""})
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "XYZ" in out  # untouched
    assert "(XYZ)" not in out  # not re-rendered as expansion


def test_manual_spellout_collision_avoided_with_parenthetical_long_form() -> None:
    """Regression: a manual spell-out using only the head of the long form must
    still suppress Auto-Expansion, even when the acronyms.qd long form carries
    a parenthetical clarification.

    acronyms.qd: "Digital Object Identifier (persistent document handle)"
    prose:       "<em>Digital Object Identifier</em> (DOI)"

    Without prefix-aware collision avoidance the postprocessor double-expands
    into "Digital Object Identifier (Digital Object Identifier (persistent document
    journal) (DOI))" which renders as a broken nested-paren mess in the PDF.
    """
    long_forms = {"DOI": "Digital Object Identifier (persistent document handle)"}
    doc = parse(
        "<div><p>The European Union's <em>Digital Object Identifier</em> "
        "(DOI) is used.</p></div>"
    )
    expand_first_occurrences(doc, long_forms)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Manual spell-out survives untouched; no nested double-paren.
    assert "Digital Object Identifier (Digital Object Identifier" not in out
    # Only one "(DOI)" — the manual one. No "(persistent document handle) (DOI)" appended.
    assert out.count("(DOI)") == 1
    assert "(persistent document handle)" not in out


def test_parenthetical_long_form_expands_core_only() -> None:
    """A long form carrying a parenthetical clarification expands to its head
    only. 'Abkürzungsverzeichnis (list of abbreviations)' must render in
    prose as 'Abkürzungsverzeichnis (AV)', NOT the double-parenthesised
    'Abkürzungsverzeichnis (list of abbreviations) (AV)'."""
    long_forms = {"AV": "Abkürzungsverzeichnis (list of abbreviations)"}
    doc = parse("<div><p>The AV lists positions.</p></div>")
    expand_first_occurrences(doc, long_forms)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "Abkürzungsverzeichnis (AV)" in out
    assert "(list of abbreviations)" not in out


def test_no_expand_suppresses_spellout() -> None:
    """A key passed via no_expand (--no-expand) is never spelled out in prose:
    the bare key survives (for add_body_links to wrap) and its long form does
    not leak in."""
    long_forms = {"XYZ-DA": "XYZ Datenaustausch (XML exchange format)"}
    doc = parse("<div><p>The XYZ-DA format carries the bill.</p></div>")
    expand_first_occurrences(doc, long_forms, no_expand=frozenset({"XYZ-DA"}))
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "XYZ-DA" in out
    assert "Datenaustausch" not in out  # long form not spelled out
    assert "(XYZ-DA)" not in out        # no "Long Form (XYZ-DA)" expansion


def test_no_expand_suppresses_hyphen_compound_use() -> None:
    """A no_expand key inside a hyphen compound: a passing "per-RQ" must not
    auto-expand into "Research Question (RQ)" when the term is already
    established elsewhere (numbered markers, chapter headings)."""
    long_forms = {"RQ": "Research Question"}
    doc = parse("<div><p>Per-RQ evidence is reported in the next chapter.</p></div>")
    expand_first_occurrences(doc, long_forms, no_expand=frozenset({"RQ"}))
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "RQ" in out
    assert "Research Question" not in out  # no inline spell-out


def test_lmecover_wrapper_skipped_for_both_passes() -> None:
    """Regression: the thesis cover (`<div class="container fullwidth lmecover">`)
    must render with the bare KEY only — no Auto-Expansion and no body-link
    wrapping. Otherwise a cover title reads "Evaluating an Large Language
    Model (LLM)-Based Method ..." or carries a clickable anchor.

    The class-substring skip is scoped (substring match), so a regular body
    paragraph still gets both treatments — proving the skip doesn't leak.
    """
    acromap = {"LLM": "acro-llm"}
    long_forms = {"LLM": "Large Language Model"}
    doc = parse(
        '<div>'
        '<div class="container fullwidth lmecover">'
        '<span class="size-large" style="font-weight: bold;">'
        'Evaluating an LLM-Based Method for Document Conversion'
        '</span>'
        '</div>'
        '<p>The LLM-based prototype uses an LLM at its core.</p>'
        '</div>'
    )
    # Auto-Expansion pass first (matches production ordering).
    expand_first_occurrences(doc, long_forms)
    rewrite_acronyms(doc, acromap)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Cover wrapper: bare KEY, no expansion, no anchor.
    assert "Evaluating an LLM-Based Method for Document Conversion" in out
    assert "Large Language Model (LLM)-Based Document Conversion" not in out
    # The cover's <a href="#acro-llm">LLM</a> must NOT be present inside the
    # lmecover wrapper.
    cover_div = doc.xpath('.//div[contains(@class, "lmecover")]')[0]
    cover_html = lxml_html.tostring(cover_div, encoding="unicode")
    assert "<a " not in cover_html, (
        f"lmecover must contain no <a> children, got: {cover_html}"
    )
    # Regular body prose still gets the body link. The hyphenated compound
    # "LLM-based" is no expansion candidate (hyphen guard); the expansion
    # lands on the free-standing LLM instead (the body-link pass wraps the
    # LLM inside the parens, so the contiguous substring becomes
    # `Large Language Model (<a ...>LLM</a>)`).
    assert 'href="#acro-llm"' in out
    body_text = doc.text_content()
    assert "LLM-based prototype" in body_text
    assert "Large Language Model (LLM)-based" not in body_text
    assert "Large Language Model (" in body_text


# ---------------------------------------------------------------------------
# SME-bug regression: normalised lookbehind for already-spelled-out long forms
# ---------------------------------------------------------------------------


def test_no_expansion_when_long_form_directly_precedes_acronym() -> None:
    """When the long form already precedes the acronym in body text (manual
    pre-expansion), the first occurrence is NOT expanded again — only linked.
    Regression: the pair rendered as 'small-to-medium enterprise (Small-to-Medium
    Enterprise (SME))'."""
    html = (
        "<html><body><p>At the partner site, a small-to-medium "
        "enterprise (SME), three roles touch the workflow.</p>"
        "<table><tr><td><strong>SME</strong></td>"
        "<td>Small-to-Medium Enterprise</td></tr></table></body></html>"
    )
    root = etree.fromstring(html)
    acromap = {"SME": "acro-sme"}
    long_forms = {"SME": "Small-to-Medium Enterprise"}
    rewrite_acronyms(root, acromap, long_forms)
    rendered = etree.tostring(root, encoding="unicode")
    # The linked anchor must be present
    assert 'href="#acro-sme"' in rendered
    # The unwanted double expansion must NOT appear
    assert "(Small-to-Medium Enterprise (" not in rendered
    assert "small-to-medium enterprise (SME)" in rendered.lower() or \
        "small-to-medium enterprise (<a" in rendered

def test_normal_first_occurrence_still_expands_without_preceding_long_form() -> None:
    """When the long form is NOT pre-expanded, the first occurrence DOES
    expand to 'Long Form (KEY)' as before — regression for Auto-Expansion."""
    html = (
        "<html><body><p>The HIR pre-registered in §4 frames supervision.</p>"
        "<table><tr><td><strong>HIR</strong></td>"
        "<td>Human Intervention Rate</td></tr></table></body></html>"
    )
    root = etree.fromstring(html)
    acromap = {"HIR": "acro-hir"}
    long_forms = {"HIR": "Human Intervention Rate"}
    rewrite_acronyms(root, acromap, long_forms)
    rendered = etree.tostring(root, encoding="unicode")
    assert "Human Intervention Rate" in rendered
    assert 'href="#acro-hir"' in rendered

def test_lookbehind_normalises_hyphens_and_case() -> None:
    """Long-form match is case-insensitive and treats hyphens / spaces as
    equivalent so 'Small-to-Medium Enterprise' matches 'small to medium
    enterprise' too."""
    html = (
        "<html><body><p>Acting as a small to medium enterprise (SME) in "
        "conversion.</p>"
        "<table><tr><td><strong>SME</strong></td>"
        "<td>Small-to-Medium Enterprise</td></tr></table></body></html>"
    )
    root = etree.fromstring(html)
    acromap = {"SME": "acro-sme"}
    long_forms = {"SME": "Small-to-Medium Enterprise"}
    rewrite_acronyms(root, acromap, long_forms)
    rendered = etree.tostring(root, encoding="unicode")
    assert "(Small-to-Medium Enterprise (" not in rendered
    assert 'href="#acro-sme"' in rendered


def test_acronyms_table_is_skipzone() -> None:
    """Regression: with a real "Acronyms" heading the table becomes a
    skip-zone, so an acronym appearing inside ANOTHER acronym's definition
    cell is not expanded/linked there. Without this, DOCX="Office Open XML
    Document" was corrupted to "...Extensible Markup Language (XML)...".
    """
    acromap = {"DOCX": "acro-docx", "XML": "acro-xml"}
    long_forms = {
        "DOCX": "Office Open XML Document",
        "XML": "Extensible Markup Language",
    }
    doc = parse(
        "<div>"
        '<h1 id="acronyms">Acronyms</h1>'
        "<table><tbody>"
        "<tr><td><strong>DOCX</strong></td><td>Office Open XML Document</td></tr>"
        "</tbody></table>"
        "<p>We export DOCX files.</p>"
        "</div>"
    )
    rewrite_acronyms(doc, acromap, long_forms)
    # The "XML" inside the DOCX definition cell stays plain — not expanded,
    # not link-wrapped.
    docx_def = doc.xpath('//table//tr[1]/td[2]')[0]
    assert docx_def.text_content() == "Office Open XML Document"
    assert docx_def.xpath(".//a") == []


def test_acronym_key_backlinks_to_first_occurrence() -> None:
    """Each table KEY becomes a back-link to its first body occurrence
    (#<slug>-first), and that id sits on the first body acro-link."""
    acromap = {"DOCX": "acro-docx"}
    doc = parse(
        "<div>"
        '<h1 id="acronyms">Acronyms</h1>'
        "<table><tbody>"
        "<tr><td><strong>DOCX</strong></td><td>Office Open XML Document</td></tr>"
        "</tbody></table>"
        "<p>We export DOCX files, more DOCX later.</p>"
        "</div>"
    )
    rewrite_acronyms(doc, acromap)
    # KEY in the table links to the first-occurrence id.
    key_links = doc.xpath("//table//strong/a")
    assert len(key_links) == 1
    assert key_links[0].get("href") == "#acro-docx-first"
    assert key_links[0].text == "DOCX"
    # The first (and only the first) body occurrence carries that id.
    first = doc.xpath('//p//a[@id="acro-docx-first"]')
    assert len(first) == 1
    assert first[0].get("href") == "#acro-docx"


def test_acronym_referenced_only_in_another_definition_survives() -> None:
    """Regression: an acronym whose only occurrence is inside ANOTHER
    acronym's definition cell (FAU in the LME definition) stays listed
    (keep-signal from the definition scan) but is not link-wrapped there
    (the table is a skip-zone)."""
    acromap = {"LME": "acro-lme", "FAU": "acro-fau"}
    doc = parse(
        "<div>"
        '<h1 id="acronyms">Acronyms</h1>'
        "<table><tbody>"
        "<tr><td><strong>LME</strong></td><td>Pattern Recognition Lab, FAU</td></tr>"
        "<tr><td><strong>FAU</strong></td><td>Friedrich-Alexander University</td></tr>"
        "</tbody></table>"
        "<p>The LME chair runs this.</p>"
        "</div>"
    )
    rewrite_acronyms(doc, acromap)
    # FAU row survives even though FAU never appears in prose.
    assert doc.xpath('//tr[@id="acro-fau"]')
    # FAU is NOT link-wrapped inside the LME definition cell (skip-zone).
    lme_def = doc.xpath('//tr[@id="acro-lme"]/td[2]')[0]
    assert lme_def.xpath(".//a") == []
    assert "FAU" in lme_def.text_content()


# --- Hyphen-guarded first-occurrence expansion -----------------------------
# A plain \b boundary also matches inside hyphenated compounds ("GPT-5.4",
# "generative-AI"); expansion there tears the compound apart. The expansion
# pattern skips hyphen-glued matches; body links intentionally still match
# them (usage signal for _remove_dead_rows).

HYPHEN_LONG_FORMS = {
    "GPT": "Generative Pre-trained Transformer",
    "AI": "Artificial Intelligence",
    "LLM": "Large Language Model",
}


def test_expansion_skips_hyphenated_compounds() -> None:
    doc = parse("<div><p>The GPT-5.4 model and generative-AI frameworks.</p></div>")
    expand_first_occurrences(doc, HYPHEN_LONG_FORMS)
    text = doc.text_content()
    assert "GPT-5.4" in text
    assert "Generative Pre-trained Transformer" not in text
    assert "generative-AI" in text
    assert "Artificial Intelligence" not in text


def test_expansion_fires_on_first_free_standing_occurrence() -> None:
    doc = parse(
        "<div><p>The GPT-5.4 model. Later, GPT advanced and AI matured.</p></div>"
    )
    expand_first_occurrences(doc, HYPHEN_LONG_FORMS)
    text = doc.text_content()
    assert "The GPT-5.4 model." in text  # compound untouched
    assert "Generative Pre-trained Transformer (GPT) advanced" in text
    assert "Artificial Intelligence (AI) matured" in text


def test_expansion_plural_after_skipped_compound() -> None:
    doc = parse("<div><p>The LLM-based system uses LLMs heavily.</p></div>")
    expand_first_occurrences(doc, HYPHEN_LONG_FORMS)
    text = doc.text_content()
    assert "LLM-based system" in text  # compound untouched
    assert "Large Language Models (LLMs) heavily" in text
