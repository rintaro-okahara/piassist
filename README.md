# Piassist

[![Tests](https://github.com/rintaro-okahara/piassist/actions/workflows/test.yml/badge.svg)](https://github.com/rintaro-okahara/piassist/actions/workflows/test.yml)

楽譜PDFを解析し、♯・♭が有効な音符へベクターの丸印を重ねるPython CLIです。

現在のMVPは、MuseScore・Dorico・Sibeliusなどが出力した「五線と楽譜記号がベクター/グリフとして残っているPDF」を対象にしています。スキャンPDF向けの画像OMRは今後追加予定です。

## 対応範囲

- SMuFL、およびSibeliusのlegacy Opus fontから音符頭・♯・♭・♮・ト音記号・ヘ音記号を抽出
- ベクター線から五線と小節線を検出
- 五線上の位置と音部記号から音名・オクターブを推定
- 標準順序の調号を自動検出
- 小節内で臨時記号を持続し、小節線でリセット
- ベクター曲線からタイを推定し、小節線をまたぐタイ先へ臨時記号を持続
- naturalによる♯・♭の解除
- 元PDFへ固定サイズのベクター楕円を描画
- 検出結果のデバッグPDF・JSON出力

未対応:

- スキャンPDF・写真のOMR
- 対応表のない独自楽譜フォント

### 検証済みのDorico出力

Dorico 5.1から直接書き出された1ページのベクターPDFを、同じ譜面のMusicXMLと全音符について照合しています。検証fixtureでは281音すべての音名・オクターブ・実効臨時記号が一致し、対象78音に対してfalse positive / false negativeともに0です。

入力、固定commitの出典、SHA-256、CC BY-SA 4.0の帰属表示、検証方法と目視レビューは[`tests/fixtures/purcell_what_power_dorico/`](tests/fixtures/purcell_what_power_dorico/)に記録しています。これは当該fixtureでの検証結果であり、別ソフトで後処理されたPDFや全Doricoバージョンへの対応を意味しません。

### 検証済みのSibelius出力

Sibelius 18.5が直接書き出したlead sheet 2件と2-part ensemble 1件、およびSibelius 8.2が直接書き出した3ページのpiano grand staffを継続テストしています。

PDSAの3譜面は合計326音についてMusicXMLと譜面順に照合し、音名・octave・実効臨時記号・マーク対象が全件一致します。Beethovenのpiano譜は69小節、18 systems、PDF上1181 notehead glyphsをsystem/staff単位でMusicXMLと照合しています。MusicXMLの1182 note要素との差は、m15の2 voicesが同じB3 noteheadを共有する1件だけです。

Sibelius固有のOpus文字encoding、文字originによる音高anchor、休符のみで始まる小節、treble/bass clef、fill+stroke形式のtie pathを検証しています。tie/slurの完全な意味分類やsystem/pageをまたぐtieは、まだ全件一致を保証しません。fixture、固定DOI、checksum、独立oracle、ライセンスは[`tests/fixtures/sibelius/`](tests/fixtures/sibelius/)に記録しています。

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

`recognized_symbols` が0の場合、楽譜フォントのコードポイントがSMuFLまたは対応済みのSibelius Opus encodingと異なる可能性があります。`glyphs` のダンプをもとに `src/piassist/vector_pdf.py` のfont-specific対応表を追加できます。

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

## ライセンス

PiassistはGNU Affero General Public License Version 3のみ（`AGPL-3.0-only`）の下で公開されています。詳細は[LICENSE](LICENSE)を参照してください。

第三者提供のテストfixtureはAGPLの対象外です。各fixtureのNOTICEと[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に記載されたライセンスが適用されます。

## テスト

```sh
uv run pytest
```

テスト内で小さなベクターPDFを生成し、五線検出から調号・臨時記号の状態管理、PDF描画までを検証します。

GitHub Actionsではlintと全テストをpull requestごとに実行します。DoricoとSibeliusの実譜テストは、PDFから得た現在値をそのまま正解にせず、同じ固定sourceにあるMusicXMLを独立oracleとして比較します。
