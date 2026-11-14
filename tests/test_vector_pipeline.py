import json
from pathlib import Path

import pymupdf
import pytest

from piassist.models import (
    Accidental,
    AccidentalSource,
    BBox,
    Clef,
    Glyph,
    Staff,
    SymbolKind,
)
from piassist.music_logic import MusicAnalyzer
from piassist.render import OutputExistsError, PDFRenderer
from piassist.vector_pdf import (
    NOTEHEAD_CODEPOINTS,
    UnsupportedVectorPdfError,
    VectorPDFParser,
)


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
                id="keysig-flat",
                page=page_number,
                kind=SymbolKind.FLAT,
                char="\ue260",
                bbox=BBox(34, 36, 39, 44),
            ),
            Glyph(
                id="note",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(97, 37, 103, 43),
            ),
        ]


class TiedSyntheticVectorParser(VectorPDFParser):
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
                id="tie-source",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(87, 37, 93, 43),
            ),
            Glyph(
                id="tie-target",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(107, 37, 113, 43),
            ),
        ]


class LongStemSyntheticVectorParser(VectorPDFParser):
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
                id="first-note",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(67, 47, 73, 53),
            ),
            Glyph(
                id="sharp",
                page=page_number,
                kind=SymbolKind.SHARP,
                char="\ue262",
                bbox=BBox(110, 47, 115, 53),
            ),
            Glyph(
                id="stem-note",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(117, 47, 123, 53),
            ),
            Glyph(
                id="same-measure-note",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(137, 47, 143, 53),
            ),
            Glyph(
                id="next-measure-note",
                page=page_number,
                kind=SymbolKind.NOTEHEAD,
                char="\ue0a4",
                bbox=BBox(167, 47, 173, 53),
            ),
        ]


def make_vector_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    for y in (20, 30, 40, 50, 60):
        page.draw_line((10, y), (190, y), width=0.4)
    document.save(path)
    document.close()


def make_tied_vector_pdf(path: Path, *, fill_and_stroke: bool = False) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    for y in (20, 30, 40, 50, 60):
        page.draw_line((10, y), (190, y), width=0.4)
    page.draw_line((100, 20), (100, 60), width=0.4)

    tie = page.new_shape()
    start = pymupdf.Point(93, 45)
    end = pymupdf.Point(107, 45)
    tie.draw_bezier(start, pymupdf.Point(97, 49), pymupdf.Point(103, 49), end)
    tie.draw_bezier(end, pymupdf.Point(103, 47), pymupdf.Point(97, 47), start)
    tie.finish(
        fill=(0, 0, 0),
        color=(0, 0, 0) if fill_and_stroke else None,
        width=0.1,
        closePath=True,
    )
    tie.commit()

    document.save(path)
    document.close()


def make_long_stem_vector_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    for y in (20, 30, 40, 50, 60):
        page.draw_line((10, y), (190, y), width=0.4)

    # Both of these lines satisfy the old coarse barline heuristic. The first
    # is a long stem placed just outside ``stem-note``'s reported glyph box;
    # the second is an unrelated vertical mark that does not cover enough of
    # the staff to be a barline.
    page.draw_line((123.5, 10), (123.5, 55), width=0.4)
    page.draw_line((150, 25), (150, 55), width=0.4)
    # The two nearby full-height lines form one double-bar boundary.
    page.draw_line((160, 20), (160, 60), width=0.4)
    page.draw_line((166, 20), (166, 60), width=0.4)

    document.save(path)
    document.close()


def test_vector_pdf_pipeline_and_render(tmp_path: Path) -> None:
    source = tmp_path / "score.pdf"
    output = tmp_path / "annotated.pdf"
    make_vector_pdf(source)

    score = SyntheticVectorParser().parse(source)
    score = MusicAnalyzer().analyze(score)

    assert len(score.pages[0].staffs) == 1
    assert score.pages[0].key_signatures[0]["B"].value == "flat"
    assert score.notes[0].should_mark
    assert PDFRenderer().render(source, output, score) == 1
    assert output.is_file()

    with pymupdf.open(source) as original, pymupdf.open(output) as annotated:
        assert len(annotated[0].get_drawings()) > len(original[0].get_drawings())

    with pytest.raises(OutputExistsError):
        PDFRenderer().render(source, output, score)


