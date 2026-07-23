# サロン別ゼロベース画像生成 計画

- 作成日: 2026-07-23
- 対象: Hairbook 集客カタログ（HB_02）
- 目的: 既存サムネの補正・クロップではなく、**サロンごとの確認済み情報から広告用画像を新規生成**し、承認済み画像だけを既存の `thumbnail_override` 経路へ接続する。
- 本書の範囲: データ取得、生成ブリーフ、プロンプト、候補生成、QA、承認、配信、計測、ロールバックの設計。画像の本番生成・配信はまだ行わない。

---

## 1. 結論

採用する基本方針は次の通り。

1. **生成単位は商品ではなくサロン**とする。同一サロンの複数商品には、原則として同じ承認済みベース画像を使う。
2. 元画像の編集ではなく、サロン情報と公式リンク先の文章を根拠に、1サロンずつ独立したプロンプトでゼロベース生成する。
3. 公式ページの写真は初期段階ではモデル入力に使わない。まずは**確認済みテキストだけをグラウンディング情報として使用**し、実在スタッフ・顧客・店内を再現したように見せない。
4. 生成画像内に店名、価格、キャンペーン、ロゴを描かせない。正確な日本語とブランド表示は、承認後に既存のコード合成で載せる。
5. 画像切替の候補は、**現在画像（比較・復元用）＋ゼロベース生成画像1〜2案**だけにする。入稿、動画キャプチャ、疑似フレーム、既存画像のAI加工は選択肢から外す。
6. 日次約1,385商品を毎日再生成しない。入力情報のハッシュが変わった時、または担当者が再生成を指示した時だけ候補を生成する。
7. 自動生成から自動配信へ直結させない。`generated → qa_passed → approved → published` の承認状態を必須にする。
8. 画像切替の公開履歴を不変ログとして残し、Metaの `product_id` 日次実績と結び付けて、切替前後・生成案別の配信結果を管理画面で振り返れるようにする。
9. 効果検証では**画像ソース以外を固定**する。新しい帯デザインと生成画像を同時に変えない。

この方針により、生成AIは「サロンごとの広告素材作成」に限定し、既存の日次エンリッチ処理は「承認済み画像の配信・帯合成」に専念させる。

---

## 2. 「個別生成」の定義

### 2-1. 生成粒度

| 粒度 | 初期方針 | 理由 |
|---|---|---|
| サロン | **採用** | サロンのブランド・得意領域・立地を反映でき、商品単位よりコストと管理量を抑えられる |
| スタイリスト | 初期対象外 | 実在人物との同一性・誤認リスクが高い。本人確認済み情報と利用許諾が整ってから別フェーズ |
| 商品／post | 原則対象外 | 1,385件規模の継続生成になり、同一サロン内で画像の一貫性も失いやすい |

サロン単位の安定キーは、`title` や商品IDの文字列分解で作らず、フィード生成元の `salon_id` を使う。Stylist Boost の商品であっても、初期パイロットではサロン共通画像を使い、スタッフ本人を示す表現は避ける。

### 2-2. ゼロベースの意味

- 既存 `image_link` の補正、フィルタ、アウトペイント、クロップは行わない。
- サロンの事実情報から広告コンセプトを組み立て、まったく新しい画像を生成する。
- 実店舗の内装、スタッフ、施術実績を忠実に再現した画像だとは表現しない。
- 初期生成物の表現区分を `concept_image` として記録する。

### 2-3. 管理画面に表示する画像

| 表示 | 用途 | 切替可否 |
|---|---|---|
| 現在画像 | 比較、ロールバック、切替前実績の参照 | 復元時のみ |
| 生成案1 | ゼロベース生成の標準案 | 可 |
| 生成案2 | 必要な場合だけ作る代替案 | 可 |

- 切替候補の上限は2案。3案目を追加せず、再生成時は生成案1または2の新バージョンとして保存する。
- 入稿、動画から別フレーム、疑似クロップ、既存画像へのフィルタ加工は新仕様から削除する。
- 現在画像は「生成候補」ではないが、比較と復元に必要なためUIには残す。

---

## 3. 入力情報と正本

### 3-1. 優先順位

