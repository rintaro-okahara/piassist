# Piassist

楽譜PDFを解析し、♯・♭が有効な音符へベクターの丸印を重ねるPython CLIです。

現在のMVPは、MuseScoreなどが出力した「五線と楽譜記号がベクター/グリフとして残っているPDF」を対象にしています。スキャンPDF向けの画像OMRは今後追加予定です。

## 対応範囲

- SMuFLの音符頭・♯・♭・♮・ト音記号・ヘ音記号を抽出
- ベクター線から五線と小節線を検出
- 五線上の位置と音部記号から音名・オクターブを推定
- 標準順序の調号を自動検出
- 小節内で臨時記号を持続し、小節線でリセット
- naturalによる♯・♭の解除
- 元PDFへ固定サイズのベクター楕円を描画
- 検出結果のデバッグPDF・JSON出力

未対応:

- スキャンPDF・写真のOMR
- tieによる小節をまたぐ臨時記号の持続
- SMuFLコードポイントを保持していない独自フォント

## セットアップ

Python 3.12以上と[uv](https://docs.astral.sh/uv/)を使用します。

```sh
uv sync
```

## 使い方

基本実行:

```sh
uv run piassist annotate score.pdf --out score-annotated.pdf
```

自動調号判定が合わないPDFでは、調号を明示できます。

```sh
uv run piassist annotate score.pdf \
  --key-signature Bb,Eb \
  --debug-json debug/score.json \
  --debug-pdf debug/score.pdf \
  --out score-annotated.pdf
```

主なオプション:

```text
--mode sharp-flat|sharp-only|flat-only
--key-signature Bb,Eb          # 自動検出を上書き
--key-signature none           # 調号なし
--no-include-key-signature     # 調号由来の音符を除外
--clef treble|bass             # clefグリフが読めないPDF用
--color '#ff0000'
--overwrite
```

リポジトリ直下の互換エントリーポイントも利用できます。

```sh
uv run python annotate_score.py score.pdf --out score-annotated.pdf
```

## PDFの調査

うまく検出できない場合は、PDF内の文字・コードポイント・フォントと五線検出数をJSONで確認します。

```sh
uv run piassist inspect score.pdf --out debug/glyphs.json
```

`recognized_symbols` が0の場合、楽譜フォントのコードポイントがSMuFLと異なる可能性があります。`glyphs` のダンプをもとに `src/piassist/vector_pdf.py` の対応表を追加できます。

## ブラウザUI

`web/` にGitHub Pages向けの静的UIがあります。Pyodide / WebAssemblyでPythonとPyMuPDFをブラウザ内で実行するため、選択したPDFは外部サーバーへ送信されません。

```sh
mkdir -p web/assets
uv build --wheel --out-dir web/assets
uv run python -m http.server 8000 --directory web
```

`http://localhost:8000` を開き、手元のPDFを選択します。GitHub Pagesへの公開は `.github/workflows/pages.yml` が行います。PDFは既定でgit対象外になり、Pagesの成果物にPDFが含まれている場合もデプロイを停止します。

## 構成

```text
src/piassist/
├── models.py       # パーサ共通の中間表現
├── vector_pdf.py   # ベクターPDF解析
├── music_logic.py  # 調号・臨時記号・小節状態
├── render.py       # PDFへの描画とデバッグ表示
└── cli.py          # annotate / inspect CLI
```

後から画像OMRパーサを追加しても、`ScoreAnalysis` 以降の音楽ロジックと描画処理は共用できます。

## テスト

```sh
uv run pytest
```

テスト内で小さなベクターPDFを生成し、五線検出から調号・臨時記号の状態管理、PDF描画までを検証します。

`tests/fixtures/` のPDFは開発環境だけに置き、gitには含めません。ローカルに赤丸なし入力と赤丸付き期待出力がある場合は、ページ構造、赤丸の中心座標、サイズを照合するgoldenテストも実行されます。現在のベースラインはprecision 98.6%、recall 98.7%です。
