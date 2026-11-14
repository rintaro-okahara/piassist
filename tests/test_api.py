from pathlib import Path

import pymupdf

from piassist import api
from piassist.models import BBox, Glyph, SymbolKind
from piassist.vector_pdf import VectorPDFParser


class SyntheticVectorParser(VectorPDFParser):
    def _extract_glyphs(self, page: pymupdf.Page, page_number: int) -> list[Glyph]:
        del page
        return [
            Glyph(
                id="clef",
                page=page_number,
                kind=SymbolKind.TREBLE_CLEF,
                char="\ue050",
                bbox=BBox(12, 16, 24, 64),
            ),
            Glyph(
                id="note",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(97, 37, 103, 43),
            ),
        ]


def make_vector_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    for y in (20, 30, 40, 50, 60):
        page.draw_line((10, y), (190, y), width=0.4)
    document.save(path)
    document.close()


def test_browser_facing_api_annotates_synthetic_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "score.pdf"
    output = tmp_path / "score-annotated.pdf"
    make_vector_pdf(source)
    monkeypatch.setattr(api, "VectorPDFParser", SyntheticVectorParser)

    result = api.annotate_pdf_file(
        source,
        output,
        key_signature="Bb",
    )

    assert output.is_file()
    assert result == {
        "pages": 1,
        "staffs": 1,
        "notes": 1,
        "marked_notes": 1,
        "output_name": "score-annotated.pdf",
    }
