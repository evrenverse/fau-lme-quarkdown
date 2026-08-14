"""Dynamic glossary linking, dead-row pruning, and a hard-gate scan.

The glossary table lives in app-c-glossary.qd and contains rows of the
form <tr><td><strong>DE-Term</strong></td><td>EN gloss / description</td></tr>.
It is identified by an explicit id="glossary" (set via {#glossary} on the
markdown table label), or heuristically by a <table> whose nearest preceding
<h1> heading contains "Glossary" (case-insensitive).

`rewrite_glossary` orchestrates the in-place transformation, mirroring
rewrite_acronyms. Dead-row pruning and linking use SEPARATE criteria so the
glossary stays complete (user decision "keep glossary complete"): a term that
occurs only as a compound or inflection (Zeilenhöhe inside
Zeilenhöhenprüfung, Los as Lose) stays LISTED but is not clickable.
  1. link_body_occurrences -- wrap every EXACT word-boundary term occurrence
     (\bTerm\b) inside an <em> with a gloss-link anchor pointing at its
     glossary row, skipping the glossary table itself and the dom_rewriter
     skip zones.
  2. mark_first_occurrences -- give the first gloss-link of each term the
     #gloss-ref-SLUG jump id so the row's back-link resolves.
  3. set_glossary_ids -- tag each row id=gloss-SLUG; turn its DE term into a
     link back to its first body occurrence ONLY when an exact occurrence
     exists (a #gloss-ref-SLUG target is present). Runs AFTER step 2 so those
     targets already exist.
  4. remove_dead_glossary_rows -- drop rows whose term never appears as a
     word-START inside a non-skip <em> (word-start, not exact, so compound /
     inflection uses keep the row); returns the dropped DE terms.

`find_unglossed_italics` is the separate hard-gate scan: italic single-word
spans that escape every bucket (glossary / acronym / GLOSSARY_IGNORE /
fragment) are BLOCKERs surfaced by postprocess_links.py --check-only.
"""
from __future__ import annotations

import copy
import math
import re

from lxml import etree

from .dom_rewriter import iter_text_nodes, replace_text_with_anchor

GLOSS_BODY_SKIP_TAGS = frozenset({
    "code", "pre", "kbd", "samp", "a", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "head", "title", "style", "script", "meta", "link",
})
# "glossary" tags the (possibly multiple) glossary sub-tables produced by
# paginate_glossary; including it here makes every sub-table a body skip-zone,
# so a term sitting inside a continuation sub-table is not mistaken for an
# un-glossed body italic during the --check-only hard gate.
GLOSS_BODY_SKIP_CLASS = ("katex", "bibliography", "lmecover", "glossary")


def _find_glossary_table(root: etree._Element) -> etree._Element | None:
    # 1. Explicit id.
    tbl = root.xpath('//table[@id="glossary"]')
    if tbl:
        return tbl[0]
    # 2. Heuristic: nearest preceding h1 contains "Glossary".
    for candidate in root.xpath('//table'):
        h1 = candidate.xpath('preceding::h1[1]')
        if h1 and "glossary" in (h1[0].text_content() or "").lower():
            return candidate
    return None


_UMLAUTS = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


def _slugify(term: str) -> str:
    """gloss-slug body: umlaut-folded, lowercased, non-alnum -> '-'."""
    bare = term.split("(")[0].strip().translate(_UMLAUTS).lower()
    return re.sub(r"[^a-z0-9]+", "-", bare).strip("-")


def _strong_text(strong: etree._Element) -> str:
    """Term text robust to a wrapped <a> after a rewrite pass: itertext()
    flattens both <strong>Term</strong> and <strong><a>Term</a></strong>."""
    return "".join(strong.itertext()).split("(")[0].strip()


def _all_glossary_tables(root: etree._Element) -> list[etree._Element]:
    """Every glossary (sub-)table. After paginate_glossary has run (e.g. the
    --check-only pass reads already-built HTML) the glossary is several
    class="glossary" tables; before it, a single table found heuristically.
    Either way the union of their rows is the full glossary."""
    tagged = root.xpath(
        '//table[contains(concat(" ", normalize-space(@class), " "), " glossary ")]'
    )
    if tagged:
        return tagged
    one = _find_glossary_table(root)
    return [one] if one is not None else []


