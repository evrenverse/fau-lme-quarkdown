"""Acronym rewrite: body `HTTP` (etc.) becomes an <a> link pointing at
the matching <tr> in the acronyms table; the <tr> gets an `id`.

The first cell of each acronyms table row contains `<strong>KEY</strong>`.
Strong cells get the `id`, the body occurrences get the `href`.
"""

from __future__ import annotations

import re
from lxml import etree

from .dom_rewriter import iter_text_nodes, replace_text_with_anchor

# Skip zones for body acronyms — wider than for citations because we also
# avoid headings, captions, the acronyms table itself, and the document
# head (title/style/script/meta/link). Without head-skipping, a second
# pass over the rewritten HTML wraps text in <title> and re-escapes
# entities in <style>, breaking idempotence on real Quarkdown output.
BODY_SKIP_TAGS = frozenset(
    {"code", "pre", "kbd", "samp", "a", "h1", "h2", "h3", "h4", "h5", "h6",
     "strong",
     "head", "title", "style", "script", "meta", "link"}
)
# "lmecover" — thesis cover-page wrapper; skip so the title renders as
# "LLM-Based" (no acronym link clutter, no first-occurrence expansion).
# "acronyms-table" — the acronyms table itself (tagged by rewrite_acronyms);
# skip so neither Auto-Expansion nor body-linking touches its definition
# cells (otherwise an acronym used inside another's definition expands there,
# e.g. "Office Open XML Document" -> "...Extensible Markup Language (XML)...",
# and "first occurrence" would resolve to the table instead of real prose).
BODY_SKIP_CLASS_SUBSTRINGS = ("katex", "bibliography", "lmecover", "acronyms-table")

# Class marker placed on the acronyms table so the skip-zone above catches it.
ACRONYMS_TABLE_CLASS = "acronyms-table"

# Regex for scanning body text for uppercase acronym-shaped tokens.
BODY_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")

# Tokens that match BODY_ACRONYM_RE but are not acronyms in ANY document:
# linguistic noise only (words, numerals, codes, date formats). Project-specific
# tokens (enum values, product names, prompt-listing samples) belong in the
# consumer's --lint-ignore file, not here.
ACRONYM_TOKEN_BLOCKLIST = frozenset({
    # Common English words that happen to be all-caps in some contexts.
    "I", "A", "OK", "TO", "IS", "OR", "BUT", "AND", "FOR", "THE", "NO", "NOT", "MAY",
    # German function words that appear all-caps in markdown emphasis.
    "NICHT", "NIEMALS", "IMMER", "KEIN", "NIE", "MUSS", "GENAU", "EINEN", "SELBST",
    # Roman numerals used in list numbering / chapter references.
    "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
    # ISO language / country codes and currency codes that appear in prose.
    "BY", "DE", "EN", "GR", "EUR", "USD",
    # Date-format placeholders (English and German).
    "YYYY", "MM", "DD", "JJJJ",
})


def _find_acronyms_table(root: etree._Element) -> etree._Element | None:
    """The table whose nearest preceding <h1> mentions "Acronyms"
    (the heading carries id="acronyms" and text "Acronyms")."""
    for candidate in root.xpath("//table"):
        h1 = candidate.xpath("preceding::h1[1]")
        if h1 and "acronym" in (h1[0].text_content() or "").lower():
            return candidate
    return None


