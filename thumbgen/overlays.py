"""overlays.py — 広告CR向けの複数デザイン方向（帯レイアウトのバリエーション）

band_overlay.py の「上部ソリッド帯」を基準に、より広告クリエイティブとして
見やすく・訴求力の高いレイアウトを複数実装する。全レイアウト共通で:
  * セーフエリア（中央約70%・左右各14.8%を避ける）を守る
  * 髪型（＝商品）をなるべく隠さない
  * 可読性のため必要に応じ影/スクリム/フロストで下地コントラストを確保
  * 入力寸法に相対スケール

レイアウト:
  top_band     上部ソリッド帯（基準・現行）
  bottom_scrim 下部グラデーション・スクリム（髪型優先／プレミアム）★推奨
  lower_third  ロワーサード・カード（ブランド感の出る浮きカード）
  frosted_bar  フロストガラス帯（下地をぼかす・モダン）
  corner_tag   コーナー・ミニマルタグ（最小占有・写真主役）
  editorial    エディトリアル（大タイポ＋金ヘアライン＋任意バッジ）
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from band_overlay import (
    REF_WIDTH, SAFE_INSET_RATIO,
    _load_font, _fit_font, _ellipsize, _draw_pin, _draw_pill,
    _FONT_CANDIDATES_BOLD, _FONT_CANDIDATES_REG,
)

GOLD = (206, 169, 96)
WHITE = (255, 255, 255)
LIGHT = (232, 232, 232)
DARK = (17, 15, 13)


# ─────────────────────────────────────────────
# 共通ヘルパ
# ─────────────────────────────────────────────
def _metrics(W: int):
    scale = W / REF_WIDTH
    inset = int(W * SAFE_INSET_RATIO)
    left = inset + int(40 * scale)
    right = W - inset - int(40 * scale)
    return scale, inset, left, right, max(60, right - left)


def _text_sh(draw, pos, text, font, fill, off=2, shadow=(0, 0, 0, 140)):
    """可読性のためのソフトな影付きテキスト（RGBA overlay 上で描画）。"""
    x, y = pos
    draw.text((x + off, y + off), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def _vgrad(size, y0, y1, max_a, color=DARK, gamma=1.15):
    """y0(透明)→y1(max_a) の縦グラデーションRGBAを返す（下部スクリム用）。"""
    W, H = size
    ramp = np.clip((np.arange(H) - y0) / max(1, (y1 - y0)), 0, 1) ** gamma
    a = (ramp * max_a).astype(np.uint8)
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = a[:, None]
    return Image.fromarray(arr, "RGBA")


def _pin_advance(px):
    return int(px * 0.72) + int(px * 0.28)


# ─────────────────────────────────────────────
# レイアウト実装（各 (salon, area, badge) → RGB）
# ─────────────────────────────────────────────
def top_band(im, salon, area="", badge=""):
    """基準: 上部ソリッド帯（band_overlay と同等）。"""
    from band_overlay import BandSpec, render_band
    return render_band(im, BandSpec(salon=salon, area=area, badge=badge))


def bottom_scrim(im, salon, area="", badge=""):
    base = im.convert("RGBA")
    W, H = base.size
    scale, inset, left, right, usable = _metrics(W)
    ov = _vgrad((W, H), int(H * 0.52), H, 232)
    base = Image.alpha_composite(base, ov)
    d = ImageDraw.Draw(base, "RGBA")
    m = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    sf = _fit_font(m, salon, _FONT_CANDIDATES_BOLD, int(56 * scale), int(34 * scale), usable)
    salon = _ellipsize(m, salon, sf, usable)
    af = _load_font(_FONT_CANDIDATES_REG, int(30 * scale))
    aps = int(30 * scale)
    area = _ellipsize(m, area, af, usable - _pin_advance(aps)) if area else ""

    sh = m.textbbox((0, 0), salon, font=sf)[3]
    ah = m.textbbox((0, 0), area or "あ", font=af)[3]
    gap = int(12 * scale)
    bottom_pad = int(70 * scale)
    block = sh + (gap + ah if area else 0)
    y = H - bottom_pad - block

    # 金の短いルール（プレミアム感）
    d.rectangle([left, y - int(18 * scale), left + int(54 * scale), y - int(18 * scale) + int(4 * scale)], fill=GOLD)
    _text_sh(d, (left, y), salon, sf, WHITE)
    if area:
        ay = y + sh + gap
        tx = _draw_pin(d, left, ay, ah, LIGHT)
        _text_sh(d, (tx, ay), area, af, LIGHT)
    if badge:
        _corner_badge(d, badge, right, int(58 * scale), scale)
    return base.convert("RGB")


def lower_third(im, salon, area="", badge=""):
    base = im.convert("RGBA")
    W, H = base.size
    scale, inset, left, right, usable = _metrics(W)
    m = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    pad = int(30 * scale)
    sf = _fit_font(m, salon, _FONT_CANDIDATES_BOLD, int(44 * scale), int(30 * scale), usable - pad * 2 - int(14 * scale))
    salon = _ellipsize(m, salon, sf, usable - pad * 2 - int(14 * scale))
    af = _load_font(_FONT_CANDIDATES_REG, int(26 * scale))
    aps = int(26 * scale)
    area = _ellipsize(m, area, af, usable - pad * 2 - _pin_advance(aps)) if area else ""

    sh = m.textbbox((0, 0), salon, font=sf)[3]
    ah = m.textbbox((0, 0), area or "あ", font=af)[3]
    gap = int(10 * scale)
    inner = sh + (gap + ah if area else 0)
    card_h = inner + pad * 2
    card_w = usable
    cx0, cy0 = left, H - int(80 * scale) - card_h
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([cx0, cy0, cx0 + card_w, cy0 + card_h], radius=int(18 * scale), fill=(17, 15, 13, 214))
    # 金の左アクセント
    od.rounded_rectangle([cx0 + int(16 * scale), cy0 + pad, cx0 + int(16 * scale) + int(5 * scale), cy0 + card_h - pad],
                         radius=int(3 * scale), fill=GOLD)
    base = Image.alpha_composite(base, ov)
    d = ImageDraw.Draw(base, "RGBA")
    tx0 = cx0 + int(16 * scale) + int(20 * scale)
    ty = cy0 + pad
    d.text((tx0, ty), salon, font=sf, fill=WHITE)
    if area:
        ay = ty + sh + gap
        px = _draw_pin(d, tx0, ay, ah, GOLD)
        d.text((px, ay), area, font=af, fill=LIGHT)
    if badge:
        _corner_badge(d, badge, right, int(58 * scale), scale)
    return base.convert("RGB")


def frosted_bar(im, salon, area="", badge=""):
    base = im.convert("RGBA")
    W, H = base.size
    scale, inset, left, right, usable = _metrics(W)
    m = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    sf = _fit_font(m, salon, _FONT_CANDIDATES_BOLD, int(48 * scale), int(32 * scale), usable)
    salon = _ellipsize(m, salon, sf, usable)
    af = _load_font(_FONT_CANDIDATES_REG, int(28 * scale))
    aps = int(28 * scale)
    area = _ellipsize(m, area, af, usable - _pin_advance(aps)) if area else ""
    sh = m.textbbox((0, 0), salon, font=sf)[3]
    ah = m.textbbox((0, 0), area or "あ", font=af)[3]
    gap = int(10 * scale)
    block = sh + (gap + ah if area else 0)
    bar_h = block + int(52 * scale)
    y0 = H - bar_h

    # 下地をぼかして帯に（フロストガラス）
    region = base.crop((0, y0, W, H)).filter(ImageFilter.GaussianBlur(int(20 * scale)))
    region = Image.alpha_composite(region, Image.new("RGBA", region.size, (14, 12, 11, 120)))
    base.paste(region, (0, y0))
    # 上端に細い光のライン
    d = ImageDraw.Draw(base, "RGBA")
    d.line([(0, y0), (W, y0)], fill=(255, 255, 255, 40), width=max(1, int(2 * scale)))
    ty = y0 + int(24 * scale)
    _text_sh(d, (left, ty), salon, sf, WHITE, off=1)
    if area:
        ay = ty + sh + gap
        tx = _draw_pin(d, left, ay, ah, LIGHT)
        _text_sh(d, (tx, ay), area, af, LIGHT, off=1)
    if badge:
        _corner_badge(d, badge, right, int(58 * scale), scale)
    return base.convert("RGB")


def corner_tag(im, salon, area="", badge=""):
    base = im.convert("RGBA")
    W, H = base.size
    scale, inset, left, right, usable = _metrics(W)
    m = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    label = salon + (f"  ·  {area}" if area else "")
    f = _fit_font(m, label, _FONT_CANDIDATES_BOLD, int(30 * scale), int(22 * scale), usable)
    label = _ellipsize(m, label, f, usable)
    bb = m.textbbox((0, 0), label, font=f)
    pin_px = int(bb[3] * 0.9)
    padx, pady = int(22 * scale), int(14 * scale)
    tag_w = _pin_advance(pin_px) + (bb[2] - bb[0]) + padx * 2
    tag_h = (bb[3] - bb[1]) + pady * 2
    x0, y0 = left, int(40 * scale)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([x0, y0, x0 + tag_w, y0 + tag_h], radius=tag_h // 2, fill=(17, 15, 13, 194))
    base = Image.alpha_composite(base, ov)
    d = ImageDraw.Draw(base, "RGBA")
    tx = _draw_pin(d, x0 + padx, y0 + pady, bb[3] - bb[1] + int(2 * scale), GOLD)
    d.text((tx, y0 + pady - bb[1]), label, font=f, fill=WHITE)
    if badge:
        _corner_badge(d, badge, right, y0, scale)
    return base.convert("RGB")


def editorial(im, salon, area="", badge=""):
    base = im.convert("RGBA")
    W, H = base.size
    scale, inset, left, right, usable = _metrics(W)
    ov = _vgrad((W, H), int(H * 0.46), H, 238)
    base = Image.alpha_composite(base, ov)
    d = ImageDraw.Draw(base, "RGBA")
    m = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    sf = _fit_font(m, salon, _FONT_CANDIDATES_BOLD, int(66 * scale), int(38 * scale), usable)
    salon = _ellipsize(m, salon, sf, usable)
    # エリアはトラッキングを効かせた見出し風（CJKは細スペース、英字は大文字）
    area_disp = " ".join(list(area.split("・")[0].strip())) if area and _is_cjk(area) else area.split("・")[0].strip().upper()
    af = _load_font(_FONT_CANDIDATES_REG, int(24 * scale))
    area_disp = _ellipsize(m, area_disp, af, usable)

    sh = m.textbbox((0, 0), salon, font=sf)[3]
    ah = m.textbbox((0, 0), area_disp or "あ", font=af)[3]
    bottom_pad = int(74 * scale)
    rule_gap = int(20 * scale)
    block = ah + rule_gap + sh
    y = H - bottom_pad - block
    _text_sh(d, (left, y), area_disp, af, GOLD, off=1)
    ry = y + ah + rule_gap // 2
    d.line([(left, ry), (right, ry)], fill=(255, 255, 255, 70), width=max(1, int(2 * scale)))
    _text_sh(d, (left, ry + rule_gap // 2), salon, sf, WHITE)
    if badge:
        _corner_badge(d, badge, right, int(56 * scale), scale)
    return base.convert("RGB")


# ─────────────────────────────────────────────
# 補助
# ─────────────────────────────────────────────
def _is_cjk(s: str) -> bool:
    return any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in s)


def _corner_badge(d, text, right_x, top_y, scale):
    """右上（セーフエリア内）に金のピル・バッジ。"""
    f = _load_font(_FONT_CANDIDATES_BOLD, int(27 * scale))
    bb = d.textbbox((0, 0), text, font=f)
    padx, pady = int(20 * scale), int(11 * scale)
    w = (bb[2] - bb[0]) + padx * 2
    h = (bb[3] - bb[1]) + pady * 2
    x = right_x - w
    _draw_pill(d, x, top_y, w, h, GOLD)
    d.text((x + (w - (bb[2] - bb[0])) // 2 - bb[0], top_y + (h - (bb[3] - bb[1])) // 2 - bb[1]),
           text, font=f, fill=(26, 20, 12))


LAYOUTS = {
    "top_band": top_band,
    "bottom_scrim": bottom_scrim,
    "lower_third": lower_third,
    "frosted_bar": frosted_bar,
    "corner_tag": corner_tag,
    "editorial": editorial,
}


def render(im, layout: str, salon: str, area: str = "", badge: str = ""):
    return LAYOUTS[layout](im, salon, area, badge)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--layout", choices=list(LAYOUTS), default="bottom_scrim")
    ap.add_argument("--salon", required=True)
    ap.add_argument("--area", default="")
    ap.add_argument("--badge", default="")
    ap.add_argument("-o", "--out", default="out.jpg")
    a = ap.parse_args()
    with Image.open(a.src) as im:
        render(im, a.layout, a.salon, a.area, a.badge).save(a.out, "JPEG", quality=90)
    print(a.out)
