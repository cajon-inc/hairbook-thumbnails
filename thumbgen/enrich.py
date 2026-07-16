"""enrich.py — カタログサムネの定期エンリッチ（推奨=下部スクリムの帯を全件に付与）

現行の「壊れたサムネだけ動画再抽出」パイプラインの後段。全カタログ商品について:

  1. 有効な元画像を取得（autofix済みがあればそれ、無ければHairBookサムネ）
  2. 情報が少なければ改善（improve.py: broken=再抽出フラグ / low_info=静止画補正）
  3. 推奨レイアウト（下部スクリム）でサロン名＋エリアの帯を合成
  4. content-hash で変化時のみ enriched/<hash>.jpg を更新（差分だけ）
  5. thumbnail_override タブに id→enriched raw URL を upsert（本番フィードH1が最優先参照）
  6. 更新結果を results.json に出力（build_results_index.py が一覧化）

モード:
  live     GOOGLE_SHEETS_KEY_JSON があればフィードから全商品を処理し override を更新
  dry-run  鍵が無ければローカルの *.jpg を素材に処理（サロン名・エリアはダミー）。overrideは触らない

  python3 enrich.py [--dry-run] [--limit N] [--rollout 1.0] [--design bottom_scrim]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PIL import Image

import overlays
from improve import assess, improve

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ENRICHED = REPO / "enriched"

FEED_ID = "1nCim5RCsQ9AIksey-AP4PQ6eryR-nGUOg0h8NJHmek4"
FEED_TAB = "入稿用データフィード_ローカル商品"     # id / title / image_link / address.city …
OVERRIDE_TAB = "thumbnail_override"
THUMBNAILS_REPO = "cajon-inc/hairbook-thumbnails"
BRANCH = "master"
RAW_BASE = f"https://raw.githubusercontent.com/{THUMBNAILS_REPO}/{BRANCH}"
JST = timezone(timedelta(hours=9))
DESIGN = "bottom_scrim"                             # 推奨レイアウト
MIN_PRODUCTS = int(os.environ.get("MIN_PRODUCTS", "300"))  # 安全ガード（liveのみ）
HTTP_TIMEOUT = 30
UA = "Mozilla/5.0 (compatible; HairbookThumbEnrich/1.0; +https://hairbook.jp)"

# dry-run 用ダミー（本番はフィードの access_salon_name / address.city を使用）
DUMMY = [
    ("hair salon Lumière", "東京都渋谷区・表参道駅 徒歩3分"),
    ("BELLA（ベラ）", "大阪市阿倍野区・阿倍野駅 1分"),
    ("Atelier NOX 表参道", "東京都港区・南青山"),
    ("ラフィネ", "名古屋市中区・栄"),
    ("KAMI CHARISMA 銀座", "東京都中央区・銀座一丁目"),
    ("hair&make earth", "横浜市西区・横浜駅 5分"),
    ("tricca", "福岡市中央区・天神"),
    ("cocotto by ADOOR", "札幌市中央区・大通"),
    ("美容室 いち", "京都市中京区・烏丸御池"),
    ("GRACE 仙台一番町", "仙台市青葉区・一番町"),
    ("Neroli", "神戸市中央区・三宮"),
    ("SLOW", "広島市中区・八丁堀"),
]


def product_hash(product_id: str) -> str:
    return hashlib.sha1(product_id.encode()).hexdigest()[:12]


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def in_rollout(key: str, ratio: float) -> bool:
    """ハッシュで安定的に一部だけ対象化（段階ロールアウト）。ratio=1.0で全件。"""
    if ratio >= 1.0:
        return True
    bucket = int(hashlib.sha1(key.encode()).hexdigest()[:4], 16) / 0xFFFF
    return bucket < ratio


# ─────────────────────────────────────────────
# worklist
# ─────────────────────────────────────────────
def worklist_live(gc) -> list[dict]:
    """フィードタブ＋override タブから {id, salon, area, image_link} を作る。"""
    sh = gc.open_by_key(FEED_ID)
    rows = sh.worksheet(FEED_TAB).get_all_records()
    try:
        ov = {r["id"]: r.get("image_link", "") for r in sh.worksheet(OVERRIDE_TAB).get_all_records()}
    except Exception:
        ov = {}
    items = []
    for r in rows:
        pid = str(r.get("id", "")).strip()
        if not pid:
            continue
        # サロン名: title は「サロン名 + スタッフ名」。先頭語をサロン名として使う（本番は専用列推奨）
        salon = str(r.get("title", "")).strip()
        area = str(r.get("address.city", "") or r.get("address.region", "")).strip()
        eff = ov.get(pid) or str(r.get("image_link", "")).strip()   # autofix済みを優先
        if eff:
            items.append({"id": pid, "salon": salon, "area": area, "image_link": eff})
    return items


def worklist_dry() -> list[dict]:
    """ローカルの *.jpg を素材に、ダミーのサロン名・エリアを割り当てる。"""
    items = []
    for i, p in enumerate(sorted(REPO.glob("*.jpg"))):
        salon, area = DUMMY[i % len(DUMMY)]
        items.append({"id": p.stem, "salon": salon, "area": area, "image_link": str(p)})
    return items


def load_image(image_link: str) -> bytes:
    """ローカルパス or URL から画像バイトを取得。"""
    if image_link.startswith("http"):
        import requests
        r = requests.get(image_link, headers={"User-Agent": UA}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.content
    return Path(image_link).read_bytes()


# ─────────────────────────────────────────────
# override upsert（liveのみ）
# ─────────────────────────────────────────────
def upsert_override(gc, entries: list[dict]) -> None:
    """entries: [{id, url, hash}] を thumbnail_override に反映（id で upsert）。"""
    sh = gc.open_by_key(FEED_ID)
    try:
        ws = sh.worksheet(OVERRIDE_TAB)
        rows = ws.get_all_values()
    except Exception:
        ws = sh.add_worksheet(title=OVERRIDE_TAB, rows=2000, cols=6)
        ws.update([["id", "image_link", "hash", "title", "srow", "note"]], "A1")
        rows = [["id", "image_link", "hash", "title", "srow", "note"]]
    header = rows[0] if rows else ["id", "image_link", "hash", "title", "srow", "note"]
    by_id = {r[0]: list(r) + [""] * (6 - len(r)) for r in rows[1:] if r and r[0]}
    today = datetime.now(JST).strftime("%Y-%m-%d")
    for e in entries:
        row = by_id.get(e["id"], [e["id"], "", "", "", "", ""])
        row[1] = e["url"]; row[2] = e["hash"]; row[5] = f"enrich {today}"
        by_id[e["id"]] = row
    out = [header] + list(by_id.values())
    ws.clear()
    ws.update(out, "A1", value_input_option="RAW")


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def load_creative_config() -> dict:
    """管理画面が書き出す id別設定 {id: {design, salon, area, badge, enabled}} を読む。"""
    for p in (REPO / "creative_config.json", ROOT / "creative_config.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
    return {}


def run(dry_run: bool, limit: int, rollout: float, design: str) -> dict:
    gc = None if dry_run else _gspread_from_env()
    items = worklist_dry() if gc is None else worklist_live(gc)
    mode = "dry-run" if (dry_run or gc is None) else "live"
    if limit:
        items = items[:limit]
    config = load_creative_config()   # 管理画面の個別選択（無ければ全件デフォルト）

    ENRICHED.mkdir(exist_ok=True)
    results, entries = [], []
    counts = {"total": 0, "updated": 0, "unchanged": 0, "enhanced": 0,
              "needs_reextract": 0, "disabled": 0, "skipped_rollout": 0, "failed": 0}

    for it in items:
        counts["total"] += 1
        pid = it["id"]
        h = pid if mode == "dry-run" else product_hash(pid)
        if not in_rollout(h, rollout):
            counts["skipped_rollout"] += 1
            continue
        cfg = config.get(pid, {})
        if cfg.get("enabled") is False:                     # 管理画面で無効化 → 帯を付けない
            counts["disabled"] += 1
            results.append({"id": pid, "hash": h, "salon": it["salon"], "area": it["area"],
                            "verdict": "-", "action": "disabled", "changed": False})
            continue
        item_design = cfg.get("design") or design           # 個別デザイン優先
        salon = cfg.get("salon") or it["salon"]
        area = cfg.get("area") if cfg.get("area") is not None else it["area"]
        badge = cfg.get("badge", "")
        # 管理画面で選んだ画像ソース（入稿/別フレーム/AI生成のホスト先URL）を優先
        src_link = cfg.get("source_url") or cfg.get("source") or ""
        src_link = src_link if isinstance(src_link, str) and (src_link.startswith("http") or src_link.startswith("/")) else it["image_link"]
        try:
            data = load_image(src_link)
            im = Image.open(io.BytesIO(data))
            a = assess(im)
            improved, action = improve(im, a)
            banded = overlays.render(improved, item_design, salon, area, badge)
            buf = io.BytesIO(); banded.save(buf, "JPEG", quality=88)
            out_bytes = buf.getvalue()
        except Exception as e:
            counts["failed"] += 1
            results.append({"id": pid, "hash": h, "salon": it["salon"], "area": it["area"],
                            "verdict": "error", "action": "failed", "changed": False, "error": repr(e)})
            continue

        out_path = ENRICHED / f"{h}.jpg"
        changed = (not out_path.exists()) or _sha(out_path.read_bytes()) != _sha(out_bytes)
        if changed:
            out_path.write_bytes(out_bytes)
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
        if action == "enhanced":
            counts["enhanced"] += 1
        if action == "needs_reextract":
            counts["needs_reextract"] += 1

        results.append({"id": pid, "hash": h, "salon": salon, "area": area,
                        "design": item_design, "badge": badge,
                        "verdict": a["verdict"], "mean": a["mean"], "std": a["std"],
                        "action": action, "changed": changed,
                        "url": f"{RAW_BASE}/enriched/{h}.jpg"})
        entries.append({"id": pid, "url": f"{RAW_BASE}/enriched/{h}.jpg", "hash": h})

    # 安全ガード（liveのみ）: 生成が異常に少ない日は override を書き換えない
    ok_count = counts["updated"] + counts["unchanged"]
    if mode == "live":
        if ok_count < MIN_PRODUCTS:
            raise SystemExit(f"安全ガード: 生成 {ok_count} < 下限 {MIN_PRODUCTS}。override更新を中止。")
        upsert_override(gc, entries)

    meta = {"mode": mode, "design": design, "rollout": rollout,
            "generated_at_note": "タイムスタンプは呼び出し側で付与", "counts": counts}
    payload = {"meta": meta, "results": results}
    (ENRICHED / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{mode}] " + " / ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"→ {ENRICHED/'results.json'}")
    return payload


def _gspread_from_env():
    key = os.environ.get("GOOGLE_SHEETS_KEY_JSON")
    if not key:
        return None
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(key), scopes=scopes)
    return gspread.authorize(creds)


def main() -> None:
    ap = argparse.ArgumentParser(description="カタログサムネの定期エンリッチ")
    ap.add_argument("--dry-run", action="store_true", help="ローカル素材で実行（override非更新）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rollout", type=float, default=1.0, help="段階ロールアウトの割合(0-1)")
    ap.add_argument("--design", default=DESIGN, choices=list(overlays.LAYOUTS))
    args = ap.parse_args()
    run(args.dry_run, args.limit, args.rollout, args.design)


if __name__ == "__main__":
    main()
