# メーカーキャリアラボ 企業比較 v3

全ファイルをGitHub Pagesリポジトリ直下に置けます。`index.html` がトップページ、`company-check.html` が企業比較画面です。`style.css` は共通CSSです。

## v3の追加
- `edinet_pipeline.py`: EDINET APIで有価証券報告書を発見し、CSV ZIPから財務候補を抽出（標準ライブラリのみ）
- `test_pipeline.py`: 合成CSVで抽出ロジックを検証
- `V3-DATA-OPERATIONS.md`: データ検証と承認・更新手順
- `company-check.html`: v3の収録状態・注意事項
- `validate_data.py`: 公開前検証を強化

**承認済みの実在企業データは0社です。** EDINET APIキーがなく、一次資料との照合を実施していないため、数値の自動公開はしません。会社名だけで実在企業を比較するには、まずデータ登録が必要です。架空デモは利用できます。

### GitHubにアップロードするファイル
解凍した全ファイルをリポジトリ直下に置いて構いません。PythonファイルはGitHub Pages上では実行されません。APIキーをリポジトリに追加しないでください。

詳しい手順: `V3-DATA-OPERATIONS.md`。


## v3.25.1：1,000社拡張手順

50社単位のEDINET監査と既存公開209社を維持する運用については [`V3251-1000-COMPANIES.md`](V3251-1000-COMPANIES.md) を参照してください。
