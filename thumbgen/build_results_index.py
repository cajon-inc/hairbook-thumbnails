"""build_results_index.py — enrich.py の結果を一覧化する。

出力:
  enriched/RESULTS.md            GitHubで見やすい表（サマリ＋各件）
  enriched/index.html            相対パス参照のギャラリー（リポジトリ/ローカル閲覧用）
  enriched/results_gallery.html  画像を data URI 埋め込みの自己完結HTML（共有/Artifact用）

  python3 build_results_index.py
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ENRICHED = REPO / "enriched"

VERDICT_JA = {"ok": "十分", "low_info": "低情報", "broken": "破損相当", "error": "エラー"}
ACTION_JA = {"none": "そのまま", "enhanced": "改善", "needs_reextract": "要再抽出", "failed": "失敗"}


def _load():
    return json.loads((ENRICHED / "results.json").read_text(encoding="utf-8"))


def _thumb_uri(path: Path, w: int = 220) -> str:
    if not path.exists():
        return ""
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > w:
            im = im.resize((w, round(im.height * w / im.width)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────
# RESULTS.md
# ─────────────────────────────────────────────
def build_md(payload: dict) -> None:
    c = payload["meta"]["counts"]
    m = payload["meta"]
    lines = [
        "# サムネ更新結果 一覧", "",
        f"- モード: **{m['mode']}** ／ デザイン: **{m['design']}** ／ ロールアウト: {m['rollout']}",
        f"- 合計 **{c['total']}** ／ 更新 **{c['updated']}** ／ 据置き {c['unchanged']} "
        f"／ 改善 {c['enhanced']} ／ 要再抽出 {c['needs_reextract']} ／ 失敗 {c['failed']}",
        "",
        "| hash | サロン名 | エリア | 情報判定 | 改善 | 更新 |",
        "|---|---|---|---|---|---|",
    ]
    for r in payload["results"]:
        changed = "✅" if r.get("changed") else "―"
        lines.append(f"| `{r['hash'][:10]}` | {r.get('salon','')} | {r.get('area','')} "
                     f"| {VERDICT_JA.get(r.get('verdict',''), r.get('verdict',''))} "
                     f"| {ACTION_JA.get(r.get('action',''), r.get('action',''))} | {changed} |")
    (ENRICHED / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────
# ギャラリーHTML
# ─────────────────────────────────────────────
def _card(r, src) -> str:
    verdict = r.get("verdict", "")
    action = r.get("action", "")
    vcls = {"ok": "n", "low_info": "g", "broken": "d", "error": "d"}.get(verdict, "n")
    acls = {"none": "n", "enhanced": "ok", "needs_reextract": "w", "failed": "d"}.get(action, "n")
    changed = r.get("changed")
    return f"""<article class="card" data-action="{action}" data-changed="{str(bool(changed)).lower()}">
  <img loading="lazy" src="{src}" alt="{r.get('salon','')}">
  <div class="cbody">
    <div class="cname">{r.get('salon','') or '—'}</div>
    <div class="carea">{r.get('area','') or ''}</div>
    <div class="chips">
      <span class="chip {vcls}">{VERDICT_JA.get(verdict, verdict)}</span>
      <span class="chip {acls}">{ACTION_JA.get(action, action)}</span>
      <span class="chip {'c' if changed else 'm'}">{'更新' if changed else '据置き'}</span>
    </div>
  </div>
