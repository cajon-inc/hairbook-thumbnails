# Contributing / 運用上の注意

## ⚠️ このリポジトリは public です

Meta カタログ広告が `raw.githubusercontent.com` の URL を直接参照して画像を配信するため、
このリポジトリは**意図的に public** になっています。push する前に必ず以下を確認してください。

## push してよいもの

- **ハッシュ名のサムネイル画像(`<hash>.jpg`)のみ**
- 画像は元々 hairbook.jp で公開配信されている広告クリエイティブのフレームに限る

## push してはいけないもの

- `salon_id` などの内部IDを含むファイル名・ファイル
- id ↔ hash の対応表(社内ドキュメントで管理する)
- フレーム抽出・選別のスクリプトや設定ファイル
- `.env`・認証情報・トークン類(いかなる形でも不可)
- 社内向けドキュメント

## 禁止事項

- **リポジトリのリネーム・ブランチ(`master`)のリネーム** — 配信中の raw URL が壊れます
- **git 履歴の書き換え(force push)** — 配信中の画像 URL が壊れる恐れがあります
- 配信中の画像の削除(フィード側の差し替えが完了してから削除すること)

## 権限について

public リポジトリのため、push 権限・admin 権限は必要最小限に保ちます。
admin は原則 Organization Owner のみとします。

## 関連

- [リポジトリ運用ガイド](https://github.com/cajon-inc/meta-managements/blob/main/docs/repository-guide.md)