def rewrite_acronyms(
    root: etree._Element,
    acromap: dict[str, str],
    long_forms: dict[str, str] | None = None,
    no_expand: frozenset[str] = frozenset(),
) -> None:
    """In-place rewrite (bidirectional, mirroring rewrite_glossary):
    0. Tag the acronyms table with ACRONYMS_TABLE_CLASS so the skip-zone
       excludes its definition cells from every text pass below.
    1. (Optional) Expand first body occurrence of each KEY to "Long Form
       (KEY)" via `expand_first_occurrences` when `long_forms` is provided.
    2. Tag each `<tr>` whose first cell holds `<strong>KEY</strong>` with
       `id="acro-<lowercased-key>"`.
    3. Wrap every body occurrence of a known KEY with an <a> link to its row.
    4. Mark the FIRST body link of each KEY with `id="<slug>-first"`.
    5. Turn each table KEY into a back-link to `#<slug>-first` when that
       first occurrence exists (composite-/table-only keys stay plain).
    6. Remove rows for acronyms that had no body occurrence (dead acronyms).

    Steps run in this order so each pass sees the targets the next one needs:
    Auto-Expansion before link-wrapping (so the inserted "(KEY)" still gets an
    anchor); mark_first_occurrences after link-wrapping; key back-linking after
    the first-occurrence ids exist.
    """
    if not acromap:
        return
    table = _find_acronyms_table(root)
    if table is not None:
        cls = table.get("class", "")
        if ACRONYMS_TABLE_CLASS not in cls.split():
            table.set("class", (cls + " " + ACRONYMS_TABLE_CLASS).strip())
    if long_forms:
        expand_first_occurrences(root, long_forms, no_expand=no_expand)
    set_acro_ids(root, acromap)
    add_body_links(root, acromap)
    mark_first_occurrences(root, acromap)
    _link_keys_to_first(root, acromap, table)
    _remove_dead_rows(root, acromap, table)


def mark_first_occurrences(root: etree._Element, acromap: dict[str, str]) -> None:
    """Give the first body acro-link of each slug (document order) an
    `id="<slug>-first"` so the table KEY can back-link to it. Mirrors
    glossary.mark_first_occurrences."""
    pending = set(acromap.values())
    for a in root.iter("a"):
        if not pending:
            break
        if "acro-link" not in (a.get("class") or ""):
            continue
        href = a.get("href", "")
        if not href.startswith("#"):
            continue
        slug = href[1:]
        if slug in pending:
            a.set("id", f"{slug}-first")
            pending.discard(slug)


def _link_keys_to_first(
    root: etree._Element, acromap: dict[str, str], table: etree._Element | None
) -> None:
    """Turn each table KEY (`<strong>KEY</strong>`) into a link to its first
    body occurrence (`#<slug>-first`) when that anchor exists. Mirrors
    glossary.set_glossary_ids' back-link step; keys with no body occurrence
    stay plain text."""
    if table is None:
        return
    for tr in table.iter("tr"):
        cells = list(tr)
        if not cells:
            continue
        strong = cells[0].find("strong")
        if strong is None or strong.text is None:
            continue
        key = strong.text.strip()
        slug = acromap.get(key)
        if not slug:
            continue
        target = f"{slug}-first"
        if strong.find("a") is None and root.xpath(f'//*[@id="{target}"]'):
            txt = strong.text
            strong.text = None
            a = etree.SubElement(strong, "a")
            a.set("href", f"#{target}")
            a.text = txt


def set_acro_ids(root: etree._Element, acromap: dict[str, str]) -> None:
    """Assign `id` to acronym table rows. The first child of the first
    cell must be `<strong>` containing the KEY text."""
    for tr in root.iter("tr"):
        cells = list(tr)
        if not cells:
            continue
        first_cell = cells[0]
        strong = first_cell.find("strong")
        if strong is None or strong.text is None:
            continue
        key = strong.text.strip()
        if key not in acromap:
            continue
        slug = acromap[key]
        if tr.get("id") != slug:
            tr.set("id", slug)


def add_body_links(root: etree._Element, acromap: dict[str, str]) -> None:
    """Wrap each body occurrence of any acronym KEY with an <a> anchor.

    Keys are concatenated into one alternation, longest-first so longer
    keys (e.g. BFCL) win over shorter prefixes (BF). A trailing lowercase
    "s" is absorbed into the match so English plurals like "LLMs" or
    "APIs" link to the same anchor as the singular ("LLM", "API"), with
    the original surface form preserved as the link text. Skip zones
    include `<strong>` so the acronyms-table KEY cells are not
    self-linked.
    """
    keys_sorted = sorted(acromap.keys(), key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in keys_sorted) + r")s?\b"
    )

    def make_anchor(match: re.Match) -> tuple[str, str, str] | None:
        key = match.group(1)
        if key not in acromap:
            return None
        return (f"#{acromap[key]}", "acro-link", match.group(0))

    for text_node in list(iter_text_nodes(root, BODY_SKIP_TAGS, BODY_SKIP_CLASS_SUBSTRINGS)):
        replace_text_with_anchor(text_node, pattern, make_anchor)