</article>"""


def build_html(payload: dict, embed: bool) -> str:
    c = payload["meta"]["counts"]
    m = payload["meta"]

    def src(h):
        return _thumb_uri(ENRICHED / f"{h}.jpg") if embed else f"./{h}.jpg"

    # enhanced の Before/After
    enh = [r for r in payload["results"] if r.get("action") == "enhanced"]
    enh_html = ""
    if enh:
        rows = ""
        for r in enh[:12]:
            h = r["hash"]
            before = _thumb_uri(REPO / f"{h}.jpg") if embed else f"../{h}.jpg"
            after = src(h)
            rows += f"""<div class="ba"><figure><img loading="lazy" src="{before}"><figcaption>元（{VERDICT_JA.get(r.get('verdict',''),'')}）</figcaption></figure>
      <figure><img loading="lazy" src="{after}"><figcaption>改善＋帯</figcaption></figure></div>"""
        enh_html = f"""<section><div class="eyebrow">Improved</div><h2>情報が少なかった画像の改善（{len(enh)}件）</h2>
    <p class="sub">白飛び/暗い/眠い画像をオートコントラスト等で底上げしてから帯を合成。破損相当は「要再抽出」（動画から再取得）。</p>
    <div class="balist">{rows}</div></section>"""

    cards = "\n".join(_card(r, src(r["hash"])) for r in payload["results"])
    tiles = [
        ("合計", c["total"], "n"), ("更新", c["updated"], "c"), ("据置き", c["unchanged"], "m"),
        ("改善", c["enhanced"], "ok"), ("要再抽出", c["needs_reextract"], "w"), ("失敗", c["failed"], "d"),
    ]
    tiles_html = "".join(f'<div class="tile {cl}"><div class="tv">{v}</div><div class="tk">{k}</div></div>'
                         for k, v, cl in tiles)

    return f"""<title>サムネ更新結果 一覧</title>
