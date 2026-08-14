#!/usr/bin/env bash
# Smoke test for the FAU-LME Quarkdown theme.
#
# Builds themes/fau-lme/example/main.qd and verifies a non-empty PDF was
# produced. Run from anywhere — paths resolve relative to this script.
#
# Use as a pre-commit / CI check after touching any theme file.

set -euo pipefail

THEME_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE_DIR="$THEME_DIR/example"
OUT_DIR="$EXAMPLE_DIR/output"
OUT_PDF="$OUT_DIR/example.pdf"

if ! command -v quarkdown >/dev/null 2>&1; then
  echo "ERROR: quarkdown not in PATH." >&2
  exit 1
fi

# Idempotent: install the custom CSL if not already present — the theme owns
# it, so the smoke test does the same thing a consuming project's build does.
if [ -x "$THEME_DIR/scripts/install-csl.sh" ]; then
  "$THEME_DIR/scripts/install-csl.sh"
fi

mkdir -p "$OUT_DIR"

quarkdown c "$EXAMPLE_DIR/main.qd" \
  --out "$OUT_DIR" \
  --out-name example \
  --pdf \
  --strict \
  --allow project-read \
  --allow global-read \
  --allow native-content \
  --timeout 120

if [ ! -s "$OUT_PDF" ]; then
  echo "FAIL: $OUT_PDF was not produced or is empty." >&2
  exit 1
fi

SIZE=$(stat -c%s "$OUT_PDF")
if [ "$SIZE" -lt 50000 ]; then
  echo "FAIL: $OUT_PDF is implausibly small ($SIZE bytes)." >&2
  exit 1
fi

echo "PASS: example built ($SIZE bytes) at $OUT_PDF"

# ── Slides example ────────────────────────────────────────────────────────────
SLIDES_DIR="$THEME_DIR/example-slides"
SLIDES_OUT="$SLIDES_DIR/output"
SLIDES_PDF="$SLIDES_OUT/example-slides.pdf"

mkdir -p "$SLIDES_OUT"

quarkdown c "$SLIDES_DIR/main.qd" \
  --out "$SLIDES_OUT" \
  --out-name example-slides \
  --pdf \
  --strict \
  --allow project-read \
  --allow global-read \
  --allow native-content \
  --timeout 120

if [ ! -s "$SLIDES_PDF" ]; then
  echo "FAIL: $SLIDES_PDF was not produced or is empty." >&2
  exit 1
fi

SLIDES_SIZE=$(stat -c%s "$SLIDES_PDF")
if [ "$SLIDES_SIZE" -lt 20000 ]; then
  echo "FAIL: $SLIDES_PDF is implausibly small ($SLIDES_SIZE bytes)." >&2
  exit 1
fi

echo "PASS: slides example built ($SLIDES_SIZE bytes) at $SLIDES_PDF"
