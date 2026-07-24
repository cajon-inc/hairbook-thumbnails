# HB_02 全静止画CR 人物優先V3 差し替え計画

- 作成日: 2026-07-24
- 対象: Hairbook Metaカタログ広告 HB_02
- 目的: カタログの全静止画CRを、サロンページ内の人物画像を優先した最新V3デザインで制作し、事前チェック、段階差し替え、効果確認、ロールバックまで一貫して運用する。
- 関連正本:
  - 素材選定・編集ルール: `SALON_PAGE_PERSON_IMAGE_BANNER_PLAN.md`
  - 管理画面・データ連携: `IMPLEMENTATION_PLAN.md`
  - override運用: `hairbook-ad-local-catalog/docs/catalog_thumbnail_override_仕様.md`

## 0. 着手状況（2026-07-24）

本番Google Sheetを読み取り専用で確認した時点の観測値。

| 項目 | 2026-07-24 12:22 JST |
|---|---:|
| IDがあるフィード行 | 1,169 |
| `in stock` product ID | 1,007 |
| 対象salon ID | 396 |
| サロン単位product | 863 |
| スタイリスト単位product | 144 |
| 着地URL欠損 | 0 |
| `image_link` 欠損 | 0 |
| `thumbnail_override` 全行 | 66 |
| in-stock商品のうちoverride適用 | 26 |

- 読み取り中の在庫同期で、19件が `in stock` から `out of stock` へ変わった。上表は同期後の観測値。
- このため公開対象は固定件数として扱わず、公開直前に日時付きの原子的なsnapshotを再取得する。
- 現時点ではシート／overrideへの書き込みは行っていない。
- 3店舗のsample manifestを使い、人物V3のデータ駆動renderer、自動QA、人手レビュー画面、preflight、publish／rollback dry-run manifestまで実装済み。
- `enrich.py` は `render_mode="complete_banner"` を認識し、承認statusとasset SHA-256が一致した完成バナーだけを帯の二重合成なしで処理できる。

同日15:35 JSTの再取得では在庫同期後の分母が **980 product / 382 salon / 現行override 25 product** へ変化した。固定件数は計画値にせず、認証付き `/creative` がページ読込時に本番Sheetを再集計した値を正とする。

追加実装済み:

- `/creative` を既存Dashboard認証へ接続し、全productの進行、3件の人物V3事前チェック、配信結果、実行・復元gateを実データで表示。
- asset・割当・append-onlyレビュー・公開batch/event・商品日次実績のprivate Supabase表。
- 承認済みmanifestだけを対象に、SHA確認、楽観ロック、全量snapshot、read-back、自動復元を行うpublisher。
- Google Sheetの公開eventを画面へ即時反映し、Meta商品日次を切替前28日・後7/14日へ結合する定期処理。
- パイロット3assetは自動QA済み・人手レビュー待ち。本番画像の変更は0件。

---

## 1. 決定事項

1. 標準CRは、サロンページまたは対象店舗の掲載ページにある既存の人物／スタイル画像を使う。
2. 人物、髪型、髪色、顔を生成・差し替えしない。許可するのは、4:5最適化、軽微な色調補正、背景整理、文字用スクラム、コードによる正確なテキスト合成。
3. デザインは、Fier 大阪梅田案を基準にした **人物画像版V3レイヤード**へ統一する。
4. 店内写真版は通常候補にしない。使用可能な人物画像がない場合も自動で店内版へ切り替えず、`person_source_hold` として現行画像を維持する。店内版を使う場合は例外承認を必須にする。
5. 生成完了から配信へ直結させない。全ての公開assetは、自動QA、人手事前チェック、バッチ公開前確認の3段階を通す。
6. 差し替えは全件一括ではなく、サロン単位の段階公開とする。同一サロンのproduct IDを複数バッチへ分けない。
7. 公開前の現行overrideを必ず保存し、サロン単位で直前画像へ戻せる状態を作ってから差し替える。
8. 画像versionと公開期間を不変ログへ残し、配信結果を切替前後および未切替群と比較できるようにする。

