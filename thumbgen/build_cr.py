"""build_cr.py — cr_directions.template.html に画像を data URI で差し込み cr_directions.html を生成。"""
from __future__ import annotations
import base64, io
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
CR = ROOT / "samples" / "cr"

IMAGES = {
    "__IMG_01__": CR / "01_top_band.jpg",
    "__IMG_02__": CR / "02_bottom_scrim.jpg",
    "__IMG_03__": CR / "03_lower_third.jpg",
    "__IMG_04__": CR / "04_frosted_bar.jpg",
    "__IMG_05__": CR / "05_corner_tag.jpg",
    "__IMG_06__": CR / "06_editorial.jpg",
    "__IMG_REC_LIGHT__": CR / "rec_light.jpg",
    "__IMG_REC_PLAIN__": CR / "rec_plain.jpg",
    "__IMG_REC_BUSY__": CR / "rec_busy.jpg",
    "__IMG_BADGE__": CR / "scrim_badge.jpg",
}
TARGET_W = 560


def data_uri(path: Path, width: int = TARGET_W) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()


def main() -> None:
    html = (ROOT / "cr_directions.template.html").read_text(encoding="utf-8")
    total = 0
    for token, path in IMAGES.items():
        uri = data_uri(path)
        total += len(uri)
        html = html.replace(token, uri)
    out = ROOT / "cr_directions.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)/1024:.0f} KB, images {total/1024:.0f} KB)")


if __name__ == "__main__":
    main()
