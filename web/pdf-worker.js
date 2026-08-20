const PYODIDE_INDEX = "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/";
const PYMUPDF_WHEEL = "https://files.pythonhosted.org/packages/72/f6/1e52ce243ca792254f6223b4017c5667194c146ce9b88baf37bc5eb3d1c9/pymupdf-1.28.0-cp313-abi3-pyemscripten_2025_0_wasm32.whl";
const PIASSIST_WHEEL = new URL("./assets/piassist-0.1.0-py3-none-any.whl", self.location.href).href;

let enginePromise = null;

function progress(value, message) {
  self.postMessage({ type: "progress", value, message });
}

async function loadEngine() {
  if (enginePromise) return enginePromise;
  enginePromise = (async () => {
    progress(8, "ブラウザ処理エンジンを準備しています");
    importScripts(`${PYODIDE_INDEX}pyodide.js`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX });

    progress(30, "PDF解析ライブラリを読み込んでいます（初回のみ）");
    await pyodide.loadPackage(PYMUPDF_WHEEL);

    progress(62, "piassistを読み込んでいます");
    await pyodide.loadPackage("micropip");
    pyodide.globals.set("piassist_wheel_url", PIASSIST_WHEEL);
    await pyodide.runPythonAsync(`
import micropip
await micropip.install(piassist_wheel_url, deps=False)
`);
    return pyodide;
  })();
  try {
    return await enginePromise;
  } catch (error) {
    enginePromise = null;
    throw error;
  }
}

function cleanError(error) {
  const raw = String(error?.message || error || "処理中にエラーが発生しました。");
  const lines = raw.split("\n").filter(Boolean);
  return lines.at(-1) || raw;
}

self.addEventListener("message", async (event) => {
  if (event.data?.type !== "annotate") return;
  try {
    const pyodide = await loadEngine();
    const inputPath = "/tmp/piassist-input.pdf";
    const outputPath = "/tmp/piassist-output.pdf";
    for (const path of [inputPath, outputPath]) {
      try {
        pyodide.FS.unlink(path);
      } catch (_) {
        // The in-memory file does not exist on the first run.
      }
    }
    pyodide.FS.writeFile(inputPath, new Uint8Array(event.data.pdf));
    pyodide.globals.set("annotation_options_json", JSON.stringify(event.data.options));

    progress(72, "五線と音符を解析しています");
    const summaryJson = await pyodide.runPythonAsync(`
import json
from piassist.api import annotate_pdf_file

options = json.loads(annotation_options_json)
summary = annotate_pdf_file(
    "/tmp/piassist-input.pdf",
    "/tmp/piassist-output.pdf",
    mode=options["mode"],
    key_signature=options["key_signature"],
    include_key_signature=options["include_key_signature"],
    color=options["color"],
    overwrite=True,
)
json.dumps(summary, ensure_ascii=False)
`);

    progress(96, "ダウンロード用PDFを仕上げています");
    const pdf = pyodide.FS.readFile(outputPath);
    const transferable = pdf.buffer.slice(pdf.byteOffset, pdf.byteOffset + pdf.byteLength);
    self.postMessage(
      { type: "complete", pdf: transferable, summary: JSON.parse(summaryJson) },
      [transferable],
    );
  } catch (error) {
    console.error(error);
    self.postMessage({ type: "error", message: cleanError(error) });
  }
});
