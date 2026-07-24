# 引き継ぎ — カタログサムネ改善（2026-07-23 更新）

> **前提**: 旧HANDOFF（「/creative のVercel公開が残タスク」）は**完了済み**。本書が最新版。
> 次の主テーマ＝**「画像改善」を別アプローチで試す**。そのための現状全部入りドキュメント。

---

## 0. 現在地（TL;DR）

- 管理画面は **https://hairbook-dashboard.vercel.app/creative で公開中**（認証なし・localStorage保存のプロトタイプ）
- 帯デザインは **新10種に全面刷新済み（管理画面のみ）**。本番合成側 `thumbgen/overlays.py` は**旧10種のまま＝未移植**
- 画像切替は **「現在画像＋ゼロベース生成案1〜2」だけ**へ更新済み。入稿・動画キャプチャ・疑似フレーム・既存画像のAI加工は管理画面から撤去
- 生成案1〜2はサロン名・エリアをseedに0から描くCanvasデモ。実運用のサロン情報／公式リンク調査と画像生成APIは未接続
- 詳細ドロワーに **「画像設定」「配信結果」**の2タブを実装。切替イベントをlocalStorageへ追記し、画像別CTR/CPM/Meta実測ATCのサンプル比較と履歴を確認可能
- サンプル指標はUI上で **Meta未連携**と明示。本番は公開履歴とMeta `product_id` 日次実績を結び、画像バージョン別に振り返る
- 実装ブランチ: `claude/catalog-thumbnail-improvement-xw8vo2`（未マージ）。**cajon-inc本体へはpush不可** → fork `Mickey-Takeshi/hairbook-thumbnails` へpush（履歴は `git log` 参照）

## 1. リポジトリ・権限・デプロイ経路（重要な落とし穴）

| 項目 | 内容 |
|---|---|
| 実装リポ | `cajon-inc/hairbook-thumbnails`・ブランチ `claude/catalog-thumbnail-improvement-xw8vo2` |
| ローカル | `/Users/takes/株式会社Cajon/hairbook-thumbnails`（remote `fork` 設定済み） |
| push権限 | ローカルのGitHub認証（Mickey-Takeshi）は cajon-inc に **read-only**。SSH鍵なし・招待なし。**push先は fork** (`git push fork <branch>`)。本体へ戻すには write付与 or forkからPR |
| 公開経路 | `/creative` の実体は **別リポ `cajon-inc/Hairbook_Dashboard` の `creative/index.html`**（ローカル: `/Users/takes/株式会社Cajon/hairbook-dashboard`）。main へ push → GitHub Actions `deploy.yml` → Vercel 本番 |
| ⚠️ 禁止 | `vercel-deploy/` を **CLIで直接デプロイしない**こと。Vercelプロジェクト `hairbook-dashboard` はGit未接続で、直デプロイすると既存の売上ダッシュボード(sales.html等)が消える |
| 検証 | デプロイ後 `gh run list --workflow=deploy.yml` と `curl https://hairbook-dashboard.vercel.app/creative` で確認 |

### 管理画面の更新手順（確立済み）

```bash
cd /Users/takes/株式会社Cajon/hairbook-thumbnails/dashboard
python3 build_dashboard.py                       # creative.html 生成（doctype等はテンプレに含まれる）
cp creative.html /Users/takes/株式会社Cajon/hairbook-dashboard/creative/index.html
cp creative.html ../vercel-deploy/creative/index.html   # リポ内の控えも同期
cd /Users/takes/株式会社Cajon/hairbook-dashboard && git add creative/index.html && git commit && git push
```

## 2. 管理画面（dashboard/creative.template.html）の機能状態

- 一覧グリッド24件（ダミーサロン名）＋詳細ドロワー。編集は `hb_creative_cfg_v1`、ソース選択は `hb_creative_source_choice_v1`、切替履歴は `hb_creative_publish_events_v1` としてlocalStorage保存
- **画像ソース**: 現在画像（比較・復元用）／生成案1／生成案2の最大3枠だけ。生成案は元画像を参照せず、サロン名・エリア・商品IDをseedにCanvasで0から描く画面検証用コンセプト画像
- **画像設定タブ**: 画像選択、帯10デザイン、サロン名、エリア、特典、有効状態を編集。生成案選択は再読込後も復元
- **配信結果タブ**: 「切替を記録（デモ）」で旧→新ソース、商品ID、asset_id、候補番号、version、公開時刻、翌日の集計開始日を追記。現在画像／生成案1／生成案2のサンプルImp./Clicks/CTR/CPM/ATCと切替履歴を表示
- 一覧カードにも切替済み画像とサンプルCTRを表示。サンプル値は商品ID×画像キーから決定論的に作り、Meta未連携であることを画面に明示
- **書き出し**: 生成案選択時は `source:"generated"` と `source_params:{asset_id,candidate_slot,asset_version,representation,demo}` を出力。実画像URLとenrich側は未接続なので本番投入禁止
- 全体リセットは編集・ソース選択・切替履歴を全破棄。個別リセットは切替履歴を保持

## 3. 帯デザイン（2026-07-23 全面刷新・管理画面のみ）

