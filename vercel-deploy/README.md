# vercel-deploy/ — クリエイティブ管理画面のデプロイパッケージ

`https://hairbook-dashboard.vercel.app/creative` で管理画面を配信するための静的パッケージ。

## 中身
- `creative/index.html` … 管理画面（自己完結・`dashboard/build_dashboard.py` で再生成）
- `vercel.json` … `/` → `/creative` リダイレクト

## デプロイ方法（いずれか）

### A. 既存の hairbook-dashboard プロジェクトに載せる（同じURLになる・推奨）
Vercelプロジェクト `hairbook-dashboard` を所有するアカウントで:
```bash
cd vercel-deploy
npx vercel --prod   # プロジェクト選択で hairbook-dashboard を指定
```
※ 既存プロジェクトが Next.js アプリの場合は、このHTMLをそのリポジトリの
`public/creative/index.html` に置くだけで `/creative` で配信される（ビルド不要・既存ルートと共存）。

### B. リポジトリ連携（自動デプロイ）
このフォルダ（または public/creative/ に置いたHTML）をデプロイ元リポジトリへコミット
→ Vercel が自動デプロイ。

> この管理画面は完全に静的（外部API不要・編集はlocalStorage保存）。
> 本番データ連携版（フィード読込・creative_config保存）は dashboard/IMPLEMENTATION_PLAN.md 参照。
