from __future__ import annotations

from pathlib import Path
from typing import Any

from piassist.models import Clef
from piassist.music_logic import (
    AnnotationMode,
    AnnotationOptions,
    MusicAnalyzer,
    parse_key_signature,
)
from piassist.render import PDFRenderer, parse_hex_color
from piassist.vector_pdf import VectorPDFParser


def annotate_pdf_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    mode: str = AnnotationMode.SHARP_FLAT.value,
    key_signature: str | None = None,
    include_key_signature: bool = True,
    clef: str = "auto",
    color: str = "#ff0000",
    line_width: float = 1.0,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Annotate one PDF and return a JSON-serializable summary.

    This small API is shared by non-CLI clients such as the browser/Pyodide UI.
    Paths work in both a regular filesystem and Pyodide's in-memory filesystem.
    """
    source = Path(input_path)
    destination = Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(f"入力PDF `{source}` が見つかりません。")
    if line_width <= 0:
        raise ValueError("line_width には0より大きい値を指定してください。")

    annotation_mode = AnnotationMode(mode)
    if clef not in {"auto", Clef.TREBLE.value, Clef.BASS.value}:
        raise ValueError("clef は auto / treble / bass のいずれかです。")

    default_clef = None if clef == "auto" else Clef(clef)
    parsed_key_signature = (
        parse_key_signature(key_signature) if key_signature is not None else None
    )
    score = VectorPDFParser(default_clef=default_clef).parse(source)
    score = MusicAnalyzer(
        AnnotationOptions(
            mode=annotation_mode,
            include_key_signature=include_key_signature,
            key_signature=parsed_key_signature,
        )
    ).analyze(score)
    marked = PDFRenderer(
        color=parse_hex_color(color), line_width=line_width
    ).render(source, destination, score, overwrite=overwrite)

    return {
        "pages": len(score.pages),
        "staffs": sum(len(page.staffs) for page in score.pages),
        "notes": len(score.notes),
        "marked_notes": marked,
        "output_name": destination.name,
    }