旧10種（黒帯＋極太ゴシック＋金ピン＋赤系Loud）を廃止。新システム:
- パレット: 墨 `#221c15` / 生成り `#f5f1e8` / くすみ金 `#b08d57`（赤系全廃）
- 書体: ゴシック＋明朝（`MINCHO`定数）の2声・字間(`spTxt`)・アイコン全廃
- 新キー: `bottom_scrim`(スタンダード★・キー名は互換のため旧のまま) / `caption` / `magazine` / `letterbox`(シネマ) / `namecard` / `tategaki`(縦書き) / `frameline` / `polaroid` / `poster` / `plate`
- **焼き込みキャプション対策**: 元画像の下部に店名等が焼き込まれた素材が多い（例: `031cac364ee0.jpg` の「BELLA【ベラ】阿倍野駅1分」）。旧黒帯は偶然隠していた。新デザインは `fade()` を内蔵し下部を沈める（シネマ/ポラロイドは構造的に覆うため不要）。**overlays.py移植時も必須の知見**

### ⚠️ 本番未接続

`thumbgen/overlays.py` は旧10種のまま。`enrich.py` は `overlays.LAYOUTS[design]` を直引きするため、**新キーのconfigを投入すると KeyError**。ラインナップ承認後に overlays.py へPillow移植すること（fade内蔵も）。それまで書き出しJSONは本番投入しない。

## 4. 画像改善の現状 ← 次テーマ「別の方法」の対象

### 現行実装（ルールベース・実装済み）

- `thumbgen/improve.py`: 輝度の平均/標準偏差で `broken`(std<18・ほぼ単色→静止画では復元不可・動画再抽出フラグ) / `low_info`(眠い std<42・暗い mean<62・白飛び mean>205 → オートコントラスト＋暗部持ち上げ) / `ok` を判定して補正。しきい値は feed_qa / frame_quality と整合
- `enrich.py` が improve→帯合成→`thumbnail_override` upsert の順で毎日実行（CI: `.github/workflows/thumbnail-enrich.yml` JST6:40、secret `GOOGLE_SHEETS_KEY_JSON` 無しならdry-run）
- 管理画面の旧「AI生成」フィルタは撤去済み。現行の生成案は元画像を加工しないゼロベースCanvasデモ

### 未実装（「別の方法」の候補領域）

1. **実動画からのフレーム抽出**（管理画面の画像切替候補からは除外。壊れたサムネを直すautofix系の別タスクとしてのみ残す）
2. **生成AI活用**: 9:16アウトペイント（ストーリーズ見切れ対策 → 素材4:5 vs 9:16サイズ不一致問題）、超解像、背景整理
3. **Claude Vision等での品質判定**（現行は輝度統計のみ。構図・顔・文字焼き込みの判定はない）
4. 焼き込みキャプション検出（あれば自動で fade 強め or クロップ位置調整、という連携も可能）
- 過去の設計判断: 本体の日次約1,385枚は**生成AIを使わずコード合成が正解**（日本語文字の正確性・コスト）。AIが効くのは「デザインたたき台/9:16アウトペイント/動的コピー」の3箇所 — 「別の方法」検討時はこの線引きの再評価から
- **2026-07-23 追加**: サロン情報と公式リンク先の確認済み情報から、サロン単位で画像をゼロベース生成する計画を
  [`dashboard/ZERO_BASE_IMAGE_GENERATION_PLAN.md`](dashboard/ZERO_BASE_IMAGE_GENERATION_PLAN.md) に整理済み。UIの動作デモは実装済みだが実データ／生成APIは未接続で、次はPhase 0（権利・保存先・承認者の確定）→Phase 1（8サロン程度のブリーフPoC）。
- **2026-07-23 方針更新**: 生成候補は1〜2案に固定。公開ごとに `creative_publish_events` を残し、Meta `product_id` 日次実績を時系列結合して画像別の配信結果を表示する。切替日は比較から除外する。

## 5. 効果計測の前提（変えないこと）

- 主指標 CTR/CPM、従指標 Meta実測 add_to_cart。期間比較は計測ロジック固定
- カタログBotの「メタCPA/CV」は実測の約1.5倍に過大（絶対値は信用しない・トレンドのみ有効）
- 広告アカウントのスコープは HB_01/02/07（カタログはHB_02）
- Metaから画像URLは返らないため、画像別実績はpublish eventと `product_id × 日付` の時系列結合で作る。切替日・不完全日は除外

## 6. 未確定・残タスク一覧

- [ ] 帯デザイン新10種のラインナップ承認（削る/調整）→ overlays.py 移植
- [ ] サロン別ゼロベース画像生成: 計画済み。Phase 0/1の実装 ←次テーマ
- [x] 現行UIの入稿・動画フレーム・フィルタ式AI生成を撤去し、生成案1〜2のデモへ置換
- [x] 「配信結果」タブとlocalStorage版の切替履歴／サンプル指標を実装
- [ ] 永続 `creative_publish_events` とMeta商品別日次実績を実装し、サンプル指標を実測値へ置換
- [ ] privateのcreative_config／生成メタデータ／publish events／日次実績の保存先を決定
- [x] プロトタイプの `source_params` を生成asset_id / candidate_slot / asset_version用へ変更
- [ ] enrich/API側で生成assetの `source_url` と `source_params` を処理
- [ ] cajon-inc/hairbook-thumbnails への write権限付与 or forkからPR（現在 fork にのみ最新がある）
- [ ] `/creative` の認証ガードと承認者記録を実装（既存docs系は sales_login.html リダイレクトガードあり）
- [ ] サロン名専用列（`title` はstaff名連結のため）

## 7. 参考

- 設計書: `dashboard/IMPLEMENTATION_PLAN.md`（本番化の全体設計）
- 管理画面プロトタイプArtifact: https://claude.ai/code/artifact/e2309957-9d8c-49af-9833-b7c2a11742d9 （旧デザイン時点）
- コミット履歴: `git log --oneline -10` を参照
