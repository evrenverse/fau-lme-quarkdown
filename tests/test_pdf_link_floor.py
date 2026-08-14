"""Regression floor: the full-thesis PDF must contain at least N internal
link annotations. Floor — not equality — so the test passes as more prose
is written.

Skipped automatically if the PDF has not been built (the unit tests must
remain runnable without an expensive end-to-end compile).
"""

from pathlib import Path
import pytest

pypdf = pytest.importorskip("pypdf")

THESIS_ROOT = Path(__file__).resolve().parents[4]
PDF_PATH = THESIS_ROOT / "thesis" / "output" / "main.pdf"

# Today (2026-05-14, pre-patch) the PDF has 139 ToC links. After this
# change, body citations + acronyms add at least 60 more (~21 bib entries,
# ~45 acronyms, with most having multiple body occurrences). 200 is a
# defensive floor; raise it as the thesis grows.
LINK_FLOOR = 200


@pytest.mark.skipif(not PDF_PATH.exists(), reason="PDF not built yet")
def test_pdf_has_at_least_floor_links() -> None:
    reader = pypdf.PdfReader(str(PDF_PATH))
    count = 0
    for page in reader.pages:
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            obj = annot.get_object()
            if obj.get("/Subtype") == "/Link":
                count += 1
    assert count >= LINK_FLOOR, (
        f"internal-link annotations dropped below floor: {count} < {LINK_FLOOR}"
    )


@pytest.mark.skipif(not PDF_PATH.exists(), reason="PDF not built yet")
def test_pdf_has_body_page_links() -> None:
    """At least one body page (page index > 17, after frontmatter)
    must carry a link annotation — proves the postprocessor actually ran
    and that Puppeteer preserved the annotations in the final PDF."""
    reader = pypdf.PdfReader(str(PDF_PATH))
    body_links = 0
    for i, page in enumerate(reader.pages):
        if i + 1 <= 17:
            continue
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            if annot.get_object().get("/Subtype") == "/Link":
                body_links += 1
    assert body_links >= 5, f"body-page links too few: {body_links}"