def glossary_terms(root: etree._Element) -> dict[str, str]:
    """Map each glossary DE term (first <strong> of each body row) to its slug,
    across all glossary sub-tables."""
    terms: dict[str, str] = {}
    for tbl in _all_glossary_tables(root):
        for tr in tbl.xpath(".//tbody/tr"):
            strong = tr.find(".//strong")
            if strong is None:
                continue
            term = _strong_text(strong)
            if term:
                terms[term] = _slugify(term)
    return terms


def _within(el: etree._Element, ancestor: etree._Element | None) -> bool:
    if ancestor is None:
        return False
    p = el
    while p is not None:
        if p is ancestor:
            return True
        p = p.getparent()
    return False


def _in_skip_zone(
    el: etree._Element, skip_tags: frozenset[str], skip_class: tuple[str, ...]
) -> bool:
    """True if any ANCESTOR of el is a skip-zone tag/class. acronyms.add_body_links
    traverses from the root, so iter_text_nodes skips whole skip-zone subtrees for
    free; our per-<em> loop must check ancestors explicitly, else it rewrites/scans
    italic terms inside the bibliography, headings, code, katex, etc."""
    p = el.getparent()
    while p is not None:
        if p.tag in skip_tags:
            return True
        cls = p.get("class", "")
        if any(n in cls for n in skip_class):
            return True
        p = p.getparent()
    return False


# Italic single-word terms that are deliberately NOT German glossary terms
# (English emphasis-italics, proper nouns, concept names the author keeps out
# of the glossary). Which terms those are is a per-document editorial decision,
# so the theme ships an empty set; consumers pass their exemptions via the
# --lint-ignore file (see postprocess_links.py). Sibling of
# acronyms.ACRONYM_TOKEN_BLOCKLIST.
GLOSSARY_IGNORE = frozenset()

_ACRONYM_SHAPE = re.compile(r"^[A-ZÄÖÜ][A-ZÄÖÜ0-9-]*$")


def find_unglossed_italics(
    root: etree._Element,
    terms: dict[str, str],
    acromap: dict[str, str],
    table: etree._Element | None,
    extra_ignore: frozenset[str] = frozenset(),
) -> set[str]:
    """Italic single-word spans that escape every bucket (glossary / acronym /
    ignore-list / fragment). Each is a hard-gate BLOCKER. `extra_ignore`
    carries the consumer's project-specific exemptions (--lint-ignore)."""
    flagged: set[str] = set()
    for em in root.iter("em"):
        if _within(em, table) or _in_skip_zone(em, GLOSS_BODY_SKIP_TAGS, GLOSS_BODY_SKIP_CLASS):
            continue
        text = "".join(em.itertext()).strip()
        if not text or " " in text:          # empty or multi-word
            continue
        if text.endswith("-"):                # fragment (Qualitäts-)
            continue
        if not text[:1].isupper():            # lowercase / digit start = English word, code id
            continue                          # (runtime, iframe), or artefact — never a German
                                              # glossary noun (German nouns are capitalised)
        if _ACRONYM_SHAPE.match(text):        # acronym-shaped (RAG, TÜV, KFZ-HU)
            continue
        if text in acromap or text in terms or text in GLOSSARY_IGNORE \
                or text in extra_ignore:
            continue
        flagged.add(text)
    return flagged


def link_body_occurrences(
    root: etree._Element, terms: dict[str, str], table: etree._Element | None
) -> None:
    """Wrap each word-boundary term occurrence inside an <em> with a gloss-link
    anchor. Skips the glossary table subtree and dom_rewriter skip zones."""
    if not terms:
        return
    keys_sorted = sorted(terms, key=len, reverse=True)  # longest-first
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys_sorted) + r")\b")

    def make_anchor(match: re.Match):
        slug = terms.get(match.group(1))
        if slug is None:
            return None
        return (f"#gloss-{slug}", "gloss-link", match.group(0))

    for em in list(root.iter("em")):
        if _within(em, table) or _in_skip_zone(em, GLOSS_BODY_SKIP_TAGS, GLOSS_BODY_SKIP_CLASS):
            continue
        for text_node in list(iter_text_nodes(em, GLOSS_BODY_SKIP_TAGS, GLOSS_BODY_SKIP_CLASS)):
            replace_text_with_anchor(text_node, pattern, make_anchor)


