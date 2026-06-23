# hairbook-thumbnails

Hairbook カタログ広告フィードの image_link 差し替え用サムネイル画像ホスティング。

- ヘアブック自動生成サムネが真っ白/低情報になった商品について、元動画から抽出した代替フレームを配置。
- ファイル名は post id のハッシュ（salon_id 等は出さない）。
- 対応表（id ↔ ハッシュ）は本番フィードスプシの override タブで管理（非公開）。
- raw URL を Meta カタログフィードの image_link に指定して配信する。
