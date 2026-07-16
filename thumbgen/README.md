# thumbgen — カタログ広告サムネイル改善プロジェクト (v2)

現行の「壊れたサムネだけ直す」自動修正パイプラインを、**全サムネを継続的により良くする**基盤へ
アップデートするためのツール群。企画・PoC段階（本番未接続）。

- ステータス: PoC / 提案段階（上長承認・意思決定待ち）
- 開発ブランチ: `claude/catalog-thumbnail-improvement-xw8vo2`
- 位置づけ: 既存 `cajon-inc/hairbook-ad-local-catalog` の autofix パイプラインの **拡張**（新規基盤ではない）

---

## 2つの方針

| | 方針1: フレーム品質の底上げ | 方針2: 情報リッチ化（帯） |
|---|---|---|
| 現状 | **壊れたサムネのみ**動画から再抽出 | 加工なし（素材そのまま配信） |
| 目標 | **全サムネ**で「より良いフレーム」を選ぶ | **全サムネ**にサロン名・エリア等を共通表示 |
| 実装 | `frame_quality.py`（品質スコア＋AI判定） | `band_overlay.py`（帯合成） |

> **重要（PoCで判明）**: この2つは独立ではなく**連結している**。既存サムネのほぼ全てに
> サロンが動画へ焼き込んだ文字（「¥5,500」「極上ヘッドスパ」、時に「スタイリスト募集」＝求人）が
> 入っている。現行 v3 選別が「情報量(std)＝文字密度」を高評価するため、**価格/告知/求人カードを
> 引き当てやすい**。この上に帯を重ねると二重テキストで破綻する。
> → **方針1で清潔なフレームを選び → 方針2で一貫した帯を載せる**、の順で初めて成立する。

---

## 現行システム（確認済みの前提）

既に本番稼働している「サムネ生成」GitHub Actions：

```
catalog_feed.py            月次でフィード生成（image_link = hairbook サムネURL）
        ↓
feed-qa.yml (毎日 6:07 JST) → feed_qa_check.py --auto-fix
        ↓                        白/黒/単色/低情報を検出（analyze_image）
thumbnail_autofix.py       元動画→ffmpeg 3fps→v3スコアで良フレーム選別
        ↓                        → sha1(id)[:12].jpg を public repo(このrepo)へ push
thumbnail_override タブ     id→raw URL を登録（唯一の真実源）
        ↓
本番フィード H1 ARRAYFORMULA  override を最優先 XLOOKUP → Meta が毎時取得
```

- ホスティング = **このリポジトリ**（`raw.githubusercontent.com/.../master/<hash>.jpg`）。private の catalog repo は raw 配信不可のため public な本 repo を新設済み。
- push 用 PAT `THUMBNAILS_REPO_TOKEN`、フレーム選別 v3、override 数式、`#REF!` スピル注意 等の詳細は
  catalog repo `docs/catalog_thumbnail_override_仕様.md` を参照。

## この新プロジェクトの接続点

`thumbnail_autofix.py`（壊れたものだけ）の**後段に「全件処理」ステップ**を足す：

```
… autofix（壊れたフレームを良フレーム化）
        ↓
【新規】全件パイプライン
        ↓ 1. frame_quality: 各商品の「有効な画像」を評価（清潔フレームを選ぶ / 要改善を抽出）
        ↓ 2. band_overlay : サロン名(access_salon_name)＋エリア(city_name) の帯を合成
        ↓ 3. content-hash で変化時のみ push（差分だけ）
override タブへ upsert → 既存の H1 数式がそのまま配信に反映
```

データは既存フィードにすべて存在（新規収集不要）:
- サロン名 = `access_salon_name` / `salon_name`（`title` は staff 名連結のため直接使わない）
- エリア = `city_name`→`address.city`（例「大阪市中央区」）、`prefecture_name`→`address.region`

---

## 収録物

