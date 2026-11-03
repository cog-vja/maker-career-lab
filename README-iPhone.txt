メーカーキャリアラボ｜月3万円収益化監査 差分パッチ
作成日: 2026年11月3日
公開ドメイン: https://maker-career-lab.com/
GitHub: https://github.com/cog-vja/maker-career-lab

【重要】これは既存リポジトリへ追加・上書きする差分ZIPです。
既存のcompany-data.js、company-compare.js、EDINET取得用スクリプト、A8広告素材は含めていません。これらは変更しないでください。

【本番公開に必要な6ファイル】
リポジトリの直下へ上書き・新規追加する4ファイル：
  cloudflare-build.py        （既存ファイルを上書き）
  mcl_revenue_layer.py      （新規追加）
  mcl-revenue.css           （新規追加）
  mcl-revenue.js            （新規追加）

GitHubの articles/ フォルダ内へ追加する2ファイル：
  articles/manufacturer-career-checklist.html
  articles/manufacturer-engineer-agent-selection.html

【任意：GitHubに入れても公開されない監査用ファイル】
  tests/test_revenue_release.py  （テスト時のみ使用）
  AUDIT-REPORT-2026-11-03.md （監査結果）
  MANIFEST.json             （ハッシュ付きファイル一覧）
  README-iPhone.txt         （この手順）

【iPhoneから反映する手順】
1. ZIPを「ファイル」アプリに保存し展開します。
2. GitHubで上記リポジトリの main ブランチを開きます。
3. 直下の4ファイルを追加・更新（cloudflare-build.pyだけ既存のものを上書き）。
4. articles フォルダに新規2記事を追加します。
5. **4 + 2 の合計6ファイルがmainにそろった状態**でCloudflareの自動ビルドを確認してください。
   注：cloudflare-build.pyだけを先に反映すると、新モジュールがないためビルドエラーになります。
6. Cloudflareの Workers & Pages → maker-career-lab-web → Deployments を開いて成功を確認します。

【公開後の確認URL】
  https://maker-career-lab.com/
  https://maker-career-lab.com/company-check
  https://maker-career-lab.com/articles/manufacturer-career-checklist
  https://maker-career-lab.com/articles/manufacturer-engineer-agent-selection
  https://maker-career-lab.com/articles/science-career-market
  https://maker-career-lab.com/articles/it-scm-career
  https://maker-career-lab.com/sitemap.xml

【確認ポイント】
- トップに「企業を調べた後は、自分に合う仕事か確認する」が1度だけ表示される
- 企業比較の後に、無料チェックリストと技術職向けガイドへのリンクがある
- 7つのチェック欄、コピー、印刷・PDF保存の動作が正常
- 理系就活記事に学生向けの導線がある
- 新2記事が sitemap に入っており、canonical がmaker-career-lab.comである
- 本番GA4に mcl_funnel_action が記録され、従来の計測や広告クリックが残っている
- 右下のA8転職広告は指定された転職向け記事のみであり、他ページに拡大されていない
- 企業比較が実際の既存1,000社以上データで正しく動く

【オフライン検証】
Pythonが利用できる場合、GitHubリポジトリ直下から:
  python tests/test_revenue_release.py
配布パッケージで2テストに成功しています。実運用のHTTP・広告成果は未検証です。

【調査・提携について】
アカリク／スミジョブは第三者サイトでA8取扱い情報を確認しました。
その他のサービスも含め、当サイトの実際の提携承認や成果単価は未確認です。
承認されていない広告リンクは追加していません。
詳細は AUDIT-REPORT-2026-11-03.md をご確認ください。
