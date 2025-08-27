# staff_detect_viz.py
# 五線検出 + 可視化（ピーク点・5本セット帯・段番号）
# 使い方:  poetry run python staff_detect_viz.py --img images/-01.png

import argparse
import cv2
import numpy as np
from pathlib import Path
import sys
import json


def load_gray(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"画像が読み込めません: {path}")
    return img


def binarize(img: np.ndarray) -> np.ndarray:
    h, w = img.shape
    block = max(31, ((w // 80) * 2 + 1))  # 奇数
    bw = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block, 15
    )
    return bw


def deskew(bw: np.ndarray) -> np.ndarray:
    h, w = bw.shape
    edges = cv2.Canny(bw, 80, 160)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi/1800,
        threshold=max(120, w//8),
        minLineLength=int(w*0.6), maxLineGap=10
    )
    angle = 0.0
    if lines is not None and len(lines) > 4:
        angs = []
        for x1, y1, x2, y2 in lines[:, 0, :]:
            dx, dy = x2 - x1, y2 - y1
            if dx == 0:
                continue
            a = np.degrees(np.arctan2(dy, dx))
            if abs(a) < 10:
                angs.append(a)
        if angs:
            angle = float(np.median(angs))
    if abs(angle) > 0.2:
        M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
        bw = cv2.warpAffine(bw, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    return bw


def suppress_vertical(bw: np.ndarray) -> np.ndarray:
    h, _ = bw.shape
    vert = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, h//80)))
    )
    bw_masked = cv2.subtract(bw, vert)
    return bw_masked


def emphasize_horizontal(bw_masked: np.ndarray) -> np.ndarray:
    h, w = bw_masked.shape
    hor_k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w//24), 1))
    horiz = cv2.morphologyEx(bw_masked, cv2.MORPH_OPEN, hor_k, iterations=1)
    return horiz


def projection_1d(img_bin: np.ndarray) -> np.ndarray:
    proj = img_bin.sum(axis=1).astype(np.float32)
    k = cv2.getGaussianKernel(9, 1.2).ravel()
    k = k / (k.sum() + 1e-6)  # 念のため正規化
    proj = np.convolve(proj, k, mode="same")
    return proj


def estimate_spacing_and_groups(proj: np.ndarray, h: int):
    # 自己相関で線間隔の目安
    ac = np.correlate(proj - proj.mean(), proj - proj.mean(), mode="full")
    mid = len(ac) // 2
    d_guess = int(np.argmax(ac[mid+5:mid+80]) + 5) if len(ac) > 160 else 6
    d_guess = max(6, d_guess)
    win = max(3, d_guess // 2)

    def extract_groups(thr_pct: int):
        peaks = []
        thr = np.percentile(proj, thr_pct)
        for y in range(win, h - win):
            local = proj[y - win:y + win + 1]
            if proj[y] >= local.max() and proj[y] > thr:
                if peaks and y - peaks[-1] < win:
                    continue  # 近接ピークは統合
                peaks.append(y)

        # スペーシングの許容幅はd_guessに比例
        tol = max(2, int(d_guess * 0.35))
        groups, cur = [], []
        for y in peaks:
            if not cur:
                cur = [y]
                continue
            if abs((y - cur[-1]) - d_guess) <= tol:
                cur.append(y)
                if len(cur) == 5:
                    groups.append(cur)
                    cur = []
            else:
                cur = [y]
        return groups, peaks

    # しきい値は結果が最も多く安定するやつを選ぶ
    best = dict(groups=[], peaks=[], thr=None, score=-1)
    for p in range(60, 91, 5):  # 60..90%
        groups, peaks = extract_groups(p)
        if not groups:
            continue
        # スコア: グループ数 + スペーシングのばらつきに対するペナルティ
        spacings = []
        for g in groups:
            gs = np.diff(g)
            if len(gs) > 0:
                spacings.extend(gs.tolist())
        if spacings:
            var = np.var(spacings)
            score = len(groups) - 0.01 * var
        else:
            score = len(groups)
        if score > best["score"]:
            best = dict(groups=groups, peaks=peaks, thr=p, score=score)

    return d_guess, best["thr"], best["groups"], best["peaks"]


def draw_translucent_rect(img_bgr: np.ndarray, x1, y1, x2, y2, color=(0,255,255), alpha=0.25):
    """半透明矩形を重ねる"""
    overlay = img_bgr.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    return cv2.addWeighted(overlay, alpha, img_bgr, 1 - alpha, 0)


def visualize(img_gray: np.ndarray, groups, peaks, proj, d_guess: int, outdir: Path,
              draw_peak_bars: bool = False):
    outdir.mkdir(parents=True, exist_ok=True)
    h, w = img_gray.shape

    # ベース画像
    vis = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)

    # 5本セットの帯（上下に 0.6*d_guess ずつ余白）
    for idx, g in enumerate(groups):
        top = max(0, int(min(g) - 0.6 * d_guess))
        bot = min(h-1, int(max(g) + 0.6 * d_guess))
        vis = draw_translucent_rect(vis, 0, top, w, bot, color=(0,255,255), alpha=0.20)
        # 段番号
        cv2.putText(vis, f"staff {idx}", (10, max(15, top+15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,128,255), 2, cv2.LINE_AA)

    # 採用した五線（赤線）
    for g in groups:
        for y in g:
            cv2.line(vis, (0, y), (w, y), (0, 0, 255), 1)

    # ピーク候補（緑点 or 横バー）
    for y in peaks:
        if draw_peak_bars:
            x0 = int(w * 0.85)
            cv2.line(vis, (x0, y), (w, y), (0,255,0), 1)
        else:
            cv2.circle(vis, (w-10, y), 3, (0, 255, 0), -1)

    # 保存
    cv2.imwrite(str(outdir / "staff_detect_vis.png"), vis)

    # 投影の可視化（縦棒グラフ風）
    proj_vis = (proj / (proj.max() + 1e-6) * 255).astype(np.uint8)
    proj_vis = np.repeat(proj_vis.reshape(-1, 1), 240, axis=1)
    cv2.imwrite(str(outdir / "debug_projection.png"), proj_vis)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", type=str, default="images/-01.png", help="入力画像パス（PNG/JPG）")
    ap.add_argument("--out", type=str, default="out", help="出力フォルダ")
    ap.add_argument("--peak-bars", action="store_true", help="ピークを横バーで描画（デバッグ用）")
    ap.add_argument("--json", action="store_true", help="検出結果のJSONをstdoutに出力")
    args = ap.parse_args()

    outdir = Path(args.out)
    # ★ 先に作成（旧コードの保存エラー原因）
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        img = load_gray(args.img)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    h, w = img.shape

    bw = binarize(img);                         cv2.imwrite(str(outdir / "debug_bw.png"), bw)
    bw = deskew(bw);                            cv2.imwrite(str(outdir / "debug_bw_deskew.png"), bw)
    bw_masked = suppress_vertical(bw);          cv2.imwrite(str(outdir / "debug_bw_masked.png"), bw_masked)
    horiz = emphasize_horizontal(bw_masked);    cv2.imwrite(str(outdir / "debug_horiz.png"), horiz)

    proj = projection_1d(horiz)
    d_guess, thr_pct, groups, peaks = estimate_spacing_and_groups(proj, h)

    visualize(img, groups, peaks, proj, d_guess, outdir, draw_peak_bars=args.peak-bars if hasattr(args, "peak-bars") else False)

    # 結果ログ
    print(f"found {len(groups)} staffs, spacing≈{d_guess}px, auto_threshold={thr_pct}")
    if not groups:
        print("ヒント: --img の解像度を上げる（dpi 350–400 相当で作成）/ 縦線が強い場合は suppress_vertical のカーネルを少し大きく")

    # JSON出力（他工程と連携したい場合に便利）
    if args.json:
        result = {
            "spacing_px": int(d_guess),
            "threshold_percentile": int(thr_pct) if thr_pct is not None else None,
            "groups": groups,   # [[y1,...,y5], ...]
            "peaks": peaks      # [y,...]
        }
        print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
