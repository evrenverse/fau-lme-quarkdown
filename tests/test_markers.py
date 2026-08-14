"""Tests for definition-marker linking (RQ / G / C)."""

from lxml import html as lxml_html

from postprocess_links.markers import rewrite_markers


def parse(s: str):
    return lxml_html.fragment_fromstring(s, create_parent="div")


# ---- RQ -----------------------------------------------------------------


def test_rq_definition_paragraph_gets_id() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>Sample question definition…</em></p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="rq-1"' in out


def test_rq_body_occurrence_becomes_link() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>Q1 defined here</em></p>"
        "<p>This relates to RQ1.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert '<a href="#rq-1" class="marker-link">RQ1</a>' in out


def test_rq_undefined_left_alone() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>defined</em></p>"
        "<p>typo: RQ99 should not link.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "RQ99" in out
    assert 'href="#rq-99"' not in out


# ---- Goals --------------------------------------------------------------


def test_goal_definition_with_trailing_label() -> None:
    # Strong text includes a label parenthesis: `**G1 (Sample label).**`.
    doc = parse(
        "<div>"
        "<p><strong>G1 (Sample label).</strong> Goal definition body…</p>"
        "<p>achieves G1 end-to-end.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="g-1"' in out
    assert '<a href="#g-1" class="marker-link">G1</a>' in out


# ---- Contributions ------------------------------------------------------


def test_contribution_definition_with_trailing_label() -> None:
    doc = parse(
        "<div>"
        "<p><strong>C1 (Sample, own).</strong> <em>Contribution body…</em></p>"
        "<p>C1 grounds the empirical chapter.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="c-1"' in out
    assert '<a href="#c-1" class="marker-link">C1</a>' in out


# ---- Skip-zone and edge-case behaviour ----------------------------------


def test_strong_definition_not_self_linked() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>defined</em></p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Strong text itself must stay untouched.
    assert "<strong>RQ1</strong>" in out
    assert "<a " not in out


def test_heading_occurrence_skipped() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>defined</em></p>"
        "<h2>RQ1 — Sample heading</h2>"
        "<p>see RQ1.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "<h2>RQ1 — Sample heading</h2>" in out
    assert out.count('href="#rq-1"') == 1


def test_code_block_skipped() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>defined</em></p>"
        "<p>see <code>RQ1</code>.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "<code>RQ1</code>" in out
    assert "<a " not in out


def test_multiple_definitions_independent() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>r1</em></p>"
        "<p><strong>G2 (Sample label).</strong> g2</p>"
        "<p><strong>C3 (Sample, own).</strong> <em>c3</em></p>"
        "<p>see RQ1, G2, and C3.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="rq-1"' in out
    assert 'id="g-2"' in out
    assert 'id="c-3"' in out
    assert out.count('href="#rq-1"') == 1
    assert out.count('href="#g-2"') == 1
    assert out.count('href="#c-3"') == 1


def test_only_first_definition_paragraph_per_marker_is_tagged() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>first def</em></p>"
        "<p><strong>RQ1</strong> — <em>second def</em></p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert out.count('id="rq-1"') == 1


def test_non_definition_strong_ignored() -> None:
    # Mid-sentence emphasis is not a definition: <p>.text is non-empty
    # before the strong tag.
    doc = parse(
        "<div>"
        "<p>The contribution to <strong>RQ1</strong> is significant.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="rq-1"' not in out


def test_idempotent() -> None:
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — <em>defined</em></p>"
        "<p><strong>C1 (Sample, own).</strong> <em>described</em></p>"
        "<p>RQ1 again. C1 again. C1 yet again.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    first = lxml_html.tostring(doc, encoding="unicode")
    rewrite_markers(doc)
    second = lxml_html.tostring(doc, encoding="unicode")
    assert first == second


# ---- Hypotheses (H<n>.<m> in paragraph or table cell) -------------------


def test_hypothesis_paragraph_definition_gets_dot_slug() -> None:
    doc = parse(
        "<div>"
        "<p><strong>H2.4</strong> — On the champion configuration, "
        "confidence and correctness are correlated.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-2-4"' in out


def test_hypothesis_table_cell_definition() -> None:
    # Hypotheses in this thesis are typically defined as the first column
    # of a hypotheses table, not as standalone paragraphs.
    doc = parse(
        "<div>"
        "<table><tbody>"
        "<tr><td><strong>H1.1</strong></td>"
        "<td>At least one configuration achieves TSR ≥ 60%.</td></tr>"
        "<tr><td><strong>H2.4</strong></td>"
        "<td>Confidence correlates with correctness.</td></tr>"
        "</tbody></table>"
        "<p>The calibration hypothesis is H2.4 of the table above.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-1-1"' in out
    assert 'id="h-2-4"' in out
    assert '<a href="#h-2-4" class="marker-link">H2.4</a>' in out


def test_hypothesis_body_occurrence_becomes_link() -> None:
    doc = parse(
        "<div>"
        "<p><strong>H3.1</strong> — past-bid retrieval improves MAPE.</p>"
        "<p>Hypothesis H3.1 is the central treatment of RQ3.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-3-1"' in out
    assert '<a href="#h-3-1" class="marker-link">H3.1</a>' in out


def test_hypothesis_undefined_left_alone() -> None:
    doc = parse(
        "<div>"
        "<p><strong>H1.1</strong> — defined.</p>"
        "<p>typo: H9.9 should not link.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert "H9.9" in out
    assert 'href="#h-9-9"' not in out


def test_hypothesis_without_dot_recognised() -> None:
    # Edge case: a hypothesis named without dot (`H1`) is still supported
    # by the regex even though the thesis convention is dotted notation.
    doc = parse(
        "<div>"
        "<p><strong>H1</strong> — bare-integer hypothesis.</p>"
        "<p>see H1 above.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-1"' in out
    assert '<a href="#h-1" class="marker-link">H1</a>' in out


def test_mixed_marker_types_in_same_doc() -> None:
    # Smoke test that the four prefix families coexist.
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — research question.</p>"
        "<p><strong>G2 (Construction).</strong> goal body.</p>"
        "<p><strong>C3 (Critic, own).</strong> contribution body.</p>"
        "<table><tbody><tr>"
        "<td><strong>H2.4</strong></td><td>hypothesis body</td>"
        "</tr></tbody></table>"
        "<p>see RQ1, G2, C3, and H2.4.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="rq-1"' in out
    assert 'id="g-2"' in out
    assert 'id="c-3"' in out
    assert 'id="h-2-4"' in out
    assert out.count('href="#rq-1"') == 1
    assert out.count('href="#g-2"') == 1
    assert out.count('href="#c-3"') == 1
    assert out.count('href="#h-2-4"') == 1


# ---- Hypothesis legs with lowercase suffix (H2.3a / H3.1b) --------------


def test_hypothesis_leg_a_table_cell_definition() -> None:
    # ch04 tab:hypotheses splits H2.3 into legs (a)/(b) and uses bold-prefix
    # cells; the regex must keep the trailing letter intact.
    doc = parse(
        "<div>"
        "<table><tbody><tr>"
        "<td><strong>H2.3a</strong></td>"
        "<td>Past-bid retrieval lowers MAPE.</td>"
        "</tr></tbody></table>"
        "<p>see H2.3a in tab:hypotheses.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-2-3a"' in out
    assert '<a href="#h-2-3a" class="marker-link">H2.3a</a>' in out


def test_hypothesis_leg_b_body_occurrence_becomes_link() -> None:
    doc = parse(
        "<div>"
        "<p><strong>H3.1b</strong> — leg (b) definition.</p>"
        "<p>H3.1b again, with the same outcome.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-3-1b"' in out
    assert '<a href="#h-3-1b" class="marker-link">H3.1b</a>' in out


def test_hypothesis_legs_a_and_b_independent() -> None:
    # (a) and (b) must not collide on the slug-key "h-2-3".
    doc = parse(
        "<div>"
        "<table><tbody>"
        "<tr><td><strong>H2.3a</strong></td><td>leg a.</td></tr>"
        "<tr><td><strong>H2.3b</strong></td><td>leg b.</td></tr>"
        "</tbody></table>"
        "<p>contrast H2.3a with H2.3b.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-2-3a"' in out
    assert 'id="h-2-3b"' in out
    assert out.count('href="#h-2-3a"') == 1
    assert out.count('href="#h-2-3b"') == 1


def test_hypothesis_dotted_without_letter_still_matches() -> None:
    # Regression: H2.4 must still be matched after the [a-z]? extension.
    doc = parse(
        "<div>"
        "<p><strong>H2.4</strong> — dotted leg.</p>"
        "<p>H2.4 holds.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="h-2-4"' in out
    assert '<a href="#h-2-4" class="marker-link">H2.4</a>' in out


# ---- Requirements (R / R-NF) --------------------------------------------


def test_requirement_paragraph_definition_gets_id() -> None:
    doc = parse(
        "<div>"
        "<p><strong>R3</strong> — Sample functional requirement.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="r-3"' in out


def test_requirement_table_cell_definition() -> None:
    # ch05 tab:requirements defines R/R-NF as table-cell bold prefixes.
    doc = parse(
        "<div>"
        "<table><tbody>"
        "<tr><td><strong>R3</strong></td><td>Body of R3.</td></tr>"
        "<tr><td><strong>R-NF1</strong></td><td>NF requirement body.</td></tr>"
        "</tbody></table>"
        "<p>R3 in sec:requirements; the R-NF1 paragraph follows.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="r-3"' in out
    assert 'id="r-nf-1"' in out
    assert '<a href="#r-3" class="marker-link">R3</a>' in out
    assert '<a href="#r-nf-1" class="marker-link">R-NF1</a>' in out


def test_requirement_with_letter_suffix() -> None:
    doc = parse(
        "<div>"
        "<table><tbody>"
        "<tr><td><strong>R4a</strong></td><td>Sub-requirement a.</td></tr>"
        "<tr><td><strong>R4b</strong></td><td>Sub-requirement b.</td></tr>"
        "</tbody></table>"
        "<p>closes R4b at the planning level.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="r-4a"' in out
    assert 'id="r-4b"' in out
    assert '<a href="#r-4b" class="marker-link">R4b</a>' in out


def test_r_prefix_must_not_swallow_rq() -> None:
    # The alternation must keep RQ over R: an RQ1 reference stays an RQ
    # link, not an R-link of "1".
    doc = parse(
        "<div>"
        "<p><strong>RQ1</strong> — research question.</p>"
        "<p>see RQ1.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="rq-1"' in out
    assert 'id="r-1"' not in out
    assert '<a href="#rq-1" class="marker-link">RQ1</a>' in out
    assert 'href="#r-1"' not in out


def test_r_nf_prefix_must_not_be_misread_as_r() -> None:
    # R-NF1 must not be matched as R + "-NF1" (which would slug to r--nf-1
    # via the dot/dash mangle) — the longer prefix wins.
    doc = parse(
        "<div>"
        "<p><strong>R-NF1</strong> — non-functional requirement.</p>"
        "<p>see R-NF1.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="r-nf-1"' in out
    assert '<a href="#r-nf-1" class="marker-link">R-NF1</a>' in out


def test_r_droid_not_a_marker() -> None:
    # "R2D2" must not be matched as R2 (trailing 'D' breaks the boundary
    # only if the regex enforces \b after the digit/letter; verify the
    # body is left literally untouched and no anchor exists).
    doc = parse(
        "<div>"
        "<p><strong>R2</strong> — defined requirement two.</p>"
        "<p>R2D2 droid is not a requirement reference.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    # Definition still tagged.
    assert 'id="r-2"' in out
    # The droid string remains literal: no <a> wrapping inside R2D2.
    assert "R2D2 droid is not a requirement reference." in out
    assert '>R2</a>D2' not in out


def test_reference_word_no_match() -> None:
    # "Reference" begins with R but has no digit — must not match.
    doc = parse(
        "<div>"
        "<p><strong>R3</strong> — defined.</p>"
        "<p>Reference list at the end of the chapter.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="r-3"' in out
    # "Reference" stays as plain text; only the literal "R3" earlier links.
    assert "Reference list at the end of the chapter." in out


def test_mixed_h_leg_and_requirement_in_same_doc() -> None:
    # Smoke test that H legs + R + R-NF coexist with the legacy families.
    doc = parse(
        "<div>"
        "<p><strong>RQ2</strong> — second research question.</p>"
        "<table><tbody>"
        "<tr><td><strong>R3</strong></td><td>functional body.</td></tr>"
        "<tr><td><strong>R-NF1</strong></td><td>NF body.</td></tr>"
        "<tr><td><strong>H2.3a</strong></td><td>leg a body.</td></tr>"
        "</tbody></table>"
        "<p>see RQ2, R3, R-NF1, and H2.3a.</p>"
        "</div>"
    )
    rewrite_markers(doc)
    out = lxml_html.tostring(doc, encoding="unicode")
    assert 'id="rq-2"' in out
    assert 'id="r-3"' in out
    assert 'id="r-nf-1"' in out
    assert 'id="h-2-3a"' in out
    assert out.count('href="#rq-2"') == 1
    assert out.count('href="#r-3"') == 1
    assert out.count('href="#r-nf-1"') == 1
    assert out.count('href="#h-2-3a"') == 1