### 標準デザイン

- 出力: JPEG、sRGB、Exifなし、1080×1350px。
- 写真: 全面配置。顔、髪、主要スタイルをセーフエリアに残す。
- 情報順: エリア → 店舗名 → アクセス → 主訴求 → CTA。
- 表現: 段階スクラム、半透明店舗名プレート、アクセス枠、影付きCTA、外周フレーム、アクセント罫線。
- 書体: 店舗名／主訴求は明朝、アクセス／補足／CTAはゴシックを基本とする。
- 確認サイズ: 1080×1350pxに加え、Meta面を想定した360×450px相当で判読確認する。
- design version: `person_v3_layered`
- render mode: `complete_banner`

V3は文字まで合成済みの完成バナーとして扱う。`enrich.py` 側では、既存の帯を重ねず、検証済みassetをそのまま `thumbnail_override` へ接続する。

---

## 2. 「全静止画CR」の対象定義

棚卸しの正本は、対象日時に取得した本番タブ `入稿用データフィード_ローカル商品` のスナップショットとする。

### 対象

- HB_02カタログの本番フィードに存在するproduct ID。
- `availability` が `out of stock` ではない。
- `image_link` が設定されている。
- 着地URLとサロンIDを一意に解決できる。
- Metaへ静止画として取り込まれる `image_link` の差し替え対象。

動画列の有無は対象判定から除外しない。各商品が動画を持っていても、今回変更するのは `image_link` の静止画CRである。

### 対象外または保留

| 状態 | 条件 | 処理 |
|---|---|---|
| `excluded_out_of_stock` | 在庫外 | 差し替えない |
| `data_hold` | salon ID、正式店名、着地URL、アクセスの対応が不明 | 現行画像維持 |
| `person_source_hold` | 使用可能な人物画像が見つからない | 現行画像維持 |
| `quality_hold` | 解像度、構図、文字焼き込み等でV3に適さない | 別sourceを再選定 |
| `landing_mismatch` | 人物／コピーと着地先の対応が取れない | 現行画像維持 |
| `review_rejected` | 自動QAまたは人手チェックで不合格 | 再制作まで公開不可 |
| `exception_interior_pending` | 店内版の例外利用を検討 | 例外承認まで現行画像維持 |

「全件完了」は、無理に全product IDを差し替えることではなく、次を満たした状態とする。

- 対象product IDの100%が棚卸し・分類済み。
- `eligible` の100%がV3制作、承認、差し替え、反映確認済み。
- 保留の100%に理由、担当者、次回確認日がある。
- 現行画像を維持した保留件数が明示されている。

### 制作・公開単位

- 基本の公開単位は `salon_id`。
- 同一サロンに複数のproduct IDがある場合は同じ公開バッチへ入れる。
- 同じsource、コピー、着地を共有できるproduct IDは、同一の承認済みassetを再利用できる。
- スタイリスト固有の着地／訴求を持つproduct IDは、対象スタッフと一致するsourceとコピーを別assetとして作る。ただし公開は同じサロンの他product IDと同時に行う。
- 配信結果の主な比較単位もサロンとし、product IDは画像versionとの結合キーとして保持する。

---

## 3. 全体フロー

```text
本番フィードのスナップショット
  → 対象／保留／対象外を分類
  → salon・stylistとproduct IDを対応付け
  → 人物sourceを取得・選定
  → V3完成バナーを一括生成
  → 自動QA
  → 人手事前チェック
  → 承認済みassetと公開manifestを固定
  → overrideの現行値をバックアップ
  → 3〜5サロンのパイロット
  → 小規模canary
  → 25% → 50% → 残り
  → Meta反映確認
  → 完全日で配信結果を比較
  → 継続／修正／ロールバック
```

