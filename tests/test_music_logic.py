import pytest

from piassist.models import (
    Accidental,
    AccidentalSource,
    BBox,
    Clef,
    PageAnalysis,
    RawAccidental,
    RawNote,
    ScoreAnalysis,
    Staff,
)
from piassist.music_logic import (
    AnnotationMode,
    AnnotationOptions,
    MusicAnalyzer,
    parse_key_signature,
)


def note(identifier: str, x: float, measure: int) -> RawNote:
    return RawNote(
        id=identifier,
        page=0,
        staff=0,
        bbox=BBox(x - 3, 27, x + 3, 33),
        letter="B",
        octave=4,
        measure=measure,
    )


def test_key_signature_natural_and_measure_reset() -> None:
    staff = Staff(
        page=0,
        index=0,
        line_ys=(10, 20, 30, 40, 50),
        x0=10,
        x1=190,
        clef=Clef.TREBLE,
        barlines=[150],
    )
    notes = [
        note("n1", 100, 0),
        note("n2", 120, 0),
        note("n3", 140, 0),
        note("n4", 170, 1),
    ]
    natural = RawAccidental(
        id="a1",
        page=0,
        staff=0,
        bbox=BBox(110, 27, 114, 33),
        accidental=Accidental.NATURAL,
        letter="B",
        octave=4,
    )
    score = ScoreAnalysis(
        pages=[
            PageAnalysis(
                page=0,
                staffs=[staff],
                notes=notes,
                accidentals=[natural],
            )
        ]
    )
    options = AnnotationOptions(key_signature={"B": Accidental.FLAT})

    result = MusicAnalyzer(options).analyze(score)

    assert [item.effective_accidental for item in result.notes] == [
        Accidental.FLAT,
        Accidental.NATURAL,
        Accidental.NATURAL,
        Accidental.FLAT,
    ]
    assert [item.source for item in result.notes] == [
        AccidentalSource.KEY_SIGNATURE,
        AccidentalSource.EXPLICIT,
        AccidentalSource.CARRIED,
        AccidentalSource.KEY_SIGNATURE,
    ]
    assert [item.should_mark for item in result.notes] == [True, False, False, True]


def test_mode_and_key_signature_filter() -> None:
    analyzer = MusicAnalyzer(
        AnnotationOptions(
            mode=AnnotationMode.FLAT_ONLY,
            include_key_signature=False,
        )
    )

    assert not analyzer._should_mark(  # noqa: SLF001
        Accidental.FLAT, AccidentalSource.KEY_SIGNATURE
    )
    assert analyzer._should_mark(  # noqa: SLF001
        Accidental.FLAT, AccidentalSource.EXPLICIT
    )
    assert not analyzer._should_mark(  # noqa: SLF001
        Accidental.SHARP, AccidentalSource.EXPLICIT
    )


def test_accidental_association_ignores_spurious_measure_boundary() -> None:
    staff = Staff(
        page=0,
        index=0,
        line_ys=(10, 20, 30, 40, 50),
        x0=10,
        x1=190,
        clef=Clef.BASS,
        barlines=[101],
    )
    sharp = RawAccidental(
        id="sharp",
        page=0,
        staff=0,
        bbox=BBox(94, 47, 99, 53),
        accidental=Accidental.SHARP,
        letter="F",
        octave=3,
    )
    target = RawNote(
        id="f-sharp",
        page=0,
        staff=0,
        bbox=BBox(102, 47, 108, 53),
        letter="F",
        octave=3,
        measure=1,
    )

    associated = MusicAnalyzer()._associate_accidentals(  # noqa: SLF001
        staff, [target], [sharp]
    )

    assert associated == {"f-sharp": Accidental.SHARP}


def test_parse_key_signature() -> None:
    assert parse_key_signature("Bb, Eb") == {
        "B": Accidental.FLAT,
        "E": Accidental.FLAT,
    }
    assert parse_key_signature("F#,C#") == {
        "F": Accidental.SHARP,
        "C": Accidental.SHARP,
    }
    assert parse_key_signature("none") == {}


def test_parse_key_signature_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="不正な調号"):
        parse_key_signature("H#")
