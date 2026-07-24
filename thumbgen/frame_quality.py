"""frame_quality.py — サムネ品質スコアリング（方針1のコア／探索）

現行の autofix v3 選別は「情報量(std) × 静止度」で最良フレームを選ぶ。これは
**文字密度の高いフレーム＝価格カード/告知/求人カードを高評価**してしまう傾向がある
（PoC で既存サムネのほぼ全てに焼き込みテキストが確認された）。

「全体的により良い画像」を目指す方針1では、"good" の定義自体を見直す必要がある:
  - 顧客向けサロン広告としては、文字だらけのカードより**髪型・仕上がりが見える清潔なフレーム**が良い。
  - 求人(スタイリスト募集)フレームは顧客向け広告に不適（仕様書でも「修正不可」扱い）。

このモジュールは 2 層で品質を測る:
  1. 軽量ヒューリスティック（PIL+numpy・無料・全数を高速スクリーニング）
       brightness / contrast(std) / edge密度（焼き込みテキストの代理指標） を算出し、
       broken / text_heavy / clean にざっくり分類する。
  2. AI判定（任意・Claude Vision）
       「髪型が見えるか / テキスト過多か / 求人・告知でないか / 広告適性」を実判定。
       ANTHROPIC_API_KEY があれば有効化（既存 feed_qa の Phase3 と同じ流儀）。プラグイン口のみ用意。

  python3 frame_quality.py report [--limit N]   # 既存 *.jpg をスクリーニングして分布を出す
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent

# しきい値（PoC観察ベースの初期値。実運用で要チューニング）
BROKEN_STD = 22.0        # これ未満は低情報/破損（feed_qa と同基準）
TEXT_CELL_HI = 0.15      # セルが「テキスト塊」とみなす edge 密度
TEXT_HEAVY_RATIO = 0.10  # テキスト塊セルがこの割合超 or 局所が突出で text_suspect
TEXT_CELL_MAX = 0.34     # 単一セルの edge 密度がこれ超なら見出しカードの疑い（局所検出）
GRID = (8, 6)            # 行, 列


@dataclass
class QualityReport:
    name: str
    width: int
    height: int
    brightness: float      # 明るさ平均
    contrast: float        # 明るさ標準偏差（情報量）
    edge_density: float    # 画面全体のエッジ率
    text_cell_ratio: float # 「テキスト塊」セルの割合（焼き込み文字の代理指標）
    top_heavy: float       # 上1/3 の edge 偏在（見出しカードらしさ）
    verdict: str           # broken | text_heavy | clean
    note: str = ""


def _gray_array(im: Image.Image) -> np.ndarray:
    return np.asarray(im.convert("L"), dtype=np.float32)


def _edge_map(g: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    # 正規化して 0..1、しきい値でエッジ判定
    m = mag / (mag.max() + 1e-6)
    return (m > 0.12).astype(np.float32)


def analyze(path: Path) -> QualityReport:
    with Image.open(path) as im:
        W, H = im.size
        g = _gray_array(im)
    brightness = float(g.mean())
    contrast = float(g.std())
    edges = _edge_map(g)
    edge_density = float(edges.mean())

    rows, cols = GRID
    h, w = edges.shape
    cell_dens = []
    for r in range(rows):
        for c in range(cols):
            cell = edges[r * h // rows:(r + 1) * h // rows, c * w // cols:(c + 1) * w // cols]
            cell_dens.append(float(cell.mean()))
    cell_dens = np.array(cell_dens).reshape(rows, cols)
    text_cell_ratio = float((cell_dens > TEXT_CELL_HI).mean())
    cell_max = float(cell_dens.max())
    top_heavy = float(edges[: h // 3].mean() / (edge_density + 1e-6))

    if contrast < BROKEN_STD:
        verdict, note = "broken", "低情報/単色の疑い（現行autofixの対象）"
    elif text_cell_ratio > TEXT_HEAVY_RATIO or cell_max > TEXT_CELL_MAX:
        verdict, note = "text_suspect", "焼き込みテキストの疑い（価格/告知/求人カード）※要AI判定"
    else:
        verdict, note = "clean?", "清潔フレームの可能性（確証はAI判定が必要）"

    return QualityReport(path.name, W, H, round(brightness, 1), round(contrast, 1),
                         round(edge_density, 4), round(text_cell_ratio, 3),
                         round(top_heavy, 2), verdict, note)


# ─────────────────────────────────────────────
# AI判定プラグイン口（任意・Claude Vision）
# ─────────────────────────────────────────────
VISION_PROMPT = (
    "この画像は美容室のカタログ広告サムネイル候補です。次をJSONで評価してください: "
    '{"hairstyle_visible": 0-1, "text_clutter": 0-1, "is_recruitment_or_notice": bool, '
    '"ad_suitability": 0-1, "reason": "..."} '
    "hairstyle_visible=髪型/仕上がりの見えやすさ, text_clutter=焼き込み文字の多さ, "
    "is_recruitment_or_notice=求人/告知など顧客向けでない内容か, ad_suitability=顧客向け広告としての総合適性。"
)


def score_with_vision(path: Path) -> dict | None:
    """Claude Vision で広告適性を判定（要 ANTHROPIC_API_KEY / anthropic SDK）。
    未設定なら None（＝ヒューリスティックのみで運用）。ここは口だけ用意し本実装は着手時に。"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import base64
        import anthropic  # 未導入なら None
    except ImportError:
        return None
    client = anthropic.Anthropic()
    data = base64.standard_b64encode(path.read_bytes()).decode()
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
            {"type": "text", "text": VISION_PROMPT},
        ]}],
    )
    try:
        return json.loads(msg.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError):
        return {"raw": msg.content[0].text if msg.content else ""}


def cmd_report(args) -> None:
    imgs = sorted(REPO.glob("*.jpg"))
    if args.limit:
        imgs = imgs[: args.limit]
    reports = [analyze(p) for p in imgs]

    counts = {"broken": 0, "text_suspect": 0, "clean?": 0}
    for r in reports:
        counts[r.verdict] += 1
    n = len(reports)

    print(f"=== サムネ品質スクリーニング（{n}枚・ヒューリスティックのみ）===")
    for v in ("broken", "text_suspect", "clean?"):
        pct = 100 * counts[v] / n if n else 0
        print(f"  {v:13s}: {counts[v]:3d}枚 ({pct:4.1f}%)")
    print()
    print(f"{'name':20s} {'size':10s} {'bright':>6s} {'contr':>6s} {'edge':>6s} {'txt%':>6s} verdict")
    for r in reports:
        print(f"{r.name:20s} {r.width}x{r.height:<5d} {r.brightness:6.1f} {r.contrast:6.1f} "
              f"{r.edge_density:6.3f} {r.text_cell_ratio:6.2f} {r.verdict}")

    if args.json:
        Path(args.json).write_text(json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2))
        print(f"\nJSON: {args.json}")

    print("\n注: これは静止画ヒューリスティック。実運用では元動画からの再選別＋AI判定(score_with_vision)で"
          "「清潔な髪型フレーム」を積極選択する（方針1の本実装）。")


def main() -> None:
    ap = argparse.ArgumentParser(description="サムネ品質スコアリング（方針1）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("report", help="既存サムネをスクリーニング")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", default="")
    p.set_defaults(func=cmd_report)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
