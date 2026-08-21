from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pymupdf

from piassist.music_logic import MusicAnalyzer
from piassist.vector_pdf import VectorPDFParser

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "aura_lee_dorico"
INPUT = FIXTURE_DIR / "input.pdf"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())


def test_dorico_pdf_integrity() -> None:
    expected = MANIFEST["files"]["input"]
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest() == expected["sha256"]

    with pymupdf.open(INPUT) as document:
        assert len(document) == expected["pages"]
        assert [len(page.get_images(full=True)) for page in document] == expected[
            "images_by_page"
        ]


def test_dorico_oversized_noteheads_are_parsed() -> None:
    score = VectorPDFParser().parse(INPUT)
    expected = MANIFEST["score_structure"]

    assert [len(page.staffs) for page in score.pages] == expected["staffs_by_page"]
    assert [len(page.notes) for page in score.pages] == expected[
        "detected_notes_by_page"
    ]
    assert sum(len(page.notes) for page in score.pages) == expected["detected_notes"]
    assert [len(page.accidentals) for page in score.pages] == expected[
        "detected_accidentals_by_page"
    ]


def test_dorico_inspection_matches_manifest() -> None:
    inspection = VectorPDFParser().inspect(INPUT)
    expected = MANIFEST["inspection_baseline"]

    assert [page["raw_character_count"] for page in inspection["pages"]] == expected[
        "raw_characters_by_page"
    ]
    assert [page["horizontal_line_count"] for page in inspection["pages"]] == expected[
        "horizontal_lines_by_page"
    ]
    recognized = [
        dict(page["recognized_symbols"]) for page in inspection["pages"]
    ]
    assert recognized == expected["recognized_symbols_by_page"]

    expected_codepoints = MANIFEST["smufl_oversized_noteheads"]["counts_by_page"]
    for page_number, page in enumerate(inspection["pages"]):
        counts = {
            glyph["codepoints"]: glyph["count"]
            for glyph in page["glyphs"]
            if glyph["codepoints"] in expected_codepoints
        }
        assert counts == {
            codepoint: page_counts[page_number]
            for codepoint, page_counts in expected_codepoints.items()
        }


def test_dorico_annotation_baseline() -> None:
    score = MusicAnalyzer().analyze(VectorPDFParser().parse(INPUT))
    marks_by_page = Counter(
        note.note.page for note in score.notes if note.should_mark
    )

    expected = MANIFEST["annotation_baseline"]
    assert [marks_by_page[page] for page in range(len(score.pages))] == expected[
        "predicted_marks_by_page"
    ]
    assert sum(marks_by_page.values()) == expected["predicted_marks"]
