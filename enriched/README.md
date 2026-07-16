# enriched/ — 情報帯を付与した配信用サムネ

`thumbgen/enrich.py`（定期実行: `.github/workflows/thumbnail-enrich.yml`）が生成する、
**推奨レイアウト（下部スクリム）でサロン名・エリアの情報帯を合成した配信用サムネ**の置き場。

- 元サムネ（リポジトリ直下の `<hash>.jpg`＝autofixの再抽出フレーム）を入力に、
  低情報なら改善（`improve.py`）→ 情報帯を合成 → ここへ `<hash>.jpg` として出力。
- `thumbnail_override` タブは id → `.../enriched/<hash>.jpg` を指し、本番フィードH1が最優先参照する。
- 更新結果は次で一覧確認できる:
  - `RESULTS.md` … サマリ＋各件の表
  - `index.html` … サムネ・ステータス・改善Before/Afterのギャラリー（フィルタ付き）

配信URL形式:
```
https://raw.githubusercontent.com/cajon-inc/hairbook-thumbnails/master/enriched/<hash>.jpg
```

> 画像本体・結果ファイルはワークフローが自動コミットする（ローカルのdry-run出力は追跡しない）。