<style>
:root{{--paper:#edeae4;--surface:#f6f4f0;--surface-2:#e6e2da;--ink:#201c17;--ink-soft:#5b5348;--ink-faint:#8a8072;--line:#d6d0c5;--gold:#9a7328;--ok:#4c7355;--warn:#b6802a;--danger:#c0472f;--font:-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP",Meiryo,system-ui,sans-serif;--mono:ui-monospace,Menlo,Consolas,monospace;}}
@media (prefers-color-scheme:dark){{:root{{--paper:#16130f;--surface:#1f1b16;--surface-2:#262019;--ink:#ece7de;--ink-soft:#b3a996;--ink-faint:#857b6b;--line:#332c22;--gold:#cba85e;--ok:#7fa985;--warn:#d6a34e;--danger:#e0715a;}}}}
:root[data-theme="light"]{{--paper:#edeae4;--surface:#f6f4f0;--surface-2:#e6e2da;--ink:#201c17;--ink-soft:#5b5348;--ink-faint:#8a8072;--line:#d6d0c5;--gold:#9a7328;--ok:#4c7355;--warn:#b6802a;--danger:#c0472f;}}
:root[data-theme="dark"]{{--paper:#16130f;--surface:#1f1b16;--surface-2:#262019;--ink:#ece7de;--ink-soft:#b3a996;--ink-faint:#857b6b;--line:#332c22;--gold:#cba85e;--ok:#7fa985;--warn:#d6a34e;--danger:#e0715a;}}
*{{box-sizing:border-box;}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font);line-height:1.6;-webkit-font-smoothing:antialiased;}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 22px;}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--gold);font-weight:600;}}
header{{padding:44px 0 22px;border-bottom:1px solid var(--line);}}
h1{{font-size:clamp(26px,4vw,38px);margin:14px 0 0;font-weight:800;letter-spacing:-.01em;}}
.meta{{font-family:var(--mono);font-size:12.5px;color:var(--ink-soft);margin-top:12px;}}
.tiles{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:22px 0 4px;}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 12px;text-align:center;}}
.tile .tv{{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums;}}
.tile .tk{{font-size:12px;color:var(--ink-soft);margin-top:2px;}}
.tile.c .tv{{color:var(--gold);}} .tile.ok .tv{{color:var(--ok);}} .tile.w .tv{{color:var(--warn);}} .tile.d .tv{{color:var(--danger);}}
section{{padding:34px 0;border-bottom:1px solid var(--line);}}
h2{{font-size:clamp(19px,3vw,24px);margin:10px 0 0;font-weight:750;}}
.sub{{color:var(--ink-soft);margin:8px 0 0;max-width:70ch;font-size:14px;}}
.balist{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-top:20px;}}
.ba{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.ba img{{width:100%;border-radius:8px;border:1px solid var(--line);display:block;}}
.ba figcaption{{font-family:var(--mono);font-size:11px;color:var(--ink-faint);text-align:center;margin-top:6px;}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0 4px;}}
.fbtn{{font-family:var(--mono);font-size:12.5px;padding:7px 14px;border-radius:100px;border:1px solid var(--line);background:var(--surface);color:var(--ink-soft);cursor:pointer;}}
.fbtn.active{{background:var(--gold);color:#fff;border-color:var(--gold);}}
:root[data-theme="dark"] .fbtn.active{{color:#16130f;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-top:18px;}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;}}
.card img{{width:100%;display:block;border-bottom:1px solid var(--line);aspect-ratio:4/5;object-fit:cover;}}
.cbody{{padding:10px 11px 12px;}}
.cname{{font-weight:700;font-size:13.5px;line-height:1.35;}}
.carea{{font-size:11.5px;color:var(--ink-soft);margin-top:2px;min-height:1em;}}
.chips{{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px;}}
.chip{{font-family:var(--mono);font-size:10.5px;padding:2px 8px;border-radius:100px;border:1px solid var(--line);color:var(--ink-soft);}}
.chip.g{{color:var(--gold);border-color:var(--gold);}} .chip.ok{{color:var(--ok);border-color:var(--ok);}}
.chip.w{{color:var(--warn);border-color:var(--warn);}} .chip.d{{color:var(--danger);border-color:var(--danger);}}
.chip.c{{color:var(--gold);border-color:var(--gold);}} .chip.m{{opacity:.6;}}
footer{{padding:26px 0 60px;color:var(--ink-faint);font-size:12px;font-family:var(--mono);}}
@media (max-width:640px){{.tiles{{grid-template-columns:repeat(3,1fr);}}.ba{{grid-template-columns:1fr 1fr;}}}}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Thumbnail Enrichment · Results</div>
    <h1>サムネ更新結果 一覧</h1>
    <div class="meta">モード {m['mode']} ／ デザイン {m['design']} ／ ロールアウト {m['rollout']}</div>
    <div class="tiles">{tiles_html}</div>
  </header>
  {enh_html}
  <section>
    <div class="eyebrow">All items</div>
    <h2>全{c['total']}件</h2>
    <div class="filters">
      <button class="fbtn active" data-f="all">すべて</button>
      <button class="fbtn" data-f="changed">更新あり</button>
      <button class="fbtn" data-f="enhanced">改善</button>
      <button class="fbtn" data-f="needs_reextract">要再抽出</button>
      <button class="fbtn" data-f="failed">失敗</button>
    </div>
    <div class="grid" id="grid">{cards}</div>
  </section>
  <footer>※ dry-run のサロン名・エリアはダミー（本番はフィード由来）。生成: enrich.py → build_results_index.py</footer>
</div>
<script>
  const btns=document.querySelectorAll('.fbtn'), cards=document.querySelectorAll('.card');
  btns.forEach(b=>b.addEventListener('click',()=>{{
    btns.forEach(x=>x.classList.remove('active')); b.classList.add('active');
    const f=b.dataset.f;
    cards.forEach(c=>{{
      let show = f==='all' || (f==='changed'&&c.dataset.changed==='true') || c.dataset.action===f;
      c.style.display = show ? '' : 'none';
    }});
  }}));
</script>"""


def main() -> None:
    payload = _load()
    build_md(payload)
    (ENRICHED / "index.html").write_text(build_html(payload, embed=False), encoding="utf-8")
    (ENRICHED / "results_gallery.html").write_text(build_html(payload, embed=True), encoding="utf-8")
    print(f"wrote {ENRICHED/'RESULTS.md'}, {ENRICHED/'index.html'}, {ENRICHED/'results_gallery.html'}")


if __name__ == "__main__":
    main()
