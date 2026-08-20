# piassist web

GitHub Pages向けの静的UIです。PDFとPython処理はPyodide / WebAssemblyによりブラウザ内で動作します。

ローカル確認用のアセットを準備します。

```sh
mkdir -p web/assets
uv build --wheel --out-dir web/assets
uv run python -m http.server 8000 --directory web
```

その後、`http://localhost:8000` を開きます。初回処理時はPyodideとPyMuPDFを取得するため、インターネット接続が必要です。
