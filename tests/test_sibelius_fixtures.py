from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import pymupdf
import pytest

from piassist.models import Accidental, Clef, SymbolKind
from piassist.music_logic import MusicAnalyzer
from piassist.vector_pdf import VectorPDFParser

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sibelius"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
SAMPLES = tuple(MANIFEST["samples"])
PDSA_SAMPLES = ("aura_lee", "beale_street_blues", "beautiful_ohio")

ALTER_FOR_ACCIDENTAL = {
    None: 0,
    Accidental.NATURAL: 0,
    Accidental.FLAT: -1,
    Accidental.SHARP: 1,
}


def _paths(sample: str) -> tuple[Path, Path]:
    directory = FIXTURE_ROOT / sample
    return directory / "input.pdf", directory / "oracle.musicxml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def _opus_characters(path: Path) -> Counter[str]:
    characters: Counter[str] = Counter()
    with pymupdf.open(path) as document:
        for page in document:
            for block in page.get_text("rawdict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("font") != "OpusStd":
                            continue
                        characters.update(
                            char["c"] for char in span.get("chars", []) if char.get("c")
                        )
    return characters


def _musicxml_notes(part: ElementTree.Element) -> list[tuple[str, int, int]]:
    notes: list[tuple[str, int, int]] = []
    for note in part.findall(".//note"):
        pitch = note.find("pitch")
        if pitch is None or note.find("grace") is not None:
            continue
        alter = int(float(pitch.findtext("alter", "0")))
        notes.append(
            (
                pitch.findtext("step", ""),
                int(pitch.findtext("octave", "0")),
                1 if alter > 0 else -1 if alter < 0 else 0,
            )
        )
    return notes


@pytest.mark.parametrize("sample", SAMPLES)
def test_sibelius_fixture_integrity_and_provenance(sample: str) -> None:
    fixture = MANIFEST["samples"][sample]
    input_pdf, oracle = _paths(sample)

    assert _sha256(input_pdf) == fixture["files"]["input"]["sha256"]
    assert _sha256(oracle) == fixture["files"]["oracle"]["sha256"]
    assert _md5(input_pdf) == fixture["files"]["input"]["md5"]
    assert _md5(oracle) == fixture["files"]["oracle"]["md5"]

    export = fixture["export"]
    with pymupdf.open(input_pdf) as document:
        assert document.metadata["creator"] == export["pdf_creator"]
        assert document.metadata["producer"] == export["pdf_producer"]
        assert len(document) == export["pages"]
        assert [len(page.get_images(full=True)) for page in document] == export[
            "images_by_page"
        ]

    root = ElementTree.parse(oracle).getroot()
    assert (
        root.findtext("./identification/encoding/software", "")
        == export["musicxml_software"]
    )

    characters = _opus_characters(input_pdf)
    for group in fixture["opus_glyphs"].values():
        assert {char: characters[char] for char in group} == group


@pytest.mark.parametrize("sample", SAMPLES)
def test_sibelius_pdf_structure(sample: str) -> None:
    fixture = MANIFEST["samples"][sample]
    input_pdf, _ = _paths(sample)
    expected = fixture["expected"]

    score = VectorPDFParser().parse(input_pdf)

    assert [len(page.staffs) for page in score.pages] == expected["staffs_by_page"]
    assert [len(page.notes) for page in score.pages] == expected["notes_by_page"]
    assert [len(page.accidentals) for page in score.pages] == expected[
        "accidentals_by_page"
    ]
    assert [len(page.ties) for page in score.pages] == expected[
        "tie_detection_baseline_by_page"
    ]
    assert [
        [len(staff.barlines) for staff in page.staffs] for page in score.pages
    ] == expected["barlines_by_staff"]

    clefs = Counter(staff.clef for page in score.pages for staff in page.staffs)
    expected_clefs = fixture["opus_glyphs"]["clefs"]
    assert clefs[Clef.TREBLE] == expected_clefs["&"]
    assert clefs[Clef.BASS] == expected_clefs["?"]

    notehead_glyphs = sum(fixture["opus_glyphs"]["noteheads"].values())
    assert sum(len(page.notes) for page in score.pages) == notehead_glyphs
    accidental_glyphs = sum(fixture["opus_glyphs"]["accidentals"].values())
    assert sum(len(page.accidentals) for page in score.pages) == accidental_glyphs


@pytest.mark.parametrize("sample", PDSA_SAMPLES)
def test_pdsa_sibelius_pdf_matches_musicxml_note_for_note(sample: str) -> None:
    input_pdf, oracle = _paths(sample)
    root = ElementTree.parse(oracle).getroot()
    parts = root.findall("part")
    score = MusicAnalyzer().analyze(VectorPDFParser().parse(input_pdf))

    assert len(parts) == MANIFEST["samples"][sample]["expected"]["parts"]
    for part_index, part in enumerate(parts):
        expected = _musicxml_notes(part)
        actual_notes = [
            note
            for note in score.notes
            if len(parts) == 1 or note.note.staff % len(parts) == part_index
        ]
        actual = [
            (
                note.note.letter,
                note.note.octave,
                ALTER_FOR_ACCIDENTAL[note.effective_accidental],
            )
            for note in actual_notes
        ]

        assert len(actual) == MANIFEST["samples"][sample]["expected"][
            "notes_by_part"
        ][part_index]
        assert actual == expected
        assert [note.should_mark for note in actual_notes] == [
            alter != 0 for _, _, alter in expected
        ]


def test_beethoven_sibelius_pdf_matches_musicxml_by_system_and_staff() -> None:
    sample = MANIFEST["samples"]["beethoven_op27_no2_i"]
    input_pdf, oracle = _paths("beethoven_op27_no2_i")
    score = VectorPDFParser().parse(input_pdf)
    root = ElementTree.parse(oracle).getroot()
    part = root.find("part")
    assert part is not None

    expected = sample["expected"]
    assert len(_musicxml_notes(part)) == expected["musicxml_note_elements"]
    assert sum(len(page.notes) for page in score.pages) == expected[
        "pdf_notehead_glyphs"
    ]

    shared = expected["shared_notehead"]
    ranges = expected["system_measure_ranges"]
    for page in score.pages:
        for staff in page.staffs:
            first_measure, last_measure = ranges[page.page][staff.index // 2]
            xml_staff = staff.index % 2 + 1
            expected_pitches: Counter[tuple[str, int]] = Counter()
            for measure in part.findall("measure"):
                measure_number = int(measure.get("number", "0"))
                if not first_measure <= measure_number <= last_measure:
                    continue
                for note in measure.findall("note"):
                    pitch = note.find("pitch")
                    if (
                        pitch is None
                        or note.find("grace") is not None
                        or int(note.findtext("staff", "1")) != xml_staff
                    ):
                        continue
                    expected_pitches[
                        (
                            pitch.findtext("step", ""),
                            int(pitch.findtext("octave", "0")),
                        )
                    ] += 1

            if (
                first_measure <= shared["measure"] <= last_measure
                and xml_staff == shared["staff"]
            ):
                shared_pitch = (shared["letter"], shared["octave"])
                assert expected_pitches[shared_pitch] > 1
                expected_pitches[shared_pitch] -= 1

            actual_pitches = Counter(
                (note.letter, note.octave)
                for note in page.notes
                if note.staff == staff.index
            )
            assert actual_pitches == +expected_pitches

    analyzed = MusicAnalyzer().analyze(score)
    expected_key = {
        "F": Accidental.SHARP,
        "C": Accidental.SHARP,
        "G": Accidental.SHARP,
        "D": Accidental.SHARP,
    }
    assert all(
        page.key_signatures[staff.index] == expected_key
        for page in analyzed.pages
        for staff in page.staffs
    )


def test_legacy_opus_symbols_are_font_scoped() -> None:
    parser = VectorPDFParser()

    assert parser._symbol_kind("œ", "OpusStd") is SymbolKind.NOTEHEAD
    assert parser._symbol_kind("?", "OpusStd") is SymbolKind.BASS_CLEF
    assert parser._symbol_kind("#", "OpusStd") is SymbolKind.SHARP
    assert parser._symbol_kind("#", "OpusChordsStd") is None
    assert parser._symbol_kind("b", "PlantinMTStd-Regular") is None
