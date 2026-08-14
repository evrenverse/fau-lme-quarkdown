# lme-alpha.csl

Custom Citation Style Language (CSL) file producing alpha-style labels
(`[Pet07]`, `[KS11]`) that approximate BibTeX's `alphamod.bst` — the
bibliography style required by the FAU LME thesis guideline (drichtl §1.8,
English variant).

## License

The CSL file itself carries **CC-BY-SA 3.0** (see the `<rights>` element
inside `lme-alpha.csl`). This is the standard CSL community licence and is
inherited from the upstream styles this file derives from (notably the
DIN-1505 family on the official CSL repository).

The rest of the FAU-LME Quarkdown theme is **MIT** (see the parent
`LICENSE` file). The two licences are compatible for combined distribution
provided the `<rights>` element in the CSL file is preserved.

## How it gets loaded

Quarkdown 2.0.1's `.bibliography style:{...}` accepts only CSL identifiers
that ship inside `quarkdown-core.jar` — there is no user-side plugin path.
The theme works around this by injecting `lme-alpha.csl` into the JAR via
`scripts/install-csl.sh`, run once per Quarkdown install (idempotent).

## Why a custom style at all?

Standard CSL styles like `din-1505-2-alphanumeric` produce alpha keys but
generate them automatically from author + year. LME's `alphamod` produces
hand-tuned 3-letter keys (`Pet07` for "Peffers et al. 2007", `KS11` for
"Kuechler & Schubert 2011") that are stable across edits. Citeproc-java
doesn't expose BibTeX's `citation-key` to CSL's `citation-label` variable,
so this file reads the alpha label from the BibTeX `note` field instead.

**Practical consequence for users:** in your `refs.bib`, put your
hand-picked alpha label in `note = {...}` (e.g. `note = {Pef07}`). Use
`annote = {...}` for free-form annotations (which would otherwise hijack
your alpha label).
