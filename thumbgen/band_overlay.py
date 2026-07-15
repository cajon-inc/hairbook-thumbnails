"""band_overlay.py — カタログ広告サムネへ「情報帯」を合成する（方針2のコア）

決まった文字を決まった位置に載せる定型処理なので、画像生成AIではなくコードで合成する。
サロン名・エリアは既存フィード（catalog_feed.py）のデータをそのまま使う（生成しない）。

設計の要:
  * 寸法適応 — 入力は概ね 1080x1350(4:5) だが、実データには 1080x1920(9:16) や 720x900 の
    例外が混在する。すべてのサイズ・比率で破綻しないよう、寸法から相対計算する。
  * セーフエリア — ストーリーズ/リールの 9:16 カバー表示では左右が各 14.8% 見切れる。
    文字は必ず中央約70%（左右各14.8%を避ける）に収める。切れても情報が消えない配置。
  * パターン拡張 — 第1弾は A(サロン名+エリア)。B(価格帯)/C(特典)/D(メニュー) を
    BandSpec の差し替えだけで追加できるようにする。

依存: Pillow のみ（フォントは Noto Sans CJK JP を推奨、無ければ IPAGothic 等にフォールバック）。

  python3 band_overlay.py <入力.jpg> <出力.jpg> --salon "salon名" --area "エリア"
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────
# セーフエリア定数（9:16 カバー時の見切れ）
# ─────────────────────────────────────────────
# キャンバス 4:5 の中央に見える 9:16 の幅 = H*(9/16)。1080x1350 なら 759px。
# → 左右 (1080-759)/2 = 160.5px ≒ 14.8% ずつが見切れる。
SAFE_INSET_RATIO = 0.148  # 左右それぞれ見切れる割合（セーフエリア外）
REF_WIDTH = 1080          # フォント/余白の基準幅（この幅で下の px 値になる）


@dataclass
class BandSpec:
    """帯のデザイン仕様。文言・寸法・色をここで差し替える（パターンA〜Dを表現）。"""
    # 表示テキスト
    salon: str = ""
    area: str = ""
    # レイアウト（REF_WIDTH=1080 基準の px。実寸は width に比例スケール）
    band_height: int = 180          # 帯の高さ
    pad_x: int = 40                 # 帯内テキストの左パディング（セーフエリア左端からさらに内側へ）
    salon_size: int = 48            # サロン名フォント(px)・太字
    area_size: int = 28             # エリアフォント(px)
    line_gap: int = 10              # サロン名とエリアの行間
    # 色
    band_rgba: tuple = (20, 20, 20, 184)   # rgba(20,20,20,0.72) ≒ alpha 184
    salon_fill: tuple = (255, 255, 255)    # 白
    area_fill: tuple = (230, 230, 230)     # #E6E6E6
    # 挙動
    salon_min_size: int = 30        # 収まらない時に縮める下限
    style: str = "solid"            # "solid"（仕様準拠） or "gradient"（下方向フェード）


# ─────────────────────────────────────────────
# フォント読み込み（.ttc の JP フェイスを解決）
# ─────────────────────────────────────────────
_FONT_CANDIDATES_BOLD = [
    Path(__file__).parent / "fonts" / "NotoSansJP-Bold.otf",     # 同梱があれば最優先
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"),   # 太字が無い時の最終手段
]
_FONT_CANDIDATES_REG = [
    Path(__file__).parent / "fonts" / "NotoSansJP-Regular.otf",
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"),
]


def _load_font(candidates: list[Path], size: int) -> ImageFont.FreeTypeFont:
    """候補パスを順に試す。.ttc は JP フェイスの index を探索して使う。"""
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix.lower() == ".ttc":
            # コレクション内の Noto Sans CJK JP フェイスを探す（無ければ index 0）
            for idx in range(0, 10):
                try:
                    f = ImageFont.truetype(str(path), size=size, index=idx)
                    name = " ".join(str(n) for n in f.getname())
                    if "JP" in name or idx == 0:
                        if "JP" in name:
                            return f
                        fallback = f  # index 0 を控えに
                except Exception:
                    break
            try:
                return fallback  # type: ignore[name-defined]
            except NameError:
                continue
        else:
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    raise RuntimeError("日本語フォントが見つかりません（fonts/ に NotoSansJP を同梱するか fonts-noto-cjk を導入）")


# ─────────────────────────────────────────────
# テキスト計測・自動フィット
# ─────────────────────────────────────────────
def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    return draw.textbbox((0, 0), text, font=font)[2]


def _fit_font(draw, text, candidates, start_size, min_size, max_width) -> ImageFont.FreeTypeFont:
    """max_width に収まる最大フォントを返す（min_size まで段階的に縮小）。"""
    size = start_size
    while size >= min_size:
        f = _load_font(candidates, size)
        if _text_width(draw, text, f) <= max_width:
            return f
        size -= 2
    return _load_font(candidates, min_size)


def _ellipsize(draw, text, font, max_width) -> str:
    """それでも収まらない場合は末尾を … で省略。"""
    if _text_width(draw, text, font) <= max_width:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if _text_width(draw, text[:mid] + ell, font) <= max_width:
            lo = mid + 1
        else:
            hi = mid
    return (text[: max(0, lo - 1)] + ell) if lo > 0 else ell


# ─────────────────────────────────────────────
# ピンアイコン（エリア行頭・ベクター描画で色フォント不要）
# ─────────────────────────────────────────────
def _draw_pin(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, fill: tuple) -> int:
    """左上(x,y)基準に高さ size のマップピンを描き、次のテキスト開始 x を返す。"""
    w = int(size * 0.72)
    head_r = w / 2
    cx = x + head_r
    cy = y + head_r
    # 頭（円）
    draw.ellipse([x, y, x + w, y + w], fill=fill)
    # 尖り（三角）
    draw.polygon([(x, cy), (x + w, cy), (cx, y + size)], fill=fill)
    # 中央の抜き（穴）
    hole = head_r * 0.42
    draw.ellipse([cx - hole, cy - hole, cx + hole, cy + hole], fill=(20, 20, 20))
    return x + w + int(size * 0.28)


# ─────────────────────────────────────────────
# 帯合成 本体
# ─────────────────────────────────────────────
def render_band(img: Image.Image, spec: BandSpec) -> Image.Image:
    """img（RGB/RGBA）に帯を合成した RGB 画像を返す。元画像は破壊しない。"""
    base = img.convert("RGBA")
    W, H = base.size
    scale = W / REF_WIDTH  # 基準幅からのスケール（非1080入力にも適応）

    band_h = int(spec.band_height * scale)
    safe_inset = int(W * SAFE_INSET_RATIO)          # 見切れる左右の幅
    text_left = safe_inset + int(spec.pad_x * scale)  # テキスト開始 x（セーフエリア内）
    text_right = W - safe_inset - int(spec.pad_x * scale)
    usable_w = max(10, text_right - text_left)

    # 帯レイヤ（半透明）
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    if spec.style == "gradient":
        # 上端が濃く下へフェード（ハードな下線を避けたい時のオプション）
        r, g, b, a = spec.band_rgba
        for yy in range(band_h):
            alpha = int(a * (1 - yy / band_h) ** 0.6)
            od.line([(0, yy), (W, yy)], fill=(r, g, b, alpha))
    else:
        od.rectangle([0, 0, W, band_h], fill=spec.band_rgba)

    draw = ImageDraw.Draw(overlay)

    # サロン名（太字・自動フィット）
    salon = spec.salon.strip()
    salon_font = _fit_font(draw, salon, _FONT_CANDIDATES_BOLD,
                           int(spec.salon_size * scale), int(spec.salon_min_size * scale), usable_w)
    salon = _ellipsize(draw, salon, salon_font, usable_w)

    # エリア（ピン + テキスト）。ピン幅を差し引いた残り幅に収める
    area = spec.area.strip()
    area_font = _load_font(_FONT_CANDIDATES_REG, int(spec.area_size * scale))
    pin_size = int(spec.area_size * scale)
    pin_advance = int(pin_size * 0.72) + int(pin_size * 0.28)
    area = _ellipsize(draw, area, area_font, usable_w - pin_advance)

    # 縦位置：2行ブロックを帯の中央に
    salon_h = draw.textbbox((0, 0), salon, font=salon_font)[3]
    area_h = draw.textbbox((0, 0), area or "あ", font=area_font)[3]
    line_gap = int(spec.line_gap * scale)
    block_h = salon_h + (line_gap + area_h if area else 0)
    y0 = max(int(6 * scale), (band_h - block_h) // 2)

    draw.text((text_left, y0), salon, font=salon_font, fill=spec.salon_fill)

    if area:
        ay = y0 + salon_h + line_gap
        tx = _draw_pin(draw, text_left, ay, area_h, spec.area_fill)
        draw.text((tx, ay), area, font=area_font, fill=spec.area_fill)

    out = Image.alpha_composite(base, overlay).convert("RGB")
    return out


def overlay_file(src: str, dst: str, spec: BandSpec, quality: int = 85) -> None:
    with Image.open(src) as im:
        out = render_band(im, spec)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "JPEG", quality=quality)


def _main() -> None:
    ap = argparse.ArgumentParser(description="サムネへ情報帯を合成")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--salon", required=True)
    ap.add_argument("--area", default="")
    ap.add_argument("--style", choices=["solid", "gradient"], default="solid")
    args = ap.parse_args()
    spec = BandSpec(salon=args.salon, area=args.area, style=args.style)
    overlay_file(args.src, args.dst, spec)
    print(f"OK: {args.dst}")


if __name__ == "__main__":
    _main()
