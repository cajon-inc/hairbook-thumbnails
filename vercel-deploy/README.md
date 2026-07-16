# vercel-deploy/ — クリエイティブ管理画面のデプロイパッケージ

`https://hairbook-dashboard.vercel.app/creative` で管理画面を配信するための静的パッケージ。

## 中身
- `creative/index.html` … 管理画面（自己完結・`dashboard/build_dashboard.py` で再生成）
- `vercel.json` … `/` → `/creative` リダイレクト

## デプロイ方法

### A. 既存プロジェクトに /creative を共存させる（同じURL・推奨・非破壊）
`hairbook-dashboard` のデプロイ元リポジトリに、この1ファイルを置くだけ:
```
<デプロイ元リポ>/public/creative/index.html   ← creative/index.html をコピー
```
コミット→push で Vercel が自動デプロイ。既存アプリのルートと**共存**し、
`/creative` で配信される（ビルド設定の変更不要）。

> ⚠️ 注意: `vercel-deploy/` フォルダを単体で `npx vercel --prod` して既存プロジェクトに
> 紐づけると、**既存ダッシュボード全体がこの静的ページに置き換わる**。既存アプリを保つ場合は
> 必ず上記A（リポジトリに public/creative/ として追加）で行うこと。

### B. 別URLのプレビューとして新規デプロイ（既存に触れない）
既存アプリを一切変更せず、別プロジェクト/別URLで公開したい場合のみ:
```bash
cd vercel-deploy
npx vercel --prod   # 新規プロジェクト名を指定（例: hairbook-creative）
```

> この管理画面は完全に静的（外部API不要・編集はlocalStorage保存）。
> 本番データ連携版（フィード読込・creative_config保存）は dashboard/IMPLEMENTATION_PLAN.md 参照。
