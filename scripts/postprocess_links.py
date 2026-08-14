#!/usr/bin/env python3
"""CLI entry: postprocess Quarkdown HTML to inject anchors for citations
and acronyms.

Usage:
    postprocess_links.py --html PATH --bib PATH --acronyms PATH [--check-only]

In default mode, rewrites HTML in place. In --check-only mode, emits no
changes; exits non-zero if orphan citations or dead acronyms are found.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from lxml import html as lxml_html

# Make the package importable when invoked as a script.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from postprocess_links.bibmap import parse_bibmap
from postprocess_links.acromap import parse_acromap, parse_acromap_long_forms
from postprocess_links.citations import (
    rewrite_citations,
    drop_uncited_bib_entries,
    find_unused_bib_labels,
    CITE_LABEL,
)
from postprocess_links.acronyms import (
    rewrite_acronyms,
    find_undefined_body_acronyms,
)
from postprocess_links.markers import rewrite_markers
from postprocess_links.crossrefs import materialise_cross_references
from postprocess_links.codeblocks import rewrite_codeblocks
from postprocess_links.listings import inject_listings
from postprocess_links.champions import mark_champion_rows
from postprocess_links.mean_row import mark_mean_rows
from postprocess_links.glossary import (
    rewrite_glossary,
    find_unglossed_italics,
    glossary_terms,
    _find_glossary_table,
)
from postprocess_links.captions import find_caption_period_violations

PLACEHOLDER_LABELS = frozenset({"fill", "TBD", "NOTE", "TODO"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True, help="index.html to rewrite")
    parser.add_argument("--bib", type=Path, required=True, help="path to refs.bib")
    parser.add_argument(
        "--acronyms", type=Path, required=True, help="path to acronyms.qd"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="report orphan citations / dead acronyms; do not modify HTML",
    )
    parser.add_argument(
        "--lint-ignore",
        type=Path,
        default=None,
        help="optional file (one token per line, # comments) with project-"
        "specific exemptions for the undefined-body-acronym and "
        "glossary-italics lints",
    )
    parser.add_argument(
        "--no-expand",
        default="",
        help="comma-separated acronym keys whose first-occurrence "
        "auto-expansion is suppressed (they stay linked and listed)",
    )
    args = parser.parse_args(argv)

    bibmap = parse_bibmap(args.bib)
    acromap = parse_acromap(args.acronyms)
    long_forms = parse_acromap_long_forms(args.acronyms)
    lint_ignore = _load_lint_ignore(args.lint_ignore)
    no_expand = frozenset(k.strip() for k in args.no_expand.split(",") if k.strip())

    if args.check_only:
        return check(args.html, bibmap, acromap, long_forms, lint_ignore)

    rewrite(args.html, bibmap, acromap, long_forms, no_expand)
    return 0


def _load_lint_ignore(path: Path | None) -> frozenset[str]:
    """One token per line; blank lines and #-comment lines are skipped."""
    if path is None or not path.exists():
        return frozenset()
    tokens = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tokens.add(line)
    return frozenset(tokens)


def rewrite(
    html_path: Path,
    bibmap: dict[str, str],
    acromap: dict[str, str],
    long_forms: dict[str, str],
    no_expand: frozenset[str] = frozenset(),
) -> None:
    tree = lxml_html.parse(str(html_path))
    root = tree.getroot()
    rewrite_citations(root, bibmap)
    # Make the reference list dynamic: drop entries the body never cites.
    # Quarkdown renders the whole .bib with no cited-only option, so we
    # filter here. Reported to stderr because a dropped entry silently
    # vanishing from the PDF is worth surfacing.
    dropped_bib = drop_uncited_bib_entries(root)
    if dropped_bib:
        print(
            f"postprocess-links: dropped {len(dropped_bib)} uncited reference "
            f"entries: {sorted(dropped_bib)}",
            file=sys.stderr,
        )
    # Source-level orphan check: bib entries that no body cite resolves to.
    # The drop above can no-op silently if Quarkdown already filters its
    # bibliography output; this catches the entry at the bibmap level.
    unused_bib = find_unused_bib_labels(root, bibmap)
    if unused_bib:
        print(
            f"postprocess-links: {len(unused_bib)} bib entries defined but never cited: "
            f"{sorted(unused_bib)} — remove from refs.bib or add a .cite{{}} in the body",
            file=sys.stderr,
        )
    # rewrite_acronyms runs Auto-Expansion internally as its first text pass:
    # it first tags the acronyms table as a skip-zone, THEN expands, so the
    # expansion never rewrites the table's own definition cells and "first
    # occurrence" resolves to real prose. (Passing long_forms here is what
    # enables that internal expansion step.)
    rewrite_acronyms(root, acromap, long_forms, no_expand=no_expand)
    rewrite_markers(root)
    # Materialise CSS-generated cross-reference text into the DOM so
    # PagedJS sees the real line width (without this, PagedJS treats
    # empty `<span class="cross-reference">` as width 0 and over-packs
    # the line; Chromium then paints the attr()-content past the page
    # boundary and page.pdf() silently clips the overflow).
    materialise_cross_references(root)
    # Split long `<pre><code>` blocks into per-line spans so PagedJS can
    # break across pages. Without this PagedJS treats the inner text as
    # one atomic chunk and silently clips overflowing rows when the block
    # exceeds the remaining page space.
    rewrite_codeblocks(root)
    # Inject List of Figures + List of Tables tables into front-matter
    # marker divs. Must run after cross-references are materialised so
    # data-location attributes are stable; runs before write-back so the
    # injected table HTML is included in the final PDF render.
    inject_listings(root)
    mark_champion_rows(root)
    mark_mean_rows(root)
    # Dynamic glossary: link italic occurrences both ways and drop dead rows.
    dropped_gloss = rewrite_glossary(root)
    if dropped_gloss:
        print(
            f"postprocess-links: dropped {len(dropped_gloss)} unused glossary "
            f"terms: {sorted(dropped_gloss)}",
            file=sys.stderr,
        )
    # Write with explicit doctype to keep PagedJS happy.
    html_bytes = lxml_html.tostring(
        tree, encoding="utf-8", method="html", doctype="<!DOCTYPE html>"
    )
    html_path.write_bytes(html_bytes)


