"""build_brief.py — design_brief.template.html に画像を data URI で差し込み design_brief.html を生成。

Artifact は外部リソースを禁止（strict CSP）のため、画像は base64 で自己完結させる。
表示用に縮小（幅620px, JPEG q80）してファイルサイズを抑える。
"""
from __future__ import annotations
import base64
import io
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PAT = ROOT / "samples" / "patterns"

IMAGES = {
    "__IMG_BEFORE__": REPO / "307f62f7c2e1.jpg",
    "__IMG_A__": PAT / "A.jpg",
    "__IMG_B__": PAT / "B.jpg",
    "__IMG_C__": PAT / "C.jpg",
    "__IMG_D__": PAT / "D.jpg",
    "__IMG_SAFE__": PAT / "safearea.jpg",
    "__IMG_ANTI__": PAT / "antipattern.jpg",
}
TARGET_W = 620


def data_uri(path: Path, width: int = TARGET_W) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80, optimize=True)
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def main() -> None:
    html = (ROOT / "design_brief.template.html").read_text(encoding="utf-8")
    total = 0
    for token, path in IMAGES.items():
        uri = data_uri(path)
        total += len(uri)
        html = html.replace(token, uri)
    out = ROOT / "design_brief.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)/1024:.0f} KB, images {total/1024:.0f} KB)")


if __name__ == "__main__":
    main()
