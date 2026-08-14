# Contributing to the FAU-LME Quarkdown Theme

Bug reports, feature ideas, and pull requests are welcome — especially from
LME students who are pushing the theme to cover scenarios it doesn't yet handle.

## Quick checklist before opening a PR

1. **Tests and examples pass.** From the repository root:

   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -q          # postprocessor
   bash scripts/test.sh      # builds example/ and example-slides/ to PDF
   shellcheck scripts/*.sh tests/*.sh
   ```

   CI runs the same three on every push.
2. **No new TODO / FIXME without an issue.** If you can't fix it now, open an
   issue and link it from the comment.
3. **Update `CHANGELOG.md`** under `## [Unreleased]` describing what changed
   and why. If your change is purely internal (refactor, comment), say so.
4. **Don't bump `theme.json` `version`** in your PR — releases are cut by
   the maintainer in a separate commit.
5. **Documentation drift is a PR-blocker.** If you change behaviour, update
   the README sections that describe it (Quick start, parameter tables,
   Quarkdown-specific gotchas).

## Areas that need work

- **More locales.** Today: EN + DE. Adding French, Italian, Spanish requires
  duplicating the `.localization {lme}` block under a new language ID and
  filling in 17 keys.
- **More math macros.** We ship a 15-macro subset of LME `math.sty`. PRs
  adding `\unitvec`, `\half`, custom set notation, etc. should also extend
  `tests/math.qd` (see #math-smoke-test).
- **`diss` cover variant.** LaTeX's `\dissdeckblatt` has a vertically-centered
  title page that we currently render with the same layout as `mt`. A proper
  variant matching the legacy LME dissertation cover would close the gap.
- **CSL polish.** `assets/csl/lme-alpha.csl` is derived from DIN-1505 with the
  `note`-field hijack for alpha labels. Feedback from anyone who has compared
  output side-by-side against `alphamod.bst` is welcome.
- **Newer Quarkdown.** Tested against 2.0.1, 2.3.1 and 2.5.1. PRs that test a
  newer release and adjust the workarounds (see "Quarkdown-specific gotchas"
  in the README) are valuable.

## Development workflow

```bash
# 1. Change the theme
# 2. Smoke-test both examples end to end
bash scripts/test.sh

# 3. If you touched the postprocessor, run its suite too
pytest tests/ -q

# 4. Open a PR with the changelog entry
```

If you use the theme inside a real document, rebuild that document as well
before opening the PR — the examples cover the layout, not every combination
a full thesis produces.

## Style

- 4-space indent for `.qd`, 2-space for CSS/JSON/Markdown (see `.editorconfig`).
- Comment the *why*, not the *what*. CSS rules in particular benefit from a
  one-line `/* matches LaTeX X */` comment when they exist for parity.
- Prefer Quarkdown-native abstractions (`.text size:{X}`, `.pagemargin`) over
  raw CSS where they exist. Drop to CSS only when the named API doesn't cover
  the case (e.g. exact pt sizing for the cover title).

## License

By contributing you agree your changes are licensed under MIT (see `LICENSE`).
