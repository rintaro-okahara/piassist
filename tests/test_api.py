from pathlib import Path

import pytest

from piassist.api import annotate_pdf_file

FIXTURE = Path(__file__).parent / "fixtures" / "autumn_leaves" / "input.pdf"
pytestmark = pytest.mark.skipif(
    not FIXTURE.is_file(),
    reason="Autumn Leaves fixture is not installed",
)


def test_browser_facing_api_annotates_fixture(tmp_path: Path) -> None:
    output = tmp_path / "autumn-leaves-annotated.pdf"

    result = annotate_pdf_file(
        FIXTURE,
        output,
        key_signature="Bb,Eb",
    )

    assert output.is_file()
    assert result == {
        "pages": 11,
        "staffs": 103,
        "notes": 2_041,
        "marked_notes": 697,
        "output_name": "autumn-leaves-annotated.pdf",
    }
