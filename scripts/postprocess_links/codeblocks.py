"""Long-`<pre>` pagination: rewrite Quarkdown's `<pre><code>` fence into
a `<div class="codeblock">` of `<div class="code-line">` rows so PagedJS
can find block-level break points inside otherwise-atomic code blocks.

Quarkdown emits fenced code as `<pre><code class="language-X">...</code></pre>`
whose inner text is a single CDATA-style chunk. PagedJS treats the chunk
as one indivisible atom and silently clips overflow when the listing
exceeds the remaining page space — even with `break-inside: auto` and
`overflow: visible` on the host element, there are no internal block
boundaries the paginator can split at.

Two structural fixes were attempted and discarded before this one:

1. Wrap each line in `<span class="code-line">` inside `<pre><code>`.
   CSS `display: block` on the span was meant to expose per-line block
   boundaries, but PagedJS-on-Chromium does not honor it consistently
   when the span lives inside a `<pre>` whose `white-space` is `pre`.
2. Wrap each line in `<div class="code-line">` inside `<pre><code>`.
   HTML5 forbids block-level descendants of `<pre>` (`<pre>` accepts
   only phrasing content), so the browser silently corrects the DOM —
   either hoisting the divs out of the `<pre>` or treating them as
   inline phrasing, again denying PagedJS the block boundaries.

This stage instead **replaces** `<pre><code class="language-X">…</code></pre>`
with a structurally legal `<div class="codeblock language-X">` whose
children are one `<div class="code-line">` per source line. Block-in-
block is valid; PagedJS sees each row as an independently breakable
unit and splits long listings at row boundaries. The accompanying CSS
rules in `styles.css` give the wrapper the same visual treatment a
fenced code block had (monospace, padding, light border, no background)
so the rewrite is transparent to readers.

Syntax highlighting:

Each listing is tokenized at build time with Pygments and its tokens are
wrapped in ``<span class="hl-*">`` so ``styles.css`` can colour them. The
whole block is lexed once (so multi-line string literals tokenize
correctly) and the token stream is then split at newlines into the
per-line ``<div class="code-line">`` rows PagedJS needs. The language is
taken from the fence's ``language-*`` class (e.g. ``language-json``).
Fences with no recognized language, or any tokenization failure, fall
back to plain unhighlighted text — the previous behaviour — so the stage
never breaks a build over an exotic listing.

Skip behaviour:

* Already-processed wrappers (`<div class="codeblock">`) are left
  alone — idempotent re-runs.
* Empty `<code>` elements (no text content) are left alone.
"""

from __future__ import annotations

from lxml import etree


CODEBLOCK_CLASS = "codeblock"
CODE_LINE_CLASS = "code-line"


def _token_class(token_type) -> str | None:
    """Map a Pygments token type to a ``hl-*`` CSS class, or ``None`` for
    tokens that should inherit the body ink colour (whitespace, plain
    text, errors). Subtype membership (``in``) walks the token hierarchy,
    so e.g. ``String.Double in String`` is true."""
    from pygments.token import (
        Comment,
        Keyword,
        Name,
        Number,
        Operator,
        Punctuation,
        String,
    )

    # Order matters: check specific Name subtypes before the generic ones.
    if token_type in String:
        return "hl-str"
    if token_type in Number:
        return "hl-num"
    if token_type in Keyword:
        return "hl-kw"
    if token_type in Comment:
        return "hl-comment"
    if token_type in Name.Tag:
        return "hl-key"  # JSON object keys are Name.Tag
    if token_type in Name.Builtin or token_type in Name.Function:
        return "hl-name"  # shell builtins / command names
    if token_type in Operator:
        return "hl-op"
    if token_type in Punctuation:
        return "hl-punct"
    return None


def _highlight_lines(
    text: str, language: str
) -> list[list[tuple[str | None, str]]] | None:
    """Tokenize ``text`` for ``language`` and return one list of
    ``(css_class, segment)`` pairs per source line. Returns ``None`` if
    Pygments is unavailable, the language is unknown, or lexing fails —
    callers then fall back to plain per-line text."""
    if not language:
        return None
    try:
        from pygments import lex
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound

        try:
            lexer = get_lexer_by_name(language)
        except ClassNotFound:
            return None
        lines: list[list[tuple[str | None, str]]] = [[]]
        for token_type, value in lex(text, lexer):
            css_class = _token_class(token_type)
            # A token value may straddle newlines (whitespace runs,
            # multi-line strings); split it so each row gets its slice.
            parts = value.split("\n")
            for i, part in enumerate(parts):
                if i > 0:
                    lines.append([])
                if part:
                    lines[-1].append((css_class, part))
        return lines
    except Exception:
        # Highlighting is best-effort decoration; never fail a build over it.
        return None


