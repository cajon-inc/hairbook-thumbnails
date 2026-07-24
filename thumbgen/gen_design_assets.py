"""gen_design_assets.py — 社内説明資料用のパターン・モックアップを生成する。

出力先: samples/patterns/
  A.jpg  サロン名＋エリア
  B.jpg  ＋価格帯
  C.jpg  ＋特典バッジ
  D.jpg  ＋メニュー訴求
  safearea.jpg   セーフエリア（9:16見切れ）解説図
  antipattern.jpg 焼き込みテキストの上に帯＝二重テキスト（方針1が要る理由）
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw

from band_overlay import BandSpec, SAFE_INSET_RATIO, render_band, _load_font, _FONT_CANDIDATES_BOLD, _FONT_CANDIDATES_REG

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = ROOT / "samples" / "patterns"

CLEAN = REPO / "307f62f7c2e1.jpg"   # 髪型が見える清潔な人物（デザイン検証の主素材）
DIRTY = REPO / "de0520feefc0.jpg"   # 「極上ヘッドスパ ¥4,400 志木駅徒歩2分」が焼き込み済

# デモ用の共通サロン識別（レイアウト検証用ダミー）
SALON = "hair salon Lumière"
AREA = "東京都渋谷区・表参道駅 徒歩3分"

PATTERNS = {
    "A": BandSpec(salon=SALON, area=AREA),
    "B": BandSpec(salon=SALON, area=AREA, price="カット ¥4,400〜"),
    "C": BandSpec(salon=SALON, area=AREA, badge="新規20%OFF"),
    "D": BandSpec(salon=SALON, area=AREA, menu="白髪ぼかしハイライト"),
}


def gen_patterns() -> None:
    for key, spec in PATTERNS.items():
        with Image.open(CLEAN) as im:
            render_band(im, spec).save(OUT / f"{key}.jpg", "JPEG", quality=88)
        print(f"  pattern {key}: {OUT / f'{key}.jpg'}")


def gen_safearea() -> None:
    spec = BandSpec(salon=SALON, area=AREA)
    with Image.open(CLEAN) as im:
        after = render_band(im, spec)
    W, H = after.size
    d = ImageDraw.Draw(after, "RGBA")
    inset = int(W * SAFE_INSET_RATIO)
    d.rectangle([0, 0, inset, H], fill=(220, 40, 40, 90))
    d.rectangle([W - inset, 0, W, H], fill=(220, 40, 40, 90))
    for x in (inset, W - inset):
        d.line([(x, 0), (x, H)], fill=(220, 40, 40), width=3)
    f = _load_font(_FONT_CANDIDATES_BOLD, 27)
    fc = _load_font(_FONT_CANDIDATES_REG, 25)
    d.text((14, H - 44), "← 9:16で見切れ 14.8%", font=f, fill=(240, 90, 90))
    d.text((W - inset + 12, H - 44), "見切れ →", font=f, fill=(240, 90, 90))
    d.text((inset + 22, int(H * 0.52)), "セーフエリア（文字はこの中に収める）", font=fc, fill=(255, 255, 255))
    after.save(OUT / "safearea.jpg", "JPEG", quality=88)
    print(f"  safearea: {OUT / 'safearea.jpg'}")


def gen_antipattern() -> None:
    # 既に価格・エリアが焼き込まれた素材の上に帯を載せる → 二重テキスト
    spec = BandSpec(salon="Relax Spa しき", area="埼玉県志木市・志木駅 徒歩2分", price="ヘッドスパ ¥4,400〜")
    with Image.open(DIRTY) as im:
        render_band(im, spec).save(OUT / "antipattern.jpg", "JPEG", quality=88)
    print(f"  antipattern: {OUT / 'antipattern.jpg'}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gen_patterns()
    gen_safearea()
    gen_antipattern()


if __name__ == "__main__":
    main()
