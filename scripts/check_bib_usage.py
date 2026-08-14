#!/usr/bin/env python3
"""Two-way bib-usage diff: orphan citations + unused bib entries.

Print-only (no auto-delete). Exit 0 always; the diff is for human review.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from postprocess_links.bibmap import parse_bibmap  # noqa: E402

CITE_RE = re.compile(r"\.cite\s*\{([^}]+)\}")


def collect_cited_keys(src_dirs: list[Path]) -> set[str]:
    keys: set[str] = set()
    for src in src_dirs:
        for qd in src.rglob("*.qd"):
            keys.update(CITE_RE.findall(qd.read_text(encoding="utf-8")))
    return keys


def diff_bib_usage(bib: Path, src_dirs: list[Path]) -> dict[str, set[str]]:
    bibmap = parse_bibmap(bib)
    # parse_bibmap returns {alpha-label: bibtex-key}; we need bibtex keys.
    defined = set(bibmap.values())
    cited = collect_cited_keys(src_dirs)
    return {
        "unused": defined - cited,
        "orphan": cited - defined,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bib", type=Path, required=True)
    p.add_argument("--src", type=Path, action="append", required=True,
                   help="directory tree to scan for .cite{} (repeatable)")
    args = p.parse_args(argv)

    diff = diff_bib_usage(args.bib, args.src)
    if diff["unused"]:
        print(f"\nUNUSED bib entries ({len(diff['unused'])}):")
        for k in sorted(diff["unused"]):
            print(f"  {k}")
    if diff["orphan"]:
        print(f"\nORPHAN citations ({len(diff['orphan'])}):")
        for k in sorted(diff["orphan"]):
            print(f"  {k}")
    if not diff["unused"] and not diff["orphan"]:
        print("clean -- every bib entry is cited and every cite resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
