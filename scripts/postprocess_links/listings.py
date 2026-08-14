"""List of Figures + List of Tables: dynamic DOM injection.

Scans the post-Quarkdown HTML for <figure id="fig:..."> and
<table id="tab:..."> elements and renders one listing table per kind
into the marker <div>s in the front-matter.

Markers (set by frontmatter/list-of-figures.qd and list-of-tables.qd):
  <div id="lof-marker"></div>
  <div id="lot-marker"></div>

Each listing renders as:
  <table class="lme-listing">
    <tbody>
      <tr>
        <td class="loc"><a href="#fig:slug">N.M</a></td>  <!-- locator is the link -->
        <td class="cap">short caption</td>                <!-- title stays plain -->
        <td class="page"><a href="#fig:slug"></a></td>    <!-- empty anchor; CSS
             target-counter fills it via attr(href url) on THIS cell's <a> -->
      </tr>
      ...
    </tbody>
  </table>

The locator (not the caption) carries the jump link — a deliberate choice so the
title reads as plain text and only the number is clickable. The page cell holds
its own anchor because the CSS `td.page a::after { content: target-counter(...) }`
resolves the target page from an href on the page cell itself.
"""
from __future__ import annotations

import re

from lxml import etree

FIRST_SENTENCE = re.compile(r"(.+?\.)(\s|$)")


def _short_caption(text: str) -> str:
    text = (text or "").strip()
    m = FIRST_SENTENCE.match(text)
    return m.group(1) if m else text


def _collect_items(root: etree._Element, container_tag: str, caption_tag: str, id_prefix: str) -> list[tuple[str, str, str]]:
    """Return [(data-location, short_caption, anchor_id), …]."""
    items: list[tuple[str, str, str]] = []
    for el in root.xpath(f"//{container_tag}[@id and starts-with(@id, '{id_prefix}')]"):
        cap = el.find(caption_tag)
        if cap is None:
            continue
        loc = cap.get("data-location", "")
        text = cap.text_content()
        items.append((loc, _short_caption(text), el.get("id", "")))
    return items


def _render(marker: etree._Element, items: list[tuple[str, str, str]]) -> None:
    if not items:
        return
    table = etree.SubElement(marker, "table")
    table.set("class", "lme-listing")
    tbody = etree.SubElement(table, "tbody")
    for loc, cap_text, anchor in items:
        tr = etree.SubElement(tbody, "tr")
        # Locator cell carries the jump link (user decision: link the number,
        # not the title).
        td_loc = etree.SubElement(tr, "td")
        td_loc.set("class", "loc")
        a_loc = etree.SubElement(td_loc, "a")
        a_loc.set("href", f"#{anchor}")
        a_loc.text = loc
        # Caption stays plain text — not a link.
        td_cap = etree.SubElement(tr, "td")
        td_cap.set("class", "cap")
        td_cap.text = cap_text
        # Page cell gets its own (empty) anchor so the CSS target-counter has
        # an href on this cell to resolve; Paged.js fills the page number.
        td_page = etree.SubElement(tr, "td")
        td_page.set("class", "page")
        a_page = etree.SubElement(td_page, "a")
        a_page.set("href", f"#{anchor}")


def inject_listings(root: etree._Element) -> None:
    lof = root.xpath('//*[@id="lof-marker"]')
    if lof:
        _render(lof[0], _collect_items(root, "figure", "figcaption", "fig:"))
    lot = root.xpath('//*[@id="lot-marker"]')
    if lot:
        _render(lot[0], _collect_items(root, "table", "caption", "tab:"))
