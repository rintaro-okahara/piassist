from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Clef(StrEnum):
    TREBLE = "treble"
    BASS = "bass"


class Accidental(StrEnum):
    FLAT = "flat"
    NATURAL = "natural"
    SHARP = "sharp"


class AccidentalSource(StrEnum):
    EXPLICIT = "explicit"
    CARRIED = "carried"
    KEY_SIGNATURE = "keysig"


class SymbolKind(StrEnum):
    NOTEHEAD = "notehead"
    FLAT = "flat"
    NATURAL = "natural"
    SHARP = "sharp"
    TREBLE_CLEF = "treble-clef"
    BASS_CLEF = "bass-clef"


@dataclass(frozen=True, slots=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    def to_dict(self) -> dict[str, float]:
        return {
            "x0": round(self.x0, 3),
            "y0": round(self.y0, 3),
            "x1": round(self.x1, 3),
            "y1": round(self.y1, 3),
        }


@dataclass(frozen=True, slots=True)
class Glyph:
    id: str
    page: int
    kind: SymbolKind
    char: str
    bbox: BBox
    font: str = ""


@dataclass(slots=True)
class Staff:
    page: int
    index: int
    line_ys: tuple[float, float, float, float, float]
    x0: float
    x1: float
    clef: Clef | None = None
    clef_bbox: BBox | None = None
    clef_changes: list[tuple[float, Clef]] = field(default_factory=list)
    barlines: list[float] = field(default_factory=list)

    @property
    def top(self) -> float:
        return self.line_ys[0]

    @property
    def bottom(self) -> float:
        return self.line_ys[-1]

    @property
    def spacing(self) -> float:
        gaps = [
            self.line_ys[i + 1] - self.line_ys[i] for i in range(len(self.line_ys) - 1)
        ]
        return sum(gaps) / len(gaps)

    def contains_y(self, y: float, ledger_spaces: float = 3.0) -> bool:
        margin = self.spacing * ledger_spaces
        return self.top - margin <= y <= self.bottom + margin

    def clef_at(self, x: float) -> Clef | None:
        clef = self.clef
        for position, candidate in self.clef_changes:
            if position > x:
                break
            clef = candidate
        return clef

    def pitch_at(self, y: float, clef: Clef | None = None) -> tuple[str, int] | None:
        active_clef = clef or self.clef
        if active_clef is None:
            return None

        # Moving one line/space upward advances one diatonic scale step.
        steps = round((self.bottom - y) / (self.spacing / 2))
        base_letter, base_octave = ("E", 4) if active_clef is Clef.TREBLE else ("G", 2)
        letters = ("C", "D", "E", "F", "G", "A", "B")
        absolute = base_octave * 7 + letters.index(base_letter) + steps
        octave, letter_index = divmod(absolute, 7)
        return letters[letter_index], octave

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "index": self.index,
            "line_ys": [round(y, 3) for y in self.line_ys],
            "x0": round(self.x0, 3),
            "x1": round(self.x1, 3),
            "spacing": round(self.spacing, 3),
            "clef": self.clef.value if self.clef else None,
            "clef_changes": [
                {"x": round(x, 3), "clef": clef.value} for x, clef in self.clef_changes
            ],
            "barlines": [round(x, 3) for x in self.barlines],
        }


@dataclass(frozen=True, slots=True)
class RawNote:
    id: str
    page: int
    staff: int
    bbox: BBox
    letter: str
    octave: int
    measure: int = 0

    @property
    def x(self) -> float:
        return self.bbox.center_x

    @property
    def y(self) -> float:
        return self.bbox.center_y


@dataclass(frozen=True, slots=True)
class RawAccidental:
    id: str
    page: int
    staff: int
    bbox: BBox
    accidental: Accidental
    letter: str
    octave: int


@dataclass(frozen=True, slots=True)
class AnnotatedNote:
    note: RawNote
    effective_accidental: Accidental | None
    source: AccidentalSource | None
    should_mark: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.note.id,
            "page": self.note.page + 1,
            "staff": self.note.staff,
            "measure": self.note.measure + 1,
            "bbox": self.note.bbox.to_dict(),
            "letter": self.note.letter,
            "octave": self.note.octave,
            "accidental": (
                self.effective_accidental.value if self.effective_accidental else None
            ),
            "source": self.source.value if self.source else None,
            "marked": self.should_mark,
        }


@dataclass(slots=True)
class PageAnalysis:
    page: int
    staffs: list[Staff] = field(default_factory=list)
    notes: list[RawNote] = field(default_factory=list)
    accidentals: list[RawAccidental] = field(default_factory=list)
    key_signatures: dict[int, dict[str, Accidental]] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreAnalysis:
    pages: list[PageAnalysis]
    notes: list[AnnotatedNote] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "pages": len(self.pages),
                "staffs": sum(len(page.staffs) for page in self.pages),
                "notes": len(self.notes),
                "marked_notes": sum(note.should_mark for note in self.notes),
            },
            "pages": [
                {
                    "page": page.page + 1,
                    "staffs": [staff.to_dict() for staff in page.staffs],
                    "key_signatures": {
                        str(staff): {
                            letter: accidental.value
                            for letter, accidental in signature.items()
                        }
                        for staff, signature in page.key_signatures.items()
                    },
                }
                for page in self.pages
            ],
            "notes": [note.to_dict() for note in self.notes],
        }
