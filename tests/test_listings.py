"""Tests for List-of-Figures + List-of-Tables DOM injection."""
from __future__ import annotations

from lxml import html

from postprocess_links.listings import inject_listings


def _doc(body_html: str) -> html.HtmlElement:
    return html.document_fromstring(
        f"<html><body>{body_html}</body></html>",
    )


FIG_FRAG = '''
<div id="lof-marker"></div>
<div id="lot-marker"></div>
<figure id="fig:alpha">
  <img src="a.svg"/>
  <figcaption class="caption-bottom" data-location="1.1" data-localized-kind="Figure">First figure caption. Second sentence ignored.</figcaption>
</figure>
<table id="tab:beta">
  <caption class="caption-top" data-location="2.3" data-localized-kind="Table">First table caption. Second sentence ignored.</caption>
  <tbody><tr><td>x</td></tr></tbody>
</table>
'''


def test_lof_injects_listing_for_each_figure() -> None:
    root = _doc(FIG_FRAG)
    inject_listings(root)
    lof = root.xpath('//div[@id="lof-marker"]/table[@class="lme-listing"]')
    assert len(lof) == 1
    rows = lof[0].xpath('./tbody/tr')
    assert len(rows) == 1
    # Row carries the figure number, the shortened caption, and an anchor.
    text = rows[0].text_content()
    assert "1.1" in text
    assert "First figure caption" in text
    assert "Second sentence" not in text  # truncated at first sentence
    # Locator + page cell each carry an anchor (caption itself is plain text).
    a = rows[0].xpath('.//a/@href')
    assert a == ["#fig:alpha", "#fig:alpha"]
    # The number is the link; the caption is NOT a link.
    assert rows[0].xpath('./td[@class="loc"]/a/text()') == ["1.1"]
    assert rows[0].xpath('./td[@class="cap"]/a') == []
    # Page cell holds an (empty) anchor so the CSS target-counter resolves.
    assert rows[0].xpath('./td[@class="page"]/a/@href') == ["#fig:alpha"]


def test_lot_injects_listing_for_each_table() -> None:
    root = _doc(FIG_FRAG)
    inject_listings(root)
    lot = root.xpath('//div[@id="lot-marker"]/table[@class="lme-listing"]')
    assert len(lot) == 1
    rows = lot[0].xpath('./tbody/tr')
    assert len(rows) == 1
    text = rows[0].text_content()
    assert "2.3" in text
    assert "First table caption" in text


def test_no_marker_no_op() -> None:
    root = _doc('<figure id="fig:alpha"><figcaption data-location="1.1" data-localized-kind="Figure">cap</figcaption></figure>')
    # No `lof-marker` div present; must not raise.
    inject_listings(root)


def test_no_figures_marker_stays_empty() -> None:
    root = _doc('<div id="lof-marker"></div><div id="lot-marker"></div>')
    inject_listings(root)
    # Markers stay (possibly empty) — must not raise.
    assert root.xpath('//div[@id="lof-marker"]')
