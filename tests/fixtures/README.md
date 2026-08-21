# PDF fixtures

公開可能と確認したPDFだけを、fixtureごとのディレクトリにまとめます。由来と評価結果は各ディレクトリの `manifest.json` を正とし、テストがPDFのハッシュ、構造、実測精度との一致を検証します。

## `autumn_leaves/`

- `input.pdf`: MuseScoreが出力した、赤丸なしの入力PDF
- `expected_annotated.pdf`: 正解の赤丸を含むgolden output
- `manifest.json`: 生成元、PDFメタデータ、ハッシュ、正解数、評価条件、実測値

精度は赤いベクター楕円の中心をページ単位で一対一照合して算出します。PDFバイナリ全体の出力比較は、PDFライターのバージョンによる直列化差を避けるため行いません。

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
