from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import pymupdf

from piassist.models import Accidental
from piassist.music_logic import MusicAnalyzer
from piassist.render import PDFRenderer
from piassist.vector_pdf import VectorPDFParser

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "purcell_what_power_dorico"
INPUT = FIXTURE_DIR / "input.pdf"
ORACLE = FIXTURE_DIR / "oracle.musicxml"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())

ALTER_FOR_ACCIDENTAL = {
    None: 0,
    Accidental.NATURAL: 0,
    Accidental.FLAT: -1,
    Accidental.SHARP: 1,
}


def _musicxml_notes() -> tuple[list[tuple[str, int, int]], list[int], str, str]:
    root = ElementTree.parse(ORACLE).getroot()
    part_id = MANIFEST["verification"]["oracle_part_id"]
    part = root.find(f"./part[@id='{part_id}']")
    assert part is not None

    notes: list[tuple[str, int, int]] = []
    notes_by_measure: list[int] = []
    for measure in part.findall("measure"):
        measure_notes = 0
        for note in measure.findall("note"):
            pitch = note.find("pitch")
            if pitch is None or note.find("grace") is not None:
                continue
            notes.append(
                (
                    pitch.findtext("step", ""),
                    int(pitch.findtext("octave", "0")),
                    int(float(pitch.findtext("alter", "0"))),
                )
            )
            measure_notes += 1
        notes_by_measure.append(measure_notes)

    software = root.findtext("./identification/encoding/software", "")
    rights = root.findtext("./identification/rights", "")
    return notes, notes_by_measure, software, rights


def test_dorico_fixture_integrity_and_provenance() -> None:
    files = MANIFEST["files"]
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest() == files["input"]["sha256"]
    assert hashlib.sha256(ORACLE.read_bytes()).hexdigest() == files["oracle"]["sha256"]

    with pymupdf.open(INPUT) as document:
        assert document.metadata["creator"] == MANIFEST["export"]["pdf_creator"]
        assert document.metadata["producer"] == MANIFEST["export"]["pdf_producer"]
        assert len(document) == files["input"]["pages"]
        assert [len(page.get_images(full=True)) for page in document] == files["input"][
            "images_by_page"
        ]

    _, _, software, rights = _musicxml_notes()
    assert software == MANIFEST["export"]["musicxml_software"]
    assert "CC BY-SA 4.0" in rights


def test_dorico_pdf_matches_musicxml_note_for_note() -> None:
    expected, expected_by_measure, _, _ = _musicxml_notes()
    score = MusicAnalyzer().analyze(VectorPDFParser().parse(INPUT))
    actual = [
        (
            note.note.letter,
            note.note.octave,
            ALTER_FOR_ACCIDENTAL[note.effective_accidental],
        )
        for note in score.notes
    ]

    verification = MANIFEST["verification"]
    assert expected_by_measure == verification["notes_by_measure"]
    assert len(expected) == verification["notes"]
    assert actual == expected

    expected_marks = [alter != 0 for _, _, alter in expected]
    actual_marks = [note.should_mark for note in score.notes]
    true_positives = sum(
        expected_mark and actual_mark
        for expected_mark, actual_mark in zip(expected_marks, actual_marks, strict=True)
    )
    false_positives = sum(
        not expected_mark and actual_mark
        for expected_mark, actual_mark in zip(expected_marks, actual_marks, strict=True)
    )
    false_negatives = sum(
        expected_mark and not actual_mark
        for expected_mark, actual_mark in zip(expected_marks, actual_marks, strict=True)
    )

    acceptance = verification["acceptance"]
    assert sum(actual_marks) == verification["marked_notes"]
    assert true_positives == verification["marked_notes"]
    assert false_positives == acceptance["false_positives"]
    assert false_negatives == acceptance["false_negatives"]
    assert (
        true_positives / (true_positives + false_positives) == acceptance["precision"]
    )
    assert true_positives / (true_positives + false_negatives) == acceptance["recall"]

    sources = Counter(
        note.source.value for note in score.notes if note.should_mark and note.source
    )
    expected_sources = verification["marked_note_sources"]
    assert {source: sources[source] for source in expected_sources} == expected_sources

    ordinals_by_system = [
        [
            ordinal
            for ordinal, note in enumerate(
                (item for item in score.notes if item.note.staff == staff.index),
                start=1,
            )
            if note.should_mark
        ]
        for staff in score.pages[0].staffs
    ]
    assert ordinals_by_system == verification["marked_note_ordinals_by_system"]


def test_dorico_measure_boundaries_match_score() -> None:
    score = VectorPDFParser().parse(INPUT)
    verification = MANIFEST["verification"]
    page = score.pages[0]

    assert len(page.staffs) == verification["systems"]
    assert [len(staff.barlines) for staff in page.staffs] == verification[
        "barlines_by_system"
    ]

    notes_by_measure: list[int] = []
    for staff in page.staffs:
        counts = Counter(
            note.measure for note in page.notes if note.staff == staff.index
        )
        notes_by_measure.extend(counts[measure] for measure in sorted(counts))
    assert notes_by_measure == verification["notes_by_measure"]


def test_dorico_end_to_end_render(tmp_path: Path) -> None:
    score = MusicAnalyzer().analyze(VectorPDFParser().parse(INPUT))
    output = tmp_path / "annotated.pdf"

    marked = PDFRenderer().render(INPUT, output, score)

    assert marked == MANIFEST["verification"]["marked_notes"]
    with pymupdf.open(INPUT) as original, pymupdf.open(output) as annotated:
        assert len(annotated) == len(original) == 1
        assert (
            len(annotated[0].get_drawings()) - len(original[0].get_drawings()) == marked
        )
