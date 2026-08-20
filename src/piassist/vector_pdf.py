from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import pymupdf

from piassist.models import (
    Accidental,
    BBox,
    Clef,
    Glyph,
    PageAnalysis,
    RawAccidental,
    RawNote,
    ScoreAnalysis,
    Staff,
    SymbolKind,
)


class UnsupportedVectorPdfError(RuntimeError):
    """Raised when a PDF does not expose enough vector score information."""


# SMuFL code points used by Bravura and most modern notation fonts.  The
# Unicode alternatives make inspection and small synthetic fixtures useful too.
NOTEHEAD_CODEPOINTS = {
    *(chr(codepoint) for codepoint in range(0xE0A0, 0xE0AA)),
    "●",
}
SYMBOLS: dict[str, SymbolKind] = {
    **{char: SymbolKind.NOTEHEAD for char in NOTEHEAD_CODEPOINTS},
    "\ue260": SymbolKind.FLAT,
    "\ue261": SymbolKind.NATURAL,
    "\ue262": SymbolKind.SHARP,
    "♭": SymbolKind.FLAT,
    "♮": SymbolKind.NATURAL,
    "♯": SymbolKind.SHARP,
    "\ue050": SymbolKind.TREBLE_CLEF,
    "\U0001d11e": SymbolKind.TREBLE_CLEF,
    "\ue062": SymbolKind.BASS_CLEF,
    "\U0001d122": SymbolKind.BASS_CLEF,
}

ACCIDENTAL_FOR_KIND = {
    SymbolKind.FLAT: Accidental.FLAT,
    SymbolKind.NATURAL: Accidental.NATURAL,
    SymbolKind.SHARP: Accidental.SHARP,
}

UNICODE_FALLBACK_SYMBOLS = {"♭", "♮", "♯", "●"}
NOTATION_FONT_HINTS = {
    "bravura",
    "emmentaler",
    "finale",
    "gonville",
    "jazz",
    "leland",
    "maestro",
    "music",
    "musescore",
    "november",
    "opus",
    "petaluma",
    "sonata",
}


@dataclass(frozen=True, slots=True)
class _Line:
    position: float
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