# Skip zones where `add_body_links` cannot insert anchors but where an
# acronym mention still keeps the row alive. Plain-text scan over these
# zones below ensures e.g. an acronym used only in a chapter title is
# not falsely dropped from the rendered table. (figcaption/caption are
# now handled directly by `add_body_links`, so the fallback covers only
# heading tags.)
_DEAD_ROW_FALLBACK_TAGS = (
    "h1", "h2", "h3", "h4", "h5", "h6",
)


def _remove_dead_rows(
    root: etree._Element,
    acromap: dict[str, str],
    table: etree._Element | None = None,
) -> None:
    """Remove acronym table rows whose KEY had no body occurrence.

    `add_body_links` inserts `<a class="acro-link" href="#<slug>">` for every
    body occurrence outside `BODY_SKIP_TAGS`. We collect those slugs as the
    primary used-set. Headings and captions are skipped by `add_body_links`
    on purpose (they should not contain links), so a plain-text fallback
    scan over `_DEAD_ROW_FALLBACK_TAGS` adds slugs whose KEY appears there.
    Without this fallback an acronym used only in a chapter title or figure
    caption would be silently dropped from the rendered table.

    The acronyms table is a skip-zone (so its cells carry no acro-link), but a
    KEY referenced inside ANOTHER acronym's definition (e.g. "FAU" in the LME
    definition "...Pattern Recognition Lab, FAU)") must stay listed so the
    reader can look it up. When `table` is given we plain-text scan its SECOND
    cell only (the definition) as an extra keep-signal — never the first cell,
    whose KEY would otherwise keep every row alive. This separates the keep
    criterion from the link criterion, mirroring the glossary.
    """
    # Primary used-set: anchors inserted by `add_body_links`.
    used_slugs: set[str] = set()
    for a in root.iter("a"):
        if "acro-link" in (a.get("class") or ""):
            href = a.get("href", "")
            if href.startswith("#"):
                used_slugs.add(href[1:])

    # Fallback used-set: plain-text scan of headings + captions, plus the
    # acronyms table's own definition cells (keep-signal, see docstring).
    if acromap:
        fallback_pattern = re.compile(
            r"\b(" + "|".join(re.escape(k) for k in acromap.keys()) + r")s?\b"
        )

        def _harvest(text: str) -> None:
            for match in fallback_pattern.finditer(text):
                key = match.group(1)
                if key in acromap:
                    used_slugs.add(acromap[key])

        for tag in _DEAD_ROW_FALLBACK_TAGS:
            for el in root.iter(tag):
                _harvest("".join(el.itertext()))
        if table is not None:
            for tr in table.xpath(".//tr"):
                cells = list(tr)
                if len(cells) >= 2:
                    _harvest("".join(cells[1].itertext()))

    # Build a reverse map: slug -> key, for efficient lookup.
    slug_to_key = {v: k for k, v in acromap.items()}

    # Walk all <tr> elements; remove those whose slug is not in used_slugs.
    for tr in list(root.iter("tr")):
        tr_id = tr.get("id", "")
        if tr_id not in slug_to_key:
            # Not an acronym row (no id, or id not in acromap slugs).
            continue
        if tr_id not in used_slugs:
            parent = tr.getparent()
            if parent is not None:
                parent.remove(tr)