def set_glossary_ids(
    root: etree._Element, terms: dict[str, str], table: etree._Element | None
) -> None:
    """Tag each glossary row id=gloss-SLUG. Make the term a link to its first
    body occurrence ONLY when an exact occurrence exists (a #gloss-ref-SLUG
    anchor is present). Composite-only terms stay listed but not clickable."""
    if table is None:
        return
    for tr in table.xpath(".//tbody/tr"):
        strong = tr.find(".//strong")
        if strong is None:
            continue
        term = _strong_text(strong)
        slug = terms.get(term)
        if not slug:
            continue
        tr.set("id", f"gloss-{slug}")
        has_target = bool(root.xpath(f'//*[@id="gloss-ref-{slug}"]'))
        if has_target and strong.find("a") is None and strong.text:
            txt = strong.text
            strong.text = None
            a = etree.SubElement(strong, "a")
            a.set("href", f"#gloss-ref-{slug}")
            a.text = txt


def mark_first_occurrences(root: etree._Element, terms: dict[str, str]) -> None:
    """Give the first gloss-link of each slug (document order) the jump id."""
    pending = set(terms.values())
    for a in root.iter("a"):
        if not pending:
            break
        if "gloss-link" not in (a.get("class") or ""):
            continue
        href = a.get("href", "")
        if not href.startswith("#gloss-"):
            continue
        slug = href[len("#gloss-"):]
        if slug in pending:
            a.set("id", f"gloss-ref-{slug}")
            pending.discard(slug)


def remove_dead_glossary_rows(
    root: etree._Element, terms: dict[str, str], table: etree._Element | None
) -> set[str]:
    """Drop rows whose term never appears as a word-START inside a non-skip
    <em>. Word-start (not exact) keeps composite/inflection uses
    (Zeilenhöhenprüfung keeps Zeilenhöhe). Returns dropped DE terms."""
    if table is None:
        return set()
    em_texts = [
        "".join(em.itertext())
        for em in root.iter("em")
        if not _within(em, table)
        and not _in_skip_zone(em, GLOSS_BODY_SKIP_TAGS, GLOSS_BODY_SKIP_CLASS)
    ]
    used: set[str] = set()
    for term, slug in terms.items():
        pat = re.compile(r"\b" + re.escape(term))  # word-start, no trailing \b
        if any(pat.search(t) for t in em_texts):
            used.add(slug)
    slug_to_term = {v: k for k, v in terms.items()}
    dropped: set[str] = set()
    for tr in list(table.xpath(".//tbody/tr")):
        tid = tr.get("id", "")
        # Only table rows reach here (xpath is tbody/tr); they carry gloss-<slug>
        # ids. No gloss-ref- exclusion: a term whose slug legitimately starts
        # "ref-" (e.g. "Ref-Objekt" -> gloss-ref-objekt) must still be prunable.
        if not tid.startswith("gloss-"):
            continue
        slug = tid[len("gloss-"):]
        if slug not in used:
            parent = tr.getparent()
            if parent is not None:
                parent.remove(tr)
                dropped.add(slug_to_term.get(slug, slug))
    return dropped


# Glossary auto-pagination. PagedJS 0.4.3 mis-fragments a real <table> whose
# rows have multi-line cells: every continuation page is left roughly half
# empty (upstream issues #61 / #89 / #149, no CSS workaround). We pre-split the
# linked glossary into page-sized sub-tables that each fit on one page and are
# marked break-inside:avoid, so PagedJS never has to fragment a table and every
# page fills. The estimates below are deliberately approximate: a sub-table that
# slightly overshoots just gets pushed whole to the next page (a small gap),
# which still beats the un-split bug, so robustness matters more than precision.
# Characters that fit one rendered line per column at 8 pt (DE 26 %, EN 20 %,
# Description 54 % of the ~15 cm text block).
_GLOSS_CHARS_PER_LINE = (19, 16, 48)
# Text-line budget per page at 8 pt (a full A4 LME text block holds ~50 lines).
# Kept a few lines under that so a sub-table never overshoots a full page (which
# would force PagedJS back into the buggy fragment-or-clip path). The first page
# also carries the chapter title and intro paragraph, hence the smaller budget.
_GLOSS_BUDGET_FIRST = 30
_GLOSS_BUDGET_REST = 45