公開処理は「承認済み公開manifestに含まれるproduct IDだけ」を対象にする。生成フォルダの全画像や未承認assetを走査して自動公開してはならない。

---

## 4. Phase 0 — 対象棚卸しと基準固定

### 実施内容

1. 本番フィードを日時付きでスナップショット保存する。
2. product IDから `salon_id / stylist_id / post_id` を、現行 `auto_avail_sync.py` と同じ規則で解決する。
3. `availability`、現在の実効 `image_link`、着地URL、正式店名、エリア、アクセス、訴求を取得する。
4. `thumbnail_override` 全行をバックアップし、ファイルhashと取得日時を記録する。
5. product IDを、対象、保留、対象外に分類する。
6. 同一サロンのproduct ID一覧を固定し、公開単位を作る。
7. 過去28完全日から、サロン別のimpressions、CTR、CPM、Meta実測 `add_to_cart` を取得し、配信前baselineを保存する。

### 棚卸し出力

`catalog_static_inventory_<timestamp>.csv`

```text
snapshot_at
product_id
salon_id
stylist_id
creative_subject
availability
landing_url
current_image_url
current_override_url
canonical_salon_name
area
access
appeal_copy
eligibility_status
hold_reason
rollout_batch
```

### 完了条件

- 本番対象product IDの100%が分類されている。
- 各対象product IDが1つのサロン公開単位へ所属している。
- 正式店名を `title` の逆解析に依存していない。
- 現行overrideの復元用スナップショットが存在する。
- 指標の計算定義と完全日の境界が配信前に固定されている。

---

## 5. Phase 1 — 人物source選定とV3一括制作

### 人物sourceの優先順位

1. productの着地先に紐づく人物／スタイル画像。
2. Hairbookの対象サロンページにある人物／スタイル画像。
3. 対象サロンの公式ページにある人物／スタイル画像。
4. 対象店舗の掲載ページにある人物／スタイル画像。
5. スタッフ固有商品は、そのスタッフまたは着地内容との関係を確認できる人物画像。

人物画像は利用可能という本件の前提で進め、個別の権利確認待ちは置かない。ただしsourceの取り違えを防ぐため、掲載ページURL、元画像URL、取得日時、SHA-256は必ず保存する。

### source選定基準

- 顔、髪、スタイルが明瞭。
- 4:5へ配置しても顔・髪がCTAや文字面と競合しない。
- 元画像の解像度が十分。
- 対象サロン／スタッフとsourceページの対応が一意。
- 第三者ロゴ、透かし、求人文字、価格、不要な焼き込み文字が大きく残らない。
- 訴求内容と人物／スタイルの印象が矛盾しない。

### 制作処理

1. source画像をprivate保管し、hashを固定する。
2. 1080×1350pxへクロップまたは同一写真背景で拡張する。
3. 人物を変えない範囲で、露出、色温度、コントラスト、ノイズを軽微補正する。
4. V3レイヤードの段階スクラムと装飾を配置する。
5. 正本データから、エリア、店舗名、アクセス、主訴求、CTAをコード合成する。
6. 完成JPG、360×450pxチェック画像、元画像との比較画像を出力する。
7. asset、source、copy、designのversionとhashを記録する。

### 一括制作の進め方

- 最初の20サロンで、source選定、制作、自動QA、人手確認に要する時間を計測する。
- その実測から1日あたりの安全な制作・確認件数を決める。
- 残りの所要営業日は `ceil(eligibleサロン数 ÷ 実測日次処理数) + 再制作バッファ` で確定する。
- 量を優先して人物sourceの品質や人手チェックを省略しない。

---

## 6. 差し替え前の必須チェック

チェック結果は `PASS / WARN / FAIL` とする。

- `FAIL`: 公開不可。
- `WARN`: 理由と例外承認者が記録された場合だけ公開可。
- `PASS`: 次の工程へ進める。

### Gate A — 自動QA（asset単位）

