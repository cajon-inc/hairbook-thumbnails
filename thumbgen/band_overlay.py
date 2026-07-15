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
    """帯のデザイン仕様。文言・寸法・色をここで差し替える（パターンA〜Dを表現）。

    パターン:
      A サロン名＋エリア            … salon + area
      B ＋価格帯                   … + price   (例 "カット ¥4,400〜")
      C ＋特典バッジ               … + badge   (例 "新規20%OFF")
      D ＋メニュー訴求             … + menu    (例 "白髪ぼかしハイライト")
    """
    # 表示テキスト（A=salon/area、B=price、C=badge、D=menu を足す）
    salon: str = ""
    area: str = ""
    price: str = ""
    menu: str = ""
    badge: str = ""
    # レイアウト（REF_WIDTH=1080 基準の px。実寸は width に比例スケール）
    band_height: int = 180          # 帯の最小高さ（内容が増えれば自動で伸びる）
    pad_x: int = 40                 # 帯内テキストの左パディング（セーフエリア左端からさらに内側へ）
    vpad: int = 26                  # 帯の上下パディング（自動高さ計算用）
    salon_size: int = 48            # サロン名フォント(px)・太字
    area_size: int = 28             # エリアフォント(px)
    extra_size: int = 30            # 価格/メニュー行フォント(px)
    badge_size: int = 27            # バッジ文字(px)
    line_gap: int = 10              # 行間
    # 色
    band_rgba: tuple = (20, 20, 20, 184)   # rgba(20,20,20,0.72) ≒ alpha 184
    salon_fill: tuple = (255, 255, 255)    # 白
    area_fill: tuple = (230, 230, 230)     # #E6E6E6
    price_fill: tuple = (240, 214, 145)    # 淡いゴールド（数字を目立たせる）
    menu_fill: tuple = (235, 235, 235)
    badge_bg: tuple = (203, 163, 90)       # ゴールドのピル
    badge_fg: tuple = (26, 20, 12)         # バッジ文字（濃色）
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


def _draw_pill(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: tuple) -> None:
    """角丸のピル（特典バッジ用）。"""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=fill)


# ─────────────────────────────────────────────
# 帯合成 本体
# ─────────────────────────────────────────────
def render_band(img: Image.Image, spec: BandSpec) -> Image.Image:
    """img（RGB/RGBA）に帯を合成した RGB 画像を返す。元画像は破壊しない。

    行構成: サロン名（大・太字）／エリア（ピン）／価格（B）／メニュー（D）。
    バッジ（C）はサロン名行の右端にピルで重ねる。帯高は内容に応じて自動で伸びる。
    """
    base = img.convert("RGBA")
    W, H = base.size
    scale = W / REF_WIDTH  # 基準幅からのスケール（非1080入力にも適応）

    safe_inset = int(W * SAFE_INSET_RATIO)             # 見切れる左右の幅
    text_left = safe_inset + int(spec.pad_x * scale)   # テキスト開始 x（セーフエリア内）
    text_right = W - safe_inset - int(spec.pad_x * scale)
    usable_w = max(40, text_right - text_left)
    line_gap = int(spec.line_gap * scale)
    m = ImageDraw.Draw(Image.new("RGBA", (1, 1)))      # 計測専用

    # ── 特典バッジ（C）: サロン名行の右に置くピル ──
    badge = spec.badge.strip()
    badge_font = badge_w = badge_h = None
    if badge:
        badge_font = _load_font(_FONT_CANDIDATES_BOLD, int(spec.badge_size * scale))
        bb = m.textbbox((0, 0), badge, font=badge_font)
        pill_padx, pill_pady = int(20 * scale), int(11 * scale)
        badge_w = (bb[2] - bb[0]) + 2 * pill_padx
        badge_h = (bb[3] - bb[1]) + 2 * pill_pady

    # ── サロン名（A）: バッジ幅を避けて自動フィット ──
    salon = spec.salon.strip()
    salon_usable = usable_w - (badge_w + int(24 * scale) if badge else 0)
    salon_usable = max(60, salon_usable)
    salon_font = _fit_font(m, salon, _FONT_CANDIDATES_BOLD,
                           int(spec.salon_size * scale), int(spec.salon_min_size * scale), salon_usable)
    salon = _ellipsize(m, salon, salon_font, salon_usable)

    # ── サロン名の下に積む行（エリア/価格/メニュー）──
    aps = int(spec.area_size * scale)
    pin_advance = int(aps * 0.72) + int(aps * 0.28)
    lines = []  # (text, font, fill, pin)
    if spec.area.strip():
        af = _load_font(_FONT_CANDIDATES_REG, aps)
        lines.append((_ellipsize(m, spec.area.strip(), af, usable_w - pin_advance), af, spec.area_fill, True))
    if spec.price.strip():
        pf = _load_font(_FONT_CANDIDATES_BOLD, int(spec.extra_size * scale))
        lines.append((_ellipsize(m, spec.price.strip(), pf, usable_w), pf, spec.price_fill, False))
    if spec.menu.strip():
        mf = _load_font(_FONT_CANDIDATES_REG, int(spec.extra_size * scale))
        lines.append((_ellipsize(m, spec.menu.strip(), mf, usable_w), mf, spec.menu_fill, False))

    # ── 高さ計算（内容に合わせて自動）──
    salon_h = m.textbbox((0, 0), salon, font=salon_font)[3]
    line_hs = [m.textbbox((0, 0), t or "あ", font=f)[3] for (t, f, _, _) in lines]
    block_h = salon_h + sum(line_gap + lh for lh in line_hs)
    vpad = int(spec.vpad * scale)
    band_h = max(int(spec.band_height * scale), block_h + 2 * vpad)

    # ── 帯レイヤ ──
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    if spec.style == "gradient":
        r, g, b, a = spec.band_rgba
        for yy in range(band_h):
            od.line([(0, yy), (W, yy)], fill=(r, g, b, int(a * (1 - yy / band_h) ** 0.6)))
    else:
        od.rectangle([0, 0, W, band_h], fill=spec.band_rgba)
    draw = ImageDraw.Draw(overlay)

    # ── 描画 ──
    y0 = max(vpad, (band_h - block_h) // 2)
    draw.text((text_left, y0), salon, font=salon_font, fill=spec.salon_fill)

    if badge:
        bx = text_right - badge_w
        by = y0 + (salon_h - badge_h) // 2
        _draw_pill(draw, bx, by, badge_w, badge_h, spec.badge_bg)
        bb = draw.textbbox((0, 0), badge, font=badge_font)
        draw.text((bx + (badge_w - (bb[2] - bb[0])) // 2 - bb[0],
                   by + (badge_h - (bb[3] - bb[1])) // 2 - bb[1]),
                  badge, font=badge_font, fill=spec.badge_fg)

    y = y0 + salon_h + line_gap
    for (text, font, fill, pin), lh in zip(lines, line_hs):
        if pin:
            tx = _draw_pin(draw, text_left, y, lh, fill)
            draw.text((tx, y), text, font=font, fill=fill)
        else:
            draw.text((text_left, y), text, font=font, fill=fill)
        y += lh + line_gap

    return Image.alpha_composite(base, overlay).convert("RGB")


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
