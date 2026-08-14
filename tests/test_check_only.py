"""Tests for the --check-only diagnostic mode."""

from pathlib import Path
import subprocess
import sys
import textwrap


SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "postprocess_links.py"
)


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return p


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_check_only_passes_on_clean_input(tmp_path: Path) -> None:
    html = write(tmp_path, "index.html", """
        <html><body>
          <p>see [Pet07] here</p>
          <div class="bibliography">
            <span class="bibliography-entry-label">[Pet07]</span>
          </div>
          <table><tbody>
            <tr><td><strong>HTTP</strong></td><td>def</td></tr>
          </tbody></table>
          <p>HTTP works.</p>
        </body></html>
    """)
    bib = write(tmp_path, "refs.bib", """
        @article{peffers2007dsr, note={Pet07}, year=2007}
    """)
    acro = write(tmp_path, "acronyms.qd", """
        | Acronym | Definition |
        |---|---|
        | **HTTP** | Hypertext Transfer Protocol |
    """)

    result = run("--html", str(html), "--bib", str(bib), "--acronyms", str(acro), "--check-only")
    assert result.returncode == 0, result.stderr


def test_dead_acronym_check_recognises_plural(tmp_path: Path) -> None:
    # An acronym used only in its plural form ("UIs") must not be flagged as
    # dead. The lint mirrors add_body_links' \bKEYs?\b plural handling so the
    # warning matches what the rendered table keeps. Regression guard for the
    # UI false positive (plural-only usage was reported as dead).
    html = write(tmp_path, "index.html", """
        <html><body>
          <table><tbody>
            <tr><td><strong>UI</strong></td><td>User Interface</td></tr>
          </tbody></table>
          <p>The system discovers submission UIs at runtime.</p>
        </body></html>
    """)
    bib = write(tmp_path, "refs.bib", "@article{a, note={Abc20}, year=2020}")
    acro = write(tmp_path, "acronyms.qd", """
        | Acronym | Definition |
        |---|---|
        | **UI** | User Interface |
    """)

    result = run("--html", str(html), "--bib", str(bib), "--acronyms", str(acro), "--check-only")
    assert result.returncode == 0, result.stderr
    assert "dead acronyms" not in result.stderr, result.stderr


def test_check_only_fails_on_orphan_citation(tmp_path: Path) -> None:
    html = write(tmp_path, "index.html", """
        <html><body>
          <p>see [Bogus99] here</p>
        </body></html>
    """)
    bib = write(tmp_path, "refs.bib", "@article{a, note={Abc20}, year=2020}")
    acro = write(tmp_path, "acronyms.qd", "| Acronym | Definition |\n|---|---|\n")

    result = run("--html", str(html), "--bib", str(bib), "--acronyms", str(acro), "--check-only")
    assert result.returncode != 0
    assert "Bogus99" in result.stderr or "Bogus99" in result.stdout


def test_check_only_does_not_modify_html(tmp_path: Path) -> None:
    html_text = """<html><body><p>see [Pet07] here</p></body></html>"""
    html = tmp_path / "index.html"
    html.write_text(html_text)
    bib = write(tmp_path, "refs.bib", "@article{a, note={Pet07}, year=2007}")
    acro = write(tmp_path, "acronyms.qd", "| Acronym | Definition |\n|---|---|\n")

    run("--html", str(html), "--bib", str(bib), "--acronyms", str(acro), "--check-only")
    assert html.read_text() == html_text  # untouched


def test_default_mode_rewrites_html(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text("<html><body><p>see [Pet07] here</p></body></html>")
    bib = write(tmp_path, "refs.bib", "@article{a, note={Pet07}, year=2007}")
    acro = write(tmp_path, "acronyms.qd", "| Acronym | Definition |\n|---|---|\n")

    result = run("--html", str(html), "--bib", str(bib), "--acronyms", str(acro))
    assert result.returncode == 0, result.stderr
    assert 'href="#bib-pet07"' in html.read_text()
