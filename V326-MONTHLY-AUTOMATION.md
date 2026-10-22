# メーカーキャリアラボ v3.26 — 1,000社以上対応・月次自動更新

## 最初の一回（GitHub上で実施）

1. 同梱パッチのファイルを**リポジトリ直下の同名パスに配置**してcommitします。特に `company-data.js` は **1,089社版**です。
2. `Settings → Secrets and variables → Actions → Secrets` に `EDINET_API_KEY` が登録済みか確認します。
3. GitHub Pagesの公開方式が `Deploy from a branch`（`main` / `/ (root)`）なら、**Fine-grained PAT** を発行します。対象リポジトリは `cog-vja/maker-career-lab` のみに絞り、`Contents: Read and write` を許可します。**トークンそのものはチャット等で共有しない**でください。ActionsのRepository secretに `MCL_PAGES_PUBLISH_PAT` として登録します。既に登録済みなら追加設定不要です。
4. `Actions → EDINET v3.26 monthly verified-only refresh (1000+) → Run workflow` で `scan_days=55` の手動実行を1回試します。`mcl-v326-monthly-*` の成果物とログを確認します。
5. 以後は**毎月5日12:23（日本時間）**に自動実行します（GitHubの負荷により遅延・取りこぼしあり）。

## 処理仕様

- EDINET API提出書類一覧を過去55日分確認。掲載済み企業のみ対象です（社数の追加・削除・順序変更は禁止）。
- 新しい有価証券報告書を原本XBRLから取得し、6指標の照合、決算期・会計基準・異常値チェックを通過した企業だけを変更候補へ反映します。
- 訂正報告書、会計基準変更、XBRL指標不足、異常な年収変動等は保留して `monthly-details-v325.json` に記録します。保留企業の従来値は維持し、他社の合格更新まで止めません。
- 変更が0社ならGitHubのcommitは発生しません。合格データがあれば厳格なオフライン検証を通して `company-data.js` のみcommitします。
- 自動commitには `MCL_PAGES_PUBLISH_PAT` が必要です。GitHubの通常の `GITHUB_TOKEN` によるcommitは、ブランチ公開型GitHub Pagesの再ビルドを起こしません。PATがなければ**レポートだけ保存し、公開ステップは失敗**します。
- 監査ログはActions artifactsに90日保存。GitHub Pagesサイト表示はGitHub側の公開処理完了後に切り替わります。
- 古いv3.21/v3.22/v3.23月次ワークフローはスケジュールを解除し、手動実行だけを残しました。v3.25拡張監査ワークフローは変更しません。

## ページの表示変更

- `index.html`・`company-check.html`・`articles/it-scm-career.html` の「200社以上」を「1,000社以上」に変更。
- `articles/salary-market.html` は、209社時点の統計を1,089社の統計と誤認させないよう、分析対象を209社と明示し、現在の比較ツールの収録数は1,000社以上と記載。
- 企業比較ツールは会社数をJSの実レコード数から動的表示します。月次更新でも企業数は固定されます。

## 注意点・制約

- **月次更新は未検証の新会社を追加しません。** 会計数値の完全な独立照合や全社の本文目視確認を保証するものではありません。
- `company-data.js` の1,089社版は2026-10-22の提供物に基づきます。GitHubで**その後に変更している場合は先に差分比較**してください。
- GitHub Pagesが `GitHub Actions` 公開方式の場合、このPATでのブランチ更新は再公開の動作条件が異なるため、専用のPagesデプロイ設定が必要です。
- GitHub側でブランチ保護が有効な場合、PATの対象権限・プッシュ可否を確認してください。
- 月次更新で `company-data.js` が更新されても、EDINET API停止・GitHubの定期実行停止・外部仕様変更時の再試行や通知までは保証しません。
