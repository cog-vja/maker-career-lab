# メーカーキャリアラボ｜ホームコンパクト版（2026-11-11）

## 適用方法

このZIPは **既存のGitHubリポジトリに上書きする差分アップデート**です。Cloudflareの `dist/` を直接アップロードするZIPではありません。

GitHubリポジトリ `cog-vja/maker-career-lab` の **直下**で、次の4ファイルを上書きしてください。

- `mcl_editorial_layer.py`
- `mcl-editorial.css`
- `mcl-editorial.js`
- `DESIGN.md`

`README-DEPLOY.md`, `AUDIT-HOME-COMPACT.md`, `test_home_compact.py`, `TEST-RESULTS.json` は参照・再検証用の資料です。GitHubへの追加は任意です。

`cloudflare-build.py` / `mcl_revenue_layer.py` / `mcl_seo_layer.py` / `mcl-revenue.js` / `company-data.js` / `company-compare.js` / `.github/workflows` / `wrangler.jsonc` は変更しません。

## 動作方法

既存のビルドコマンド `python3 cloudflare-build.py` が最終工程で `mcl_editorial_layer.augment_editorial_output()` を呼ぶ仕組みをそのまま使います。`dist/index.html` のみ、ヒーローと横スクロール記事一覧へ短縮します。

`mcl-revenue.js` による全記事検索・カテゴリフィルターは折りたたみ内に移動し、元の記事は保持します。JavaScript無効時も16件のHTMLリンクが残ります。既存の記事図解4点は維持し、ホーム図解だけを削除します。

## デプロイ後の確認

1. `https://maker-career-lab.com/` をスマホで開き、最初の比較ボタンの直後が記事一覧になっていることを確認。
2. 左右スワイプで記事を選び、リンクを開く。
3. 「すべての記事を検索する」を展開し、カテゴリ切替・キーワード検索が使えることを確認。
4. `https://maker-career-lab.com/company-check` で実データ2社の比較、出典・警告・モバイル表が維持されることを確認。
5. 任意の記事でPR表記と図解を確認し、Google Search Console / GA4 / Cloudflare デプロイ成功を確認。

**注意:** ローカルのChromium検証には合格していますが、Cloudflare本番での再ビルドとiPhone Safariの最終操作は未検証です。