def _row_line_estimate(tr: etree._Element) -> int:
    """Estimate the rendered text-line height of one glossary row, driven by the
    longest-wrapping of its three cells."""
    lines = 1
    for cell, cpl in zip(tr.findall("td"), _GLOSS_CHARS_PER_LINE):
        text = "".join(cell.itertext()).strip()
        if text:
            lines = max(lines, math.ceil(len(text) / cpl))
    return lines


def _chunk_glossary_rows(rows: list[etree._Element]) -> list[list[etree._Element]]:
    """Greedily group rows into page-sized chunks by estimated text-line height.
    A row never lands alone past a full page; the first chunk uses the smaller
    first-page budget."""
    chunks: list[list[etree._Element]] = []
    current: list[etree._Element] = []
    used = 0
    budget = _GLOSS_BUDGET_FIRST
    for tr in rows:
        weight = _row_line_estimate(tr)
        if current and used + weight > budget:
            chunks.append(current)
            current = []
            used = 0
            budget = _GLOSS_BUDGET_REST
        current.append(tr)
        used += weight
    if current:
        chunks.append(current)
    return chunks


def paginate_glossary(table: etree._Element | None) -> int:
    """Split the linked glossary table into page-sized atomic sub-tables (see the
    block comment above). Each sub-table repeats the header and carries
    class="glossary"; the first keeps id="glossary", the rest get id="glossary-N".
    The <tr> elements are moved, not rebuilt, so their gloss-SLUG ids and the
    bidirectional links survive. Returns the number of sub-tables produced (1 = no
    split needed)."""
    if table is None:
        return 0
    tbody = table.find("tbody")
    if tbody is None:
        return 0
    rows = tbody.findall("tr")
    chunks = _chunk_glossary_rows(rows)
    cls = (table.get("class", "") + " glossary").split()
    table.set("class", " ".join(dict.fromkeys(cls)))  # dedupe, keep order
    if len(chunks) <= 1:
        return 1
    parent = table.getparent()
    if parent is None:
        return 1
    thead = table.find("thead")
    insert_at = parent.index(table)
    for i, chunk in enumerate(chunks):
        sub = etree.Element("table")
        sub.set("class", "glossary")
        sub.set("id", "glossary" if i == 0 else f"glossary-{i + 1}")
        if thead is not None:
            sub.append(copy.deepcopy(thead))
        sub_tbody = etree.SubElement(sub, "tbody")
        for tr in chunk:
            sub_tbody.append(tr)  # moves the <tr> (id + links intact)
        parent.insert(insert_at + i, sub)
    parent.remove(table)
    return len(chunks)


def rewrite_glossary(root: etree._Element) -> set[str]:
    """In-place: link exact italic body occurrences, mark first occurrence, tag
    rows (linking the term only when an exact target exists), drop rows unused
    even as a compound, then split the table into page-sized sub-tables. Returns
    dropped DE terms. Mirrors rewrite_acronyms.

    set_glossary_ids runs AFTER mark_first_occurrences so the #gloss-ref-SLUG
    targets already exist when it decides whether to make a term clickable.
    paginate_glossary runs LAST, after dead rows are gone, so chunk sizes match
    the rows that actually render."""
    table = _find_glossary_table(root)
    if table is None:
        return set()
    table.set("id", "glossary")
    terms = glossary_terms(root)
    link_body_occurrences(root, terms, table)
    mark_first_occurrences(root, terms)
    set_glossary_ids(root, terms, table)
    dropped = remove_dead_glossary_rows(root, terms, table)
    paginate_glossary(table)
    return dropped
