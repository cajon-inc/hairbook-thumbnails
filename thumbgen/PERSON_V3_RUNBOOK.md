# 人物画像版V3 制作・事前チェック Runbook

人物V3の制作、QA、人手承認、preflight、本番公開、復元、結果確認を再現するRunbook。本番変更は `creative_batch.py apply / rollback` の明示操作だけが行い、生成やQAコマンドは `thumbnail_override` を変更しない。

## 1. sample 3店舗のdry-run

```bash
python3 thumbgen/person_v3.py \
  --manifest dashboard/source_images/person_v3_manifest.sample.json \
  --output-dir dashboard/rollout_output/person-v3-sample

python3 thumbgen/creative_rollout.py qa \
  --manifest dashboard/source_images/person_v3_manifest.sample.json \
  --render-index dashboard/rollout_output/person-v3-sample/render_index.json \
  --output dashboard/rollout_output/person-v3-sample/qa_report.json

python3 thumbgen/creative_rollout.py init-review \
  --manifest dashboard/source_images/person_v3_manifest.sample.json \
  --render-index dashboard/rollout_output/person-v3-sample/render_index.json \
  --qa-report dashboard/rollout_output/person-v3-sample/qa_report.json \
  --output dashboard/rollout_output/person-v3-sample/review.json \
  --html dashboard/rollout_output/person-v3-sample/review.html

python3 thumbgen/creative_rollout.py preflight \
  --manifest dashboard/source_images/person_v3_manifest.sample.json \
  --render-index dashboard/rollout_output/person-v3-sample/render_index.json \
  --qa-report dashboard/rollout_output/person-v3-sample/qa_report.json \
  --approvals dashboard/source_images/person_v3_approvals.sample.json \
  --override-snapshot dashboard/source_images/thumbnail_override_snapshot.sample.json \
  --output-dir dashboard/rollout_output/person-v3-sample/preflight \
  --dry-run
```

`review.html`では、元source、1080×1350完成バナー、360×450プレビューを並べて確認できる。チェック結果はJSONとして書き出す。

## 2. 本番フィードの読み取り専用snapshot

```bash
GOOGLE_SHEETS_KEY_JSON='...' python3 thumbgen/creative_inventory.py \
  --google-sheet \
  --output-dir dashboard/private_snapshots/<timestamp>
```

出力:

- `inventory.json` / `inventory.csv`
- `thumbnail_override_snapshot.json`
- `summary.json`

`dashboard/private_snapshots/`はgitignore対象。元URL、内部ID、override対応をpublic repoへcommitしない。

CSV exportを入力にする場合:

```bash
python3 thumbgen/creative_inventory.py \
  --input-csv /secure/path/feed.csv \
  --override-csv /secure/path/thumbnail_override.csv \
  --output-dir dashboard/private_snapshots/<timestamp>
```

## 3. manifestの必須要素

- `design_version`: `person_v3_layered_v1`
- source path／掲載ページURL／元画像URL／SHA-256
- salon IDと対象product ID
- 正本から確定したエリア、店舗名、アクセス、訴求、CTA
- 4:5 crop用のfocal point、必要な場合だけ安全範囲内のzoom
- themeは `ink_gold` または `sage`

人物sourceを変更した場合はmanifest hashが変わるため、既存QAと承認はpreflightで無効になる。

## 4. Gate

1. `qa`: ファイル、source hash、copy hash、1080×1350、JPEG、Exif、360×450、重複等を自動確認。
2. `init-review`: 全unique assetを人が確認し、全項目をtrueにして承認者と日時を記録。
3. `preflight`: QA、承認、product mapping、公開URL、現行override snapshotをまとめて確認し、publish／rollback manifestを生成。

本番preflightでは次が必須。

- manifest `environment="production"`
- `product_ids` が空でない
- decisionが `approved`
- 全人手チェックがtrue
- HTTPSのpublic URL
- productionのoverride snapshot
- assetのSHA-256一致

`approved_for_dry_run`は本番preflightでは不合格になる。

## 5. complete banner

`enrich.py`へ渡すconfig例:

```json
{
  "<product_id>": {
    "source": "edited_banner",
    "source_url": "https://...",
    "source_params": {
      "asset_id": "<asset id>",
      "asset_version": 1,
      "render_mode": "complete_banner",
      "approval_status": "approved",
      "asset_sha256": "<sha256>"
    }
  }
}
```

`complete_banner`は以下を満たさない場合、処理を失敗させる。

- liveでは `approval_status="approved"`
- asset SHA-256一致
- 1080×1350

条件を満たす場合だけ、`improve.py`と`overlays.py`を通さず、完成バナーを二重合成なしで出力する。

## 6. テスト

```bash
python3 -m unittest discover -s thumbgen/tests -v
```

テストには、renderer、QA、未承認ブロック、dry-run preflight、inventory分類、complete banner二重合成防止を含む。

## 7. 本番公開と復元

公開は、承認済みassetだけを含むproduction manifestを固定してから、必ず `plan` → SHA確認 → `apply` の順で行う。

```bash
python3 thumbgen/creative_batch.py plan \
  --publish-manifest /secure/path/publish_manifest.json \
  --override-snapshot /secure/path/thumbnail_override_snapshot.json \
  --inventory /secure/path/inventory.json \
  --output /secure/path/execution_plan.json

GOOGLE_SHEETS_KEY_JSON='...' python3 thumbgen/creative_batch.py apply \
  --publish-manifest /secure/path/publish_manifest.json \
  --confirm-sha256 '<planが表示したmanifest SHA-256>' \
  --actor '<実行者>' \
  --output-dir /secure/path/publish-run
```

`apply` は次を強制する。

- `production / ready_to_publish / HB_02` のmanifestだけを受理。
- `pilot / wave / full` の公開範囲を必須化。
- manifest SHA-256の完全一致。
- preflight後に現行overrideが変わっていないことを全IDで確認。
- 書き込み前の `thumbnail_override` 全量snapshot。
- 対象行だけを一括更新し、read-back検証。
- append-onlyの `creative_publish_events`。
- 更新またはevent記録が失敗した場合の自動復元。

後日、公開バッチ単位で戻す場合:

```bash
GOOGLE_SHEETS_KEY_JSON='...' python3 thumbgen/creative_batch.py rollback \
  --batch-id '<公開batch ID>' \
  --confirm-batch-id '<同じ公開batch ID>' \
  --actor '<実行者>' \
  --reason '<復元理由>' \
  --output-dir /secure/path/rollback-run
```

GitHub Actionsでは `.github/workflows/person-v3-publish.yml` を手動実行する。`creative-production` environmentのrequired reviewerを設定し、`full` は公開または理由付き保留で全active product IDを解決できていない限り失敗させる。

## 8. ダッシュボードと配信結果

- `/creative` の「事前チェック」で、元人物画像、完成バナー、360×450を比較し、8項目をasset単位で承認する。
- 「実行・復元」は全件preflightが揃うまで無効。
- 公開eventはGoogle Sheetを即時参照し、翌朝の結果更新でSupabase監査表にも同期する。
- `hairbook-dashboard/scripts/fetch_creative_rollout_performance.py` が、HB_02カタログの商品別Meta実績を画像versionへ結合する。
- 切替日、不完全日を除外し、切替前28日、切替後7日・14日で比較する。
- CTRとCPMは `clicks / impressions`、`spend / impressions × 1000` をサロン単位で再計算する。
- 従指標は商品breakdownで実値が得られる `onsite_web_add_to_cart` だけを使い、Bot CPA/CVは使わない。
