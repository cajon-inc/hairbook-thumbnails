"""generate_samples.py — 既存サムネへ帯を合成した Before/After を生成（方針2の実証PoC）

このリポジトリにホスティング済みの実サムネ（ルートの *.jpg）を素材に、
  1. 帯合成後の画像              → samples/after/<name>.jpg
  2. 3列コンタクトシート          → samples/contact_sheet.png
       [Before 4:5] [After 4:5] [After→9:16カバー時に実際に見える範囲]
  3. セーフエリア可視化           → samples/safearea_9x16.png

を出力する。第3列で「帯の文字が 9:16 見切れ後も残る」ことを実証する。

注意: サロン名・エリアは**レイアウト検証用のダミー**（長さの偏りを含む）。
本番は catalog_feed のデータ（access_salon_name / city_name）を使う。

  python3 generate_samples.py [--limit 12]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from band_overlay import (
    BandSpec, REF_WIDTH, SAFE_INSET_RATIO, render_band, _load_font,
    _FONT_CANDIDATES_BOLD, _FONT_CANDIDATES_REG,
)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = ROOT / "samples"

# レイアウト検証用ダミー（サロン名の長短・英日混在・エリア表記の揺れを意図的に混ぜる）
DUMMY = [
    ("hair salon Lumière", "東京都渋谷区・表参道駅 徒歩3分"),
    ("BELLA（ベラ）", "大阪市阿倍野区・阿倍野駅 1分"),
    ("Atelier de Coiffure NOX 表参道本店", "東京都港区・南青山"),  # 長い名前 → 自動縮小/省略の検証
    ("ラフィネ", "名古屋市中区・栄"),
    ("KAMI CHARISMA salon 銀座", "東京都中央区・銀座一丁目駅"),
    ("hair&make earth", "横浜市西区・横浜駅 5分"),
    ("tricca", "福岡市中央区・天神"),
    ("cocotto by ADOOR", "札幌市中央区・大通"),
    ("美容室 いち", "京都市中京区・烏丸御池"),
    ("GRACE hair design 仙台一番町店", "仙台市青葉区・一番町"),
    ("Neroli", "神戸市中央区・三宮"),
    ("SLOW", "広島市中区・八丁堀"),
]

PANEL_W = 300          # コンタクトシート1枚の表示幅
PAD = 16
LABEL_H = 34


def _fit(im: Image.Image, w: int) -> Image.Image:
    return im.resize((w, round(im.height * w / im.width)))


def _crop_9x16(im: Image.Image) -> Image.Image:
    """4:5 を 9:16 でカバー表示した時に実際に見える中央帯（左右 14.8% を切る）。"""
    inset = int(im.width * SAFE_INSET_RATIO)
    return im.crop((inset, 0, im.width - inset, im.height))


def build_contact_sheet(pairs: list[tuple[Path, Image.Image]]) -> Image.Image:
    """pairs: [(before_path, after_img)] から 3列 [Before|After|9:16] のシートを作る。"""
    label_font = _load_font(_FONT_CANDIDATES_BOLD, 22)
    col_font = _load_font(_FONT_CANDIDATES_BOLD, 20)

    thumbs = []
    for bpath, after in pairs:
        with Image.open(bpath) as b:
            before = _fit(b.convert("RGB"), PANEL_W)
        after_fit = _fit(after, PANEL_W)
        crop_fit = _fit(_crop_9x16(after), PANEL_W)
        row_h = max(before.height, after_fit.height, crop_fit.height)
        thumbs.append((before, after_fit, crop_fit, row_h))

    cols = ["元サムネ (4:5)", "帯あり (4:5)", "9:16表示で見える範囲"]
    header_h = 40
    sheet_w = PAD + (PANEL_W + PAD) * 3
    sheet_h = header_h + sum(t[3] + LABEL_H + PAD for t in thumbs) + PAD

    sheet = Image.new("RGB", (sheet_w, sheet_h), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for i, title in enumerate(cols):
        x = PAD + i * (PANEL_W + PAD)
        d.text((x, 10), title, font=col_font, fill=(30, 30, 30))

    y = header_h
    for before, after_fit, crop_fit, row_h in thumbs:
        for i, im in enumerate((before, after_fit, crop_fit)):
            x = PAD + i * (PANEL_W + PAD)
            sheet.paste(im, (x, y))
            # 9:16列は実際の見え方を強調する枠
            if i == 2:
                d.rectangle([x, y, x + im.width - 1, y + im.height - 1], outline=(210, 60, 60), width=2)
        y += row_h + LABEL_H + PAD
    return sheet


def build_safearea_viz(before_path: Path, spec: BandSpec) -> Image.Image:
    """帯あり画像に、9:16見切れ境界とセーフエリアを重ねた解説図。"""
    with Image.open(before_path) as im:
        after = render_band(im, spec)
    W, H = after.size
    viz = after.convert("RGB").copy()
    d = ImageDraw.Draw(viz, "RGBA")
    inset = int(W * SAFE_INSET_RATIO)
    # 見切れる左右帯を赤半透明で
    d.rectangle([0, 0, inset, H], fill=(220, 40, 40, 80))
    d.rectangle([W - inset, 0, W, H], fill=(220, 40, 40, 80))
    # 境界線
    d.line([(inset, 0), (inset, H)], fill=(220, 40, 40), width=3)
    d.line([(W - inset, 0), (W - inset, H)], fill=(220, 40, 40), width=3)
    f = _load_font(_FONT_CANDIDATES_BOLD, 26)
    d.text((10, H - 40), "← 9:16で見切れ (14.8%)", font=f, fill=(220, 40, 40))
    d.text((W - inset + 10, H - 40), "見切れ →", font=f, fill=(220, 40, 40))
    fc = _load_font(_FONT_CANDIDATES_REG, 24)
    d.text((inset + 20, H // 2), "セーフエリア（文字はこの中）", font=fc, fill=(255, 255, 255))
    return viz


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    imgs = sorted(REPO.glob("*.jpg"))[: args.limit]
    if not imgs:
        raise SystemExit("素材 *.jpg が見つかりません（リポジトリ直下で実行してください）")

    (OUT / "after").mkdir(parents=True, exist_ok=True)
    pairs = []
    for i, path in enumerate(imgs):
        salon, area = DUMMY[i % len(DUMMY)]
        spec = BandSpec(salon=salon, area=area)
        with Image.open(path) as im:
            after = render_band(im, spec)
        after.save(OUT / "after" / path.name, "JPEG", quality=85)
        pairs.append((path, after))
        print(f"  {path.name}: {salon} / {area} ({im.size if False else after.size})")

    sheet = build_contact_sheet(pairs)
    sheet.save(OUT / "contact_sheet.png")
    print(f"contact sheet: {OUT / 'contact_sheet.png'} {sheet.size}")

    viz = build_safearea_viz(imgs[0], BandSpec(salon=DUMMY[0][0], area=DUMMY[0][1]))
    viz.save(OUT / "safearea_9x16.png")
    print(f"safe-area viz: {OUT / 'safearea_9x16.png'} {viz.size}")


if __name__ == "__main__":
    main()
