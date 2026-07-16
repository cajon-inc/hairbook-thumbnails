# クリエイティブ管理画面 実装計画

- 目的: カタログサムネを一覧化し、**画像ごとにデザイン・文言・有効/無効を個別選択**できる管理画面。
- 参照: 既存ダッシュボード `hairbook-dashboard.vercel.app/creative`（Next.js/Vercel想定）の `/creative` に載せる。
- プロトタイプ: `dashboard/creative.html`（このリポジトリ・クリック可能・Canvasでライブ合成）。本計画の「動く仕様書」。

---

## 1. 全体像（データの流れ）

```
[管理画面 /creative]  一覧＋個別編集（デザイン/サロン名/エリア/特典/有効）
        │  保存＝「公開」
        ▼
[creative_config]  id → {design, salon, area, badge, enabled}      ← 唯一の個別設定
        │  （保存先: リポジトリの creative_config.json ／ or Sheetタブ）
        ▼
[enrich.py]  有効な元画像→低情報なら改善→選択デザインで帯合成→enriched/<hash>.jpg
        │  （既に creative_config を読む実装済み）
        ▼
[thumbnail_override]  id → enriched raw URL（本番フィードH1が最優先参照）
        ▼
[Meta]  改善版サムネで配信
```

**要点**: 管理画面は `creative_config` を書くだけ。実際の画像生成・配信反映は既存パイプライン（`enrich.py`＋override＋H1数式）が担う。UIとパイプラインは `creative_config` で疎結合。

---

## 2. データモデル

### 一覧アイテム（GET用・読み取り）
既存データを結合して返す:
| 項目 | 出所 |
|---|---|
| id / image_link | フィード `入稿用データフィード_ローカル商品` |
| salon（既定） | `title`（=access_salon_name+staff）／将来は専用列 |
| area（既定） | `address.city`（例「大阪市中央区」） |
| verdict（情報判定） | `enrich` の `results.json`（ok/low_info/broken） |
| 現在の設定 | `creative_config`（未設定なら既定=下部スクリム/有効） |

### creative_config（POST用・唯一の個別設定）
```json
{
  "44528_01KJ...": { "design": "bottom_scrim", "salon": "hair salon Lumière",
    "area": "東京都渋谷区・表参道", "badge": "新規20%OFF", "enabled": true },
  "44530_01KQ...": { "enabled": false }
}
```
- `design`: bottom_scrim(推奨) / lower_third / top_band / frosted_bar / corner_tag / editorial
- 省略キーは既定にフォールバック（`enabled` 既定 true、`design` 既定 bottom_scrim）。

---

## 3. アーキテクチャ

### フロント（Next.js `/creative`）
プロトタイプ `creative.html` をReactに移植。構成:
- **一覧グリッド**: カード（プレビュー・サロン名・エリア・デザイン/状態チップ・選択チェック）
- **詳細ドロワー**: ライブプレビュー＋デザイン6案（各ミニプレビュー）＋文言編集＋有効トグル
- **絞り込み/検索**: デザイン別・状態別（有効/無効/要改善）・サロン名/エリア検索
- **一括操作**: 選択に対しデザイン一括適用・有効/無効
- **公開**: 変更を `creative_config` にPOST → パイプライン起動

### プレビュー（2層）
- **即時**: ブラウザ内Canvasで合成（プロトタイプの `overlays.py`→JS移植をそのまま流用）。編集の即応性。
- **正**: 公開時にサーバ側 `overlays.py`(Pillow) が生成した `enriched/<hash>.jpg` が最終成果物（Canvasは近似プレビュー）。

### 保存先（`creative_config`）— 2案
| 案 | 内容 | 長所 |
|---|---|---|
| **A. repoにコミット**（推奨） | `POST /api/creative` が GitHub API で `creative_config.json` を更新 | バージョン管理・監査・パイプラインが直読み。追加インフラ不要 |
| B. Sheetタブ | `creative_config` タブに書く | 既存gspread資産と一貫。非エンジニアも見れる |

### API（Next.js Route Handlers / Vercel Functions）
- `GET /api/creative` … 一覧アイテム（§2）を返す（フィード＋results.json＋config結合）
- `POST /api/creative` … 差分configを保存（A案=GitHubコミット）＋任意でワークフロー起動
- `POST /api/creative/publish` … `thumbnail-enrich.yml` を `workflow_dispatch` で起動（即時反映）

---

## 4. パイプライン側（実装済み）

`thumbgen/enrich.py` は既に `creative_config.json` を読み、id別に
`design / salon / area / badge / enabled` を反映してエンリッチする（`enabled:false` は帯を付けない）。
→ **管理画面はconfigを書くだけで本番反映できる状態**。定期実行は `.github/workflows/thumbnail-enrich.yml`。

---

## 5. フェーズ

1. **API（読み取り）**: `GET /api/creative` … フィード＋results.json＋configの結合。まず一覧が出る。
2. **UI移植**: `creative.html` → React `/creative`（グリッド＋ドロワー＋Canvasプレビュー）。
3. **保存**: `POST /api/creative`（A案=GitHubコミット）＋楽観更新。
4. **公開連携**: 保存後に enrich ワークフローを起動 → 反映状況を results.json でUIに表示。
5. **運用**: 変更履歴/承認、段階ロールアウト（`--rollout`）、override除去での即ロールバック。

---

## 6. 未確定・要決定
- 保存先 A（repoコミット）/ B（Sheet）どちらにするか。
- サロン名の「専用列」を用意するか（`title` はstaff名連結のため）。表記ゆれ対策。
- プレビューをCanvas近似のみにするか、公開前にサーバ生成の実画像も見せるか。
- 既存 `hairbook-dashboard` リポへのアクセス（このセッションに追加できれば直接移植可能）。

---

## 7. このリポジトリの関連物
- `dashboard/creative.html`（プロトタイプ・動く仕様書）／ `creative.template.html`＋`build_dashboard.py`（生成）
- `thumbgen/enrich.py`（creative_config対応済みパイプライン）／ `overlays.py`（デザイン6案）／ `improve.py`（低情報改善）
- `thumbgen/build_results_index.py`（結果一覧）／ `.github/workflows/thumbnail-enrich.yml`（定期実行）