| 優先 | 情報源 | 使用する項目 | 扱い |
|---:|---|---|---|
| 1 | フィード生成元DB／SQL | `salon_id`, `salon_name`, `access_salon_name`, `top_catch`, `city_name`, `prefecture_name`, `salon_url`, `staff_url`, `staff_introduction` | **事実の正本**。現在の `catalog_feed.py` が商品化する前の値を使う |
| 2 | 本番フィード | `id`, `description`, `link`, `address.*`, `custom_label_0`, `availability` | 配信状態と実際の着地先の確認に使う |
| 3 | 商品の実着地ページ | 特徴、得意メニュー、アクセス、営業時間、席数、設備、対象客層など | URL到達性とページ内根拠を保存できた項目だけ使う |
| 4 | 人による追記 | ブランドトーン、避けたい表現、優先したいメニュー | 変更者・変更日時・承認者を記録する |

### 3-2. 使用しない／そのまま信用しない情報

- `title`: アクセス文やスタッフ名が連結されるため、素のサロン名として使わない。
- 検索結果のスニペット: 古い可能性があるため、生成根拠にしない。
- 関連店舗の情報: 着地ページに同時表示されても対象サロンの情報へ混ぜない。
- 価格、割引、受賞歴、人気No.1等: 公式ページ内にあっても、期限と根拠を確認できなければプロンプトに入れない。
- 公式ページ以外の口コミ・SNS・第三者サイト: 初期パイロットでは使わない。

### 3-3. リンク先の取得ゲート

以下のいずれかに該当したサロンは `blocked` とし、画像を生成しない。

- 実着地URLが 200 で取得できない、またはリダイレクト先が想定外。
- ページ内容とDBの `salon_id`／`salon_name` が一致しない。
- サロンページとスタッフページのどちらを根拠にするか判定できない。
- 情報がサロン名と住所だけで、個別コンセプトを作る根拠が不足している。
- DB、フィード、ページのメニュー・対象客層に矛盾がある。
- 採用広告、求人、告知ページが混入している。

ブロック時は既存画像を継続し、理由を管理画面に表示する。

---

## 4. 非公開の生成ブリーフ

現行の本番フィード49列には、素の `salon_name` や `salon_url` が残らない。`catalog_feed.py` の商品化直前で、次のブリーフを**非公開側**へ書き出す。

```json
{
  "schema_version": 1,
  "salon_id": "<stable salon id>",
  "salon_name": "<canonical name>",
  "scope": "salon",
  "product_ids": ["<catalog product id>"],
  "canonical_salon_url": "https://hairbook.jp/salons/.../",
  "landing_urls": ["https://hairbook.jp/.../"],
  "facts": {
    "prefecture": "",
    "city": "",
    "access": "",
    "official_catch": "",
    "verified_services": [],
    "verified_features": [],
    "audience": "",
    "salon_scale": ""
  },
  "evidence": [
    {
      "source_type": "db|feed|landing_page|manual",
      "source_ref": "<field name or url>",
      "fetched_at": "<ISO-8601>",
      "content_hash": "<sha256>",
      "supports": ["facts.verified_services"]
    }
  ],
  "rights": {
    "text_grounding_allowed": true,
    "image_reference_allowed": false,
    "reviewed_by": ""
  },
  "readiness": {
    "status": "ready|needs_review|blocked",
    "reasons": []
  },
  "source_snapshot_hash": "<sha256>"
}
```

### 保存場所

- 推奨: private の `hairbook-ad-local-catalog` 側、または認証済みAPIのデータストア。
- public の `hairbook-thumbnails` へは、承認済み最終画像と匿名化した画像ハッシュだけを置く。
- ページ本文、内部ID対応表、プロンプト、承認者情報を public リポジトリへコミットしない。

既存 `dashboard/IMPLEMENTATION_PLAN.md` の「repoコミット案」を採用する場合も、**public画像リポと非公開生成メタデータを分離する**ことを条件にする。

---

## 5. コンセプト作成ルール

### 5-1. コンセプトの優先順位

1. 公式に確認できる得意メニュー／髪型がある → **仕上がりイメージ型**
2. メニューは弱いが、少人数・個室・ファミリー対応等の特徴がある → **体験・雰囲気型**
3. アクセス・地域性のみが明確 → **地域生活者向けの上質な美容イメージ型**
4. 個別化に十分な根拠がない → 生成しない

### 5-2. 生成してよい表現

- 確認済みメニューと整合する、架空モデルの髪型・仕上がりイメージ。
- 確認済みのブランドトーンを反映した色、光、素材感。
- 「少人数」「落ち着いた雰囲気」など、確認済み特徴を抽象化した非特定の空間。
- 地域やターゲットに合う一般的なライフスタイル表現。

