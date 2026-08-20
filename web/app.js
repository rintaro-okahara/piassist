const fileInput = document.querySelector("#fileInput");
const dropZone = document.querySelector("#dropZone");
const selectButton = document.querySelector("#selectButton");
const clearButton = document.querySelector("#clearButton");
const removeButton = document.querySelector("#removeButton");
const filePanel = document.querySelector("#filePanel");
const fileName = document.querySelector("#fileName");
const fileMeta = document.querySelector("#fileMeta");
const fileState = document.querySelector("#fileState");
const keySignature = document.querySelector("#keySignature");
const customKeyField = document.querySelector("#customKeyField");
const customKey = document.querySelector("#customKey");
const markColor = document.querySelector("#markColor");
const colorValue = document.querySelector("#colorValue");
const includeKeySignature = document.querySelector("#includeKeySignature");
const convertButton = document.querySelector("#convertButton");
const downloadButton = document.querySelector("#downloadButton");
const progressWrap = document.querySelector("#progressWrap");
const progressText = document.querySelector("#progressText");
const progressValue = document.querySelector("#progressValue");
const progressBar = document.querySelector("#progressBar");
const statusMessage = document.querySelector("#statusMessage");

let selectedFile = null;
let worker = null;
let resultUrl = null;
let processingFileName = null;

const MAX_FILE_SIZE = 50 * 1024 * 1024;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function outputName(name) {
  const stem = name.replace(/\.pdf$/i, "");
  return `${stem || "score"}-piassist.pdf`;
}

function setStatus(message = "", isError = false) {
  statusMessage.textContent = message;
  statusMessage.classList.toggle("is-error", isError);
}

function revokeResult() {
  if (resultUrl) URL.revokeObjectURL(resultUrl);
  resultUrl = null;
  downloadButton.hidden = true;
  downloadButton.removeAttribute("href");
}

function resetProgress() {
  progressWrap.hidden = true;
  progressBar.style.width = "0%";
  progressValue.textContent = "0%";
}

function updateProgress(value, message) {
  const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
  progressWrap.hidden = false;
  progressBar.style.width = `${safeValue}%`;
  progressValue.textContent = `${safeValue}%`;
  progressText.textContent = message;
}

function setSelectedFile(file) {
  if (!file) return;
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) {
    setStatus("PDFファイルを選択してください。", true);
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    setStatus("50MB以下のPDFを選択してください。", true);
    return;
  }

  selectedFile = file;
  revokeResult();
  resetProgress();
  setStatus();
  fileName.textContent = file.name;
  fileMeta.textContent = `PDF ・ ${formatBytes(file.size)}`;
  fileState.textContent = "準備完了";
  filePanel.hidden = false;
  dropZone.hidden = true;
  clearButton.disabled = false;
  convertButton.disabled = false;
}

function clearSelection() {
  selectedFile = null;
  fileInput.value = "";
  revokeResult();
  resetProgress();
  setStatus();
  filePanel.hidden = true;
  dropZone.hidden = false;
  clearButton.disabled = true;
  convertButton.disabled = true;
  convertButton.hidden = false;
  convertButton.classList.remove("is-secondary");
  convertButton.querySelector("span:first-child").textContent = "丸印付きPDFを作る";
  fileState.textContent = "準備完了";
}

function openPicker(event) {
  event.stopPropagation();
  fileInput.click();
}

selectButton.addEventListener("click", openPicker);
dropZone.addEventListener("click", (event) => {
  if (!event.target.closest("button")) fileInput.click();
});
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => setSelectedFile(fileInput.files[0]));

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  });
}
dropZone.addEventListener("drop", (event) => setSelectedFile(event.dataTransfer.files[0]));

clearButton.addEventListener("click", clearSelection);
removeButton.addEventListener("click", clearSelection);

keySignature.addEventListener("change", () => {
  customKeyField.hidden = keySignature.value !== "custom";
  if (keySignature.value === "custom") customKey.focus();
});

markColor.addEventListener("input", () => {
  colorValue.textContent = markColor.value.toUpperCase();
});

function currentOptions() {
  const keyValue = keySignature.value;
  return {
    mode: document.querySelector('input[name="mode"]:checked').value,
    key_signature: keyValue === "auto" ? null : keyValue === "custom" ? customKey.value.trim() : keyValue,
    include_key_signature: includeKeySignature.checked,
    color: markColor.value,
  };
}

function ensureWorker() {
  if (worker) return worker;
  worker = new Worker("./pdf-worker.js");
  worker.addEventListener("message", handleWorkerMessage);
  worker.addEventListener("error", (event) => finishWithError(event.message || "処理エンジンを起動できませんでした。"));
  return worker;
}

function finishWithError(message) {
  convertButton.disabled = false;
  clearButton.disabled = false;
  removeButton.disabled = false;
  fileState.textContent = "エラー";
  resetProgress();
  setStatus(message, true);
}

function handleWorkerMessage(event) {
  const message = event.data;
  if (message.type === "progress") {
    updateProgress(message.value, message.message);
    fileState.textContent = "処理中";
    return;
  }
  if (message.type === "error") {
    finishWithError(message.message);
    return;
  }
  if (message.type !== "complete") return;

  const blob = new Blob([message.pdf], { type: "application/pdf" });
  resultUrl = URL.createObjectURL(blob);
  downloadButton.href = resultUrl;
  downloadButton.download = outputName(processingFileName || "score.pdf");
  downloadButton.hidden = false;
  convertButton.hidden = false;
  convertButton.disabled = false;
  convertButton.classList.add("is-secondary");
  convertButton.querySelector("span:first-child").textContent = "設定を変えてもう一度作る";
  clearButton.disabled = false;
  removeButton.disabled = false;
  fileState.textContent = "完成";
  updateProgress(100, "丸印付きPDFが完成しました");
  setStatus(`${message.summary.marked_notes.toLocaleString()}個の音符に丸印を付けました。`);
}

convertButton.addEventListener("click", async () => {
  if (!selectedFile) return;
  const options = currentOptions();
  if (keySignature.value === "custom" && !options.key_signature) {
    setStatus("調号を入力してください。例: Bb,Eb,Ab", true);
    customKey.focus();
    return;
  }

  revokeResult();
  setStatus();
  processingFileName = selectedFile.name;
  convertButton.disabled = true;
  convertButton.classList.remove("is-secondary");
  convertButton.querySelector("span:first-child").textContent = "丸印付きPDFを作る";
  clearButton.disabled = true;
  removeButton.disabled = true;
  fileState.textContent = "処理中";
  updateProgress(3, "PDFを読み込んでいます");
  try {
    const buffer = await selectedFile.arrayBuffer();
    ensureWorker().postMessage({ type: "annotate", pdf: buffer, options }, [buffer]);
  } catch (error) {
    finishWithError(error.message || "PDFを読み込めませんでした。");
  }
});

downloadButton.addEventListener("click", () => {
  setStatus("ダウンロードを開始しました。別の設定でもう一度作成できます。");
});

window.addEventListener("beforeunload", revokeResult);
