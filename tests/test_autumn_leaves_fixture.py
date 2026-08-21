from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median

import pymupdf
import pytest

from piassist.models import Accidental
from piassist.music_logic import AnnotationOptions, MusicAnalyzer
from piassist.render import PDFRenderer
from piassist.vector_pdf import VectorPDFParser

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "autumn_leaves"
INPUT = FIXTURE_DIR / "input.pdf"
EXPECTED = FIXTURE_DIR / "expected_annotated.pdf"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())
EXPECTED_STAFFS = MANIFEST["score_structure"]["staffs_by_page"]
EXPECTED_RED_CIRCLES = MANIFEST["expected_annotations"]["red_circles_by_page"]


def _is_red(drawing: dict[str, object]) -> bool:
    color = drawing.get("color")
    if not isinstance(color, list | tuple) or len(color) < 3:
        return False
    return color[0] > 0.8 and color[1] < 0.25 and color[2] < 0.25


def test_input_and_expected_pdf_integrity() -> None:
    assert (
        hashlib.sha256(INPUT.read_bytes()).hexdigest()
        == MANIFEST["files"]["input"]["sha256"]
    )
    assert (
        hashlib.sha256(EXPECTED.read_bytes()).hexdigest()
        == MANIFEST["files"]["expected_annotated"]["sha256"]
    )

    with (
        pymupdf.open(INPUT) as input_document,
        pymupdf.open(EXPECTED) as expected_document,
    ):
        expected_pages = MANIFEST["files"]["input"]["pages"]
        assert len(input_document) == len(expected_document) == expected_pages
        assert sum(EXPECTED_RED_CIRCLES) == MANIFEST["expected_annotations"][
            "total_red_circles"
        ]
        for page_number, (input_page, expected_page) in enumerate(
            zip(input_document, expected_document, strict=True)
        ):
            input_drawings = input_page.get_drawings()
            expected_drawings = expected_page.get_drawings()
            assert not any(_is_red(drawing) for drawing in input_drawings)
            assert (
                sum(_is_red(drawing) for drawing in expected_drawings)
                == EXPECTED_RED_CIRCLES[page_number]
            )
            assert (
                len(expected_drawings) - len(input_drawings)
                == EXPECTED_RED_CIRCLES[page_number]
            )
            assert input_page.get_text("rawdict") == expected_page.get_text("rawdict")
            assert not input_page.get_images(full=True)
            assert not expected_page.get_images(full=True)


def test_input_pdf_remains_parseable_as_vector_score() -> None:
    score = VectorPDFParser().parse(INPUT)

    assert [len(page.staffs) for page in score.pages] == EXPECTED_STAFFS
    assert sum(len(page.notes) for page in score.pages) == 2_041


def test_chord_symbol_flats_are_not_parsed_as_accidentals() -> None:
    inspection = VectorPDFParser().inspect(INPUT)

    # Page 1 also contains nine Unicode ♭ characters in chord names. Only the
    # 28 SMuFL flat glyphs from the Leland notation font should be recognized.
    assert inspection["pages"][0]["recognized_symbols"]["flat"] == 28


def test_end_to_end_annotation_quality_against_golden_pdf(tmp_path: Path) -> None:
    score = MusicAnalyzer(
        AnnotationOptions(key_signature={"B": Accidental.FLAT, "E": Accidental.FLAT})
    ).analyze(VectorPDFParser().parse(INPUT))
    generated = tmp_path / "autumn_leaves_generated.pdf"
    PDFRenderer().render(INPUT, generated, score)

    with (
        pymupdf.open(INPUT) as source_document,
        pymupdf.open(generated) as generated_document,
    ):
        source_fonts = {
            xref for page in source_document for xref, *_ in page.get_fonts(full=True)
        }
        generated_fonts = {
            xref
            for page in generated_document
            for xref, *_ in page.get_fonts(full=True)
        }
        assert generated_fonts == source_fonts
        assert all(
            generated_document.xref_object(xref, compressed=False)
            == source_document.xref_object(xref, compressed=False)
            for xref in source_fonts
        )

    generated_centers, generated_sizes = _red_geometry(generated)
    expected_centers, expected_sizes = _red_geometry(EXPECTED)
    matches = sum(
        _match_centers(generated_centers[page], expected_centers[page], tolerance=1.5)
        for page in expected_centers
    )
    generated_count = sum(len(centers) for centers in generated_centers.values())
    expected_count = sum(len(centers) for centers in expected_centers.values())
    precision = matches / generated_count
    recall = matches / expected_count

    recorded = MANIFEST["evaluation"]["result"]
    assert matches == recorded["matched_circles"]
    assert generated_count == recorded["predicted_circles"]
    assert expected_count == recorded["expected_circles"]
    assert precision * 100 == pytest.approx(recorded["precision_percent"], abs=0.005)
    assert recall * 100 == pytest.approx(recorded["recall_percent"], abs=0.005)
    assert median(width for width, _ in generated_sizes) == pytest.approx(
        median(width for width, _ in expected_sizes), abs=0.1
    )
    assert median(height for _, height in generated_sizes) == pytest.approx(
        median(height for _, height in expected_sizes), abs=0.1
    )


def _red_geometry(
    path: Path,
) -> tuple[dict[int, list[tuple[float, float]]], list[tuple[float, float]]]:
    centers: dict[int, list[tuple[float, float]]] = {}
    sizes: list[tuple[float, float]] = []
    with pymupdf.open(path) as document:
        for page_number, page in enumerate(document):
            centers[page_number] = []
            for drawing in page.get_drawings():
                if not _is_red(drawing):
                    continue
                rect = drawing["rect"]
                centers[page_number].append(
                    (rect.x0 + rect.width / 2, rect.y0 + rect.height / 2)
                )
                sizes.append((rect.width, rect.height))
    return centers, sizes


def _match_centers(
    predicted: list[tuple[float, float]],
    expected: list[tuple[float, float]],
    tolerance: float,
) -> int:
    remaining = set(range(len(expected)))
    matches = 0
    for predicted_x, predicted_y in predicted:
        candidates = [
            (
                (
                    (predicted_x - expected[index][0]) ** 2
                    + (predicted_y - expected[index][1]) ** 2
                )
                ** 0.5,
                index,
            )
            for index in remaining
        ]
        if not candidates:
            continue
        distance, index = min(candidates)
        if distance <= tolerance:
            remaining.remove(index)
            matches += 1
    return matches
