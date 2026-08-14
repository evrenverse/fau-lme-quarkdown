"""Mean-row marker: tag the last row of a table with class `mean-row` when its
first cell reads `Mean`, so CSS can draw a heavier top border and italicise the
row. Mirror of champions.py."""
from __future__ import annotations

from lxml import etree

LABEL = "Mean"


def _is_mean_label(td: etree._Element) -> bool:
    text = (td.text or "").strip()
    if text == LABEL:
        return True
    for child in td.iter():
        if child is td:
            continue
        if (child.text or "").strip() == LABEL:
            return True
    return False


def mark_mean_rows(root: etree._Element) -> int:
    n = 0
    for td in root.xpath(".//table//tr/td[1]"):
        if not _is_mean_label(td):
            continue
        tr = td.getparent()
        cls = tr.get("class", "")
        tr.set("class", (cls + " mean-row").strip())
        # Clear the "Mean" label text; the heavier rule above the row is
        # already a clear visual signal that the row is the column average.
        td.text = ""
        for child in list(td):
            td.remove(child)
        # The body-row hairline (0.4pt) of the row above would visually halve
        # the mean-row's top rule under border-collapse. Tag the previous row
        # so its bottom border can be cleared in CSS.
        prev = tr.getprevious()
        if prev is not None and prev.tag == "tr":
            cls_prev = prev.get("class", "")
            prev.set("class", (cls_prev + " before-mean").strip())
        n += 1
    return n