### 5-3. 禁止・要承認表現

- 実在スタッフや顧客に似せた人物。
- 実店舗写真だと誤認させる、根拠のない内装・設備・外観。
- 確認できない施術効果、価格、クーポン、受賞、順位、医療的効能。
- サロンのロゴ、他社ロゴ、読める看板、透かし、画像内の日本語。
- 未確認のジェンダー・年齢・人種・髪質をサロンの主要顧客として固定する表現。
- 求人、採用、告知の要素。
- 未成年に見える人物。初期パイロットは成人モデルだけを対象にする。

---

## 6. プロンプト仕様

画像ごとに同じ骨格を使い、事実部分だけをサロンブリーフから差し込む。プロンプトは `prompt_template_version` とハッシュを記録する。

```text
Use case: ads-marketing
Asset type: Hairbook Meta catalog thumbnail, 4:5 portrait
Primary request: <verified factsから作ったサロン固有の1文コンセプト>
Scene/backdrop: <非特定の空間。実店舗の再現ではない>
Subject: <確認済みメニューに合う架空の成人モデル、または人物なしの美容イメージ>
Style/medium: photorealistic-natural advertising photography
Composition/framing: hair and face fully visible; main subject inside the central 70%; leave the lower area visually calm for a deterministic caption overlay
Lighting/mood: <サロン固有のトーン>
Color palette: <根拠のある範囲のトーン>
Constraints: concept image, not the actual salon interior or staff; natural hair texture; realistic skin; no misleading service result
Avoid: any text, letters, numbers, logos, signage, watermark, price, coupon, award badge, duplicate people, malformed hands, cropped hairstyle
```

### 生成時のルール

- 1サロン・1コンセプト・1候補を1ジョブとして扱う。異なる候補を1回の複数出力で代用しない。
- 1サロンにつき生成案1を必須、生成案2を任意とし、候補数は**1〜2案**に固定する。
- 2案作る場合も同じブリーフから別々の生成ジョブで作り、`pattern_1` / `pattern_2` として識別する。
- 再生成で旧候補を上書きせず、同じスロットの `version` を増やす。管理画面には各スロットの最新有効版だけを切替候補として表示する。
- パイロットでは Codex の組み込み画像生成を使用し、各候補を個別生成する。CLI/API経路への切替は、運用自動化と費用・権限の承認後に別判断とする。
- 元画像を入力しないため、処理区分は edit ではなく generate。

---

## 7. 画像仕様

| 項目 | 仕様 |
|---|---|
| マスター比率 | 4:5 |
| 配信用正規化 | 1080×1350 JPEG、sRGB、Exif除去 |
| 構図 | 顔・髪・主要要素を中央約70%へ。左右14.8%の見切れを想定 |
| 下部 | 帯デザイン用に低密度領域を確保。画像内テキストは禁止 |
| 9:16 | 初期対象外。4:5静止画の効果を確認後、別生成または別規格で検討 |
| ファイル名 | `sha1(asset_id)[:12].jpg` 等の匿名ハッシュ。サロンID・店名を含めない |

生成モデルの生出力サイズに依存せず、配信前にコードで4:5へ検証・正規化する。単純な中心クロップで髪が切れる場合はQA不合格とし、自動救済しない。

---

## 8. 生成物と状態管理

### 8-1. 状態遷移

```text
brief_draft
  → ready
  → generating
  → generated
  → qa_failed | qa_passed
  → approved | rejected
  → published
  → retired
```

- `qa_passed` だけでは配信不可。
- `approved` には承認者・承認日時・候補IDを必須にする。
- ブリーフの `source_snapshot_hash` が変わったら、既存承認を `stale` として表示する。ただし自動で配信画像を差し替えない。

### 8-2. 生成アセット記録

```json
{
  "asset_id": "<uuid>",
  "salon_id": "<private mapping>",
  "brief_hash": "<sha256>",
  "prompt_template_version": 1,
  "prompt_hash": "<sha256>",
  "candidate_slot": "pattern_1|pattern_2",
  "candidate_no": 1,
  "version": 1,
  "representation": "concept_image",
  "generator": "<provider/model/path>",
  "generated_at": "<ISO-8601>",
  "qa": {},
  "approval": {},
  "public_image_url": ""
}
```

