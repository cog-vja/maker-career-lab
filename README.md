# メーカーキャリアラボ 企業比較 v3

現在の本番は Cloudflare Workers Static Assets です。

`python3 cloudflare-build.py` が `dist/` を生成し、公開対象を選びます。開発・リリースの手順は [AGENTS.md](AGENTS.md) と [README-PDCA.md](README-PDCA.md) を参照してください。`index.html` がトップページ、`company-check.html` が企業比較画面です。`style.css` は共通CSSです。

## v3の追加
- `edinet_pipeline.py`: EDINET APIで有価証券報告書を発見し、CSV ZIPから財務候補を抽出（標準ライブラリのみ）
- `test_pipeline.py`: 合成CSVで抽出ロジックを検証
- `V3-DATA-OPERATIONS.md`: データ検証と承認・更新手順
- `company-check.html`: v3の収録状態・注意事項
- `validate_data.py`: 公開前検証を強化

現在の比較データは、EDINET原本と照合済みの1,000社以上を `company-data.js` で提供しています。月次の追加・差し替えは専用ワークフローでレビュー用PRにし、公開前に確認します。

### 開発とデータ取得
Pythonのビルドと検証はローカルまたはCIで実行します。APIキーをリポジトリに追加しないでください。

詳しい手順: `V3-DATA-OPERATIONS.md`。


## v3.25.1：1,000社拡張手順

50社単位のEDINET監査と既存公開209社を維持する運用については [`V3251-1000-COMPANIES.md`](V3251-1000-COMPANIES.md) を参照してください。
