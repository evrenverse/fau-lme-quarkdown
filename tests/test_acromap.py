"""Tests for parsing acronyms.qd's Markdown table into KEY → slug map."""

from pathlib import Path
import textwrap

from postprocess_links.acromap import (
    parse_acromap,
    parse_acromap_long_forms,
    slugify_acronym,
)


def write_acro(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "acronyms.qd"
    p.write_text(textwrap.dedent(content).strip() + "\n")
    return p


def test_parse_simple_table(tmp_path: Path) -> None:
    src = write_acro(tmp_path, """
        #! Acronyms

        | Acronym | Definition |
        |---|---|
        | **HTTP** | Hypertext Transfer Protocol |
        | **DOI** | Digital Object Identifier |
    """)
    assert parse_acromap(src) == {"HTTP": "acro-http", "DOI": "acro-doi"}


def test_skips_table_header_and_separator(tmp_path: Path) -> None:
    src = write_acro(tmp_path, """
        | Acronym | Definition |
        |---|---|
        | **LLM** | Large Language Model |
    """)
    m = parse_acromap(src)
    # The literal word "Acronym" must not become a key.
    assert "Acronym" not in m
    assert m == {"LLM": "acro-llm"}


def test_ignores_rows_without_bold_first_cell(tmp_path: Path) -> None:
    src = write_acro(tmp_path, """
        | Acronym | Definition |
        |---|---|
        | **LLM** | Large Language Model |
        | RAG | Retrieval-Augmented Generation |
    """)
    # Only **LLM** is bold; RAG without bold is rejected (defensive).
    assert parse_acromap(src) == {"LLM": "acro-llm"}


def test_slugify_lowercase_strip_special(tmp_path: Path) -> None:
    assert slugify_acronym("HTTP") == "acro-http"
    assert slugify_acronym("G-Eval") == "acro-g-eval"
    # Internal dots/underscores collapse to hyphens so the slug is URL-clean.
    assert slugify_acronym("D.S.R") == "acro-d-s-r"


def test_parses_unicode_letters_in_key(tmp_path: Path) -> None:
    # German acronyms with umlauts (e.g. TÜV = Technischer Überwachungs-
    # Einkauf) must be parsed; an ASCII-only pattern silently drops them.
    src = write_acro(tmp_path, """
        | Acronym | Definition |
        |---|---|
        | **TÜV** | Technischer Überwachungsverein |
    """)
    assert parse_acromap(src) == {"TÜV": "acro-t-v"}


def test_parse_acromap_long_forms_returns_definitions(tmp_path: Path) -> None:
    """parse_acromap_long_forms returns {KEY: Definition} from second column."""
    fixture = tmp_path / "ac.qd"
    fixture.write_text(
        "| Acronym | Definition |\n"
        "|---|---|\n"
        "| **LLM** | Large Language Model |\n"
        "| **TCP/IP** | Transmission Control Protocol / Internet Protocol |\n"
        "| **KFZ-HU** | Kraftfahrzeug-Hauptuntersuchung nach Norm |\n",
        encoding="utf-8",
    )
    out = parse_acromap_long_forms(fixture)
    assert out["LLM"] == "Large Language Model"
    assert out["TCP/IP"] == "Transmission Control Protocol / Internet Protocol"
    assert out["KFZ-HU"] == "Kraftfahrzeug-Hauptuntersuchung nach Norm"


def test_parse_acromap_long_forms_strips_whitespace(tmp_path: Path) -> None:
    fixture = tmp_path / "ac.qd"
    fixture.write_text(
        "| **CLI** |   Command-Line Interface   |\n",
        encoding="utf-8",
    )
    out = parse_acromap_long_forms(fixture)
    assert out["CLI"] == "Command-Line Interface"


def test_parse_acromap_long_forms_ignores_non_bold_rows(tmp_path: Path) -> None:
    """Defensive: a row whose first cell is not <strong>KEY</strong> is skipped."""
    fixture = tmp_path / "ac.qd"
    fixture.write_text(
        "| Acronym | Definition |\n"
        "|---|---|\n"
        "| **LLM** | Large Language Model |\n"
        "| not-bold | should be skipped |\n",
        encoding="utf-8",
    )
    out = parse_acromap_long_forms(fixture)
    assert "LLM" in out
    assert "not-bold" not in out