費用を測定できる経路では、リクエストID、単価、実コストも記録する。費用見積もりは `生成可能サロン数 × 候補数 × 1候補単価` で計算し、モデル価格をコードへ固定しない。

---

## 9. QAと人手承認

### 9-1. 自動QA

| 検査 | 合格条件 |
|---|---|
| ファイル | JPEGとしてデコード可能、1080×1350、sRGB、容量上限内 |
| 低情報 | 現行 `assess()` で `broken` ではない |
| OCR | 読める文字・数字・ロゴらしき要素がない |
| 構図 | 髪・顔・主要被写体が中央セーフエリアに収まる |
| 人物品質 | 顔、髪、耳、首、手、背景の破綻がない |
| 根拠整合 | ブリーフにないメニュー、設備、価格、受賞等を示していない |
| 誤認 | 実スタッフ・実店舗の再現を主張する表現ではない |
| 重複 | 他サロンの承認画像と知覚ハッシュが近すぎない |
| 広告適性 | 成人向け集客画像として安全で、求人・告知ではない |

Vision判定は補助に使うが、合格判定の理由とスコアを保存する。モデル判定だけで自動承認しない。

### 9-2. `/creative` の人手確認項目

管理画面では、次を同じドロワーで比較できるようにする。

- 現在配信中の画像。
- サロン名、実着地URL、リンク到達状態。
- 生成に使用した確認済み情報と、その出所。
- 最終プロンプトと禁止事項。
- 生成案1と任意の生成案2、4:5プレビュー、左右14.8%見切れプレビュー、帯合成プレビュー。
- 自動QA結果と警告。
- 「生成案1へ切替」「生成案2へ切替」「現在画像へ戻す」「却下」「再生成」。
- 現在画像／生成案1／生成案2ごとの公開期間と配信結果サマリー。

画像ソース欄には上記3枠以外を置かない。現行プロトタイプの「入稿」「動画から別フレーム」「AI生成（既存画像のフィルタ加工）」は撤去する。

承認チェックは最低でも次の6点とする。

1. サロンの得意領域・雰囲気と矛盾しない。
2. 実店舗・実スタッフの写真だと誤認させない。
3. 髪型、顔、手、背景に生成破綻がない。
4. 画像内に文字、価格、ロゴ、透かしがない。
5. 4:5と見切れプレビューの両方で主要要素が残る。
6. 着地先と広告の約束が一致する。

---

## 10. 既存パイプラインとの接続

### 10-1. 接続原則

生成ジョブは `enrich.py` の中で呼ばない。生成済み・承認済みアセットだけを `source_url` として渡す。

```text
[private brief store]
      ↓ 個別生成
[candidate assets + QA]
      ↓ 人手承認
[public final jpg / anonymous hash]
      ↓ source_url
[enrich.py: 同一帯デザインで合成]
      ↓
[thumbnail_override]
      ↓
[Meta]
```

### 10-2. `creative_config` の拡張案

```json
{
  "<product_id>": {
    "enabled": true,
    "design": "bottom_scrim",
    "source": "generated",
    "source_url": "https://raw.githubusercontent.com/.../<anonymous-hash>.jpg",
    "source_params": {
      "asset_id": "<anonymous asset id>",
      "representation": "concept_image"
    }
  }
}
```

private側で承認済みになったアセットだけを、この最小configへexportする。public側configへはプロンプト、ページ本文、承認ID、承認者名、サロンID対応表を入れない。

### 10-3. `enrich.py` 側の必要変更

- `source="generated"` を明示的に扱う。
- `source_url` のURL・Content-Type・画像寸法を検証する。
- 生成画像に `improve.py` の色補正を重ねるかは初期検証で決定する。既定は**補正なし**。
- 未知の `design` キーで全件失敗しないよう、config検証と既定デザインへの安全なフォールバックを追加する。
- 変更前のoverride URLを履歴へ保存し、削除ではなく直前画像へ戻せるようにする。
- 同一サロンの全対象商品へ同じ承認済みアセットを展開するマッピングを追加する。

### 10-4. 現在のブロッカー

- 新10デザインは `overlays.py` 未移植。生成画像の効果測定前に、使用する帯を1種へ固定し、CanvasとPillowの出力を一致させる必要がある。
- `cajon-inc/hairbook-thumbnails` へのwrite権限がないため、本番画像の格納・更新経路を確定できない。
- `/creative` は認証なし・localStorageのみ。承認者を記録する本番運用には使えない。
- 現行 `build_dashboard.py` は24件のダミーサロンを埋め込むだけで、実データと実リンクを取得しない。

