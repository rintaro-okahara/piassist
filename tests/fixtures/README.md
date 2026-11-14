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
