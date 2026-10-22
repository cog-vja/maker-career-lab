# メーカーキャリアラボ v3.25.1 — 1,000社拡張版（調査手順はv3.25を継承）

## 目的と変更範囲

既存209社の公開データ・画面・広告を変更せず、EDINET原本XBRLで**6指標照合**した製造業企業を、50社ずつ積み増して**合計1,000社以上の公開候補**を集めます。

- v3.25の `bootstrap → audit-batch → stage-review` を**維持**。新しいBootstrapは不要。
- 新規6指標照合済み企業を `staging-candidates.csv` に**自動抽出**（`include=YES`）。「審査済み」「公開承認済み」という意味ではありません。
- 指標欠損、訂正報告書の未確認、有価証券報告書なし、原本監査エラーは従来どおり**除外**。
- `stage-review` は照合証跡を再検査して**ダウンロード用の候補JSを作るだけ**。GitHubへのコミット・Pagesへのデプロイなし。
- 従来の6指標照合に独立EDINET CSV突合や個社ごとの新しい手動レビュー項目を**追加しません**。公開直前のデータ検査・最終確認は必要です。
- 600社・525社という固定件数は設けません。Stageの最小候補数はActions画面で選択（通常 `1000`）。

## 反映方法

1. このGitHub更新ZIPを展開し、`maker-career-lab-main/` 配下の**内容**をリポジトリ直下に配置する（上書き）。GitHubの既存ファイルは削除しない。
2. `company-data.js` のSHA256が引き続き `f537551070013639acb6f1c3396b4ea0386701d2b9e91bd3ece21adc8d530ade` であることを確認する。
3. `.github/workflows/edinet-v325-expansion-review.yml` の **EDINET v3.25 expansion REVIEW ONLY** をActionsから実行する。
4. **Mode `audit-batch`**、Bootstrap run ID `39435494812`、Offset `600` で実行する。続けて `650, 700, 750, 800, 850, 900` と50ずつ実行する（未調査の対象が残る限り）。
5. バッチ出力 `mcl-v325-audit-b{offset}-root39435494812` をその都度ZIPで保存する。GitHub Actions Artifactには保持期限（このWorkflowでは90日）があるため、重要。
6. 新規調査が揃ったらMode **`stage-review`**、同じBootstrap run ID、`require_count=1000`、`acknowledgement=REVIEWED_REPORTS` を入力して実行。入力文字列は従来と同じ。これは**ステージング作成の確認**であり、公開承認や数値の独立検証を意味しない。
7. Actionの成果物 `mcl-v325-staged-...` にある `REVIEW-BATCHES.json`、`staging-candidates.csv`、`MANUAL-RELEASE-SUMMARY.json` およびステージング用 `company-data.js` を確認する。
8. 異常値・書類ID・会計範囲・重複・企業数を確認して**別途公開判断**する。ステージングしただけで実サイトは更新されない。

## 重要な制約

- **現行の `company-data.js` は追加調査が完了するまで更新しない**。Bootstrap作成時の公開ベースラインとのSHA256一致が必要です。
- `stage-review` は同じBootstrapのOffset `0` から `50` 刻みで**途中欠けがないバッチ**を収集する。1件でも欠けると停止。候補件数が1,000社未満でも停止。
- ブートストラップ内の未調査企業が尽きたら、`audit-batch` は空バッチとして停止します。そのときは、既存の公開元データの保全と新Bootstrap作成の時期を別途判断してください。
- バッチは依然として単一の公式文書・基準日から得たデータのスナップショットです。市場データの更新、公開用数値の最終確認、独立した突合は別作業です。
- 秘密情報や監査用の元ZIPはこのGitHub更新ZIPに含みません。`EDINET_API_KEY` はGitHub Secretsで管理してください。

## 数字の目安（2026-10-22現在の提出済み監査に基づく）

| 内訳 | 件数 |
|---|---:|
| 公開済み既存企業 | 209 |
| 監査実施（Offset 0〜550） | 600 |
| 原本6指標照合済み新規候補 | 525 |
| 保留企業 | 75 |
| 現時点の最大ステージング候補 | 734 |
| 1,000社到達までの不足候補 | 266 |

候補率87.5%を仮定した場合、追加調査は約304社分が目安です。Offset 600〜900の7バッチ（最大350社）の後に再集計してください。調査対象を使い切ることもあり、件数は保証されません。

## 検証コマンド

```bash
python3 -m unittest -v test_v325.py test_v3251_scale.py
node --check company-data.js
sha256sum company-data.js
```

古い `--approvals` は既存の手動ステージングと互換のため残しています。標準のGitHub Actionsは、新しい `--candidates` と `include` CSVで**原本6指標照合済み候補をステージング**するだけです。
