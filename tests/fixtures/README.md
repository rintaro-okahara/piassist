# PDF fixtures

PDFはリポジトリへコミットせず、各開発環境だけに保存します。以下の2ファイルをこのディレクトリへ配置すると、golden回帰テストが自動的に有効になります。ファイルがない環境では該当テストのみskipされます。

## Autumn Leaves pair

### `autumn_leaves_input.pdf`

MuseScoreが出力した赤丸なしの入力PDFです。

- SHA-256: `d9eb99a774edb1bd0f3dc4bd3119146ccccf2b0263a8f505a8a0eb6fcb957ecb`
- Pages: 11
- Red circles: 0
- Score font: Leland (SMuFL)
- Source application: MuseScore

### `autumn_leaves_expected_annotated.pdf`

MuseScoreが出力したベクター楽譜に、期待する♯・♭音の赤丸が描画済みの参照PDFです。入力ではなく期待結果（golden output）として扱います。

- SHA-256: `8cd3ec83f26da957ededd9d9abde208975a18f760371cdc022f7ba084d882a0d`
- Pages: 11
- Red circles by page: `66, 58, 67, 84, 83, 83, 41, 68, 84, 56, 6`
- Total red circles: 696
- Score font: Leland (SMuFL)
- Source application: MuseScore

現在の座標照合ベースライン（許容誤差1.5pt、調号B♭/E♭を明示）:

- Matched circles: 687
- Predicted circles: 697
- Precision: 98.6%
- Recall: 98.7%

回帰テストでは、入力PDFをPiassistで実際に処理し、生成PDFと参照PDFから赤いベクター楕円の中心座標とサイズを抽出して照合します。

PDFのバイナリ全体は比較しません。PDFライターのバージョンによって、内容が同じでも直列化結果が変化するためです。