| 項目 | 合格条件 |
|---|---|
| ファイル | JPEG、1080×1350、sRGB、Exifなし、定めた容量上限内 |
| design | `person_v3_layered` の承認済みversionと一致 |
| source | source URL、source hash、salon／stylist対応がmanifestと一致 |
| 人物 | 顔・髪・主要スタイルがセーフエリア内。人物領域に不自然な欠損や重複がない |
| 画質 | ぼけ、極端な暗部／白飛び、圧縮崩れ、単色化が基準内 |
| 焼き込み | 求人、価格、第三者ロゴ、不要な文字が広告面に残っていない |
| テキスト | 店名、エリア、アクセス、訴求、CTAが正本と完全一致 |
| レイアウト | 文字のはみ出し、重なり、孤立行、CTA欠落がない |
| 視認性 | 360×450px相当で店名、アクセス、主訴求、CTAを判読できる |
| URL | 公開候補URLが認証なしで200応答し、Content-Typeとasset hashが一致 |
| 重複合成 | 完成バナーへ既存帯を再合成していない |

OCRは補助判定として使う。日本語の最終正誤は正本文字列との比較および人手確認で確定する。

### Gate B — 人手事前チェック（承認assetの100%）

レビュー画面で次の3点を並べる。

1. 元source画像とsourceページ。
2. 1080×1350の完成バナー。
3. 360×450の実表示プレビュー。

レビュアーは次を確認する。

- 対象サロン／スタッフの人物画像である。
- 顔、髪型、髪色、髪の長さ、体型が不自然に変わっていない。
- 顔や髪が文字、CTA、Meta上の見切れで損なわれない。
- 店舗名、エリア、アクセス、訴求が着地先と一致する。
- 訴求がsource人物を施術実績だと過度に断定していない。
- V3の情報階層が崩れず、スマートフォンで読みやすい。
- 不要な求人、価格、他店舗情報、第三者ロゴがない。
- 現在画像と直前overrideが保存され、復元対象が明確。

承認記録には、`reviewer / reviewed_at / checklist_version / decision / reason` を必須にする。制作担当者と最終承認者は原則分ける。

### Gate C — 公開バッチのpreflight

公開担当者は、公開直前にバッチ全体を確認する。

- バッチ内の全assetが `approved`。
- salon単位のproduct IDが別バッチへ分断されていない。
- publish manifestのproduct ID、asset ID、URL、hashが一致。
- 対象product IDの現行overrideが全件バックアップ済み。
- rollback manifestをdry-runし、復元差分が想定どおり。
- 本番フィードH列へ直接書かず、`thumbnail_override`だけを変更する。
- 本番H1 ARRAYFORMULAが正常で、変更前件数と変更後予定件数が一致する。
- scheduled enrich、feed再生成、別の手動変更と競合しない時間帯である。
- 同じ評価期間中に、コピー、配信対象、予算、計測定義を同時変更しない。
- `creative_publish_events` を、override変更と同じ公開操作で記録できる。
- 停止条件、連絡先、ロールバック担当者が当日対応可能。

Gate Cの承認後にmanifestを凍結する。凍結後にasset、文字、product IDが変わった場合は、Gate Aから再チェックする。

---

## 7. Phase 2 — 公開基盤の実装

全件差し替えは、以下の基盤実装に加えて全対象assetの制作・人手承認・本番preflightが完了してから行う。

### 必須実装

1. `build_official_source_banners.cjs` の3店舗固定値をデータ駆動のV3バッチrendererへする。
2. `render_mode="complete_banner"` を `enrich.py` に実装し、V3へ帯を二重合成しない。
3. `creative_config` またはpublish manifestから、承認済みassetだけを読み込む。
4. `thumbnail_override` の全量スナップショットと差分更新を実装する。
5. `creative_publish_events` を追記専用で保存する。
6. サロン単位のロールバックを1操作で実行できるようにする。
7. 自動QA、元画像比較、360×450プレビュー、承認記録を管理画面へ追加する。
8. `/creative` をlocalStorageのみのプロトタイプから、認証とprivate保存を持つ承認画面へ移す。
9. 正式店名の専用値をフィード生成前データから渡し、`title` の逆解析をやめる。
10. Metaのproduct ID日次実績を画像versionの有効期間へ結合する。

