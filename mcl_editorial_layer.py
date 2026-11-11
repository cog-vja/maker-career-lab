#!/usr/bin/env python3
"""Production-only editorial design layer for Maker Career Lab.

Runs after existing Cloudflare, revenue and SEO transforms. Does not mutate the
source HTML, published numbers, analytics IDs, affiliate creatives or update jobs.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ASSETS = ('mcl-editorial.css', 'mcl-editorial.js')
MARKER = 'data-mcl-editorial="2026-11"'

HOME_FIGURE = '''
<section class="mcl-editorial-section" aria-labelledby="mcl-editorial-home-title" data-mcl-figure="home">
 <div class="container">
  <div class="mcl-figure-kicker"><span>図解 01</span> 製造業の企業研究</div>
  <h2 id="mcl-editorial-home-title">企業を見る前に、製品と工程を知る。</h2>
  <p class="mcl-figure-lead">同じメーカーでも、製品が使われる工程と、そこで求められる仕事は異なります。</p>
  <figure class="mcl-map-figure mcl-map-figure--home">
   <div class="mcl-map-caption">半導体製造装置メーカーを調べるときの例</div>
   <div class="mcl-flow-columns">
    <div class="mcl-flow-node"><span class="mcl-flow-type">製品</span><strong>成膜・洗浄・検査などの装置</strong><small>各社の製品領域は異なる</small></div>
    <div class="mcl-flow-node"><span class="mcl-flow-type">使われる工程</span><strong>ウェハ製造・検査工程</strong><small>装置に応じて担当工程が異なる</small></div>
    <div class="mcl-flow-node"><span class="mcl-flow-type">関わる仕事</span><strong>設計・生産技術・品質・IT／SCM</strong><small>実際の職務は求人票で確認</small></div>
   </div>
   <figcaption>企業研究のための概念図。特定企業の製品構成や、製造工程の厳密な順序を表すものではありません。</figcaption>
  </figure>
 </div>
</section>
'''

INDUSTRY_FIGURE = '''
<figure class="mcl-map-figure mcl-article-figure" data-mcl-figure="industry" aria-labelledby="mcl-industry-fig-title">
 <div class="mcl-figure-kicker">独自図解 01 / 業界で異なる工程と職種</div>
 <div class="mcl-map-caption" id="mcl-industry-fig-title">「生産管理」という同じ職種でも、扱う製品と工程が違う</div>
 <div class="mcl-sector-list">
  <div class="mcl-sector-row"><strong class="mcl-sector-name">半導体装置の例</strong><div class="mcl-sector-process"><span>装置を届けるまでの仕事</span><ol class="mcl-mini-steps"><li>部材を調達</li><li>装置を組立・調整</li><li>顧客工程で立上げ</li></ol></div><div class="mcl-sector-role"><span>関係する職種例</span><b>調達・生産技術・フィールドサービス</b></div></div>
  <div class="mcl-sector-row"><strong class="mcl-sector-name">自動車部品の例</strong><div class="mcl-sector-process"><span>量産工程の例</span><ol class="mcl-mini-steps"><li>材料・部品を準備</li><li>加工・組立</li><li>検査・出荷</li></ol></div><div class="mcl-sector-role"><span>関係する職種例</span><b>生産管理・品質保証・生産技術</b></div></div>
  <div class="mcl-sector-row"><strong class="mcl-sector-name">加工食品の例</strong><div class="mcl-sector-process"><span>製造・供給の例</span><ol class="mcl-mini-steps"><li>原料を受入</li><li>加工・包装</li><li>品質確認・出荷</li></ol></div><div class="mcl-sector-role"><span>関係する職種例</span><b>生産管理・品質保証・物流</b></div></div>
 </div>
 <figcaption>工程・役割の模式例です。各企業の実際の工程や厳密な順序を示すものではありません。下の表では、市場や供給制約が仕事に与える影響を比較します。</figcaption>
</figure>
'''

IT_SCM_FIGURE = '''
<figure class="mcl-map-figure mcl-article-figure" data-mcl-figure="it-scm" aria-labelledby="mcl-itscm-fig-title">
 <div class="mcl-figure-kicker">独自図解 02 / 製造業IT・SCMの仕事</div>
 <div class="mcl-map-caption" id="mcl-itscm-fig-title">生産計画が変わったとき、誰が何を確認するのか</div>
 <div class="mcl-flow-issue"><span>変更の発端</span><strong>生産計画に変更が発生</strong></div>
 <div class="mcl-role-grid">
  <div class="mcl-role"><span>01 / 生産管理</span><strong>需要と供給の再調整</strong><small>優先順位・生産日程・制約条件</small></div>
  <div class="mcl-role"><span>02 / 調達</span><strong>部材の納期を確認</strong><small>仕入先・発注・入荷見込み</small></div>
  <div class="mcl-role"><span>03 / 製造現場</span><strong>設備と段取りを確認</strong><small>作業順序・要員・仕掛品</small></div>
  <div class="mcl-role"><span>04 / 製造業IT・DX</span><strong>情報が正しく流れる状態をつくる</strong><small>業務ルール・データ連携・要件定義</small></div>
 </div>
 <figcaption>一般化した例。関係部門は同時並行で動くことがあり、上記は厳密な作業順序ではありません。実際の責任分担は企業によって異なります。</figcaption>
</figure>
'''

PROFIT_FIGURE = '''
<figure class="mcl-map-figure mcl-article-figure" data-mcl-figure="profit" aria-labelledby="mcl-profit-fig-title">
 <div class="mcl-figure-kicker">独自図解 03 / メーカーの稼ぐ構造</div>
 <div class="mcl-map-caption" id="mcl-profit-fig-title">営業利益率だけでなく、価値の源泉と資金の流れを確認する</div>
 <div class="mcl-flow-columns">
  <div class="mcl-flow-node"><span class="mcl-flow-type">顧客の課題</span><strong>品質・納期・性能・安定供給</strong><small>何に対して対価が支払われるか</small></div>
  <div class="mcl-flow-node"><span class="mcl-flow-type">企業の事業</span><strong>製品・工程・技術の競争力</strong><small>真似されにくい理由を探す</small></div>
  <div class="mcl-flow-node"><span class="mcl-flow-type">財務で確認</span><strong>利益率・営業CF・給与</strong><small>指標の意味と集計範囲を分けて読む</small></div>
 </div>
 <figcaption>企業分析の問いの順序を表したもので、利益・営業CF・給与に直接的な因果関係があることを示す図ではありません。</figcaption>
</figure>
'''

SEMICON_FIGURE = '''
<figure class="mcl-map-figure mcl-article-figure" data-mcl-figure="semiconductor" aria-labelledby="mcl-semi-fig-title">
 <div class="mcl-figure-kicker">独自図解 04 / 半導体製造装置の位置づけ</div>
 <div class="mcl-map-caption" id="mcl-semi-fig-title">半導体を作る複数の工程を、異なる装置・材料が支える</div>
 <div class="mcl-semi-flow"><span>ウェハの製造工程</span><div class="mcl-semi-steps"><b>成膜</b><b>露光</b><b>エッチング</b><b>洗浄</b><b>測定・検査</b></div><small>多くの工程を繰り返し、測定・検査で状態を確認する</small></div>
 <div class="mcl-semi-support"><div><span>装置・材料</span><strong>工程別の専用技術</strong></div><div><span>関連する職種</span><strong>開発・生産技術・品質・調達・IT</strong></div></div>
 <figcaption>工程の一部を抜粋した概念図。実際の製造順序を1周で表したものではありません。個別メーカーの担当工程は各社の公開情報をご確認ください。</figcaption>
</figure>
'''

FIGURES = {
    'articles/industry-compare.html': INDUSTRY_FIGURE,
    'articles/it-scm-career.html': IT_SCM_FIGURE,
    'articles/manufacturer-profit.html': PROFIT_FIGURE,
    'articles/semiconductor-equipment-salary-profit.html': SEMICON_FIGURE,
}


# Narrow, content-only translations. Keep the established CSS class and link markup.
HOME_EYEBROWS = {
    'MANUFACTURING × MARKET × CAREER': '製造業の企業・仕事・キャリア',
    'WHY IT MATTERS': '会社を選ぶ3つの視点',
    'DATA INSIGHT': '公開データから考える',
    'TRY IT': '企業データを比較する',
    'START HERE': '目的から探す',
    'EDITORIAL': '調査・解説記事',
    'FROM DATA TO ACTION': '調べたあとに確かめる',
}


def localize_home_labels(html: str) -> str:
    for original, japanese in HOME_EYEBROWS.items():
        pattern = r'(<div\s+class="eyebrow"\s*>)' + re.escape(original) + r'(</div>)'
        html = re.sub(pattern, lambda m: m.group(1) + japanese + m.group(2), html, count=1)
    return html


def add_figure(html: str, rel: str, figure: str) -> str:
    if 'data-mcl-figure=' in html:
        return html
    # Insert after the article introduction and before its first analysis section.
    start = html.find('<article')
    if start < 0:
        raise RuntimeError(f'{rel}: article element not found')
    h1_close = html.find('</h1>', start)
    h2_start = html.find('<h2', h1_close)
    article_close = html.find('</article>', h1_close)
    if h1_close < 0 or h2_start < 0 or (article_close >= 0 and h2_start > article_close):
        raise RuntimeError(f'{rel}: article section insertion position not found')
    return html[:h2_start] + figure + '\n' + html[h2_start:]


def augment_editorial_output(out: Path, root: Path) -> None:
    """Add editorial CSS, accessible diagrams and compact 2-company mobile tables."""
    for asset in ASSETS:
        source = root / asset
        if not source.is_file():
            raise RuntimeError(f'デザイン資産が不足しています: {asset}')
        shutil.copyfile(source, out / asset)

    # Verification tokens are intentionally plain-text .html files, not site pages.
    # They must be published byte-for-byte and must never be decorated with CSS/JS.
    # The 404 page is also left untouched, as in the original release.
    def is_content_page(p: Path) -> bool:
        rel = p.relative_to(out)
        if rel.as_posix() == '404.html':
            return False
        if len(rel.parts) == 1 and re.fullmatch(r'google[A-Za-z0-9_-]+\.html', p.name):
            return False
        return True

    paths = sorted(p for p in out.rglob('*.html') if is_content_page(p))
    if not paths:
        raise RuntimeError('デザイン対象HTMLが存在しません')
    figures_found = set()
    for path in paths:
        relative = path.relative_to(out).as_posix()
        html = path.read_text(encoding='utf-8')
        if MARKER in html:
            if relative == 'index.html' and 'data-mcl-figure="home"' in html:
                figures_found.add(relative)
            if relative in FIGURES and 'data-mcl-figure=' in html:
                figures_found.add(relative)
            continue
        if relative == 'index.html':
            html = localize_home_labels(html)
            # Home hero is one section and contains no nested section.
            match = re.search(r'<section\b[^>]*\bclass=["\']hero["\'][\s\S]*?</section>', html)
            if not match:
                raise RuntimeError('トップページのヒーローが見つかりません')
            html = html[:match.end()] + '\n' + HOME_FIGURE + html[match.end():]
            figures_found.add(relative)
        if relative in FIGURES:
            html = add_figure(html, relative, FIGURES[relative])
            figures_found.add(relative)
        prefix = '../' if relative.startswith(('articles/', 'seo-pages/')) else ''
        if html.count('</head>') != 1 or html.count('</body>') != 1:
            raise RuntimeError(f'{relative}: HTML終端タグの数が想定外')
        html = html.replace('</head>', f'<link rel="stylesheet" href="{prefix}mcl-editorial.css" {MARKER}></head>', 1)
        html = html.replace('</body>', f'<script src="{prefix}mcl-editorial.js" defer></script></body>', 1)
        path.write_text(html, encoding='utf-8')

    required = set(FIGURES) | {'index.html'}
    if not required.issubset(figures_found):
        raise RuntimeError('図解の対象HTMLが足りません: ' + ', '.join(sorted(required - figures_found)))
    print(f'[OK] Editorial: {len(paths)} HTML / {len(figures_found)} diagrams / assets {len(ASSETS)}')
