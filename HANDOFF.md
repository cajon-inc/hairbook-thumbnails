# 引き継ぎ — カタログサムネ改善（2026-07-23 更新）

> **前提**: 旧HANDOFF（「/creative のVercel公開が残タスク」）は**完了済み**。本書が最新版。
> 次の主テーマ＝**「画像改善」を別アプローチで試す**。そのための現状全部入りドキュメント。

---

## 0. 現在地（TL;DR）

- 管理画面は **https://hairbook-dashboard.vercel.app/creative で公開中**（認証なし・localStorage保存のプロトタイプ）
- 帯デザインは **新10種に全面刷新済み（管理画面のみ）**。本番合成側 `thumbgen/overlays.py` は**旧10種のまま＝未移植**
- 「動画から別フレーム」は**擬似実装**（元画像のクロップ違い）。実動画からの抽出は未実装
- 「AI生成」ボタンは**ダミー**（canvasフィルタ1種）。← **画像改善の"別の方法"はここが主戦場**
- 実装ブランチ: `claude/catalog-thumbnail-improvement-xw8vo2`（未マージ）。**cajon-inc本体へはpush不可** → fork `Mickey-Takeshi/hairbook-thumbnails` に全push済み（最新 6348b61）

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

- 一覧グリッド24件（ダミーサロン名）＋詳細ドロワー。編集は localStorage（`hb_creative_cfg_v1`）
- **画像ソース**: 入稿（ファイル）/ 動画から別フレーム / AI生成（ダミー）。選択・切替はドロワーの横スクロール帯
- **「動画から別フレーム」= 擬似フレーム**: 実動画は使わず、元画像から `[縦位置, ズーム1.45〜2.4, 横位置]` の24プリセット（超過分は黄金比で無限生成）で4:5クロップ。クリックごとに6枚追加・連番ラベル。品質対策済み: 非同期レース(id捕捉)・連打二重生成(await前に連番予約)・canvas幅840px上限・親画像から再切り出し(劣化重ね掛け防止)
- **書き出し**: 「設定を書き出す」→ `creative_config.json` 形式 `{id: {design, salon, area, badge, enabled, source, source_params}}`。フレーム選択時は `source_params:{oy,zoom,ox}` が付く（パイプラインでの再現用・enrich側は未実装）
- 全体リセットは編集・ソース選択・生成候補・連番を全破棄

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
- 管理画面の「AI生成」ボタンは canvasの saturate/contrast/vignette 1発のみの**サンプル**

### 未実装（「別の方法」の候補領域）
1. **実動画からのフレーム抽出**（現行autofixは動画再抽出を"フラグ"するだけ。管理画面の別フレームも擬似クロップ）
2. **生成AI活用**: 9:16アウトペイント（ストーリーズ見切れ対策 → 素材4:5 vs 9:16サイズ不一致問題）、超解像、背景整理
3. **Claude Vision等での品質判定**（現行は輝度統計のみ。構図・顔・文字焼き込みの判定はない）
4. 焼き込みキャプション検出（あれば自動で fade 強め or クロップ位置調整、という連携も可能）
- 過去の設計判断: 本体の日次約1,385枚は**生成AIを使わずコード合成が正解**（日本語文字の正確性・コスト）。AIが効くのは「デザインたたき台/9:16アウトペイント/動的コピー」の3箇所 — 「別の方法」検討時はこの線引きの再評価から

## 5. 効果計測の前提（変えないこと）

- 主指標 CTR/CPM、従指標 Meta実測 add_to_cart。期間比較は計測ロジック固定
- カタログBotの「メタCPA/CV」は実測の約1.5倍に過大（絶対値は信用しない・トレンドのみ有効）
- 広告アカウントのスコープは HB_01/02/07（カタログはHB_02）

## 6. 未確定・残タスク一覧

- [ ] 帯デザイン新10種のラインナップ承認（削る/調整）→ overlays.py 移植
- [ ] 画像改善の「別の方法」検討・実装 ←次テーマ
- [ ] creative_config 保存先 A(repoコミット・推奨)/B(Sheet) の決定、`GET/POST /api/creative`（設計は `dashboard/IMPLEMENTATION_PLAN.md`）
- [ ] `source_params` のenrich側実装（フレーム再現クロップ）
- [ ] cajon-inc/hairbook-thumbnails への write権限付与 or forkからPR（現在 fork にのみ最新がある）
- [ ] `/creative` の認証ガード要否（既存docs系は sales_login.html リダイレクトガードあり）
- [ ] サロン名専用列（`title` はstaff名連結のため）

## 7. 参考

- 設計書: `dashboard/IMPLEMENTATION_PLAN.md`（本番化の全体設計）
- 管理画面プロトタイプArtifact: https://claude.ai/code/artifact/e2309957-9d8c-49af-9833-b7c2a11742d9 （旧デザイン時点）
- コミット履歴（本ブランチ直近）: 6348b61 帯デザイン刷新 / ffd7483 レビュー修正 / 9e2cc04 フレーム振り幅拡大 / 0692446 フレーム生成拡張
