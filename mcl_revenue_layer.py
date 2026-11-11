#!/usr/bin/env python3
"""Existing Cloudflare revenue enhancement, with SEO and editorial generation appended.

The existing A8 creatives and analytics handlers are never modified here.
"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

REVENUE_ARTICLES = (
    'articles/manufacturer-career-checklist.html',
    'articles/manufacturer-engineer-agent-selection.html',
)
ASSETS = ('mcl-revenue.css', 'mcl-revenue.js')

HOME_BLOCK = '''
<section id="career-next-step" class="mcl-revenue-section" aria-labelledby="revenue-next-title">
 <div class="container">
  <div class="eyebrow">FROM DATA TO ACTION</div>
  <h2 id="revenue-next-title">企業を調べた後は、自分に合う仕事か確認する</h2>
  <p>企業の平均年間給与は、応募職種の提示年収ではありません。年収の比較から、職務・勤務地・働き方・昇給の確認へ進みましょう。</p>
  <div class="mcl-revenue-grid">
   <div class="mcl-revenue-card"><span class="tag">社会人・転職を検討中</span><h3>転職前の7項目チェックリスト</h3>
    <p>応募前に求人票で見る条件を整理し、2社比較から次の行動を決める無料ツール。</p>
    <a data-mcl-funnel="home_checklist" class="mcl-revenue-link" href="articles/manufacturer-career-checklist">無料チェックリストを見る</a></div>
   <div class="mcl-revenue-card"><span class="tag">技術職・研究開発・生産技術</span><h3>技術職向け転職サービスの選び方</h3>
    <p>担当領域、配属、専門性、相談方法からサービスを比較。提携状況と編集判断を分離します。</p>
    <a data-mcl-funnel="home_engineer" class="mcl-revenue-link" href="articles/manufacturer-engineer-agent-selection">技術職向けの比較ガイドを見る</a></div>
  </div>
  <p class="mcl-revenue-small">転職やサービス登録を勧めるものではありません。企業比較の数字と広告報酬は独立しています。</p>
 </div>
</section>
'''

COMPARE_BLOCK = '''
<section id="mcl-after-comparison" class="mcl-revenue-after" aria-labelledby="mcl-next-heading">
 <h2 id="mcl-next-heading">比較した数字を、応募前の確認事項に変える</h2>
 <p>利益率が高い会社でも、希望職種の年収・転勤・評価制度が合うとは限りません。比較後は条件を確認しましょう。</p>
 <ol><li>候補2社の<strong>希望職種の求人票</strong>を確認する</li>
     <li>勤務地、転勤、手当、残業、昇給・配属制度を比べる</li>
     <li>応募するか決める前に、条件の優先順位を整理する</li></ol>
 <p><a data-mcl-funnel="compare_checklist" class="mcl-revenue-link" href="articles/manufacturer-career-checklist">7項目の無料チェックリストへ</a>　
 <a data-mcl-funnel="compare_engineer" href="articles/manufacturer-engineer-agent-selection">技術職のサービス選びへ</a></p>
 <p class="mcl-revenue-small">本ツールの企業データと、広告掲載・収益は独立しています。</p>
</section>
'''

ARTICLE_BLOCK = '''
<aside class="mcl-revenue-aside" aria-label="関連する無料ガイド">
 <strong>企業比較から、具体的な求人確認まで</strong>
 <p>仕事内容と勤務地を確認する無料のチェックリストと、技術職向けの転職サービス選びを解説しています。</p>
 <p><a data-mcl-funnel="article_checklist" href="manufacturer-career-checklist">応募前チェックリスト</a> / 
 <a data-mcl-funnel="article_engineer" href="manufacturer-engineer-agent-selection">技術職向けサービスの選び方</a></p>
</aside>
'''

STUDENT_BLOCK = '''
<aside class="mcl-revenue-aside" aria-label="理系就活の比較ガイド">
 <strong>理系学生の方向け：サービス選びも職種から考える</strong>
 <p>修士・博士の研究内容と志望する仕事が合うか、メーカーの募集要項と理系向けサービスの情報を比べましょう。</p>
 <p><a data-mcl-funnel="student_services" href="manufacturer-engineer-agent-selection#students">学生向けサービスの選び方を見る</a></p>
 <p class="mcl-revenue-small">紹介記事のサービス名・リンクは、提携済みの広告を意味しません。</p>
</aside>
'''

def insert_once(body: str, needle: str, block: str, marker: str, title: str) -> str:
    if marker in body:
        return body
    if body.count(needle) != 1:
        raise RuntimeError(f'{title} の挿入位置が想定外: {body.count(needle)}件')
    return body.replace(needle, block + '\n' + needle, 1)


def augment_output(out: Path, copied_html: list[str], root: Path) -> None:
    for asset in ASSETS:
        src = root / asset
        if not src.is_file():
            raise RuntimeError(f'収益導線アセットが不足: {asset}')
        shutil.copyfile(src, out / asset)

    expected = set(REVENUE_ARTICLES)
    if not expected.issubset(set(copied_html)):
        raise RuntimeError('収益導線の記事がdistに出力されていません')

    for name in copied_html:
        path = out / name
        html = path.read_text(encoding='utf-8')
        if name == 'index.html':
            html = insert_once(html, '<section id="start-here"', HOME_BLOCK,
                               'id="career-next-step"', 'トップページ')
        elif name == 'company-check.html':
            html = insert_once(html, '<section class="mcl-onecareer-end"', COMPARE_BLOCK,
                               'id="mcl-after-comparison"', '企業比較ページ')
        elif name in ('articles/agent-guide.html', 'articles/it-scm-career.html'):
            html = insert_once(html, '</article>', ARTICLE_BLOCK,
                               'class="mcl-revenue-aside"', name)
        elif name == 'articles/science-career-market.html':
            html = insert_once(html, '</article>', STUDENT_BLOCK,
                               'data-mcl-funnel="student_services"', name)
        if name.endswith('.html'):
            base = '../' if name.startswith('articles/') else ''
            if 'mcl-revenue.css' not in html:
                if html.count('</head>') != 1:
                    raise RuntimeError(f'{name}: </head> 件数が想定外')
                html = html.replace('</head>', f'<link rel="stylesheet" href="{base}mcl-revenue.css"></head>', 1)
            if 'mcl-revenue.js' not in html:
                if html.count('</body>') != 1:
                    raise RuntimeError(f'{name}: </body> 件数が想定外')
                html = html.replace('</body>', f'<script src="{base}mcl-revenue.js" defer></script></body>', 1)
        path.write_text(html, encoding='utf-8')

    if (out / 'index.html').read_text(encoding='utf-8').count('id="career-next-step"') != 1:
        raise RuntimeError('トップページの収益導線が不足・重複しています')
    if (out / 'company-check.html').read_text(encoding='utf-8').count('id="mcl-after-comparison"') != 1:
        raise RuntimeError('比較ページの収益導線が不足・重複しています')
    print('[OK] Audience landing pages / post-compare action routes / non-PII funnel assets')

    # Add search-intent landing pages AFTER the original, audited revenue layer.
    from mcl_seo_layer import augment_seo_output
    augment_seo_output(out, copied_html, root)

    # Production-only editorial treatment: preserve all source HTML, data and ads.
    from mcl_editorial_layer import augment_editorial_output
    augment_editorial_output(out, root)