class VectorPDFParser:
    """Extract score geometry from PDFs that retain notation glyphs and lines."""

    def __init__(self, default_clef: Clef | None = None) -> None:
        self.default_clef = default_clef

    def parse(self, path: str | Path) -> ScoreAnalysis:
        pdf_path = Path(path)
        with pymupdf.open(pdf_path) as document:
            pages = [
                self._parse_page(page, page_number)
                for page_number, page in enumerate(document)
            ]

        staff_count = sum(len(page.staffs) for page in pages)
        note_count = sum(len(page.notes) for page in pages)
        if staff_count == 0 or note_count == 0:
            raise UnsupportedVectorPdfError(
                "ベクター楽譜として解析できませんでした "
                f"(五線: {staff_count}, 音符: {note_count})。"
                "スキャンPDFの場合は画像OMRが必要です。"
                "ベクターPDFの場合は `piassist inspect` でグリフを確認してください。"
            )
        return ScoreAnalysis(pages=pages)

    def inspect(self, path: str | Path) -> dict[str, Any]:
        result: dict[str, Any] = {"file": str(path), "pages": []}
        with pymupdf.open(path) as document:
            for page_number, page in enumerate(document):
                chars = list(self._raw_chars(page))
                glyphs = self._extract_glyphs(page, page_number)
                horizontal, _ = self._drawing_lines(page)
                staffs = self._detect_staffs(horizontal, page.rect.width, page_number)
                frequencies = Counter(char for char, _, _ in chars)
                result["pages"].append(
                    {
                        "page": page_number + 1,
                        "raw_character_count": len(chars),
                        "horizontal_line_count": len(horizontal),
                        "detected_staff_count": len(staffs),
                        "recognized_symbols": Counter(
                            glyph.kind.value for glyph in glyphs
                        ),
                        "glyphs": [
                            {
                                "char": char,
                                "codepoints": " ".join(
                                    f"U+{ord(part):04X}" for part in char
                                ),
                                "count": count,
                                "fonts": sorted(
                                    {
                                        font
                                        for candidate, _, font in chars
                                        if candidate == char and font
                                    }
                                ),
                            }
                            for char, count in sorted(
                                frequencies.items(),
                                key=lambda item: (-item[1], item[0]),
                            )
                        ],
                    }
                )
        return result

    def _parse_page(self, page: pymupdf.Page, page_number: int) -> PageAnalysis:
        glyphs = self._extract_glyphs(page, page_number)
        horizontal, vertical = self._drawing_lines(page)
        staffs = self._detect_staffs(horizontal, page.rect.width, page_number)
        self._assign_clefs(staffs, glyphs)

        note_glyphs = [glyph for glyph in glyphs if glyph.kind is SymbolKind.NOTEHEAD]
        accidental_glyphs = [
            glyph for glyph in glyphs if glyph.kind in ACCIDENTAL_FOR_KIND
        ]
        notes = self._make_notes(staffs, note_glyphs)
        accidentals = self._make_accidentals(staffs, accidental_glyphs)
        self._assign_barlines(staffs, vertical, notes)
        notes = self._assign_measures(staffs, notes)
        return PageAnalysis(
            page=page_number,
            staffs=staffs,
            notes=notes,
            accidentals=accidentals,
        )

    def _raw_chars(self, page: pymupdf.Page) -> Iterable[tuple[str, BBox, str]]:
        raw = page.get_text("rawdict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font = span.get("font", "")
                    for char in span.get("chars", []):
                        value = char.get("c", "")
                        bbox = char.get("bbox")
                        if value and bbox and len(bbox) == 4:
                            yield value, BBox(*map(float, bbox)), font

    def _extract_glyphs(self, page: pymupdf.Page, page_number: int) -> list[Glyph]:
        glyphs: list[Glyph] = []
        for index, (char, bbox, font) in enumerate(self._raw_chars(page)):
            kind = SYMBOLS.get(char)
            if kind is not None and self._is_notation_symbol(char, font):
                glyphs.append(
                    Glyph(
                        id=f"p{page_number}-g{index}",
                        page=page_number,
                        kind=kind,
                        char=char,
                        bbox=bbox,
                        font=font,
                    )
                )
        return glyphs

    @staticmethod
    def _is_notation_symbol(char: str, font: str) -> bool:
        """Keep text such as chord-name ``B♭`` out of score accidentals."""
        if char not in UNICODE_FALLBACK_SYMBOLS:
            return True
        normalized_font = font.casefold()
        return any(hint in normalized_font for hint in NOTATION_FONT_HINTS)

    def _drawing_lines(self, page: pymupdf.Page) -> tuple[list[_Line], list[_Line]]:
        horizontal: list[_Line] = []
        vertical: list[_Line] = []
        for drawing in page.get_drawings():
            for item in drawing.get("items", []):
                if not item:
                    continue
                if item[0] == "l" and len(item) >= 3:
                    p1, p2 = item[1], item[2]
                    x1, y1 = float(p1.x), float(p1.y)
                    x2, y2 = float(p2.x), float(p2.y)
                    if abs(y1 - y2) <= 0.5 and abs(x1 - x2) > 1:
                        horizontal.append(
                            _Line((y1 + y2) / 2, min(x1, x2), max(x1, x2))
                        )
                    elif abs(x1 - x2) <= 0.5 and abs(y1 - y2) > 1:
                        vertical.append(_Line((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
                elif item[0] == "re" and len(item) >= 2:
                    rect = pymupdf.Rect(item[1])
                    if rect.width > 1 and rect.height <= 1.5:
                        horizontal.append(
                            _Line(rect.y0 + rect.height / 2, rect.x0, rect.x1)
                        )
                    elif rect.height > 1 and rect.width <= 1.5:
                        vertical.append(
                            _Line(rect.x0 + rect.width / 2, rect.y0, rect.y1)
                        )
        return self._merge_lines(horizontal), self._merge_lines(vertical)

    @staticmethod
    def _merge_lines(lines: list[_Line], tolerance: float = 0.6) -> list[_Line]:
        merged: list[_Line] = []
        for line in sorted(lines, key=lambda value: (value.position, value.start)):
            match_index = next(
                (
                    index
                    for index, existing in enumerate(merged)
                    if abs(existing.position - line.position) <= tolerance
                    and min(existing.end, line.end)
                    >= max(existing.start, line.start) - tolerance
                ),
                None,
            )
            if match_index is None:
                merged.append(line)
                continue
            existing = merged[match_index]
            merged[match_index] = _Line(
                position=(existing.position + line.position) / 2,
                start=min(existing.start, line.start),
                end=max(existing.end, line.end),
            )
        return sorted(merged, key=lambda value: value.position)

    def _detect_staffs(
        self, lines: list[_Line], page_width: float, page_number: int
    ) -> list[Staff]:
        long_lines = [line for line in lines if line.length >= page_width * 0.15]
        candidates: list[tuple[float, tuple[int, ...], list[_Line]]] = []
        for start in range(max(0, len(long_lines) - 4)):
            group = long_lines[start : start + 5]
            gaps = [
                group[index + 1].position - group[index].position for index in range(4)
            ]
            spacing = sum(gaps) / 4
            if not 2 <= spacing <= 30:
                continue
            deviation = max(abs(gap - spacing) for gap in gaps) / spacing
            overlap = min(line.end for line in group) - max(
                line.start for line in group
            )
            if deviation <= 0.18 and overlap >= page_width * 0.12:
                candidates.append((deviation, tuple(range(start, start + 5)), group))

        chosen: list[list[_Line]] = []
        used: set[int] = set()
        for _, indices, group in sorted(candidates, key=lambda item: item[0]):
            if used.intersection(indices):
                continue
            chosen.append(group)
            used.update(indices)

        staffs: list[Staff] = []
        for index, group in enumerate(
            sorted(chosen, key=lambda value: value[0].position)
        ):
            staffs.append(
                Staff(
                    page=page_number,
                    index=index,
                    line_ys=tuple(line.position for line in group),  # type: ignore[arg-type]
                    x0=median(line.start for line in group),
                    x1=median(line.end for line in group),
                )
            )
        return staffs

    def _assign_clefs(self, staffs: list[Staff], glyphs: list[Glyph]) -> None:
        clefs = [
            glyph
            for glyph in glyphs
            if glyph.kind in {SymbolKind.TREBLE_CLEF, SymbolKind.BASS_CLEF}
        ]
        for staff in staffs:
            candidates = [
                glyph
                for glyph in clefs
                if staff.contains_y(glyph.bbox.center_y, ledger_spaces=2)
                and staff.x0 - staff.spacing <= glyph.bbox.center_x <= staff.x1
            ]
            if candidates:
                ordered = sorted(candidates, key=lambda value: value.bbox.center_x)
                staff.clef_changes = [
                    (
                        glyph.bbox.center_x,
                        Clef.TREBLE
                        if glyph.kind is SymbolKind.TREBLE_CLEF
                        else Clef.BASS,
                    )
                    for glyph in ordered
                ]
                staff.clef = staff.clef_changes[0][1]
                staff.clef_bbox = ordered[0].bbox
            else:
                staff.clef = self.default_clef

    @staticmethod
    def _nearest_staff(staffs: list[Staff], glyph: Glyph) -> Staff | None:
        candidates = [
            staff
            for staff in staffs
            # Piano arrangements regularly use notes five or six staff spaces
            # beyond the outer line. Those are still unambiguous notation
            # glyphs, so retain them instead of dropping their noteheads.
            if staff.contains_y(glyph.bbox.center_y, ledger_spaces=6)
            and staff.x0 - 2 * staff.spacing
            <= glyph.bbox.center_x
            <= staff.x1 + 2 * staff.spacing
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda staff: abs(glyph.bbox.center_y - (staff.top + staff.bottom) / 2),
        )

    def _make_notes(self, staffs: list[Staff], glyphs: list[Glyph]) -> list[RawNote]:
        notes: list[RawNote] = []
        for glyph in glyphs:
            staff = self._nearest_staff(staffs, glyph)
            if staff is None:
                continue
            pitch = staff.pitch_at(
                glyph.bbox.center_y, staff.clef_at(glyph.bbox.center_x)
            )
            if pitch is None:
                continue
            notes.append(
                RawNote(
                    id=glyph.id,
                    page=glyph.page,
                    staff=staff.index,
                    bbox=glyph.bbox,
                    letter=pitch[0],
                    octave=pitch[1],
                )
            )
        return notes

    def _make_accidentals(
        self, staffs: list[Staff], glyphs: list[Glyph]
    ) -> list[RawAccidental]:
        accidentals: list[RawAccidental] = []
        for glyph in glyphs:
            staff = self._nearest_staff(staffs, glyph)
            if staff is None:
                continue
            pitch = staff.pitch_at(
                glyph.bbox.center_y, staff.clef_at(glyph.bbox.center_x)
            )
            if pitch is None:
                continue
            accidentals.append(
                RawAccidental(
                    id=glyph.id,
                    page=glyph.page,
                    staff=staff.index,
                    bbox=glyph.bbox,
                    accidental=ACCIDENTAL_FOR_KIND[glyph.kind],
                    letter=pitch[0],
                    octave=pitch[1],
                )
            )
        return accidentals

    def _assign_barlines(
        self,
        staffs: list[Staff],
        vertical: list[_Line],
        notes: list[RawNote],
    ) -> None:
        for staff in staffs:
            staff_notes = [note for note in notes if note.staff == staff.index]
            first_note_x = min((note.x for note in staff_notes), default=staff.x0)
            candidates = [
                line.position
                for line in vertical
                if line.length >= staff.spacing * 3
                and line.start <= staff.top + staff.spacing
                and line.end >= staff.bottom - staff.spacing
                and first_note_x + staff.spacing * 0.5 < line.position
                and line.position <= staff.x1 + staff.spacing
            ]
            staff.barlines = self._dedupe_positions(
                candidates, tolerance=max(0.8, staff.spacing * 0.2)
            )

    @staticmethod
    def _dedupe_positions(values: list[float], tolerance: float) -> list[float]:
        result: list[float] = []
        for value in sorted(values):
            if not result or abs(value - result[-1]) > tolerance:
                result.append(value)
            else:
                result[-1] = (result[-1] + value) / 2
        return result

    @staticmethod
    def _assign_measures(staffs: list[Staff], notes: list[RawNote]) -> list[RawNote]:
        result: list[RawNote] = []
        by_index = {staff.index: staff for staff in staffs}
        for note in notes:
            staff = by_index[note.staff]
            measure = sum(barline < note.x for barline in staff.barlines)
            result.append(
                RawNote(
                    id=note.id,
                    page=note.page,
                    staff=note.staff,
                    bbox=note.bbox,
                    letter=note.letter,
                    octave=note.octave,
                    measure=measure,
                )
            )
        return result