def test_blank_pdf_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "blank.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(source)
    document.close()

    with pytest.raises(UnsupportedVectorPdfError):
        VectorPDFParser().parse(source)


def test_inspection_reports_staff_geometry(tmp_path: Path) -> None:
    source = tmp_path / "score.pdf"
    make_vector_pdf(source)

    result = VectorPDFParser().inspect(source)

    assert result["pages"][0]["detected_staff_count"] == 1
    assert json.loads(json.dumps(result))["pages"][0]["horizontal_line_count"] == 5


def test_vector_pdf_detects_tie_between_matching_noteheads(tmp_path: Path) -> None:
    source = tmp_path / "tied-score.pdf"
    make_tied_vector_pdf(source)

    score = TiedSyntheticVectorParser().parse(source)

    assert [(note.id, note.measure) for note in score.pages[0].notes] == [
        ("tie-source", 0),
        ("tie-target", 1),
    ]
    assert [
        (tie.source_note_id, tie.target_note_id) for tie in score.pages[0].ties
    ] == [("tie-source", "tie-target")]


def test_vector_pdf_detects_sibelius_fill_and_stroke_tie(tmp_path: Path) -> None:
    source = tmp_path / "sibelius-tied-score.pdf"
    make_tied_vector_pdf(source, fill_and_stroke=True)

    with pymupdf.open(source) as document:
        assert any(drawing["type"] == "fs" for drawing in document[0].get_drawings())

    score = TiedSyntheticVectorParser().parse(source)

    assert [
        (tie.source_note_id, tie.target_note_id) for tie in score.pages[0].ties
    ] == [("tie-source", "tie-target")]


def test_barline_detection_rejects_long_stem_and_unrelated_vertical_line(
    tmp_path: Path,
) -> None:
    source = tmp_path / "long-stem-score.pdf"
    make_long_stem_vector_pdf(source)

    score = LongStemSyntheticVectorParser().parse(source)
    staff = score.pages[0].staffs[0]

    assert staff.barlines == pytest.approx([163])
    assert [(note.id, note.measure) for note in score.pages[0].notes] == [
        ("first-note", 0),
        ("stem-note", 0),
        ("same-measure-note", 0),
        ("next-measure-note", 1),
    ]

    analyzed = MusicAnalyzer().analyze(score)
    assert [note.effective_accidental for note in analyzed.notes] == [
        None,
        Accidental.SHARP,
        Accidental.SHARP,
        None,
    ]
    assert [note.source for note in analyzed.notes] == [
        None,
        AccidentalSource.EXPLICIT,
        AccidentalSource.CARRIED,
        None,
    ]


def test_text_font_accidental_is_not_treated_as_notation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = VectorPDFParser()
    monkeypatch.setattr(
        parser,
        "_raw_chars",
        lambda page: iter(
            [
                ("♭", BBox(0, 0, 1, 1), "Edwin-Roman"),
                ("♭", BBox(1, 0, 2, 1), "Leland"),
                ("\ue260", BBox(2, 0, 3, 1), "UnknownSMuFLFont"),
            ]
        ),
    )

    glyphs = parser._extract_glyphs(None, 0)  # type: ignore[arg-type]  # noqa: SLF001

    assert [glyph.char for glyph in glyphs] == ["♭", "\ue260"]


@pytest.mark.parametrize("codepoint", range(0xF4BC, 0xF4BF))
def test_smufl_oversized_notehead_is_recognized(codepoint: int) -> None:
    assert chr(codepoint) in NOTEHEAD_CODEPOINTS


def test_notehead_on_extended_ledger_line_is_assigned_to_staff() -> None:
    staff = Staff(
        page=0,
        index=0,
        line_ys=(20, 30, 40, 50, 60),
        x0=10,
        x1=190,
        clef=Clef.TREBLE,
    )
    notehead = Glyph(
        id="high-note",
        page=0,
        kind=SymbolKind.NOTEHEAD,
        char="\ue0a4",
        bbox=BBox(97, -38, 103, -32),
    )

    assert VectorPDFParser._nearest_staff([staff], notehead) is staff  # noqa: SLF001