### 現状のNo-Go要因

| 項目 | 現状 | 公開前の必要状態 |
|---|---|---|
| V3 renderer | manifest駆動rendererと3店舗pilotを実装 | 全対象manifestの制作・再現 |
| `complete_banner` | 実装・テスト済み | 承認hash一致を維持 |
| `overlays.py` | 旧デザイン | V3完成バナーはoverlay処理を通さない |
| 承認記録 | 認証付き画面・append-only保存を実装 | 全unique assetの人手承認 |
| publish event | Sheet追記とDashboard同期を実装 | 本番実行時の全ID event確認 |
| rollback | batch単位の直前override復元を実装・テスト済み | 本番environmentから復元dry-run |
| 管理画面 | 認証・private保存・実フィード結合を実装 | 事前チェック完了 |
| 配信結果 | 商品別Meta完全日集計を実装 | 公開後7日・14日の観測 |
| source／正式店名 | pilotはcanonical copy/hash固定 | 残り全salonのcanonical値固定 |
| 本体接続 | forkブランチで実装 | cajon-inc本体へPR/mergeしActions secretを利用 |

---

## 8. Phase 3 — 段階差し替え

各段階の割合は、Phase 0で確定した `eligible salon` を分母にする。公開順はsalon hashで固定し、担当者が都合のよいサロンだけを選ばない。

| 段階 | 対象 | 目的 | 次段階への条件 |
|---|---:|---|---|
| Dry run | 100% | 制作、QA、manifest、rollback差分を検証。外部変更なし | Gate A/B/Cの手順が再現可能 |
| Pilot | 3〜5サロン | 反映、見え方、履歴、ロールバックを実機確認 | 誤配信・リンク切れ・文字誤記0件 |
| Canary | eligibleの約10% | 運用負荷と初期配信傾向を確認 | 停止条件なし、完全日データ取得 |
| Wave 1 | 累計25% | バッチ運用の安定性確認 | QA、Meta反映、結果が許容範囲 |
| Wave 2 | 累計50% | 中規模での性能・作業量確認 | 停止条件なし |
| Wave 3 | 残りeligible | 全対象へ展開 | 全件確認と保留台帳完成 |

Pilotは、FORTE 表参道、KENJE 平塚LUSCA、Fier 大阪梅田が公開時点でHB_02の対象なら候補にする。対象外の場合は、人物source、地域、アクセス文量、サロン規模が異なる稼働サロンから代替する。

未切替サロンは各waveの一時holdoutとして扱う。最終的にはeligible全件を差し替えるが、効果確認前に一括公開しない。

### 各waveの昇格判定

- 技術: 404、画像hash不一致、フィード欠損、誤ったproduct mappingが0件。
- 品質: 未承認assetの公開、人物／サロン取り違え、重大な文字誤記が0件。
- 運用: 100%の公開eventとrollback先が記録されている。
- 配信: 事前に定めた最小impressionsと最低完全日数を満たし、CTR／CPMに重大な悪化がない。
- コンバージョン: Meta実測 `add_to_cart` を従指標として確認する。母数未達は勝敗判定しない。

最小impressions、最低完全日数、重大悪化の閾値は、過去28完全日の分布からPhase 0で決め、公開後に変更しない。

---

## 9. 公開後の反映確認

公開直後から最初の完全日開始まで、次を確認する。

### 直後の技術確認