# ---------------------------------------------------------------------------
# Auto-Expansion: first-occurrence "Long Form (KEY)" rewrite.
#
# Why this lives next to add_body_links: both passes share the same body
# skip-zone semantics and walk the same iter_text_nodes stream. Keeping
# them adjacent makes the ordering contract obvious: Auto-Expansion must
# run BEFORE add_body_links so the expansion stays plain text (and the
# KEY inside the parens still gets linked by add_body_links afterwards).
# ---------------------------------------------------------------------------

# Toggle for rollback without code revert. Wired by postprocess_links.py
# (Task 3); left True here so the postprocessor pass is on by default.
ENABLE_FIRST_OCCURRENCE_EXPANSION = True

# Acronyms whose first-occurrence Auto-Expansion is suppressed: spelling the
# long form out in prose reads worse than the bare key, e.g. because the long
# form repeats the acronym ("XYZ Datenaustausch (XYZ-DA)") or the term is
# already established by numbered markers / chapter headings before its first
# bare use. Such keys stay linked by add_body_links and listed in the acronyms
# table; only the inline "Long Form (KEY)" rewrite is skipped. Project-specific
# keys are passed per document via --no-expand (see postprocess_links.py);
# this constant stays empty in the theme.
EXPANSION_BLOCKLIST = frozenset()

# Tolerance for the lookbehind: scan the last ~100 chars before the acronym match.
LOOKBEHIND_WINDOW = 100


def _normalise_for_lookbehind(s: str) -> str:
    """Lowercase + collapse any run of hyphens/spaces to a single space.
    'Small-to-Medium Enterprise' and 'small to medium enterprise' map to
    the same normalised form."""
    return re.sub(r"[-\s]+", " ", s).strip().lower()


def _long_form_already_adjacent(text_before: str, long_form: str) -> bool:
    """True when a normalised form of `long_form` appears inside the last
    LOOKBEHIND_WINDOW characters of `text_before`. Used to suppress
    re-expansion of an acronym whose long form was manually written by
    the author immediately before, regardless of case or hyphen/space
    variant ('Small-to-Medium Enterprise' vs 'small to medium enterprise').
    """
    if not long_form:
        return False
    window = (
        text_before[-LOOKBEHIND_WINDOW:]
        if len(text_before) > LOOKBEHIND_WINDOW
        else text_before
    )
    return _normalise_for_lookbehind(long_form) in _normalise_for_lookbehind(window)


def _pluralise_long_form(long_form: str) -> str:
    """Naive English plural: append 's' to the long form.

    Handles "Large Language Model" -> "Large Language Models". For multi-word
    long forms this is a reasonable default. German long forms that don't
    have a clean English plural ("Datenschutz-Grundverordnung") are
    typically not used in plural in the thesis (statutes are singular), so
    the fallback of "X (KEYs)" stays semantically correct even if the
    pluralisation reads slightly off.
    """
    if not long_form:
        return long_form
    return long_form + "s"


def _replace_text_inline(
    node,
    pattern: re.Pattern[str],
    make_replacement,
) -> None:
    """In-place plain-text substitution on a TextNode.

    Mirrors `replace_text_with_anchor` but writes plain text back into
    `element.text` / `element.tail` instead of inserting `<a>` children.
    Used by Auto-Expansion because the expanded "Long Form (KEY)" must
    stay in the text stream so a downstream `add_body_links` pass can
    still wrap the bare KEY inside the parens with an anchor.

    `make_replacement(match)` returns the replacement string for each
    match, or `None` to leave it untouched. Matches whose replacement is
    None are passed through verbatim.
    """
    original = node.text or ""
    matches = list(pattern.finditer(original))
    if not matches:
        return
    decisions: list[tuple[re.Match, str]] = []
    for m in matches:
        repl = make_replacement(m)
        if repl is not None:
            decisions.append((m, repl))
    if not decisions:
        return
    out_pieces: list[str] = []
    cursor = 0
    for m, replacement in decisions:
        out_pieces.append(original[cursor:m.start()])
        out_pieces.append(replacement)
        cursor = m.end()
    out_pieces.append(original[cursor:])
    new_text = "".join(out_pieces)
    if node.role == "text":
        node.element.text = new_text
    else:  # role == "tail"
        node.element.tail = new_text


