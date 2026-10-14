# v3.2 iPhone導入ガイド

v3.1で見つかった10社の書類IDを再利用するため、150日分の書類検索を繰り返しません。

## アップロードするファイル
GitHubのリポジトリ `cog-vja/maker-career-lab` の **mainブランチ直下**に、以下3ファイルを追加してください。
- `edinet_v32.py`
- `test_v32.py`
- `discovery-v31.json`

**注意**：これらは新規ファイルです。公開サイトの `company-data.js` を更新しません。

## ワークフローファイル
iPhoneでは `.github` フォルダが見えない場合があります。
GitHubで「Add file → Create new file」から次のパスを入力します。

`.github/workflows/edinet-v32-diagnose.yml`

ZIP内の同名ファイルの内容をGitHubエディターへコピーし、mainにCommitしてください。

## 実行
`https://github.com/cog-vja/maker-career-lab/actions/workflows/edinet-v32-diagnose.yml`

「Run workflow」→ 初回は `limit=1` →「Run workflow」。診断結果をZIPでダウンロードしてこのチャットに送ってください。
初回結果のヘッダーと抽出候補を確認後、`limit=10` にして全社実行します。

## 出力
- `summary.json` : 会社ごとの成否と候補件数
- `SUMMARY.md` : 結果概要
- `<証券コード>-<docID>-diagnostic.json` : CSVファイルの列構成、検出されたXBRL候補・エラー

数値は未検証です。連結・単体、会計期間、会社ごとのタクソノミー定義、訂正報告書の確認まで公開禁止です。
GitHub ActionsのArtifactsはログインユーザーが取得できるため、公開サイトのデータとして扱わないでください。
