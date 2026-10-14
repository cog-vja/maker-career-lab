# v3：EDINET実数値取得・検証ガイド

## 現時点で可能なこと
- EDINET API v2の書類一覧を企業名で絞り込む。
- EDINET CSV (type=5) ZIPを取得し、主要XBRLタグを保守的に抽出する。
- 候補を `company-candidates.csv` と `.review.json` に保存する。
- 手動で一次資料を照合し、`company-review-template.csv` に承認済み行を登録した後、`validate_data.py` でサイト表示データを生成する。
- 2社比較・解釈・出典表示は従来通り。

## 重要な限界
**このZIPの公開データは承認済み0社です。** この環境にはユーザーのEDINET APIキーがないため、実際のEDINETから5〜10社の数値を取得・照合していません。実数値を架空に作っていません。**v3は自動抽出の検証版であり、企業名を入れるだけで実在企業が比較できる完成版ではありません。**

## APIキーを安全に用意
1. EDINET公式のAPIキー発行画面で登録（ https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1 ）。
2. 自分のPCやGitHub ActionsのSecret `EDINET_API_KEY` に登録する。HTML/JS/公開CSVにキーを置かない。
3. 企業検索: `python3 edinet_pipeline.py discover --days 60 --names 'アドバンテスト,東京エレクトロン,ディスコ'` 。対象企業の有報が60日間に提出されていなければ出ません。過去日付を指定するなら `--start 2026-04-01`（現在から366日以内）。
4. 書類IDを確認後、`python3 edinet_pipeline.py extract --doc-id S1234567 --company-name '会社名' --edinet-code E00000` 。書類IDとコードは必ず実際の検索結果に置換。
5. 手元にZIPがあれば `--zip-file path/to/report.zip` でオフライン抽出可能。
6. 出力された `company-candidates.csv` と `company-candidates.review.json` を確認する。

## 手動検証が必須
- EDINET書類ID、提出会社、対象決算期、提出日、訂正有無、連結/単体、会計基準を確認。
- 抽出タグとコンテキスト、金額単位、前年値、営業利益定義を原本と突合。
- 売上高・営業利益・営業CFは「億円」、給与は「万円」。
- 自己資本比率はXBRLの単位・定義の違いがあるため **自動採用しない**。原本で確認し、%に換算して入力。
- 検証済み行のみ `company-review-template.csv` に転記し、`review_status=approved`、照合日・照合者・原本URLを入力。
- `python3 validate_data.py company-review-template.csv` を実行して `company-data.js` を生成する。**承認前に生成しない**。
- 実在企業が2社以上収録されると比較画面で検索できる。

## 注意すべき設計上の限界
- XBRLには企業独自の拡張タグ、IFRS、日本基準、決算期、コンテキスト、単位の差があり、全社の数値を網羅的に取得できる保証はない。
- 本スクリプトは曖昧な候補や複数値が衝突する場合は空欄にする。給与も単体の範囲を別途確認。
- APIの利用規約、著作権・第三者権利、アクセス制限、訂正報告書を確認する。短時間の大量アクセスを避ける。
- **データ更新は自動承認しない。** 訂正書類が出た場合、既存値を自動上書きしない。
- GitHub Pagesのサイト訪問者がEDINET APIにアクセスすることはない。

## テスト
`python3 -m unittest test_pipeline.py` を実行。これは合成CSVによるロジックテストであり、実在企業の数値の正しさを保証しない。

## 検証候補10社（未収録）
アドバンテスト、東京エレクトロン、SCREENホールディングス、ディスコ、レーザーテック、ファナック、キーエンス、オムロン、安川電機、村田製作所。

## 公式資料
- EDINET API仕様書・関連資料 https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0110.html
- EDINET利用規約 https://disclosure2dl.edinet-fsa.go.jp/guide/static/submit/WZEK0030.html
- APIキー登録 https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1
