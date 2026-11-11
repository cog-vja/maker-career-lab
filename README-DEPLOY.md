# メーカーキャリアラボ デザイン再監査・第7サイクル修正（2026-11-11）

## このZIPの位置づけ

既存のGitHubリポジトリ `cog-vja/maker-career-lab` に適用する**差分パッケージ**です。サイト本体の全ファイル、企業データ、画像、Cloudflare設定の同梱ZIPではありません。

## 反映するファイル

GitHubリポジトリ直下に以下の3ファイルを**上書き**してください。

- `mcl_editorial_layer.py`（ホームの日本語分類、記事用の独自図解を改訂）
- `mcl-editorial.css`（PC/スマホの表・文字・ナビ・図解を改訂）
- `mcl-editorial.js`（比較結果の実名ラベル、割合差の「ポイント」表示、記事表スクロール案内）

`DESIGN.md`も同じ階層へ**上書き**してください。`AUDIT-DESIGN-R7.md`、`test_editorial_release.py`、`deep_audit.py`は監査結果・再テスト用です（公開ビルドの対象外）。

## 変更しないもの

- `company-data.js`（1,089社）、`company-compare.js`（計算と比較動作）
- `mcl_revenue_layer.py`、`cloudflare-build.py`、`mcl_seo_layer.py`
- GA4、A8、コンバージョン測定、月次更新、Google所有権確認ファイル
- `index.html`、既存記事HTML、canonical、sitemap（ビルド中の公開HTMLにデザインが合成されます）

## 操作手順

1. ZIPを解凍して、上記4つのファイルをGitHubの**リポジトリ直下**へ上書き。
2. コミットし、Cloudflareの `Workers & Pages → maker-career-lab-web → デプロイ` で新しいビルド結果を確認。
3. ビルドコマンドは従来どおり `python3 cloudflare-build.py`、デプロイは `npx wrangler deploy`。変更不要。
4. デプロイ成功後、`maker-career-lab.com/` のトップ・企業比較・業界比較・製造業IT/SCM記事で改修内容を確認。

## 本番確認チェック

- トップの小見出しが自然な日本語へ変わり、独自図解が1つだけある
- PCの企業比較は従来の表、スマホは**実際の会社名入り**2社並列
- 記事の横長表で、横スクロールが必要な画面幅のみ案内が出る
- 業界記事の図解が「工程と職種」、表が「市場・供給制約」を別々に説明する
- Google認証ファイル・既存収益化機能・広告のPR表記・SEOに変化がない

## 切り戻し

GitHubで今回更新した4ファイルを直前コミットに戻す。元の企業データや記事HTMLを戻す必要はありません。

## 検証の限界

公開HTMLの内容はオンラインで確認しました。一方、画面スクリーンショットは本番Webサイトの物理端末撮影ではなく、Chromiumで実装ファイルを用いたローカル再現画面です。PC 1024/1440px、スマホエミュレーション 320/375/390/430pxの計36パターンを検証しました。操作感・広告計測・ライブデータ比較の実機確認はデプロイ後に実施してください。
