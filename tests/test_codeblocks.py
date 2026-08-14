"""Tests for the code-listing rewrite + Pygments syntax highlighting
(`postprocess_links/codeblocks.py`)."""

from __future__ import annotations

from lxml import html as lxml_html

from postprocess_links.codeblocks import rewrite_codeblocks


def _parse(fragment: str) -> lxml_html.HtmlElement:
    # document_fromstring keeps a stable <html><body> root so the <pre>
    # has a real parent to be replaced in place (mirrors the production
    # path where postprocess_links parses a full document).
    return lxml_html.document_fromstring(f"<body>{fragment}</body>")


def _codeblock(root):
    blocks = root.xpath(".//div[contains(@class,'codeblock')]")
    return blocks[0] if blocks else None


JSON_FENCE = (
    '<pre><code class="language-json">{\n'
    '  "name": "foo",\n'
    "  \"n\": 42,\n"
    '  "ok": true\n'
    "}\n"
    "</code></pre>"
)


def test_rewrites_pre_into_codeblock_with_code_lines():
    root = _parse(JSON_FENCE)
    n = rewrite_codeblocks(root)
    assert n == 1
    block = _codeblock(root)
    assert block is not None
    assert "codeblock" in block.get("class")
    assert "language-json" in block.get("class")
    lines = block.findall("div[@class='code-line']")
    # 4 content rows: `{`, name, n, ok, `}` -> 5 rows, trailing newline dropped.
    assert len(lines) == 5


def test_json_tokens_get_highlight_spans():
    root = _parse(JSON_FENCE)
    rewrite_codeblocks(root)
    block = _codeblock(root)
    classes = {span.get("class") for span in block.findall(".//span")}
    assert "hl-key" in classes  # object keys
    assert "hl-str" in classes  # string value "foo"
    assert "hl-num" in classes  # 42
    assert "hl-kw" in classes  # true
    assert "hl-punct" in classes  # braces / colons


def test_full_text_preserved_through_highlighting():
    root = _parse(JSON_FENCE)
    rewrite_codeblocks(root)
    block = _codeblock(root)
    rebuilt = "\n".join("".join(line.itertext()) for line in block)
    assert '"name": "foo"' in rebuilt
    assert '"n": 42' in rebuilt
    assert '"ok": true' in rebuilt


def test_leading_indentation_preserved():
    root = _parse(JSON_FENCE)
    rewrite_codeblocks(root)
    block = _codeblock(root)
    # The "name" row must keep its two-space indent.
    name_row = next(
        line for line in block if '"name"' in "".join(line.itertext())
    )
    assert "".join(name_row.itertext()).startswith("  ")


def test_no_whitespace_only_text_nodes():
    # Load-bearing for PagedJS: it strips whitespace-only text nodes while
    # paginating, which would swallow indentation and inter-token spaces.
    # Every space must live inside a non-empty token span (or as NBSP).
    root = _parse(JSON_FENCE)
    rewrite_codeblocks(root)
    block = _codeblock(root)
    offenders = []
    for el in block.iter():
        for txt in (el.text, el.tail):
            if txt is not None and txt != "" and txt.strip(" ") == "":
                offenders.append((el.tag, repr(txt)))
    assert offenders == [], offenders


def test_unknown_language_falls_back_to_plain_text():
    fence = (
        '<pre><code class="language-zzz-unknown">alpha\nbeta\n</code></pre>'
    )
    root = _parse(fence)
    rewrite_codeblocks(root)
    block = _codeblock(root)
    assert block is not None
    assert block.findall(".//span") == []  # no highlighting
    lines = block.findall("div[@class='code-line']")
    assert [line.text for line in lines] == ["alpha", "beta"]


def test_no_language_class_falls_back_to_plain_text():
    fence = "<pre><code>just text\n</code></pre>"
    root = _parse(fence)
    rewrite_codeblocks(root)
    block = _codeblock(root)
    assert block is not None
    assert block.findall(".//span") == []


def test_idempotent_on_already_rewritten():
    root = _parse(JSON_FENCE)
    rewrite_codeblocks(root)
    # Second pass: no <pre> left, nothing to do.
    assert rewrite_codeblocks(root) == 0


def test_empty_code_is_skipped():
    root = _parse("<pre><code></code></pre>")
    assert rewrite_codeblocks(root) == 0