---

## 11. 段階導入

### Phase 0 — 定義と権利の確定

- [ ] サロン情報の生成利用、AI画像の広告利用、表示上の「イメージ」扱いを社内承認する。
- [ ] 公式ページ写真をモデル参照に使うかを決定する。初期値は `false`。
- [ ] 非公開ブリーフの保存先を決定する。
- [ ] サロン単位を安定して識別する `salon_id` の出力方法を確定する。
- 完了条件: 禁止事項・承認者・保存先が文書化されている。

### Phase 1 — データ収集PoC

- `catalog_feed.py` の商品化前データから、サロン別ブリーフを作る読み取り専用スクリプトを実装する。
- landing URLの到達性、対象サロン一致、本文抽出、根拠フィールドを記録する。
- 8サロン程度で `ready / needs_review / blocked` の判定を目視確認する。
- 完了条件: 同じ入力から同じ `source_snapshot_hash` と同じブリーフが再生成される。

### Phase 2 — 定性画像パイロット

- 対象条件:
  - 集客カタログかつ `in stock`。
  - サロン単位商品。スタッフ本人訴求は除外。
  - 実着地URLが正常。
  - 個別化に十分な公式情報がある。
  - メンズ／レディース、都市／地域、得意領域が偏らない。
- 8サロン × 生成案1 = 8候補を標準とし、代替案が必要なサロンだけ生成案2を追加する（最大16候補）。
- 生成案1／2はそれぞれ独立した生成ジョブで作る。
- 配信せず、管理画面でQAと承認の一致率、再生成率、作業時間を測る。
- 完了条件: 各サロンで1候補以上が承認可能、重大な誤認・文字混入・人物破綻が0件。

### Phase 3 — 管理画面と保存

- 実データのGET、候補生成、QA、承認、切替履歴、公開、配信実績取得のAPIを追加する。
- localStorageを下書きキャッシュへ格下げし、正本は認証済みサーバ側へ置く。
- public画像保存とprivateメタデータ保存を分離する。
- Metaの `product_id` 日次実績を、画像の有効期間へ時系列結合する。
- 完了条件: 別端末でも承認状態が一致し、誰が何を公開したかと、その期間の配信結果を追跡できる。

### Phase 4 — 小規模配信実験

- 過去28日等の固定期間から、サロン別CTR・CPM・impressions分布を取得して必要サンプル数を事前計算する。
- サロン単位で、ベースラインが近い組を作って treatment / holdout へ固定割付する。
- 画像ソース以外は同一にする。帯、コピー、配信対象、計測ロジックを期間中に変えない。
- 切替日を含むMeta集計日は旧新画像が混在し得るため比較から除外し、最初の完全な配信日から集計する。
- 主指標: CTR / CPM。
- 従指標: Meta実測 `add_to_cart`。
- カタログBotのメタCPA/CVはトレンド参考に留め、絶対値の判定に使わない。
- 完了条件: 事前に定めた最小impressionsと観測期間を満たし、リンク・画像エラーがない。

### Phase 5 — 拡張

- 効果と運用負荷が許容範囲なら、情報充足サロンへ段階展開する。
- `source_snapshot_hash` 変更時の再レビューキューを運用する。
- スタッフ別画像、公式写真参照、9:16静止画は、それぞれ独立した承認フェーズとして追加する。

---

## 12. 画像切替履歴と配信結果の振り返り

### 12-1. 前提

Metaの `product_id` ブレイクダウンでは商品別の spend、impressions、clicks、actionsを取得できるが、配信された画像URLや `asset_id` は直接返らない。そのため、**公開履歴を画像バージョンの正本**とし、商品別日次実績へ時系列で結び付ける。

同一日に複数画像が配信される可能性を排除できないため、時間帯単位で按分しない。切替を含む日は旧画像・新画像のどちらにも割り当てず、比較対象外とする。

### 12-2. 公開履歴 `creative_publish_events`

画像を切り替えるたびに、既存行の上書きではなくイベントを追加する。

