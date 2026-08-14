#!/usr/bin/env python3
"""Post-build PDF repairs after Chrome's printToPDF.

1. Bookmark-title repair: Chrome's `generateDocumentOutline` loses whitespace
   at line-wrap boundaries in heading titles. Overwrite from clean HTML titles.
2. Split-link merge: Chrome splits link annotations at text-run boundaries,
   producing two adjacent rects for a single <a> (first char + remainder).
   Merge them into one rect so PDF viewers show a single click target.

Usage: fix-outline-titles.py <pdf> <html>
Best-effort: any failure leaves Chrome's output in place and exits 0.
"""
import html
import re
import sys


def heading_map(html_path):
    """{whitespace-stripped text -> clean heading text} for every h1-h6."""
    with open(html_path, encoding="utf-8") as fh:
        doc = fh.read()
    out = {}
    for inner in re.findall(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", doc, re.DOTALL | re.IGNORECASE):
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            out[re.sub(r"\s+", "", text)] = text
    return out


def merge_split_links(doc):
    """Merge adjacent link rects that Chrome split at text-run boundaries."""
    merged = 0
    for page in doc:
        links = page.get_links()
        # Index by named dest / URI for O(n) grouping
        from collections import defaultdict
        by_target = defaultdict(list)
        for link in links:
            key = link.get("uri") or link.get("nameddest") or ""
            if key:
                by_target[key].append(link)
        for group in by_target.values():
            if len(group) < 2:
                continue
            # Sort by x0 within same y-band so adjacent rects are consecutive
            group.sort(key=lambda l: (round(l["from"].y0, 0), l["from"].x0))
            i = 0
            while i < len(group) - 1:
                r1 = group[i]["from"]
                r2 = group[i + 1]["from"]
                # Same line (y within 3pt) and adjacent (gap < 2pt)
                if abs(r1.y0 - r2.y0) < 3 and abs(r1.x1 - r2.x0) < 2:
                    # Rebuild as one wider rect covering both
                    wide = r1 | r2  # fitz.Rect union
                    page.delete_link(group[i])
                    page.delete_link(group[i + 1])
                    new_link = dict(group[i])
                    new_link["from"] = wide
                    page.insert_link(new_link)
                    # Replace both entries with the merged one for further passes
                    group[i] = new_link
                    group.pop(i + 1)
                    merged += 1
                else:
                    i += 1
    return merged


def main(pdf_path, html_path):
    import fitz  # PyMuPDF

    titles = heading_map(html_path)
    doc = fitz.open(pdf_path)
    toc = doc.get_toc(simple=False)
    fixed = 0
    for entry in toc:
        clean = titles.get(re.sub(r"\s+", "", entry[1]))
        if clean and clean != entry[1]:
            entry[1] = clean
            fixed += 1
    if fixed:
        doc.set_toc(toc)

    links_merged = merge_split_links(doc)

    if fixed or links_merged:
        doc.saveIncr()
    doc.close()
    print(f"fix-outline-titles: repaired {fixed} bookmark title(s).")
    if links_merged:
        print(f"fix-split-links: merged {links_merged} split link annotation(s).")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: fix-outline-titles.py <pdf> <html>")
    try:
        main(sys.argv[1], sys.argv[2])
    except Exception as exc:  # noqa: BLE001 - polish step must never break the build
        print(f"fix-outline-titles: skipped ({exc})", file=sys.stderr)
