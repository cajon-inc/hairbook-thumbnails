# クリエイティブ管理画面 実装計画

- 目的: カタログサムネを一覧化し、**サロン別のゼロベース生成画像1〜2案から切替**でき、切替後の配信結果まで振り返れる管理画面。
- 参照: 既存ダッシュボード `hairbook-dashboard.vercel.app/creative`（Next.js/Vercel想定）の `/creative` に載せる。
- 現行プロトタイプ: `dashboard/creative.html`（クリック可能・Canvas合成）は「現在画像＋ゼロベース生成案1〜2」と「画像設定／配信結果」の2タブへ更新済み。生成画像と指標はAPI未接続のため、画面検証用デモとして明示している。
- サロン情報と公式リンク先から画像をゼロベースで個別生成する方針は、
  [`ZERO_BASE_IMAGE_GENERATION_PLAN.md`](ZERO_BASE_IMAGE_GENERATION_PLAN.md) を正とする。

---

## 1. 全体像（データの流れ）

```text
[管理画面 /creative]
  ├─ 画像設定: 現在画像＋生成案1〜2の比較／承認／切替
  └─ 配信結果: 切替履歴／画像バージョン別KPI
        │
        ├─ private creative config / asset metadata
        ├─ creative_publish_events（不変の切替履歴）
        └─ 承認済み生成画像だけpublic保存
                         │
                         ▼
[enrich.py] 同一帯デザインで合成 → [thumbnail_override] → [Meta]
                                                             │
                                                             ▼
                    [Meta product_id日次実績] → [creative_product_daily]
                                                             │
                    [creative_publish_events] ──時系列結合───┘
                                                             │
                                                             ▼
                                            [/creative 配信結果]
```

**要点**: 画像切替の正本はprivate設定、配信画像の正本はpublic JPG、結果紐付けの正本は `creative_publish_events`。Metaから画像URLは返らないため、切替履歴と `product_id × 日付` を結合して画像バージョン別実績を作る。

---

## 2. データモデル

### 一覧アイテム（GET用・読み取り）

既存データを結合して返す:
| 項目 | 出所 |
|---|---|
| id / image_link | フィード `入稿用データフィード_ローカル商品` |
| salon（既定） | フィード生成元の `salon_name`。`title` の逆解析はしない |
| area（既定） | `address.city`（例「大阪市中央区」） |
| verdict（情報判定） | `enrich` の `results.json`（ok/low_info/broken） |
| 現在画像 | フィードと `thumbnail_override` の有効URL |
| 生成案1〜2 | private asset metadataの最新承認可能版 |
| 現在の設定 | private `creative_config` |
| 配信結果 | `creative_product_daily` を画像バージョン別に集計 |

### creative_config（POST用・唯一の個別設定）

```json
{
  "44528_01KJ...": { "design": "bottom_scrim", "salon": "hair salon Lumière",
    "area": "東京都渋谷区・表参道", "badge": "", "enabled": true,
    "source": "generated",
    "source_url": "https://raw.githubusercontent.com/.../<anonymous-hash>.jpg",
    "source_params": {"asset_id": "<anonymous id>", "candidate_slot": "pattern_1",
      "asset_version": 1, "representation": "concept_image"} },
  "44530_01KQ...": { "enabled": false }
}
```
- `design`: 新10種。`bottom_scrim`（標準）/ `caption` / `magazine` / `letterbox` / `namecard` / `tategaki` / `frameline` / `polaroid` / `poster` / `plate`。
- `source_url`: 管理画面で選んだ**承認済みゼロベース生成画像**のホスト先。生成案1または2だけを指定する。
- 現在画像へ戻す場合は、公開前に保存した直前overrideを復元する。`source_url` を単純削除してautofix済み画像を失わない。
- 省略キーは既定にフォールバック（`enabled` 既定 true、`design` 既定 bottom_scrim）。

### 画像ソースのホスティング

- 切替候補は「生成案1」「生成案2」の最大2案。入稿、動画キャプチャ、疑似フレーム、既存画像のAI加工は扱わない。
- 承認済み最終JPGだけを匿名ハッシュ名でpublic画像リポジトリへ保存し、`source_url` に格納する。
- ブリーフ、プロンプト、候補履歴、承認者、切替履歴、配信実績はprivate側へ保存する。
- 再生成時は既存候補を上書きせず、同じ `candidate_slot` の `asset_version` を増やす。

### 画像切替履歴

`creative_publish_events` に、対象サロン、対象商品IDスナップショット、旧／新asset、候補番号、asset/design/copy version、公開時刻、フィード反映確認時刻、集計開始日、公開者、ロールバック理由を追記する。既存イベントは上書きしない。

### 配信実績