- `thumbnail_override` の対象product IDがpublish manifestどおり。
- 本番フィードの実効 `image_link` が承認済みURLを返す。
- URLが200、JPEG、1080×1350で、承認hashと一致する。
- H列ARRAYFORMULAがスピルエラーになっていない。
- Metaのフィード取得結果に新しいURLが反映された。
- 商品件数、in-stock件数、エラー件数が変更前と不自然に変わっていない。
- `creative_publish_events` に公開時刻、対象product ID、旧／新asset、公開者が記録された。

### 目視確認

- Pilotは対象product IDの100%をMeta実機またはCommerce Managerで確認する。
- Canary以降も自動確認は100%。人手は各waveで全unique assetを確認済みであることに加え、公開後にサロン単位のサンプル確認を行う。
- 誤った店舗、人物、文字、二重帯、見切れを1件でも発見したら当該サロンを即時ロールバックし、同一バッチを停止する。

切替日は旧新が混在し得るため配信結果から除外する。`meta_fetch_confirmed_at` の翌Meta完全日を新versionの集計開始日とする。

---

## 10. 効果測定

既存の計測前提を変えない。

- 対象: HB_02。
- 主指標: CTR、CPM。
- 従指標: Meta実測 `add_to_cart`。
- カタログBotのメタCPA／CV: 絶対値は判定に使わず、トレンドのみ参考にする。
- 集計単位: `salon_id × creative_version × 完全日`。
- 元データ: Metaの `product_id` 日次実績。
- 切替日: 除外。
- 同一サロン内の旧新混在日: 除外。
- 比較中はコピー、CTA、配信対象、計測ロジックを固定する。

### 比較

1. 同一サロンの切替前baseline対V3。
2. 同時期の未切替wave対V3。
3. 画像source、アクセス文量、地域、配信量の層別。
4. 全体の加重値に加え、サロン中央値も確認する。

### 配信結果の記録

```text
date
account_id
campaign_id
product_id
salon_id
creative_asset_id
creative_version
publish_event_id
spend
impressions
clicks
ctr
cpm
add_to_cart
is_complete_day
exclusion_reason
```

---

## 11. 停止・ロールバック

### 即時停止条件

- wrong salon／wrong person／wrong stylist。
- 店舗名、アクセス、着地先の重大な不一致。
- 未承認assetの公開。
- 画像URLの404、認証要求、Content-Type不正、hash不一致。
- 二重帯、人物の破綻、顔や髪の重大な見切れ。
- フィードH列のスピル破損、商品件数の異常減少。
- Metaの審査否認が同一原因で複数発生。

### 配信結果による停止

- Phase 0で固定した最小母数と閾値を満たしたうえで、CTRまたはCPMが重大悪化。
- 従指標の `add_to_cart` も同方向に悪化し、偶然変動だけでは説明しにくい。
- 母数未達時は、技術・品質上の問題がなければ自動ロールバックせず `insufficient_data` とする。

### ロールバック処理

1. `publish_event_id`から対象salonとproduct IDを取得。
2. 公開前snapshotの旧override URL、hash、noteを復元。
3. 本番フィードとURLを再確認。
4. `rollback_event`へ理由、実行者、実行時刻、復元先assetを追記。
5. 当該salonを `rollback_required → rolled_back → review_pending` へ移す。
6. 同じ原因がバッチ全体へ波及する場合は、次waveを停止する。

ロールバック時も、本番フィードH列へ直接値を書かない。

---

## 12. 役割と承認

| 役割 | 責任 |
|---|---|
| Project owner | 範囲、優先順位、wave昇格、例外判断 |
| Creative operator | source選定、V3制作、修正 |
| QA reviewer | 元画像、人物同一性、文字、視認性の事前チェック |
| Data owner | baseline、完全日、CTR／CPM／ATCの定義・判定 |
| Engineer／publisher | manifest、override、event、Meta反映、rollback |
| Final approver | バッチpreflightと公開承認 |

- Creative operatorとFinal approverは原則別担当にする。
- 店内写真への例外切替、人物sourceの例外利用、WARN公開はProject ownerの記名承認を必須にする。
- 誰がいつ何を承認したかを、画像ファイル名や口頭ではなく承認データに残す。

