"""improve.py — 元画像の情報が少ない場合の改善機構（アップデート版）

現行の autofix は「真っ白/真っ黒/単色/低情報」を検出して**動画から別フレームを再抽出**する。
本モジュールはそれを補完し、静止画のまま救える「眠い・暗い・白飛び」を画像補正で底上げする。

判定:
  broken   … ほぼ単色（std極小）。静止画からは復元不可 → 動画再抽出が必要（autofix系へ）。
  low_info … 眠い/暗い/白飛び。オートコントラスト＋暗部持ち上げ等で改善可。
  ok       … そのまま。

  python3 improve.py <in.jpg> <out.jpg>   # 単体テスト
"""
from __future__ import annotations

from PIL import Image, ImageOps, ImageEnhance
import numpy as np

# しきい値（feed_qa/ frame_quality と整合。実運用で微調整）
BROKEN_STD = 18.0    # これ未満はほぼ単色（破損相当）
DULL_STD = 42.0      # これ未満は「眠い/コントラスト不足」
DARK_MEAN = 62.0     # これ未満は暗すぎ
WASH_MEAN = 205.0    # これ超は白飛び


def assess(im: Image.Image) -> dict:
    """明るさ平均/標準偏差から情報量を判定する。"""
    g = np.asarray(im.convert("L"), dtype=np.float32)
    mean, std = float(g.mean()), float(g.std())
    if std < BROKEN_STD:
        v = "broken"
    elif std < DULL_STD or mean < DARK_MEAN or mean > WASH_MEAN:
        v = "low_info"
    else:
        v = "ok"
    return {"verdict": v, "mean": round(mean, 1), "std": round(std, 1)}


def improve(im: Image.Image, a: dict | None = None) -> tuple[Image.Image, str]:
    """低情報画像を可能な範囲で改善する。戻り値 (改善後画像, action)。

    action: none / enhanced / needs_reextract
    """
    im = im.convert("RGB")
    a = a or assess(im)
    v = a["verdict"]
    if v == "ok":
        return im, "none"
    if v == "broken":
        # 単色に近く静止画からは情報を復元できない → 動画から再抽出（autofix系）に委ねる
        return im, "needs_reextract"

    # low_info: まずオートコントラストで階調を復元
    out = ImageOps.autocontrast(im, cutoff=1)
    if a["mean"] < DARK_MEAN:                       # 暗い → 明るさ＋コントラストを持ち上げ
        out = ImageEnhance.Brightness(out).enhance(1.18)
        out = ImageEnhance.Contrast(out).enhance(1.08)
    elif a["mean"] > WASH_MEAN:                     # 白飛び → コントラストを締める
        out = ImageEnhance.Contrast(out).enhance(1.12)
    out = ImageEnhance.Color(out).enhance(1.05)     # わずかに彩度を補う
    return out, "enhanced"


def improve_bytes(data: bytes) -> tuple[Image.Image, dict, str]:
    """画像バイト列から (改善後画像, assessment, action) を返す。"""
    import io
    im = Image.open(io.BytesIO(data))
    a = assess(im)
    out, action = improve(im, a)
    return out, a, action


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    with Image.open(src) as im:
        a = assess(im)
        out, action = improve(im, a)
    out.save(dst, "JPEG", quality=90)
    print(f"{src}: {a} -> {action} -> {dst}")
