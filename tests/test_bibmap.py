"""Tests for parsing refs.bib's `note` field (which carries the alpha label)
into a mapping usable by the citation rewriter."""

from pathlib import Path
import textwrap

from postprocess_links.bibmap import parse_bibmap, slugify_label


def write_bib(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "refs.bib"
    p.write_text(textwrap.dedent(content).strip() + "\n")
    return p


def test_parse_single_entry(tmp_path: Path) -> None:
    bib = write_bib(tmp_path, """
        @article{peffers2007dsr,
          author = {Peffers, K.},
          title  = {DSR},
          year   = 2007,
          note   = {Pet07},
        }
    """)
    assert parse_bibmap(bib) == {"Pet07": "peffers2007dsr"}


def test_parse_multiple_entries(tmp_path: Path) -> None:
    bib = write_bib(tmp_path, """
        @article{a, year=2020, note={Abc20}}
        @inproceedings{b, year=2021, note={Def21}}
    """)
    assert parse_bibmap(bib) == {"Abc20": "a", "Def21": "b"}


def test_entry_without_note_skipped(tmp_path: Path) -> None:
    bib = write_bib(tmp_path, """
        @article{a, year=2020, note={Abc20}}
        @article{b, year=2021}
    """)
    # Entry b has no note → no alpha label → not in the map.
    assert parse_bibmap(bib) == {"Abc20": "a"}


def test_note_with_whitespace(tmp_path: Path) -> None:
    bib = write_bib(tmp_path, """
        @article{a, year=2020, note = { Abc20 }}
    """)
    assert parse_bibmap(bib) == {"Abc20": "a"}


def test_slugify_label() -> None:
    assert slugify_label("Pet07") == "bib-pet07"
    assert slugify_label("vom20") == "bib-vom20"
    assert slugify_label("EGV24") == "bib-egv24"
