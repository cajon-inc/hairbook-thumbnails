"""build_dashboard.py — 管理画面プロトタイプ(creative.html)に素材を埋め込む。

ローカルの *.jpg（現状のカタログサムネ）から ~24件を選び、
サロン名・エリア（ダミー）・情報判定・既定デザインを付けて creative.template.html に注入する。
プレビューはブラウザ内Canvasで合成するため、埋め込むのは帯なしの元画像のみ。
"""
from __future__ import annotations
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "thumbgen"))
from improve import assess          # noqa: E402
from enrich import DUMMY            # noqa: E402

N = 24
TARGET_W = 420

# 一部は「すでに個別編集済み」の状態にして、混在した一覧を見せる
PRESET = {2: ("magazine", ""), 5: ("letterbox", ""), 8: ("poster", "新規20%OFF"),
          11: ("namecard", ""), 14: ("tategaki", ""), 17: ("caption", "")}


def data_uri(path: Path, w: int = TARGET_W) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > w:
            im = im.resize((w, round(im.height * w / im.width)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=78, optimize=True)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()


def main() -> None:
    imgs = sorted(REPO.glob("*.jpg"))[:N]
    items = []
    for i, p in enumerate(imgs):
        salon, area = DUMMY[i % len(DUMMY)]
        with Image.open(p) as im:
            verdict = assess(im)["verdict"]
        design, badge = PRESET.get(i, ("bottom_scrim", ""))
        items.append({"id": p.stem, "hash": p.stem, "salon": salon, "area": area,
                      "verdict": verdict, "design": design, "badge": badge,
                      "img": data_uri(p)})
    tpl = (ROOT / "creative.template.html").read_text(encoding="utf-8")
    html = tpl.replace("__ITEMS_JSON__", json.dumps(items, ensure_ascii=False))
    out = ROOT / "creative.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)/1024:.0f} KB, {len(items)} items)")


if __name__ == "__main__":
    main()
