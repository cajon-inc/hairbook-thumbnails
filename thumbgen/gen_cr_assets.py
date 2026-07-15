"""gen_cr_assets.py — 広告CRデザイン方向 比較資料用のモックアップ生成。

出力: samples/cr/
  01_top_band.jpg 〜 06_editorial.jpg   主素材に6レイアウト
  rec_light/plain/busy.jpg              本命(bottom_scrim)を異なる背景で（ロバスト性）
  scrim_badge.jpg                       本命＋特典バッジ（訴求強化の例）
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image
import overlays

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = ROOT / "samples" / "cr"

PRIMARY = REPO / "2de4ad5837e1.jpg"       # 女性・上下クリーン（主素材）
BASES = {                                  # ロバスト性: 背景違い
    "light": REPO / "2de4ad5837e1.jpg",    # 明るい・淡色
    "plain": REPO / "daa785a23454.jpg",    # 男性・無地
    "busy":  REPO / "baad0904b5db.jpg",    # 暗め・情報多め
}
SALON, AREA = "hair salon Lumière", "東京都渋谷区・表参道駅 徒歩3分"

ORDER = ["top_band", "bottom_scrim", "lower_third", "frosted_bar", "corner_tag", "editorial"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, key in enumerate(ORDER, 1):
        with Image.open(PRIMARY) as im:
            overlays.render(im, key, SALON, AREA).save(OUT / f"{i:02d}_{key}.jpg", "JPEG", quality=90)
    for name, path in BASES.items():
        with Image.open(path) as im:
            overlays.render(im, "bottom_scrim", SALON, AREA).save(OUT / f"rec_{name}.jpg", "JPEG", quality=90)
    with Image.open(PRIMARY) as im:
        overlays.render(im, "bottom_scrim", SALON, AREA, badge="新規20%OFF").save(OUT / "scrim_badge.jpg", "JPEG", quality=90)
    print("done:", sorted(p.name for p in OUT.glob("*.jpg")))


if __name__ == "__main__":
    main()
