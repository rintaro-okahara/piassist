# PDF fixtures

公開可能と確認したPDFだけを、fixtureごとのディレクトリにまとめます。由来と評価結果は各ディレクトリの `manifest.json` を正とし、テストがPDFのハッシュ、構造、実測精度との一致を検証します。

## `autumn_leaves/`

- `input.pdf`: MuseScoreが出力した、赤丸なしの入力PDF
- `expected_annotated.pdf`: 正解の赤丸を含むgolden output
- `manifest.json`: 生成元、PDFメタデータ、ハッシュ、正解数、評価条件、実測値

精度は赤いベクター楕円の中心をページ単位で一対一照合して算出します。PDFバイナリ全体の出力比較は、PDFライターのバージョンによる直列化差を避けるため行いません。