Metaの `product_id` 日次ブレイクダウンから spend / impressions / clicks / actions を取得し、`creative_publish_events` へ時系列結合して `creative_product_daily` を作る。切替日は旧新が混在し得るため除外し、最初の完全な配信日から集計する。

---

## 3. アーキテクチャ

### フロント（Next.js `/creative`）

プロトタイプ `creative.html` をReactに移植。構成:
- **一覧グリッド**: カード（現在画像・生成案番号・配信開始日・CTR・切替前比・impressions・状態チップ）
- **画像設定タブ**: 現在画像（比較／復元用）＋生成案1＋任意の生成案2。帯プレビュー、根拠、QA、承認、切替
- **配信結果タブ**: 切替タイムライン、画像バージョン別KPI、前後比較、案1/2比較、holdout比較、除外日と母数
- **絞り込み/検索**: 画像種別・結果状態・有効/無効・要改善・サロン名/エリア検索
- **一括操作**: 選択に対しデザイン一括適用・有効/無効
- **公開**: 承認済み生成案をPOST → publish event作成 → パイプライン起動

画像ソース欄から、旧プロトタイプの「入稿」「動画から別フレーム」「AI生成（フィルタ加工）」は削除済み。

### プレビュー（2層）

- **即時**: ブラウザ内Canvasで合成（プロトタイプの `overlays.py`→JS移植をそのまま流用）。編集の即応性。
- **正**: 公開時にサーバ側 `overlays.py`(Pillow) が生成した `enriched/<hash>.jpg` が最終成果物（Canvasは近似プレビュー）。

### 保存先

- private: `creative_config`、ブリーフ、プロンプト、全候補、QA、承認、`creative_publish_events`、`creative_product_daily`。
- public: 承認済み最終JPGと匿名アセットIDだけ。
- repoコミット案を採用する場合も、public `hairbook-thumbnails` へprivateメタデータを置かない。

### API（Next.js Route Handlers / Vercel Functions）

- `GET /api/creative` … 一覧アイテム（§2）を返す（フィード＋results.json＋config結合）
- `POST /api/creative/:salon_id/generate` … 生成案1または2を1候補ずつ生成
- `POST /api/creative/:salon_id/approve` … QA済み候補を承認
- `POST /api/creative/:salon_id/publish` … 差分config保存＋publish event作成＋ワークフロー起動
- `POST /api/creative/:salon_id/rollback` … 直前画像を復元し、rollback eventを作成
- `GET /api/creative/:salon_id/performance` … 画像バージョン別配信実績と比較を返す

---

## 4. パイプライン側（現状と必要変更）

`thumbgen/enrich.py` は既に `creative_config.json` を読み、id別に
`design / salon / area / badge / enabled` を反映してエンリッチする（`enabled:false` は帯を付けない）。

ただし、生成画像の承認検証、画像バージョン、publish event、直前overrideへのロールバック、Meta実績取得は未実装。新10デザインも `overlays.py` 未移植のため、現状のまま本番接続はしない。

---

## 5. フェーズ

1. **実データ読み取り**: フィード＋privateブリーフ＋configを結合。
2. **生成案1〜2**: ゼロベース生成、QA、承認。候補上限を2へ固定。
3. **UI更新（プロトタイプ完了）**: 入稿・動画フレーム・フィルタ加工を削除し、「画像設定」「配信結果」の2タブを実装。本番API接続はPhase 4以降。
4. **保存と公開**: private config保存、public JPG保存、publish event作成、enrich起動。
5. **実績取得**: Meta `product_id` 日次実績＋ATCを取得し、画像バージョンへ時系列結合。
6. **振り返り**: 前後比較、案1/2比較、holdout比較、母数・除外日表示。
7. **運用**: 承認、段階ロールアウト、直前overrideへの即ロールバック。

---

## 6. 未確定・要決定

- private config／publish events／日次実績の保存先。
- Metaアカウントの集計タイムゾーンと「完全日」の確定方法。
- 最小impressions・最低観測日数など、結果を参考値から判定可能へ切り替える基準。
- サロン名の専用値をフィード生成前データからどう渡すか（`title` は使わない）。
- プレビューをCanvas近似のみにするか、公開前にサーバ生成の実画像も見せるか。
- 既存 `hairbook-dashboard` リポへのアクセス（このセッションに追加できれば直接移植可能）。

---

## 7. このリポジトリの関連物

- `dashboard/creative.html`（生成案1〜2・切替履歴・サンプル配信結果を含む現行プロトタイプ）／ `creative.template.html`＋`build_dashboard.py`（生成）
- `thumbgen/enrich.py`（creative_config対応済みパイプライン）／ `overlays.py`（旧10デザイン）／ `improve.py`（低情報改善）
- `thumbgen/build_results_index.py`（結果一覧）／ `.github/workflows/thumbnail-enrich.yml`（定期実行）