```json
{
  "event_id": "<uuid>",
  "salon_id": "<private salon id>",
  "product_ids": ["<snapshot of affected product ids>"],
  "from_asset_id": "<previous asset or original>",
  "to_asset_id": "<generated asset id>",
  "candidate_slot": "pattern_1|pattern_2|original",
  "asset_version": 1,
  "design_version": "<fixed overlay version>",
  "copy_version": "<fixed copy version>",
  "published_at": "<ISO-8601>",
  "feed_confirmed_at": "<ISO-8601>",
  "measurement_start_date": "<first full Meta account date after confirmation>",
  "ended_at": null,
  "published_by": "<actor>",
  "reason": "<initial|switch|rollback>"
}
```

- `product_ids` は公開時点の対象一覧をスナップショット保存する。後からフィード商品が増減しても過去実績の対象を変えない。
- `feed_confirmed_at` は本番フィードの `image_link` が対象URLへ切り替わったことを確認した時刻。
- `measurement_start_date` は、`feed_confirmed_at` より後に始まる最初の完全なMetaアカウント日。アカウントのタイムゾーンは実装時に確認し、決め打ちしない。
- 次の切替が発生したら直前イベントの `ended_at` を記録し、切替を含む日は両バージョンから除外する。
- ロールバックも新しいイベントとして残す。

### 12-3. 商品別日次実績 `creative_product_daily`

```json
{
  "date": "<Meta account date>",
  "campaign_id": "<HB_02 catalog campaign>",
  "adset_id": "<adset id>",
  "product_id": "<catalog product id>",
  "salon_id": "<resolved salon id>",
  "asset_id": "<temporal join from publish event>",
  "candidate_slot": "pattern_1|pattern_2|original",
  "spend": 0,
  "impressions": 0,
  "clicks": 0,
  "add_to_cart": 0,
  "fetched_at": "<ISO-8601>",
  "is_complete_day": true
}
```

- Meta APIは `level=adset`、`breakdowns=product_id`、日次粒度で取得する。
- CTRは `clicks / impressions × 100`、CPMは `spend / impressions × 1000` を保存値から再計算する。
- `add_to_cart` は既存定義に合わせ、次の優先順で最初に存在するactionだけを採用し、重複加算しない。
  1. `offsite_conversion.fb_pixel_add_to_cart`
  2. `add_to_cart`
  3. `omni_add_to_cart`
  4. `onsite_web_add_to_cart`
- `product_id` からのサロンID解決は、現行 `auto_avail_sync.py` と同じルールを共通関数化して使う。別実装で定義を増やさない。
- Meta APIの未確定日、取得失敗日、切替日、画像バージョンを一意に決められない日は `is_complete_day=false` とし比較から外す。

### 12-4. 管理画面「配信結果」タブ

サロン詳細に「画像設定」と「配信結果」の2タブを設ける。「配信結果」には次を表示する。

- 現在配信中の画像、生成案番号、バージョン、配信開始日、対象商品数。
- 画像切替タイムライン（現在画像 → 生成案1 → 生成案2 → ロールバック等）。
- 各画像バージョンの spend、impressions、clicks、CTR、CPM、Meta実測 `add_to_cart`。
- 切替前後の同一日数比較と増減率。
- 生成案1と生成案2を順次配信した場合の、同一日数・完全日だけの比較。
- holdoutがある場合の、同期間における生成画像群とholdout群の比較。
- 集計対象日数、除外日、データ取得状態、最小impressions到達状況。
- 「勝ち／負け」を自動断定せず、母数不足時は「参考値」と表示する。

一覧画面には、現在の画像種別、配信開始日、直近完全期間のCTR、切替前比、impressionsを表示し、結果が悪化したサロンや母数不足のサロンを絞り込めるようにする。

### 12-5. 比較方法

| 比較 | 用途 | 解釈 |
|---|---|---|
| 切替前 vs 切替後 | 個別サロンの振り返り | 季節・曜日・配信量の影響を含む記述比較 |
| 生成案1 vs 生成案2 | 同一サロンの案比較 | 順次配信のため因果断定はしない |
| treatment vs holdout | 全体効果の判断 | サロン単位固定割付。同期間・同条件で比較 |

生成案1と2を同一サロン内の商品へ同時に分ける方法は採用しない。商品post・動画の違いが画像差と混ざるため。

### 12-6. 効果測定で固定すること

引き継ぎの計測定義を変更しない。