def _coalesce_whitespace(
    segments: list[tuple[str | None, str]],
) -> list[tuple[str | None, str]]:
    """Fold untagged (``None``-class) runs into an adjacent coloured
    token's text so the emitted DOM contains **no whitespace-only text
    nodes**. This is load-bearing for pagination: PagedJS strips
    whitespace-only text nodes while cloning content into page
    fragments, which silently swallows code indentation and the spaces
    between tokens (e.g. ``"key": value`` collapses to ``"key":value``).
    Keeping every space inside a non-empty token span (or, for an
    all-whitespace line, as non-breaking spaces) survives that pass.

    Leading whitespace is prepended to the first following coloured
    token; inter-token whitespace is appended to the preceding one. A
    line with no coloured token at all (blank or indentation-only) is
    emitted as a single untagged run with its spaces turned into U+00A0
    so it, too, survives and keeps the row's rendered height."""
    if not segments:
        return [(None, " ")]  # blank line: NBSP preserves row height
    out: list[list] = []
    pending = ""  # leading/untagged run awaiting a coloured anchor
    for css_class, text in segments:
        if css_class is None:
            if out:
                out[-1][1] += text  # attach to preceding coloured token
            else:
                pending += text
        else:
            if pending:
                text = pending + text
                pending = ""
            out.append([css_class, text])
    if pending:
        # No coloured token on this line (all whitespace / plain). NBSP
        # pure-whitespace content so PagedJS does not strip the node.
        if pending.strip() == "":
            pending = pending.replace(" ", " ")
        out.append([None, pending])
    return [(css_class, text) for css_class, text in out]


def _language_of(language_classes: list[str]) -> str:
    """Extract the bare language name from the first ``language-*`` class
    (``language-json`` -> ``json``); empty string if none."""
    for cls in language_classes:
        if cls.startswith("language-"):
            return cls[len("language-") :]
    return ""


def rewrite_codeblocks(root: etree._Element) -> int:
    """Rewrite every ``<pre><code>`` fence into
    ``<div class="codeblock">`` of ``<div class="code-line">`` rows so
    PagedJS can break long listings across pages. Returns the number of
    code blocks rewritten."""
    count = 0
    # Snapshot the list because we mutate the tree as we iterate.
    for pre in list(root.iter("pre")):
        code = pre.find("code")
        if code is None:
            continue
        # Gather the inner text. Quarkdown does not emit highlight.js spans
        # in the paged build, so the inner content is raw text — we tokenize
        # it ourselves below for colouring.
        text = "".join(code.itertext())
        if not text or not text.strip():
            continue
        # Carry the `language-*` class onto the new wrapper for any
        # downstream styling that needs to discriminate per language.
        code_class = code.get("class") or ""
        language_classes = [
            c for c in code_class.split() if c.startswith("language-")
        ]

        wrapper = etree.Element("div")
        wrapper_classes = [CODEBLOCK_CLASS] + language_classes
        wrapper.set("class", " ".join(wrapper_classes))

        highlighted = _highlight_lines(text, _language_of(language_classes))
        if highlighted is not None:
            # Drop a trailing empty line from the fence's final newline.
            if highlighted and not highlighted[-1]:
                highlighted.pop()
            for segments in highlighted:
                line_div = etree.SubElement(wrapper, "div")
                line_div.set("class", CODE_LINE_CLASS)
                for css_class, segment in _coalesce_whitespace(segments):
                    span = etree.SubElement(line_div, "span")
                    if css_class is not None:
                        span.set("class", css_class)
                    span.text = segment
        else:
            # Fallback: plain unhighlighted text, one div per source line.
            lines = text.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            for line in lines:
                line_div = etree.SubElement(wrapper, "div")
                line_div.set("class", CODE_LINE_CLASS)
                # Preserve the line text exactly (including leading whitespace).
                line_div.text = line if line else " "

        # Replace the entire <pre> element with the new wrapper, in place.
        parent = pre.getparent()
        if parent is None:
            continue
        # Preserve tail text after the original <pre>.
        wrapper.tail = pre.tail
        parent.replace(pre, wrapper)
        # Tag the parent <figure> so CSS can target it without :has().
        if parent.tag == "figure":
            fig_cls = (parent.get("class") or "").split()
            if "has-codeblock" not in fig_cls:
                fig_cls.append("has-codeblock")
                parent.set("class", " ".join(fig_cls))
        count += 1
    return count
