"""Caption-period validator.

Repo convention: every <figcaption> and table <caption> ends with a period.
Run in `--check-only` mode by `postprocess_links.py`; emits a failure for
any caption whose visible text does not end with `.`.

Excludes CSS comments inside <style> blocks (the regex-based audit was
mis-interpreting CSS selector text containing the word "caption").
"""

from __future__ import annotations

from lxml import etree


CAPTION_SKIP_ANCESTORS = frozenset({"head", "style", "script"})


def find_caption_period_violations(root: etree._Element) -> list[tuple[str, str]]:
    """Return list of (tag, full_text) for captions not ending in '.'.

    Scans every <figcaption> and <caption> in the rendered HTML body,
    skips those nested inside <head>/<style>/<script> (defensive against
    parser quirks). Excludes empty / whitespace-only captions because they
    indicate a stub the writer has not filled yet — that is its own kind
    of issue, separately handled by the build pipeline.
    """
    violations: list[tuple[str, str]] = []
    for tag in ("figcaption", "caption"):
        for el in root.iter(tag):
            if any(a.tag in CAPTION_SKIP_ANCESTORS for a in el.iterancestors()):
                continue
            text = " ".join(el.itertext()).strip()
            if not text:
                continue
            if text[-1] != ".":
                violations.append((tag, text))
    return violations
