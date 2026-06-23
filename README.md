# hairbook-thumbnails

Hairbook カタログ広告フィードの `image_link` 差し替え用サムネイル画像のホスティング。

## これは何か

ヘアブックが動画から自動生成するサムネが真っ白／低情報になった商品について、
**元動画から抽出し直した代替フレーム**を置く場所。Meta カタログがここの raw URL を取得して配信する。

## 仕組み（概要）

1. 不良サムネを検出
2. 元動画から良フレームを抽出（情報量×静止度の合成スコアで選別）
3. ここ（public repo）に push して安定した raw URL で配信
4. フィード側の数式が id→画像URL を差し替え

## ファイル

- `<hash>.jpg` … ファイル名は投稿IDのハッシュ（salon_id 等の内部情報は含めない）。
- id ↔ hash の対応表・選別ロジック・配信フィードの詳細は**社内ドキュメント（非公開）**で管理。

## 配信URL形式

```
https://raw.githubusercontent.com/cajon-inc/hairbook-thumbnails/master/<hash>.jpg
```

> 画像は元々 hairbook.jp で公開配信されている広告クリエイティブのフレーム。
