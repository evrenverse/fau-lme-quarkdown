#!/usr/bin/env bash
# End-to-end smoke test: minimal Quarkdown doc → HTML → postprocess → PDF.
# Asserts the resulting PDF has at least two internal-link annotations
# (citation + acronym) injected by the postprocessor.
#
# The doc loads the theme loader (for .lmebibliography) and cites the one entry
# in tests/refs-fixture.bib, so the test is self-contained: it needs nothing
# from the project that consumes the theme.

set -euo pipefail

cd "$(dirname "$0")/.."
THEME_DIR="$PWD"
THESIS_BIB="$THEME_DIR/tests/refs-fixture.bib"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Ensure CSL is injected before building.
"$THEME_DIR/scripts/install-csl.sh"

cat > "$WORK/main.qd" << EOF
.doctype {paged}
.include {$THEME_DIR/loader.qd}

#! Acronyms

| Acronym | Definition |
|---|---|
| **DSR** | Design Science Research |

# Introduction

The DSR acronym defined above is referenced once here, and a sample
citation lands here .cite {peffers2007dsr}.

.lmebibliography {refs.bib}
EOF

command -v quarkdown >/dev/null 2>&1 || { echo "ERROR: quarkdown not in PATH." >&2; exit 1; }

quarkdown c "$WORK/main.qd" \
  --out "$WORK/html" \
  --strict --allow project-read --allow global-read --allow native-content --timeout 120

HTML_DIR=$(find "$WORK/html" -name index.html -printf '%h\n' | head -1)
HTML="$HTML_DIR/index.html"

# Build a one-row acronyms stub for the postprocessor.
ACRO="$WORK/acronyms.qd"
cat > "$ACRO" << 'EOF'
| Acronym | Definition |
|---|---|
| **DSR** | Design Science Research |
EOF

python3 "$THEME_DIR/scripts/postprocess_links.py" \
  --html "$HTML" --bib "$THESIS_BIB" --acronyms "$ACRO"

# Verify HTML has both anchor types.
grep -q 'href="#bib-pef07"' "$HTML" || { echo "FAIL: no citation anchor (href=#bib-pef07)"; exit 1; }
grep -q 'href="#acro-dsr"' "$HTML" || { echo "FAIL: no acronym anchor (href=#acro-dsr)"; exit 1; }

mkdir -p "$WORK/pdf"
node "$THEME_DIR/scripts/print-pdf.js" "$HTML_DIR" "$WORK/pdf/main.pdf"

python3 - "$WORK/pdf/main.pdf" << 'PY'
import sys, pypdf
r = pypdf.PdfReader(sys.argv[1])
n_link = 0
for p in r.pages:
    if "/Annots" not in p: continue
    for a in p["/Annots"]:
        if a.get_object().get("/Subtype") == "/Link":
            n_link += 1
assert n_link >= 2, f"expected >= 2 internal links, got {n_link}"
print(f"smoke PDF link count: {n_link} — OK")
PY
