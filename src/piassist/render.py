from __future__ import annotations

from pathlib import Path

import pymupdf

from piassist.models import ScoreAnalysis


class OutputExistsError(FileExistsError):
    pass


def parse_hex_color(value: str) -> tuple[float, float, float]:
    normalized = value.strip().removeprefix("#")
    if len(normalized) != 6:
        raise ValueError("色は #RRGGBB 形式で指定してください。")
    try:
        channels = tuple(
            int(normalized[index : index + 2], 16) / 255 for index in (0, 2, 4)
        )
    except ValueError as error:
        raise ValueError("色は #RRGGBB 形式で指定してください。") from error
    return channels  # type: ignore[return-value]


class PDFRenderer:
    CIRCLE_RADIUS_X_IN_STAFF_SPACES = 1.08
    CIRCLE_RADIUS_Y_IN_STAFF_SPACES = 0.86

    def __init__(
        self,
        color: tuple[float, float, float] = (1.0, 0.0, 0.0),
        line_width: float = 1.0,
    ) -> None:
        self.color = color
        self.line_width = line_width

    def render(
        self,
        input_path: str | Path,
        output_path: str | Path,
        score: ScoreAnalysis,
        *,
        overwrite: bool = False,
    ) -> int:
        input_pdf = Path(input_path)
        output_pdf = Path(output_path)
        self._prepare_output(input_pdf, output_pdf, overwrite)
        staffs = {
            (staff.page, staff.index): staff
            for page in score.pages
            for staff in page.staffs
        }
        marked = [note for note in score.notes if note.should_mark]

        with pymupdf.open(input_pdf) as document:
            for annotated in marked:
                note = annotated.note
                staff = staffs[(note.page, note.staff)]
                radius_x = staff.spacing * self.CIRCLE_RADIUS_X_IN_STAFF_SPACES
                radius_y = staff.spacing * self.CIRCLE_RADIUS_Y_IN_STAFF_SPACES
                rect = pymupdf.Rect(
                    note.x - radius_x,
                    note.y - radius_y,
                    note.x + radius_x,
                    note.y + radius_y,
                )
                document[note.page].draw_oval(
                    rect,
                    color=self.color,
                    width=self.line_width,
                    overlay=True,
                )
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            # Preserve the source PDF's embedded notation and text fonts. Deep
            # garbage collection can rewrite old Quartz font resources and
            # visibly shift chord names even though the page geometry is valid.
            document.save(output_pdf)
        return len(marked)

    def render_debug(
        self,
        input_path: str | Path,
        output_path: str | Path,
        score: ScoreAnalysis,
        *,
        overwrite: bool = False,
    ) -> None:
        input_pdf = Path(input_path)
        output_pdf = Path(output_path)
        self._prepare_output(input_pdf, output_pdf, overwrite)

        with pymupdf.open(input_pdf) as document:
            for page_analysis in score.pages:
                page = document[page_analysis.page]
                for staff in page_analysis.staffs:
                    for y in staff.line_ys:
                        page.draw_line(
                            (staff.x0, y),
                            (staff.x1, y),
                            color=(0.0, 0.65, 0.0),
                            width=0.4,
                            overlay=True,
                        )
                page_notes = [
                    note for note in score.notes if note.note.page == page_analysis.page
                ]
                for annotated in page_notes:
                    note = annotated.note
                    color = (
                        (1.0, 0.0, 0.0) if annotated.should_mark else (0.0, 0.3, 1.0)
                    )
                    page.draw_rect(
                        pymupdf.Rect(
                            note.bbox.x0,
                            note.bbox.y0,
                            note.bbox.x1,
                            note.bbox.y1,
                        ),
                        color=color,
                        width=0.5,
                        overlay=True,
                    )
                    accidental = (
                        annotated.effective_accidental.value[0]
                        if annotated.effective_accidental
                        else "-"
                    )
                    page.insert_text(
                        (note.bbox.x0, note.bbox.y0 - 1),
                        f"{note.letter}{note.octave}:{accidental}",
                        fontsize=4.5,
                        color=color,
                        overlay=True,
                    )
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            document.save(output_pdf)

    @staticmethod
    def _prepare_output(input_path: Path, output_path: Path, overwrite: bool) -> None:
        if input_path.resolve() == output_path.resolve():
            raise ValueError("入力PDFと出力PDFには別のパスを指定してください。")
        if output_path.exists():
            if not overwrite:
                raise OutputExistsError(
                    f"出力先 `{output_path}` は既に存在します。"
                    "上書きするには --overwrite を指定してください。"
                )
            output_path.unlink()
