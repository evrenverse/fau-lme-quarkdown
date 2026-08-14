# Agent setup

This repository is a Quarkdown theme — `.qd` sources, CSS and images — plus an
optional HTML postprocessor. It is not a Python package and has nothing to
install globally. Do not add a build system, a package manifest, or a
dependency on any sibling repository.

## Use it in a document

1. Read `README.md`, in particular § Quick start and § Quarkdown-specific
   gotchas. The gotchas are not style advice; ignoring them produces silently
   broken output.
2. Add the theme at `themes/fau-lme/` next to the consuming `main.qd`, as a git
   submodule or a plain copy.
3. Run `scripts/install-csl.sh` once so `.lmebibliography` resolves its style.
4. Build with `quarkdown c main.qd --pdf`.

Institution branding lives in `assets/`. Two files are FAU / LME property and
carved out of the MIT license — see `assets/LOGO-PROVENANCE.md` before copying
this theme anywhere outside an FAU context.

## Contributing

```bash
pip install -r requirements-dev.txt
pytest tests/ -q          # 167 tests
scripts/test.sh           # builds both examples end to end
shellcheck scripts/*.sh tests/*.sh
```

The layout follows the chair's LaTeX class `lmedoc.cls`. When a rendering
question comes up, that class is the ground truth, not preference — and a
deliberate deviation belongs in `CHANGELOG.md` with its reason.

Never put real personal data into fixtures or examples: no names, birth dates,
supervisors, or thesis titles. `example/` uses `Sample Author` and
`Example City`; keep it that way. Test fixtures use neutral acronyms
(`HTTP`, `DOI`, `TCP/IP`) rather than terms from any particular document.

Every change that alters rendered output needs a `CHANGELOG.md` entry under
Unreleased.
