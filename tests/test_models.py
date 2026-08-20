from piassist.models import Clef, Staff


def make_staff(clef: Clef) -> Staff:
    return Staff(
        page=0,
        index=0,
        line_ys=(10.0, 20.0, 30.0, 40.0, 50.0),
        x0=10.0,
        x1=190.0,
        clef=clef,
    )


def test_treble_pitch_from_staff_position() -> None:
    staff = make_staff(Clef.TREBLE)

    assert staff.pitch_at(50.0) == ("E", 4)
    assert staff.pitch_at(45.0) == ("F", 4)
    assert staff.pitch_at(10.0) == ("F", 5)


def test_bass_pitch_from_staff_position() -> None:
    staff = make_staff(Clef.BASS)

    assert staff.pitch_at(50.0) == ("G", 2)
    assert staff.pitch_at(45.0) == ("A", 2)
    assert staff.pitch_at(10.0) == ("A", 3)


def test_clef_change_applies_from_its_horizontal_position() -> None:
    staff = make_staff(Clef.TREBLE)
    staff.clef_changes = [(10.0, Clef.TREBLE), (100.0, Clef.BASS)]

    assert staff.clef_at(99.0) is Clef.TREBLE
    assert staff.clef_at(100.0) is Clef.BASS
    assert staff.pitch_at(50.0, staff.clef_at(120.0)) == ("G", 2)
