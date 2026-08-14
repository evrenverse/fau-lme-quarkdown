"""Tests for the two-way bib-usage checker."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from check_bib_usage import diff_bib_usage  # noqa: E402  (script at scripts/)


@pytest.fixture
def bib_file(tmp_path: Path) -> Path:
    bib = tmp_path / "refs.bib"
    bib.write_text(textwrap.dedent("""
        @article{used2024,
          author = {Foo, Bar},
          title  = {Title},
          year   = {2024},
          note   = {Foo24},
        }
        @online{unused2025,
          author  = {Baz},
          title   = {Other},
          year    = {2025},
          url     = {https://example.com},
          urldate = {2026-01-01},
          note    = {Baz25},
        }
    """).lstrip())
    return bib


@pytest.fixture
def src_dir(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "ch01.qd").write_text("Reference: .cite {used2024}.\n")
    (src / "ch02.qd").write_text("Another: .cite{used2024} and .cite {orphan2030}.\n")
    return src


def test_diff_reports_unused(bib_file: Path, src_dir: Path) -> None:
    diff = diff_bib_usage(bib_file, [src_dir])
    assert "unused2025" in diff["unused"]
    assert "used2024" not in diff["unused"]


def test_diff_reports_orphan(bib_file: Path, src_dir: Path) -> None:
    diff = diff_bib_usage(bib_file, [src_dir])
    assert "orphan2030" in diff["orphan"]


def test_diff_accepts_no_space_cite(bib_file: Path, src_dir: Path) -> None:
    diff = diff_bib_usage(bib_file, [src_dir])
    # used2024 is cited once with space, once without; must count as used
    assert "used2024" not in diff["unused"]