---

## 13. 社内運用・コミュニケーション

### 開始前

- 30分のレビュアー校正会を行い、V3の合格例、修正例、即FAIL例を10件で合わせる。
- 1ページのチェックガイドを管理画面から常時参照できるようにする。
- 「人物を変えない」「正式店名をtitleから推測しない」「H列へ直書きしない」を必須注意事項にする。

### rollout中

- Pilot／Canary期間は、公開件数、反映確認、FAIL／WARN、rollback、CTR／CPMの母数状況を日次共有する。
- 各wave開始前に、対象サロン数、product ID数、公開予定時刻、担当者、ロールバック先を共有する。
- 却下理由は自由記述だけでなく、`source_mismatch / person_change / crop / text / readability / technical` に分類し、再発傾向を確認する。

### 全体展開後

- 週次でperson source hold、再制作率、QA漏れ、rollback、CTR／CPM／ATCをレビューする。
- 新規product IDは、既存assetを自動継承せず、salon／stylist対応と現行design versionを検証してから公開する。
- sourceページの変更、人物画像の削除、着地／アクセス変更は承認を `stale` に戻し、再チェックする。

---

## 14. 成功条件

### 制作品質

- 全対象product IDの分類率: 100%。
- 公開assetの自動QA通過率: 100%。
- 公開unique assetの人手承認率: 100%。
- wrong salon／person／stylist: 0件。
- 重大な店舗名／アクセス誤記: 0件。
- 未承認assetの公開: 0件。

### 公開品質

- 公開product IDのpublish event記録率: 100%。
- 公開product IDのrollback先保存率: 100%。
- 404／hash不一致／フィード欠損: 0件。
- 差し替え後のMeta反映確認率: 100%。

### 効果と運用

- CTR／CPM／Meta実測 `add_to_cart`を完全日で比較可能。
- source選定、制作、QA、公開にかかる時間を測定可能。
- hold理由と再対応日を追跡可能。
- 各waveで継続、修正、停止を判断できる。

---

## 15. 推奨スケジュール

| 期間 | 内容 | 完了条件 |
|---|---|---|
| Week 1 | 棚卸し、対象定義、baseline、override backup | Phase 0完了 |
| Week 1〜2 | V3 renderer、complete banner、QA／承認／rollback実装 | 統合dry-run成功 |
| Week 2 | 最初の20サロン制作、チェック時間計測 | 日次処理能力確定 |
| Week 2〜3 | eligible全件のsource選定・V3制作・事前チェック | approved／hold分類完了 |
| Week 3 | 3〜5サロンPilot | 実機反映・rollback確認 |
| Week 3以降 | Canary → 25% → 50% → 残り | waveごとの昇格条件達成 |
| 全体展開後 | 効果測定、hold解消、新規商品運用 | 週次運用へ移行 |

実際の制作日数は、Phase 0のeligibleサロン数と最初の20サロンの実測処理時間で更新する。件数未確認の段階で全体完了日を固定しない。

---

## 16. 最初に着手する順序

1. 本番フィードと `thumbnail_override` の読み取り専用snapshotを作る。
2. 全静止画CRの対象件数、eligibleサロン数、product ID数、hold見込みを確定する。
3. V3のdesign token、文字最小サイズ、CTA、copy正本をversion固定する。
4. 3店舗のV3試作をデータ駆動rendererへ移す。
5. 自動QAと人手事前チェック画面を実装する。
6. `complete_banner`、publish event、rollbackを実装する。
7. 全件dry-runを行い、公開manifestとrollback manifestをレビューする。
8. Pilot公開へ進む。

**現時点の判断**: 方針は人物優先V3で確定できるが、公開基盤のNo-Go要因が残っているため、全件差し替えはまだ開始しない。Phase 0〜2と全件dry-runを完了し、Gate A〜Cが機能した後にPilotから差し替える。
