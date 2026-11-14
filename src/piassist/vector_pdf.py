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
    Tie,
)


class UnsupportedVectorPdfError(RuntimeError):
    """Raised when a PDF does not expose enough vector score information."""


# SMuFL's standard noteheads plus the recommended oversized alternates that
# Dorico may preserve in exported PDFs. The Unicode alternative makes small
# synthetic fixtures useful too.
NOTEHEAD_CODEPOINTS = {
    *(chr(codepoint) for codepoint in range(0xE0A0, 0xE0AA)),
    *(chr(codepoint) for codepoint in range(0xF4BC, 0xF4BF)),
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

# Sibelius' legacy Opus music font predates SMuFL. Its PDF ToUnicode map
# exposes notation as ordinary-looking characters, so these values must only
# be interpreted inside the actual notation face (never in lyrics or chord
# names). The note values differ by duration, but all three share the same
# notehead anchor used by the pitch detector.
SIBELIUS_OPUS_SYMBOLS: dict[str, SymbolKind] = {
    "œ": SymbolKind.NOTEHEAD,
    "˙": SymbolKind.NOTEHEAD,
    "w": SymbolKind.NOTEHEAD,
    "b": SymbolKind.FLAT,
    "n": SymbolKind.NATURAL,
    "#": SymbolKind.SHARP,
    "&": SymbolKind.TREBLE_CLEF,
    "?": SymbolKind.BASS_CLEF,
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
        ties = self._detect_ties(page, staffs, notes)
        return PageAnalysis(
            page=page_number,
            staffs=staffs,
            notes=notes,
            ties=ties,
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
                            glyph_bbox = BBox(*map(float, bbox))
                            origin = char.get("origin")
                            if (
                                self._is_sibelius_opus_notation_font(font)
                                and value in SIBELIUS_OPUS_SYMBOLS
                                and origin
                                and len(origin) == 2
                            ):
                                # For Opus glyphs, the text origin is the
                                # musical anchor (the notehead/accidental
                                # pitch). PyMuPDF's generic text bbox is based
                                # on the font ascent and sits roughly one staff
                                # space too high. Preserve its dimensions while
                                # moving the center onto the music anchor.
                                offset_y = float(origin[1]) - glyph_bbox.center_y
                                glyph_bbox = BBox(
                                    glyph_bbox.x0,
                                    glyph_bbox.y0 + offset_y,
                                    glyph_bbox.x1,
                                    glyph_bbox.y1 + offset_y,
                                )
                            yield value, glyph_bbox, font

    def _extract_glyphs(self, page: pymupdf.Page, page_number: int) -> list[Glyph]:
        glyphs: list[Glyph] = []
        for index, (char, bbox, font) in enumerate(self._raw_chars(page)):
            kind = self._symbol_kind(char, font)
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

    @classmethod
    def _symbol_kind(cls, char: str, font: str) -> SymbolKind | None:
        if cls._is_sibelius_opus_notation_font(font):
            return SIBELIUS_OPUS_SYMBOLS.get(char)
        return SYMBOLS.get(char)

    @staticmethod
    def _is_sibelius_opus_notation_font(font: str) -> bool:
        normalized = font.casefold().replace(" ", "")
        return normalized in {"opus", "opusstd"} or normalized.endswith(
            "+opusstd"
        )

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
            leading_region_end = staff.x0 + (staff.x1 - staff.x0) * 0.12
            candidates = [
                line.position
                for line in vertical
                if line.length >= staff.spacing * 3.25
                and line.start <= staff.top + staff.spacing * 0.75
                and line.end >= staff.bottom - staff.spacing * 0.75
                # A system can begin with one or more rest-only measures, so
                # its first genuine barline may precede the first notehead.
                # Keep those distant boundaries while excluding a left repeat
                # bar or system edge inside the leading notation region.
                and (
                    first_note_x + staff.spacing * 0.5 < line.position
                    or leading_region_end < line.position
                )
                and staff.x0 <= line.position
                and line.position <= staff.x1 + staff.spacing
                and not self._touches_notehead(line, staff, staff_notes)
            ]
            staff.barlines = self._dedupe_positions(
                # A final or double barline is drawn as two nearby vertical
                # strokes, but it still represents one measure boundary.
                candidates,
                tolerance=max(0.8, staff.spacing),
            )

    @staticmethod
    def _touches_notehead(
        line: _Line,
        staff: Staff,
        notes: list[RawNote],
    ) -> bool:
        """Return whether a vertical line is attached to a notehead.

        Long stems can cover most or all of a staff and therefore satisfy the
        same coarse height checks as barlines. Unlike barlines, a stem meets a
        notehead at one endpoint, sometimes with a small PDF rounding gap.
        """
        # Dorico places stems a small distance outside the notehead glyph's
        # reported bounding box. The gap is larger than PDF rounding noise,
        # especially for its oversized SMuFL noteheads, so compare in staff
        # spaces rather than using a near-zero absolute tolerance.
        edge_tolerance = staff.spacing * 0.1
        endpoint_tolerance = staff.spacing * 0.8
        return any(
            # SMuFL notehead boxes usually end at the stem. Sibelius' Opus
            # boxes are wider and can contain the stem position, so accept the
            # whole horizontal glyph extent plus a small rounding margin.
            note.bbox.x0 - edge_tolerance
            <= line.position
            <= note.bbox.x1 + edge_tolerance
            and min(abs(line.start - note.y), abs(line.end - note.y))
            <= endpoint_tolerance
            for note in notes
        )

    def _detect_ties(
        self,
        page: pymupdf.Page,
        staffs: list[Staff],
        notes: list[RawNote],
    ) -> list[Tie]:
        """Infer ties from narrow, filled two-curve paths in a vector score.

        Dorico exports both ties and slurs as filled Bezier paths. A tie is
        distinguished here by its compact lens shape and by having matching
        noteheads at both endpoints on the same staff and pitch.
        """
        ties: list[Tie] = []
        seen: set[tuple[str, str]] = set()
        notes_by_staff = {
            staff.index: [note for note in notes if note.staff == staff.index]
            for staff in staffs
        }

        for drawing in page.get_drawings():
            items = drawing.get("items", [])
            curve_count = sum(item and item[0] == "c" for item in items)
            if (
                drawing.get("type") not in {"f", "fs"}
                or curve_count != 2
                or any(item and item[0] not in {"c", "l"} for item in items)
            ):
                continue

            rect = pymupdf.Rect(drawing["rect"])
            if rect.width <= 0 or rect.height <= 0:
                continue
            bbox = BBox(rect.x0, rect.y0, rect.x1, rect.y1)

            for staff in staffs:
                tie = self._match_tie_path(bbox, staff, notes_by_staff[staff.index])
                if tie is None:
                    continue
                pair = (tie.source_note_id, tie.target_note_id)
                if pair not in seen:
                    ties.append(tie)
                    seen.add(pair)
                break

        return ties

    @staticmethod
    def _match_tie_path(bbox: BBox, staff: Staff, notes: list[RawNote]) -> Tie | None:
        spacing = staff.spacing
        if not (
            spacing * 0.5 <= bbox.x1 - bbox.x0 <= spacing * 25
            and bbox.y1 - bbox.y0 <= spacing * 2
        ):
            return None

        endpoint_tolerance = spacing * 2.5
        source_candidates = [
            note
            for note in notes
            if abs(note.x - bbox.x0) <= endpoint_tolerance
            and abs(note.y - bbox.center_y) <= endpoint_tolerance
        ]
        target_candidates = [
            note
            for note in notes
            if abs(note.x - bbox.x1) <= endpoint_tolerance
            and abs(note.y - bbox.center_y) <= endpoint_tolerance
        ]
        matches = [
            (source, target)
            for source in source_candidates
            for target in target_candidates
            if source.x < target.x
            and (source.letter, source.octave) == (target.letter, target.octave)
        ]
        if not matches:
            return None

        source, target = min(
            matches,
            key=lambda pair: (
                abs(pair[0].x - bbox.x0)
                + abs(pair[1].x - bbox.x1)
                + abs(pair[0].y - bbox.center_y)
                + abs(pair[1].y - bbox.center_y)
            ),
        )
        return Tie(
            source_note_id=source.id,
            target_note_id=target.id,
            page=staff.page,
            staff=staff.index,
            bbox=bbox,
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
