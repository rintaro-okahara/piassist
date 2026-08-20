from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from piassist.models import (
    Accidental,
    AccidentalSource,
    AnnotatedNote,
    RawAccidental,
    RawNote,
    ScoreAnalysis,
    Staff,
)


class AnnotationMode(StrEnum):
    SHARP_FLAT = "sharp-flat"
    SHARP_ONLY = "sharp-only"
    FLAT_ONLY = "flat-only"


@dataclass(frozen=True, slots=True)
class AnnotationOptions:
    mode: AnnotationMode = AnnotationMode.SHARP_FLAT
    include_key_signature: bool = True
    key_signature: dict[str, Accidental] | None = None


SHARP_ORDER = ("F", "C", "G", "D", "A", "E", "B")
FLAT_ORDER = ("B", "E", "A", "D", "G", "C", "F")


def parse_key_signature(value: str) -> dict[str, Accidental]:
    """Parse a CLI key signature such as ``Bb,Eb`` or ``F#,C#``."""
    if value.strip().lower() in {"", "none"}:
        return {}

    result: dict[str, Accidental] = {}
    for raw_token in value.split(","):
        token = raw_token.strip()
        if len(token) != 2 or token[0].upper() not in "ABCDEFG":
            raise ValueError(f"不正な調号 `{token}` です。例: Bb,Eb または F#,C#")
        if token[1] in {"b", "♭"}:
            accidental = Accidental.FLAT
        elif token[1] in {"#", "♯"}:
            accidental = Accidental.SHARP
        else:
            raise ValueError(
                f"不正な調号 `{token}` です。b または # を指定してください。"
            )
        result[token[0].upper()] = accidental
    return result


class MusicAnalyzer:
    def __init__(self, options: AnnotationOptions | None = None) -> None:
        self.options = options or AnnotationOptions()

    def analyze(self, score: ScoreAnalysis) -> ScoreAnalysis:
        annotated: list[AnnotatedNote] = []
        for page in score.pages:
            for staff in page.staffs:
                notes = [note for note in page.notes if note.staff == staff.index]
                accidentals = [
                    accidental
                    for accidental in page.accidentals
                    if accidental.staff == staff.index
                ]
                inferred, key_signature_ids = self._infer_key_signature(
                    staff, notes, accidentals
                )
                key_signature = (
                    dict(self.options.key_signature)
                    if self.options.key_signature is not None
                    else inferred
                )
                page.key_signatures[staff.index] = key_signature
                explicit = self._associate_accidentals(
                    staff,
                    notes,
                    [
                        accidental
                        for accidental in accidentals
                        if accidental.id not in key_signature_ids
                    ],
                )
                annotated.extend(self._apply_state(notes, explicit, key_signature))
        score.notes = sorted(
            annotated,
            key=lambda item: (
                item.note.page,
                item.note.staff,
                item.note.measure,
                item.note.x,
                item.note.y,
            ),
        )
        return score

    def _infer_key_signature(
        self,
        staff: Staff,
        notes: list[RawNote],
        accidentals: list[RawAccidental],
    ) -> tuple[dict[str, Accidental], set[str]]:
        if not notes:
            return {}, set()

        first_note_x = min(note.x for note in notes)
        clef_right = staff.clef_bbox.x1 if staff.clef_bbox is not None else staff.x0
        leading = sorted(
            (
                accidental
                for accidental in accidentals
                if accidental.accidental in {Accidental.FLAT, Accidental.SHARP}
                and clef_right
                < accidental.bbox.center_x
                < first_note_x - staff.spacing * 1.5
            ),
            key=lambda accidental: accidental.bbox.center_x,
        )
        if not leading:
            return {}, set()

        accidental_type = leading[0].accidental
        same_type = [
            accidental
            for accidental in leading
            if accidental.accidental is accidental_type
        ]
        if len(same_type) != len(leading) or len(leading) > 7:
            return {}, set()

        expected_order = (
            SHARP_ORDER if accidental_type is Accidental.SHARP else FLAT_ORDER
        )
        observed = tuple(accidental.letter for accidental in leading)
        if observed != expected_order[: len(observed)]:
            return {}, set()

        return (
            {letter: accidental_type for letter in observed},
            {accidental.id for accidental in leading},
        )

    @staticmethod
    def _measure_for_x(staff: Staff, x: float) -> int:
        return sum(barline < x for barline in staff.barlines)

    def _associate_accidentals(
        self,
        staff: Staff,
        notes: list[RawNote],
        accidentals: Iterable[RawAccidental],
    ) -> dict[str, Accidental]:
        result: dict[str, Accidental] = {}
        for accidental in accidentals:
            candidates = [
                note
                for note in notes
                if 0 < note.bbox.x0 - accidental.bbox.x1 <= staff.spacing * 3
                and abs(note.y - accidental.bbox.center_y) <= staff.spacing * 0.85
            ]
            if not candidates:
                continue
            # An accidental and its notehead are a single visual unit. Do not
            # require the preliminary measure detector to put them on the same
            # side of a boundary: long chord stems can resemble barlines and
            # otherwise split a sharp from the note immediately to its right.
            note = min(
                candidates,
                key=lambda candidate: (
                    candidate.bbox.x0
                    - accidental.bbox.x1
                    + 0.35 * abs(candidate.y - accidental.bbox.center_y)
                ),
            )
            result[note.id] = accidental.accidental
        return result

    def _apply_state(
        self,
        notes: list[RawNote],
        explicit: dict[str, Accidental],
        key_signature: dict[str, Accidental],
    ) -> list[AnnotatedNote]:
        result: list[AnnotatedNote] = []
        state: dict[tuple[str, int], Accidental] = {}
        current_measure: int | None = None

        for note in sorted(notes, key=lambda item: (item.measure, item.x, item.y)):
            if note.measure != current_measure:
                state = {}
                current_measure = note.measure

            pitch = (note.letter, note.octave)
            if note.id in explicit:
                effective = explicit[note.id]
                source = AccidentalSource.EXPLICIT
                state[pitch] = effective
            elif pitch in state:
                effective = state[pitch]
                source = AccidentalSource.CARRIED
            elif note.letter in key_signature:
                effective = key_signature[note.letter]
                source = AccidentalSource.KEY_SIGNATURE
            else:
                effective = None
                source = None

            result.append(
                AnnotatedNote(
                    note=note,
                    effective_accidental=effective,
                    source=source,
                    should_mark=self._should_mark(effective, source),
                )
            )
        return result

    def _should_mark(
        self,
        accidental: Accidental | None,
        source: AccidentalSource | None,
    ) -> bool:
        if accidental not in {Accidental.FLAT, Accidental.SHARP}:
            return False
        if (
            source is AccidentalSource.KEY_SIGNATURE
            and not self.options.include_key_signature
        ):
            return False
        if self.options.mode is AnnotationMode.SHARP_ONLY:
            return accidental is Accidental.SHARP
        if self.options.mode is AnnotationMode.FLAT_ONLY:
            return accidental is Accidental.FLAT
        return True