- 対象広告アカウント: HB_01 / HB_02 / HB_07。カタログ実験はHB_02。
- 主指標: CTR / CPM。
- 従指標: Meta実測 `add_to_cart`。
- カタログBotのメタCPA/CV: 絶対値ではなくトレンドのみ。
- 割付単位: 商品ではなくサロン。1サロンがtreatmentとholdoutへ混在しないようにする。
- 比較期間中は生成画像以外の変更を凍結する。
- 生成画像の導入日、対象サロン、対象商品ID、旧URL、新URL、承認IDを監査ログへ残す。

運用指標として、`ready率`、`QA合格率`、`人手承認率`、`再生成回数`、`1承認画像あたりコスト`、`1サロンあたり作業時間` を別途測る。これらは広告効果指標とは混ぜない。

---

## 13. ロールバック

1. 公開前に、対象商品ごとの現在のoverride URLをスナップショット保存する。
2. 問題があれば、対象サロンの全商品を直前スナップショットへ戻す。
3. 生成画像のURLを消すだけにしない。元動画再抽出済みの優良overrideが存在した場合、それを失わないようにする。
4. 画像エラー、着地先不一致、広告審査問題、重大な生成破綻は即時ロールバック条件とする。
5. ロールバック後も生成アセットと監査ログは `retired` として保持する。

---

## 14. 実装ファイル案

| ファイル | 役割 |
|---|---|
| private repo: `creative_grounding.py` | DB／フィード／landing pageからサロン別根拠を収集 |
| private repo: `creative_brief.py` | 正規化、矛盾検出、readiness判定、ブリーフhash生成 |
| private repo: `creative_prompt.py` | version付きの決定的プロンプト生成 |
| private repo: `creative_assets.py` | 候補・QA・承認・公開状態の管理 |
| private repo: `creative_performance.py` | Meta `product_id` 日次実績取得、ATC定義統一、画像バージョンとの時系列結合 |
| `thumbgen/generated_qa.py` | 画像寸法、OCR、セーフエリア、Vision、重複検査 |
| `thumbgen/enrich.py` | 承認済み `source_url` のみ読み、帯合成とoverride反映 |
| `dashboard/creative.template.html` | 根拠・生成案1〜2・QA・承認・切替履歴・配信結果UIのプロトタイプ |
| authenticated dashboard API | generate / approve / publish / rollback / performance |

初期PoCではAPIを作る前に、読み取り専用スクリプト→JSON→ローカル管理画面の順で検証する。生成品質と運用ルールが固まる前に本番APIを作り込まない。

---

## 15. 実装開始前の意思決定

| 決定事項 | 推奨初期値 |
|---|---|
| 生成単位 | サロン |
| 画像参照 | 使わず、公式テキストのみ |
| 人物 | 架空の成人モデル。実在人物の再現禁止 |
| 店内表現 | 非特定のコンセプト空間。実店舗再現禁止 |
| 画像内文字 | 全面禁止。コード合成のみ |
| 1サロン候補数 | 生成案1を必須、生成案2を任意。上限2 |
| 自動公開 | しない |
| 再生成 | 根拠hash変更または人手指示時のみ |
| 保存 | privateメタデータ／public最終JPGを分離 |
| 最初の配信テスト | サロン単位のholdout、画像ソース以外を固定 |

---

## 16. 最初に実行する作業順

1. `catalog_feed.py` の商品化前レコードから `salon_id / salon_name / salon_url / top_catch / city / prefecture / product_ids` を出せるか確認する。
2. 実着地URLとcanonical salon URLを分けて、8サロン分の非公開ブリーフを作る。
3. 8件を人が読み、事実誤認・関連店舗混入・情報不足のルールを調整する。
4. `ready` のサロンだけ、version 1プロンプトで生成案1を個別生成し、必要なサロンだけ生成案2を追加する。
5. 生成結果を4:5へ正規化し、自動QAと管理画面の人手QAを通す。
6. 承認画像をまだ配信せず、運用時間・合格率・再生成率をレビューする。
7. 切替履歴と `product_id` 日次実績の結合を検証し、管理画面の「配信結果」でテストデータを表示する。
8. 権利・表示・保存・write権限・認証・帯1種のブロッカーが解消後、小規模配信実験へ進む。

この順序では、最初の実装対象は「AI生成ボタン」ではなく、**生成根拠の正規化と承認可能なブリーフ作成**になる。これが整ってから、ボタンを実画像生成へ接続する。
