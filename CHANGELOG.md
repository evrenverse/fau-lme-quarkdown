# Changelog

All notable changes to the FAU-LME Quarkdown theme are documented here.
Format adapted from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] — 2026-08-14

First public release.

### What it does

A Quarkdown theme reproducing the FAU Pattern Recognition Lab thesis layout
(`lmedoc.cls`): A4 twoside in Latin Modern Roman with the LME margin geometry,
front-matter page numbering, a parameterised cover with a doctype switch, an
alpha-style CSL bibliography, 15 LaTeX-equivalent KaTeX math macros, EN/DE
localization, and a slides layer for talks. Ships an optional HTML link
postprocessor — citations, acronyms, glossary, cross-references, captions,
listings — covered by 167 tests, plus two runnable examples.

Tested against Quarkdown 2.0.1, 2.3.1 and 2.5.1.

### Asset terms

The two cover logos ship with the theme: they are byte-identical to the ones in
the chair's openly published LaTeX template, and without them the theme is not
the clone-and-build artifact it is meant to be. `LICENSE`, the README and
`assets/LOGO-PROVENANCE.md` carve them out of the MIT grant explicitly and name
their source.

The three slide-layer images came from presentation templates handed over by
the chair, with no public source to point at, and are neutral placeholders at
the same nominal sizes. Anyone holding the official templates can drop the real
art back in.

### Self-contained

`tests/smoke-postprocess.sh` reads `tests/refs-fixture.bib` rather than walking
up the tree for a consuming project's `refs.bib`, so it runs from a fresh clone.
Test fixtures use neutral acronyms, and the English cover label reads `Advisor`,
matching `lmedoc.cls`.

### Known behaviour worth documenting

Where the theme deviates from `lmedoc.cls` on purpose, the README section
"Deliberate deviations from `lmedoc.cls`" lists each case and its reason. The
Quarkdown and PagedJS quirks the theme works around are in "Quarkdown-specific
gotchas".

[0.1.0]: https://github.com/evrenverse/fau-lme-quarkdown/releases/tag/v0.1.0
