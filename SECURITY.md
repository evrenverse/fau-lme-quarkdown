# Security policy

## Supported versions

Fixes are provided for the latest released version.

## Report a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue containing exploit details or an unpublished thesis. Include the
affected version, impact, reproduction steps, and any suggested mitigation.

## Trust model

The theme itself is declarative — `.qd` sources, CSS and images. It executes
nothing. The risk surface is the optional tooling under `scripts/`:

- **`postprocess_links.py`** rewrites a rendered HTML file in place using
  `lxml`. It parses attacker-influenced input if you postprocess a document
  built from sources you do not control, and it overwrites the file it is
  given. Run it on your own build output.
- **`install-csl.sh`** modifies your Quarkdown installation: it injects
  `lme-alpha.csl` into `quarkdown-core.jar`. It writes inside `QUARKDOWN_ROOT`
  and refuses to run if the jar is not writable by the current user.
- **`print-pdf.js`** launches headless Chromium via Puppeteer and serves the
  build directory over a local HTTP server on the loopback interface for the
  duration of the run. Chromium renders whatever the document embeds.
- **`fix-outline-titles.py`** rewrites PDF outline entries via PyMuPDF.

None of these send data anywhere. The theme has no telemetry and makes no
network requests at build time; `print-pdf.js` binds a local port only.

Dependencies are declared in `requirements.txt` and `requirements-dev.txt` and
kept current by Dependabot. Keep them updated — `lxml`, `PyMuPDF` and Puppeteer
all parse untrusted formats.

## Assets

`assets/logo-fau-techfak.png` and `assets/logo-lme.png` are FAU / LME property
and excluded from the MIT license. Republishing them under different branding
is a licensing question, not a security one — see `assets/LOGO-PROVENANCE.md`.
