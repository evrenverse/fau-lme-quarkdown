"""pytest config for fau-lme theme tests.

Adds the theme's scripts/ directory to sys.path so tests can import the
postprocess_links package without packaging the theme as an installable.
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
