# Image assets: provenance and terms

The files here fall into two groups. The distinction matters if you fork this
theme, and especially if you publish that fork.

## FAU / LME marks — not covered by the MIT license

| File | Nominal size | Used by |
| --- | --- | --- |
| `logo-fau-techfak.png` | 2512 × 1196 | `cover.qd` — upper cover logo |
| `logo-lme.png` | 2048 × 718 | `cover.qd` — lower cover logo |

Both are the property of Friedrich-Alexander-Universität Erlangen-Nürnberg and
its Lehrstuhl für Mustererkennung. **They are excluded from this repository's
MIT license** — see the "Brand assets" section in the README.

They ship with the theme because they ship with the LaTeX template this theme
reproduces. The chair publishes that template openly, without login or stated
terms, at

```
https://lme.tf.fau.de/wp-content/uploads/2024/06/thesis-templates-master.zip
```

as `lmedoc/FAU_TechFak_EN_H_RGB_darkblue-1.png` and `lmedoc/logo_large.png`.
The copies here are byte-identical to those files:

| File | SHA-256 |
| --- | --- |
| `logo-fau-techfak.png` | `f7ab595fe4b30b328fec049ca76f4a3b…` |
| `logo-lme.png` | `b0ff19bc2ffe603dc3085245388f25f6…` |

Including them keeps the theme usable the way the LaTeX template is usable: a
member of the chair clones it and builds a correct cover, without hunting down
two images first.

**Outside an FAU context, replace them.** Their intended use is work written
under the chair's supervision. A fork carrying different branding should swap
both files (keeping the nominal sizes) and update this document.

## Placeholders — MIT, like the rest of the repository

| File | Nominal size | Used by |
| --- | --- | --- |
| `logo-prl.png` | 557 × 195 | `titlecard.qd`, `slides.qd` — slide footer |
| `logo-fau-wortmarke.svg` | 601 × 282.57 pt | `titlecard.qd`, `slides.qd` — slide footer |
| `slides-title-bg.jpg` | 2000 × 1125 | `titlecard.qd` — slide title background |

The slide layer originally carried art from the chair's PowerPoint and beamer
templates. Those were handed over directly rather than published, so unlike the
cover logos there is no public source to point at — they are replaced here with
neutral placeholders. Members of the chair who have the official presentation
templates can drop the real art in; everyone else gets a deck that builds and
looks deliberate rather than broken.

## Swapping in your own branding

Replace a file in place and keep its nominal size — the layouts scale by width
(`!(5.5cm)[…]`), so the aspect ratio is what keeps the cover and slide footer in
proportion. Filenames stay as they are unless you also adjust the `.row` blocks
in `cover.qd`, `titlecard.qd` and `slides.qd`.
