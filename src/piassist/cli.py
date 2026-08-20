from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from piassist.models import Clef
from piassist.music_logic import (
    AnnotationMode,
    AnnotationOptions,
    MusicAnalyzer,
    parse_key_signature,
)
from piassist.render import OutputExistsError, PDFRenderer, parse_hex_color
from piassist.vector_pdf import UnsupportedVectorPdfError, VectorPDFParser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="piassist",
        description="ベクター楽譜PDFの♯/♭音に印を付けます。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    annotate = subparsers.add_parser(
        "annotate", help="楽譜を解析して対象音符に丸を描画"
    )
    annotate.add_argument("input", type=Path, help="入力PDF")
    annotate.add_argument("--out", "-o", type=Path, help="出力PDF")
    annotate.add_argument(
        "--mode",
        choices=[mode.value for mode in AnnotationMode],
        default=AnnotationMode.SHARP_FLAT.value,
        help="印を付ける臨時記号の種類",
    )
    annotate.add_argument(
        "--key-signature",
        metavar="NOTES",
        help="自動検出を上書き（例: Bb,Eb / F#,C# / none）",
    )
    annotate.add_argument(
        "--include-key-signature",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="調号由来の♯/♭音も対象にする（既定: 有効）",
    )
    annotate.add_argument(
        "--clef",
        choices=["auto", Clef.TREBLE.value, Clef.BASS.value],
        default="auto",
        help="clefグリフが読めない場合の既定音部記号",
    )
    annotate.add_argument("--color", default="#ff0000", help="丸の色（#RRGGBB）")
    annotate.add_argument("--line-width", type=float, default=1.0, help="丸の線幅")
    annotate.add_argument("--debug-json", type=Path, help="解析結果JSON")
    annotate.add_argument("--debug-pdf", type=Path, help="検出位置の可視化PDF")
    annotate.add_argument("--overwrite", action="store_true", help="既存の出力を上書き")

    inspect = subparsers.add_parser("inspect", help="PDF内のグリフと五線検出結果を調査")
    inspect.add_argument("input", type=Path, help="入力PDF")
    inspect.add_argument("--out", "-o", type=Path, help="JSON出力先")
    return parser


def run_annotate(args: argparse.Namespace) -> int:
    input_path: Path = args.input
    if not input_path.is_file():
        raise FileNotFoundError(f"入力PDF `{input_path}` が見つかりません。")
    output_path = args.out or input_path.with_name(f"{input_path.stem}-annotated.pdf")
    output_paths = [
        path for path in (output_path, args.debug_json, args.debug_pdf) if path
    ]
    resolved_outputs = [path.resolve() for path in output_paths]
    if input_path.resolve() in resolved_outputs:
        raise ValueError("入力ファイルと出力ファイルには別のパスを指定してください。")
    if len(resolved_outputs) != len(set(resolved_outputs)):
        raise ValueError(
            "出力PDF・デバッグJSON・デバッグPDFは別々のパスにしてください。"
        )
    if not args.overwrite:
        existing = next((path for path in output_paths if path.exists()), None)
        if existing:
            raise OutputExistsError(
                f"出力先 `{existing}` は既に存在します。"
                "上書きするには --overwrite を指定してください。"
            )
    if args.line_width <= 0:
        raise ValueError("--line-width には0より大きい値を指定してください。")

    default_clef = None if args.clef == "auto" else Clef(args.clef)
    key_signature = (
        parse_key_signature(args.key_signature)
        if args.key_signature is not None
        else None
    )
    options = AnnotationOptions(
        mode=AnnotationMode(args.mode),
        include_key_signature=args.include_key_signature,
        key_signature=key_signature,
    )
    score = VectorPDFParser(default_clef=default_clef).parse(input_path)
    score = MusicAnalyzer(options).analyze(score)
    renderer = PDFRenderer(
        color=parse_hex_color(args.color), line_width=args.line_width
    )
    marked = renderer.render(input_path, output_path, score, overwrite=args.overwrite)

    if args.debug_json:
        args.debug_json.parent.mkdir(parents=True, exist_ok=True)
        args.debug_json.write_text(
            json.dumps(score.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.debug_pdf:
        renderer.render_debug(
            input_path, args.debug_pdf, score, overwrite=args.overwrite
        )

    print(
        f"{output_path} に {marked} 個の音符をマークしました "
        f"(検出音符: {len(score.notes)})。"
    )
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        raise FileNotFoundError(f"入力PDF `{args.input}` が見つかりません。")
    result = VectorPDFParser().inspect(args.input)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
        print(f"解析情報を {args.out} に保存しました。")
    else:
        print(serialized, end="")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "annotate":
            return run_annotate(args)
        return run_inspect(args)
    except (
        FileNotFoundError,
        OSError,
        UnsupportedVectorPdfError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
