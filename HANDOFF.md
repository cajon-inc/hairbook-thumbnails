# 引き継ぎ — カタログサムネ改善 & クリエイティブ管理画面のデプロイ

> **この引き継ぎの目的**: 作業した環境が Vercel 未接続だったため、
> `hairbook-dashboard.vercel.app/creative` への公開だけが残っている。
> **Vercel 接続済みの Claude 環境**で、この最終デプロイを完了してほしい（必要なら本番化も）。

---

## 0. 最短でやること（TL;DR）

1. このリポジトリ `cajon-inc/hairbook-thumbnails` の作業ブランチを取得
   `git fetch origin claude/catalog-thumbnail-improvement-xw8vo2 && git checkout claude/catalog-thumbnail-improvement-xw8vo2`
2. デプロイ対象は **`vercel-deploy/`**（自己完結・外部依存なしの静的サイト）
3. Vercel プロジェクト **`hairbook-dashboard`**（team: `emplays-projects` / EMPLAY's projects・Hobby）へデプロイ
   ```bash
   cd vercel-deploy
   vercel link --yes --project hairbook-dashboard --scope emplays-projects   # 接続済みトークンで
   vercel --prod
   ```
   → `hairbook-dashboard.vercel.app/creative` に公開（`/` は `/creative` へリダイレクト）
4. 公開URLをユーザーに報告

### ⚠️ 事前確認（重要）
このVercelプロジェクトは **Git未接続**（Settings→Git に接続リポジトリなし）＝ **CLIデプロイした内容がそのまま本番**になる。
- プロジェクトに**既存の別アプリ/ページがある場合、上書きされる**。
- デプロイ前に「この管理画面（`/creative`）で公開してよいか、既存を残す必要はないか」を**ユーザーに確認**すること。
- 既存を残す場合は、Vercelのデプロイ元（＝別のローカルプロジェクト or リポ）に
  `public/creative/index.html` として `vercel-deploy/creative/index.html` を追加して共存させる。

---

## 1. リポジトリ状態

- repo: `cajon-inc/hairbook-thumbnails`（public）
- branch: `claude/catalog-thumbnail-improvement-xw8vo2`（**全てpush済み**・未マージ）
- 本番化する場合、この成果物を master に取り込むPRが必要（Vercelでリポ連携する場合は本番ブランチ設定も）

### デプロイ対象
| パス | 役割 |
|---|---|
| `vercel-deploy/creative/index.html` | 管理画面（自己完結HTML・Canvasで帯合成・localStorage保存） |
| `vercel-deploy/vercel.json` | `/` → `/creative` リダイレクト設定 |
| `vercel-deploy/README.md` | デプロイ手順（安全な共存方法の注意含む） |

### 管理画面の再生成（内容を更新したいとき）
```bash
cd dashboard && python3 build_dashboard.py     # creative.html を生成
cp creative.html ../vercel-deploy/creative/index.html
```
依存: `pip install pillow numpy` ＋ 日本語フォント（`fonts-noto-cjk`）。素材はリポジトリ直下の `*.jpg`。

---

## 2. これまでに作ったもの（文脈）

### A. サムネ改善パイプライン（`thumbgen/`）— 実装済み・動作確認済み
- `overlays.py` … 帯デザイン **10種**（推奨 `bottom_scrim` ＋ `lower_third`/`top_band`/`frosted_bar`/`corner_tag`/`editorial`、目立つ系 `bold_bar`/`billboard`/`burst`/`ribbon`）
- `improve.py` … 低情報画像の改善（暗い/白飛び/眠い→補正、破損相当→動画再抽出フラグ）
- `enrich.py` … 全カタログを定期エンリッチ。**`creative_config.json` を読み** id別に design/salon/area/badge/enabled/source を反映 → `enriched/<hash>.jpg` → `thumbnail_override` upsert。安全ガード・段階ロールアウト・content-hash差分。`GOOGLE_SHEETS_KEY_JSON` があれば live、無ければ dry-run。
- `build_results_index.py` … 更新結果の一覧（`enriched/RESULTS.md`・`index.html`・共有ギャラリー）
- `.github/workflows/thumbnail-enrich.yml` … 毎日 JST 6:40（autofix後段）。secret未設定ならdry-runで無害。

### B. 管理画面（`dashboard/`）
- `creative.template.html` ＋ `build_dashboard.py` … プロトタイプ生成。一覧グリッド＋詳細ドロワー（10デザインをライブCanvasプレビューで選択・文言/バッジ編集・有効トグル・**画像ソース選択=入稿/動画別フレーム/AI生成**）＋検索/絞り込み＋一括操作＋`creative_config` 書き出し。
- `IMPLEMENTATION_PLAN.md` … 本番化計画（データモデル `creative_config`＋`source_url`、`/api/creative` の GET/POST、保存先A=repoコミット/B=Sheet、フェーズ）。**まず読むべき設計書**。

### C. 公開済み Artifact（共有可・参考）
- 管理画面プロトタイプ: https://claude.ai/code/artifact/e2309957-9d8c-49af-9833-b7c2a11742d9
- 広告CR デザイン方向6案: https://claude.ai/code/artifact/427ff822-f247-4f6b-990b-5cd93c5e8d26
- 更新結果 一覧: https://claude.ai/code/artifact/c5c93a15-9c29-4d73-a0f5-8e49e56e66ea
- パターン説明資料: https://claude.ai/code/artifact/e07ea1f4-7e52-41bc-9cdb-50ea65f931ff

---

## 3. デプロイの先（本番化・任意）

`IMPLEMENTATION_PLAN.md` の通り、疎結合設計:
```
管理画面 /creative → creative_config(JSON or Sheet) → enrich.py(帯合成) → thumbnail_override → Meta配信
```
- パイプライン側（enrich.py）は **creative_config 対応済み**。管理画面はconfigを書くだけで本番反映できる。
- 次の実装: `GET /api/creative`（フィード＋results.json＋config結合で一覧）→ `POST /api/creative`（保存＝GitHubコミット）→ 保存後に `thumbnail-enrich.yml` を `workflow_dispatch` で起動。
- 静的プロトタイプの `creative.html` を Next.js の `/creative` へ移植すれば、実データ連携版になる。

## 4. 未確定（ユーザー確認事項）
- 既存 `hairbook-dashboard` の中身を上書きしてよいか（§0の確認）。
- `creative_config` 保存先 A（repoコミット・推奨）/ B（Sheet）。
- サロン名の専用列を用意するか（`title` はstaff名連結のため）。
- プレビューをCanvas近似のみか、公開前にサーバ生成実画像も見せるか。
