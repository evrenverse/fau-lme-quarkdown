"""Citation rewrite and dynamic reference list.

Forward link: body `[Pet07]` becomes <a href="#bib-pet07">, and the matching
bibliography entry label gets `id="bib-pet07"`.

Back link: the first body occurrence of each cite gets `id="cite-pet07"`, and
the bibliography entry label links back to it (<a href="#cite-pet07">), so a
click on `[Pet07]` in the reference list jumps to its first use in the text.

Dynamic list: `drop_uncited_bib_entries` removes reference entries the body
never cites. Quarkdown's `.bibliography` renders the whole .bib file with no
"cited-only" option, so the list is filtered here at the HTML stage."""

from __future__ import annotations

import re
from lxml import etree

from .bibmap import slugify_label
from .dom_rewriter import iter_text_nodes, replace_text_with_anchor

CITE_LABEL = re.compile(r"\[(?P<label>[A-Za-z][A-Za-z0-9+]{2,})\]")

# Skip zones for body citations: never rewrite inside code, pre, kbd, samp,
# inside an existing <a>, inside KaTeX-rendered math, inside the bibliography
# itself (the bib entry label is handled by `set_bib_ids`), or inside the
# document head (title/style/script/meta/link) to preserve idempotence.
BODY_SKIP_TAGS = frozenset(
    {"code", "pre", "kbd", "samp", "a",
     "head", "title", "style", "script", "meta", "link"}
)
BODY_SKIP_CLASS_SUBSTRINGS = ("katex", "bibliography")


def rewrite_citations(root: etree._Element, bibmap: dict[str, str]) -> None:
    """In-place rewrite:
    1. Set `id` on every bibliography-entry-label span that matches a
       known bibmap label.
    2. Wrap every body occurrence of `[<known-label>]` with an <a> link
       pointing at the corresponding `id`.
    3. Tag the first body occurrence of each cite with `id="cite-<label>"`.
    4. Link each cited bibliography label back to that first occurrence.
    """
    set_bib_ids(root, bibmap)
    add_body_links(root, bibmap)
    cited = mark_first_occurrences(root)
    add_backrefs(root, cited)


def set_bib_ids(root: etree._Element, bibmap: dict[str, str]) -> None:
    """Inject `id="bib-<lowercased-label>"` on each bibliography label."""
    for span in root.iter("span"):
        cls = span.get("class") or ""
        if "bibliography-entry-label" not in cls:
            continue
        text = (span.text or "").strip()
        # text is "[Pet07]" — strip the brackets.
        if not (text.startswith("[") and text.endswith("]")):
            continue
        label = text[1:-1].strip()
        if label not in bibmap:
            continue
        slug = slugify_label(label)
        # Idempotent: only set if missing or different.
        if span.get("id") != slug:
            span.set("id", slug)


def add_body_links(root: etree._Element, bibmap: dict[str, str]) -> None:
    """Wrap each `[Label]` occurrence in body text with an <a> anchor."""

    def make_anchor(match: re.Match) -> tuple[str, str, str] | None:
        label = match.group("label")
        if label not in bibmap:
            return None
        return (f"#{slugify_label(label)}", "bib-cite", match.group(0))

    for text_node in list(iter_text_nodes(root, BODY_SKIP_TAGS, BODY_SKIP_CLASS_SUBSTRINGS)):
        replace_text_with_anchor(text_node, CITE_LABEL, make_anchor)


def _cited_slugs(root: etree._Element) -> set[str]:
    """Bib slugs (`bib-pet07`) that the body cites, read off the forward links."""
    return {
        (a.get("href") or "")[1:]
        for a in root.iter("a")
        if "bib-cite" in (a.get("class") or "")
        and (a.get("href") or "").startswith("#bib-")
    }


def mark_first_occurrences(root: etree._Element) -> set[str]:
    """Tag the first body citation of each target with `id="cite-<label>"`
    and return the set of cited slugs. Idempotent: re-running re-tags the
    same first anchor with the same id."""
    cited: set[str] = set()
    for a in root.iter("a"):
        if "bib-cite" not in (a.get("class") or ""):
            continue
        href = a.get("href") or ""
        if not href.startswith("#bib-"):
            continue
        slug = href[1:]  # "bib-pet07"
        if slug in cited:
            continue
        cited.add(slug)
        a.set("id", "cite-" + slug[len("bib-"):])
    return cited


def add_backrefs(root: etree._Element, cited: set[str]) -> None:
    """Wrap each *cited* bibliography label in a link back to its first body
    occurrence. Uncited labels are left untouched (no target exists).
    Idempotent: a label already wrapped in an <a> is skipped."""
    for span in root.iter("span"):
        if "bibliography-entry-label" not in (span.get("class") or ""):
            continue
        slug = span.get("id")
        if not slug or slug not in cited:
            continue
        if span.find("a") is not None:  # already wrapped
            continue
        label = span.text
        if not label:
            continue
        span.text = None
        a = etree.SubElement(span, "a")
        a.set("href", "#cite-" + slug[len("bib-"):])
        a.set("class", "bib-backref")
        a.text = label


def find_unused_bib_labels(root: etree._Element, bibmap: dict[str, str]) -> set[str]:
    """Bib labels defined in refs.bib but never cited in the body.

    Complements `drop_uncited_bib_entries`: that one acts on the rendered
    bibliography div, which Quarkdown may already filter to cited entries,
    so it can no-op silently when an entry is orphaned. This walks bibmap
    directly and is independent of how Quarkdown renders the list."""
    cited_lower = {s[len("bib-"):] for s in _cited_slugs(root)}
    return {label for label in bibmap if label.lower() not in cited_lower}


def drop_uncited_bib_entries(root: etree._Element) -> set[str]:
    """Remove reference entries the body never cites, making the rendered
    list dynamic. An entry is a `bibliography-entry-label` span plus the
    immediately following `bibliography-entry-content` span. Returns the
    set of dropped slugs."""
    cited = _cited_slugs(root)
    dropped: set[str] = set()
    bib_xpath = '//*[contains(concat(" ", normalize-space(@class), " "), " bibliography ")]'
    for div in root.xpath(bib_xpath):
        for label in list(div):
            if "bibliography-entry-label" not in (label.get("class") or ""):
                continue
            slug = label.get("id") or slugify_label((label.text or "").strip(" []"))
            if slug in cited:
                continue
            nxt = label.getnext()
            div.remove(label)
            if nxt is not None and "bibliography-entry-content" in (nxt.get("class") or ""):
                div.remove(nxt)
            dropped.add(slug)
    return dropped
