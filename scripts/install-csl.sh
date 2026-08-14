#!/usr/bin/env bash
# Install the LME-alpha CSL bibliography style into the Quarkdown installation.
#
# Quarkdown 2.0.1 has no documented user-CSL plugin path; the `.bibliography style:{name}`
# parameter resolves names via classpath lookup against quarkdown-core.jar. This script
# injects themes/fau-lme/assets/csl/lme-alpha.csl into the JAR so it's discoverable
# as `style:{lme-alpha}`.
#
# Re-run after every Quarkdown upgrade. Idempotent (re-running on an already-patched
# JAR is a no-op via `zip --update`).
#
# Prerequisites: `zip` (sudo apt-get install -y zip on Debian/Ubuntu).
#
# Configuration via env:
#   QUARKDOWN_ROOT — override the Quarkdown install dir. Default: $HOME/.local/opt/quarkdown
#
# Exit codes:
#   0 — success (or no-op if already patched)
#   1 — Quarkdown install dir not found
#   2 — quarkdown-core.jar not found or not writable
#   3 — zip command not available

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THEME_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CSL_FILE="$THEME_DIR/assets/csl/lme-alpha.csl"

QUARKDOWN_ROOT="${QUARKDOWN_ROOT:-$HOME/.local/opt/quarkdown}"

if ! command -v zip >/dev/null 2>&1; then
    echo "ERROR: 'zip' is required to inject the CSL into quarkdown-core.jar." >&2
    echo "Install: sudo apt-get install -y zip" >&2
    exit 3
fi

if [ ! -d "$QUARKDOWN_ROOT" ]; then
    echo "ERROR: Quarkdown install directory not found at: $QUARKDOWN_ROOT" >&2
    echo "Set QUARKDOWN_ROOT or install Quarkdown first (see scripts/install-quarkdown.sh)." >&2
    exit 1
fi

# Glob rather than `ls`: an unquoted `ls` output would split on spaces in the
# install path, and the loop needs no subshell to pick the first hit.
CORE_JAR=""
for jar in "$QUARKDOWN_ROOT"/lib/quarkdown-core*.jar; do
    if [ -e "$jar" ]; then CORE_JAR="$jar"; break; fi
done
if [ -z "$CORE_JAR" ]; then
    echo "ERROR: quarkdown-core*.jar not found under $QUARKDOWN_ROOT/lib/" >&2
    exit 2
fi

if [ ! -w "$CORE_JAR" ]; then
    echo "ERROR: $CORE_JAR is not writable by the current user." >&2
    echo "Either run with appropriate permissions or re-install Quarkdown to a user-writable location." >&2
    exit 2
fi

if [ ! -f "$CSL_FILE" ]; then
    echo "ERROR: CSL file not found at $CSL_FILE" >&2
    exit 1
fi

# Inject (or update). The -j flag strips the directory prefix so the file ends up at
# the JAR root, matching where citeproc-java's classpath loader looks for "*.csl".
zip -jq "$CORE_JAR" "$CSL_FILE"
echo "Injected $(basename "$CSL_FILE") into $(basename "$CORE_JAR")."