| ファイル | 役割 |
|---|---|
| `enrich.py` | **本番パイプライン**。全件に推奨レイアウト（下部スクリム）の帯を付与し `enriched/` に出力・override upsert |
| `overlays.py` | 広告CRデザイン方向6案。`bottom_scrim`(推奨)/`lower_third`/`frosted_bar`/`corner_tag`/`editorial`/`top_band` |
| `improve.py` | **低情報画像の改善**。broken=動画再抽出フラグ／low_info=オートコントラスト等で底上げ |
| `build_results_index.py` | 更新結果の一覧生成（`enriched/RESULTS.md`・`index.html`・共有用ギャラリー） |
| `band_overlay.py` | 帯合成（上部帯）。`BandSpec` 差替でパターンA〜D（サロン名/価格/特典/メニュー） |
| `frame_quality.py` | 品質スコアリング（軽量ヒューリスティック＋Claude Vision プラグイン口） |
| `generate_samples.py` / `gen_*` | 各種PoC・資料モックアップ生成 |
| `design_brief.*` / `cr_directions.*` / `build_pdf.sh` | 社内説明資料（HTML/PDF）とビルド |

定期実行は `../.github/workflows/thumbnail-enrich.yml`（毎日 JST 6:40・autofixの後段）。

### 定期エンリッチ（本番パイプライン）
```
元サムネ(<hash>.jpg / autofix再抽出) or フィードの image_link
  → improve: 低情報なら改善（暗い/白飛び/眠い→補正、破損相当→要再抽出）
  → overlays.bottom_scrim: サロン名＋エリアの帯を合成
  → content-hash で変化時のみ enriched/<hash>.jpg を更新
  → thumbnail_override に id→enriched raw URL を upsert（本番H1が最優先参照）
  → results.json → 一覧(RESULTS.md / index.html)
```
- `GOOGLE_SHEETS_KEY_JSON` があれば **live**（全商品）、無ければ **dry-run**（ローカル素材・ダミー文言）。
- 安全ガード（`MIN_PRODUCTS`）・段階ロールアウト（`--rollout`）・即ロールバック（override除去）対応。

### 実行
```bash
pip install -r requirements.txt                 # + 日本語フォント(fonts-noto-cjk)
python3 enrich.py --dry-run                      # ローカル素材で全件エンリッチ → enriched/
python3 build_results_index.py                   # enriched/ の結果を一覧化
python3 overlays.py in.jpg --layout bottom_scrim --salon "サロン名" --area "エリア" -o out.jpg
python3 improve.py in.jpg out.jpg                # 低情報画像の改善だけ試す
```

---

## セーフエリア設計（見切れ対策）

- キャンバス 1080×1350（4:5）。9:16 カバー表示で**左右各 14.8%（≒160px）が見切れる**。
- 文字・ピンは**中央約70%**に収める（`SAFE_INSET_RATIO=0.148`）。長い名前は自動縮小→末尾省略(`…`)。
- 実データに **1080×1920(9:16) や 720×900** の例外が混在 → 寸法決め打ちせず幅から相対計算。
- `samples/safearea_9x16.png` で「帯の文字が見切れ後も残る」ことを実証済み。

## ロールアウト / 安全

- **段階展開**: 一部サロン→問題なければ全展開。一部を旧サムネのまま残し**簡易対照群**に。
- **即ロールバック**: override タブから外せば旧サムネへ即復帰。
- **安全ガード**: 生成失敗時に override を壊さない（`catalog_feed.py` の `MIN_PRODUCTS` と同様の下限）。
- **`#REF!` 厳禁**: 反映は必ず override タブ＋H1数式経由。本番H列への直接書き込みはスピル破壊。
- **スケール**: 全1,385件の DL→合成→push を日次。別ワークフロー化＋並列＋content-hashスキップ前提。

## 未決定（意思決定ポイント）

1. **方針1の "good" 定義**: 清潔な髪型フレームを優先するか（求人/価格カードを避けるか）。AI判定を使うか。
2. 帯デザインの確定（第1弾＝サロン名＋エリアでよいか。色・高さ・フォント）。
3. エリア表記: `city_name`（市区町村）か、都道府県＋市区か、最寄駅か（駅は専用列が無く要抽出）。
4. サロン名の表記ゆれクレンジング規則。
5. 対照群を残すか、ホスティング (A)GitHub raw継続 /(B)GCS等 、開発リソース。
6. Ads Manager「自動トリミング」現在値の確認（画面のみ・要人手）。

> サンプル内のサロン名・エリアは**レイアウト検証用のダミー**。本番は上記フィールドを使う。