def _parent_text_before_match(
    text_node, original: str, match_start: int
) -> str | None:
    """Return the contiguous text content of the text node's owning paragraph
    (or table cell, etc.) up to the start of the match.

    Used to detect a manual spell-out that sits in a sibling text node (e.g.
    inside <em>...</em>) which the within-node window cannot see.

    For text-role nodes the block ancestor is the element itself; for tail-role
    nodes it is the element's parent (the tail belongs to the parent's text
    stream). Returns `None` if the block cannot be located or `original` is
    not found inside the reconstructed text (e.g. node was already mutated).
    """
    if text_node.role == "text":
        block = text_node.element
    else:  # role == "tail" — tail belongs to the parent's content stream.
        block = text_node.element.getparent()
    if block is None:
        return None
    full = "".join(block.itertext())
    # Find where `original` (the current text-node window) lives inside
    # the reconstructed block text, then return the prefix up to the match.
    idx = full.find(original)
    if idx == -1:
        return None
    return full[: idx + match_start]


def expand_first_occurrences(
    root: etree._Element,
    long_forms: dict[str, str],
    enabled: bool = ENABLE_FIRST_OCCURRENCE_EXPANSION,
    no_expand: frozenset[str] = frozenset(),
) -> None:
    """Expand the first body occurrence of each KEY to "Long Form (KEY)".

    Scans text nodes in document order; for each KEY whose Long Form is
    non-empty, mutates the first surface-form occurrence (singular OR
    plural) by replacing it with the expanded form. Subsequent
    occurrences of the same KEY are left untouched. Plural surface forms
    are pluralised via `_pluralise_long_form` -> "Large Language Models
    (LLMs)".

    Skips when:
        - `enabled` is False (rollback toggle)
        - the KEY's Long Form value is empty (no expansion possible)
        - the Long Form already appears within ~30 chars immediately
          before the match (manual-spellout collision avoidance, so prose
          that already says "European Union (EU)" isn't rewritten as
          "European Union (European Union (EU))")
        - the match sits inside a skip zone (BODY_SKIP_TAGS /
          BODY_SKIP_CLASS_SUBSTRINGS)

    Mutates `root` in place. Idempotent on already-expanded HTML: the
    collision-avoidance check sees the Long Form just before the KEY and
    skips, while keys with no surviving bare occurrence are simply not
    matched a second time.
    """
    if not enabled or not long_forms:
        return

    pending: set[str] = {k for k, v in long_forms.items() if v}
    if not pending:
        return
    # Longest-first so TCP/IP wins over TCP, KFZ-HU over RTV.
    keys_sorted = sorted(pending, key=len, reverse=True)
    # Hyphen-guarded boundaries: a plain \b also matches inside hyphenated
    # compounds ("GPT-5.4", "generative-AI"), where a first-occurrence
    # expansion tears the compound apart ("Generative Pre-trained
    # Transformer (GPT)-5.4"). Matches glued to a hyphen on either side are
    # therefore not expansion candidates; the first FREE-standing occurrence
    # expands instead. Body LINKS (add_body_links) keep plain \b on purpose:
    # a compound occurrence must still count as usage so the acronym row
    # survives _remove_dead_rows.
    pattern = re.compile(
        r"(?<![\w-])("
        + "|".join(re.escape(k) for k in keys_sorted)
        + r")(s?)(?![\w-])"
    )

    for text_node in list(
        iter_text_nodes(root, BODY_SKIP_TAGS, BODY_SKIP_CLASS_SUBSTRINGS)
    ):
        if not pending:
            break
        original = text_node.text or ""
        if not original:
            continue

        def make_replacement(match: re.Match) -> str | None:
            key = match.group(1)
            plural_s = match.group(2)
            if key not in pending:
                return None
            if key in EXPANSION_BLOCKLIST or key in no_expand:
                pending.discard(key)
                return None
            long_form = long_forms.get(key, "")
            if not long_form:
                pending.discard(key)
                return None
            # Collision avoidance: Long Form already spelled out within
            # ~30 chars before the match? Skip + mark as handled so
            # subsequent matches of the same key are also left alone.
            #
            # Two checks because authors typically spell out only the head
            # of a long form before parenthetical clarification:
            #   acronyms table: "Long Form (clarifying remark)"
            #   prose:          "Long Form (KEY)"
            # Without prefix matching, the prose triggers a double-expansion:
            # "Long Form (Long Form (clarifying remark) (KEY))".
            long_form_prefix = long_form.split(" (", 1)[0].strip()
            window_start = max(0, match.start() - len(long_form) - 5)
            window = original[window_start:match.start()]
            if long_form in window or long_form_prefix in window:
                pending.discard(key)
                return None
            # Normalised lookbehind: catches case + hyphen/space variants
            # the exact-substring check above misses, e.g. prose
            # "small-to-medium enterprise (SME)" against a table entry
            # "Small-to-Medium Enterprise".
            if _long_form_already_adjacent(window, long_form) or \
                    _long_form_already_adjacent(window, long_form_prefix):
                pending.discard(key)
                return None
            # Cross-node check: italic / bold / code wrappers split the
            # manual spell-out across sibling text nodes, e.g.
            #   <em>Large Language Model</em> (LLM)
            # puts the long form in <em>.text and "(LLM)" in <em>.tail,
            # so the within-node window above cannot see it. Reconstruct
            # the owning element's contiguous text via itertext() and
            # re-run the same window check on that view.
            full_text = _parent_text_before_match(text_node, original, match.start())
            if full_text is not None and (
                long_form in full_text or long_form_prefix in full_text
            ):
                pending.discard(key)
                return None
            # Normalised cross-node lookbehind: same tolerance as above
            # but applied to the reconstructed parent-block text.
            if full_text is not None and (
                _long_form_already_adjacent(full_text, long_form)
                or _long_form_already_adjacent(full_text, long_form_prefix)
            ):
                pending.discard(key)
                return None
            # Build the expansion from the long-form CORE (the head before any
            # parenthetical clarification), so an acronyms-table gloss like
            # "Abkürzungsverzeichnis (list of abbreviations)" expands in
            # prose as "Abkürzungsverzeichnis (AV)", not the double-parenthesised
            # "Abkürzungsverzeichnis (list of abbreviations) (AV)".
            # long_form_prefix is the same split-on-" (" head the collision
            # checks above already use; for clarification-free long forms it
            # equals long_form, so unparenthesised acronyms are unaffected.
            if plural_s:
                expansion = f"{_pluralise_long_form(long_form_prefix)} ({key}{plural_s})"
            else:
                expansion = f"{long_form_prefix} ({key})"
            pending.discard(key)
            return expansion

        _replace_text_inline(text_node, pattern, make_replacement)


def find_undefined_body_acronyms(
    root: etree._Element,
    acromap: dict[str, str],
    extra_blocklist: frozenset[str] = frozenset(),
) -> set[str]:
    """Return body tokens matching \\b[A-Z]{2,}\\b that are not in acromap.

    Scans the body text (respecting the same skip zones as `add_body_links`)
    and collects uppercase tokens that look like acronyms but are not defined
    in the acronyms table. Used by the `--check-only` pass to surface
    missing-acronym candidates for review. `extra_blocklist` carries the
    consumer's project-specific exemptions (--lint-ignore).
    """
    seen: set[str] = set()
    for text_node in iter_text_nodes(root, BODY_SKIP_TAGS, BODY_SKIP_CLASS_SUBSTRINGS):
        text = text_node.text or ""
        for tok in BODY_ACRONYM_RE.findall(text):
            if tok in ACRONYM_TOKEN_BLOCKLIST or tok in extra_blocklist:
                continue
            if tok in acromap:
                continue
            seen.add(tok)
    return seen
