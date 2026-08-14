"""Champion-row marker: strip a `[CHAMP]` sentinel from the first cell of a
table row and tag the `<tr>` with class `champion`, so CSS can frame it."""
from __future__ import annotations

from lxml import etree

SENTINEL = "[CHAMP]"


def mark_champion_rows(root: etree._Element) -> int:
    n = 0
    for td in root.xpath(".//table//tr/td[1]"):
        text = (td.text or "")
        if SENTINEL in text:
            td.text = text.replace(SENTINEL, "", 1).lstrip()
            tr = td.getparent()
            cls = tr.get("class", "")
            tr.set("class", (cls + " champion").strip())
            n += 1
            continue
        # Sentinel may be inside an inline child (e.g. `<strong>[CHAMP]Opus…`)
        for child in td.iter():
            if child is td:
                continue
            if child.text and SENTINEL in child.text:
                child.text = child.text.replace(SENTINEL, "", 1).lstrip()
                tr = td.getparent()
                cls = tr.get("class", "")
                tr.set("class", (cls + " champion").strip())
                n += 1
                break
    return n
