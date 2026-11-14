# PDF fixtures

公開可能と確認したPDFだけを、fixtureごとのディレクトリにまとめます。由来と検証条件は各ディレクトリの `manifest.json` に記録します。

## `aura_lee_dorico/`

- `input.pdf`: Doricoが出力したBravuraベクター楽譜
- `manifest.json`: PDFメタデータ、ハッシュ、五線・音符・記号の検出数、現行パイプラインの基準値

DoricoがPDFに保持するSMuFLのoversized音符頭 `U+F4BC`〜`U+F4BE`を検出できることを回帰テストします。手動正解注釈PDFはまだないため、注釈数は精度評価ではなく現行動作のbaselineとして記録します。

注釈PDFは次のコマンドで生成します。出力はGit管理対象外の `output/pdf/aura_lee_dorico_annotated.pdf` です。

```sh
mkdir -p output/pdf
uv run piassist annotate tests/fixtures/aura_lee_dorico/input.pdf \
  --out output/pdf/aura_lee_dorico_annotated.pdf \
  --overwrite
```

## `purcell_what_power_dorico/`

- `input.pdf`: Dorico 5.1から直接書き出されたViolino 1のベクターPDF
- `oracle.musicxml`: 同じ固定commitにある全スコアのMusicXML。`P1`を意味上の正解として使用
- `manifest.json`: 固定URL、ライセンス、ハッシュ、期待する小節・音符・マーク数
- `NOTICE.md`: CC BY-SA 4.0の帰属表示と派生元
- `REVIEW.md`: note-by-note照合と目視確認の記録

このfixtureではPDFの281音をMusicXMLと譜面順に照合します。78対象音についてfalse positive / false negativeが0であること、小節ごとの音符数、各段の対象音位置、最終PDF描画数まで自動テストします。実装が現在出している件数をそのまま正解にしたbaselineではありません。