def check(
    html_path: Path,
    bibmap: dict[str, str],
    acromap: dict[str, str],
    long_forms: dict[str, str],
    lint_ignore: frozenset[str] = frozenset(),
) -> int:
    # long_forms: reserved for future caption/heading expansion checks.
    # Unused in check() today; accepted for signature symmetry with rewrite().
    # Read prose text only — strip <head>, <style>, <script>, <code>, <pre>
    # via an XPath that excludes those ancestors. A whole-file regex match
    # would false-positive on `html:not([lang])` CSS selectors and
    # `options.lang` JS properties. We deliberately DO descend into <a>
    # because the check should work both pre-rewrite (bare body brackets)
    # and post-rewrite (brackets wrapped in <a class="bib-cite">).
    tree = lxml_html.parse(str(html_path))
    text_nodes = tree.xpath(
        "//text()"
        "[not(ancestor::head)]"
        "[not(ancestor::style)]"
        "[not(ancestor::script)]"
        "[not(ancestor::code)]"
        "[not(ancestor::pre)]"
        "[not(ancestor::kbd)]"
        "[not(ancestor::samp)]"
    )
    prose = "\n".join(str(t) for t in text_nodes)

    # Orphan citation labels: [XYZ] in body text whose label is unknown.
    orphans: set[str] = set()
    for match in CITE_LABEL.finditer(prose):
        label = match.group("label")
        if label in bibmap:
            continue
        if label in PLACEHOLDER_LABELS:
            continue
        orphans.add(label)

    # Dead acronyms: KEY with no word-boundary occurrence in body prose
    # beyond the acronyms-table entry itself. The table contributes one
    # occurrence per key, so we require >= 2 (table + at least one body use).
    # The trailing `s?` mirrors add_body_links' plural handling so a key
    # used only in plural ("UIs", "LLMs") still counts as used — otherwise
    # this warning flags acronyms the rendered table correctly keeps.
    keys_in_use: set[str] = set()
    for key in acromap:
        pattern = re.compile(rf"\b{re.escape(key)}s?\b")
        if len(pattern.findall(prose)) >= 2:
            keys_in_use.add(key)
    dead_acronyms = set(acromap) - keys_in_use

    failed = False
    if orphans:
        print(
            f"postprocess-links: orphan citation labels (no matching bib entry): "
            f"{sorted(orphans)}",
            file=sys.stderr,
        )
        failed = True

    # Unused bib entries are warnings, not blockers — symmetric with dead
    # acronyms / dead glossary terms. Needs the body-link side-effect from
    # add_body_links, so we run it on a fresh parse copy.
    root_for_unused = lxml_html.parse(str(html_path)).getroot()
    rewrite_citations(root_for_unused, bibmap)
    unused_bib = find_unused_bib_labels(root_for_unused, bibmap)
    if unused_bib:
        print(
            f"postprocess-links: bib entries defined but never cited: "
            f"{sorted(unused_bib)}",
            file=sys.stderr,
        )
    if dead_acronyms:
        print(
            f"postprocess-links: dead acronyms (defined but never used in body): "
            f"{sorted(dead_acronyms)}",
            file=sys.stderr,
        )
        # Dead acronyms are a warning, not an error — they are common during
        # writing. Return 0 from this check; the failure path stays for
        # orphan citations only.

    # Hard gate: italic German single-word terms that escape the glossary.
    root = tree.getroot()
    table = _find_glossary_table(root)
    terms = glossary_terms(root)
    unglossed = (
        find_unglossed_italics(root, terms, acromap, table, lint_ignore)
        if table is not None else set()
    )
    if unglossed:
        print(
            f"postprocess-links: italic terms missing from glossary (BLOCKER): "
            f"{sorted(unglossed)} — either add to the glossary appendix "
            f"or list in the --lint-ignore file",
            file=sys.stderr,
        )
        failed = True
    # Dead glossary terms: report as a warning (mutates the local tree only).
    dropped_terms = rewrite_glossary(root)
    if dropped_terms:
        print(
            f"postprocess-links: dead glossary terms (defined but never used italic in body): "
            f"{sorted(dropped_terms)}",
            file=sys.stderr,
        )

    # Body-acronym diff: uppercase tokens in body prose that look like
    # acronyms but are absent from the acronyms table. Failing check —
    # every body acronym must be defined or explicitly blocklisted.
    undefined = find_undefined_body_acronyms(root, acromap, lint_ignore)
    if undefined:
        print(
            f"postprocess-links: body acronyms missing from acronyms table: "
            f"{sorted(undefined)} — either add to acronyms.qd or list in "
            f"the --lint-ignore file",
            file=sys.stderr,
        )
        failed = True

    # Caption-period rule: every <figcaption> and table <caption> must end
    # with a period. Repo convention; enforces consistency across all
    # figures and tables.
    caption_violations = find_caption_period_violations(root)
    if caption_violations:
        print(
            f"postprocess-links: captions not ending in '.': "
            f"{[(t, s[:60] + '...' if len(s) > 60 else s) for t, s in caption_violations]}",
            file=sys.stderr,
        )
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
