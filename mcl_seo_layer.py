#!/usr/bin/env python3
"""Build search-friendly pages from the *current* validated EDINET company-data.js.

Called only from mcl_revenue_layer.augment_output after cloudflare-build.py
has created dist, sitemap, and copied all existing, approved assets.
No requests, no API keys, no changes to the ranking or update pipelines.
"""
from __future__ import annotations
import html
import json
import math
import re
import shutil
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = 'https://maker-career-lab.com/'
LAUNCH_DATE = '2026-11-04'
PAGES = (
    ('manufacturer-salary-ranking-2026', 'メーカー年収ランキング2026｜EDINETで比較する1,000社以上の給与',
     'メーカーの平均年収ランキング2026。1,000社以上のEDINET検証済み企業データを対象に、提出会社単体の平均年間給与を上位100社まで一覧表示。年収1,000万円以上の社数、集計方法、持株会社の注意点を掲載。', '給与・企業研究'),
    ('manufacturer-operating-margin-ranking', '営業利益率が高いメーカーランキング｜上場企業の収益力比較',
     '上場メーカーを中心とした掲載企業の営業利益率をEDINET財務データから比較。連結売上高・営業利益を使った計算方法、対象社数、決算期差、給与との違いを解説。', '企業収益力'),
    ('manufacturing-generative-ai', '製造業の生成AI活用事例｜設計・生産管理・品質保証・AIエージェント',
     '製造業の生成AIはどこで使われている？品質保証、設計知識検索、生産計画、AIエージェントを公的資料と企業公表事例から整理し、効果と限界を区別します。', '生成AI・DX'),
    ('manufacturing-ai-careers', 'AIで製造業の仕事はなくなる？職種別の変化とキャリア対策',
     '生成AI・フィジカルAIは製造業の仕事をどう変える？生産管理・品質管理・生産技術・研究開発・社内ITの業務別に自動化可能性と残る判断責任を整理します。', 'キャリア・AI'),
)


def company_records(source: Path) -> list[dict]:
    raw = source.read_text(encoding='utf-8')
    m = re.search(r'window\.MCL_COMPANIES\s*=\s*(\[[\s\S]*?\])\s*;', raw)
    if not m:
        raise RuntimeError('SEO ranking: 現行企業データを読めません')
    rows = json.loads(m.group(1))
    ids = [str(x.get('id', '')) for x in rows]
    if len(rows) < 1000 or len(ids) != len(set(ids)) or '6390' in ids:
        raise RuntimeError('SEO ranking: 企業数・重複・保留企業のデータ検証に失敗')
    if not all(isinstance(x.get('name'), str) and x['name'] and x.get('period') for x in rows):
        raise RuntimeError('SEO ranking: 名前または対象期間が欠落')
    return rows


def numeric(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def format_end(period: str) -> str:
    return period.split('〜')[-1]


def calc_salary(rows: list[dict]) -> tuple[list[dict], int]:
    good = [x for x in rows if numeric(x.get('averageSalary')) and x['averageSalary'] > 0]
    good.sort(key=lambda x: (-x['averageSalary'], str(x['id'])))
    return good, sum(x['averageSalary'] >= 1000 for x in good)


def calc_margin(rows: list[dict]) -> list[dict]:
    good = [x for x in rows if numeric(x.get('revenue')) and x['revenue'] > 0
            and numeric(x.get('operatingProfit'))]
    out = []
    for item in good:
        copy = dict(item)
        copy['calculated_margin'] = copy['operatingProfit'] / copy['revenue'] * 100
        if math.isfinite(copy['calculated_margin']):
            out.append(copy)
    out.sort(key=lambda x: (-x['calculated_margin'], str(x['id'])))
    return out


def render_rows(data: list[dict], mode: str) -> str:
    result = []
    for n, item in enumerate(data[:100], 1):
        name = html.escape(item['name'])
        industry = html.escape(str(item.get('industry') or '分類未記録'))
        period = html.escape(format_end(str(item['period'])))
        source_id = html.escape(str(item.get('sourceDocId') or '未記録'))
        value = (f"{item['averageSalary']:,.1f}万円" if mode == 'salary'
                 else f"{item['calculated_margin']:,.1f}%")
        companion = (f"{item['calculated_margin']:,.1f}%" if mode == 'salary' and 'calculated_margin' in item
                     else (f"{item['averageSalary']:,.1f}万円" if mode == 'margin' and numeric(item.get('averageSalary')) else '—'))
        if mode == 'salary':
            companion = (f"{100 * item['operatingProfit']/item['revenue']:.1f}%"
                         if numeric(item.get('revenue')) and item['revenue'] > 0 and numeric(item.get('operatingProfit')) else '—')
        result.append(f'<tr data-company="{html.escape(item["name"], quote=True)}" data-sector="{html.escape(industry, quote=True)}">'
                      f'<td>{n}</td><th scope="row">{name}<small>証券コード {html.escape(str(item["id"]))}</small></th>'
                      f'<td>{industry}</td><td class="mcl-number"><strong>{value}</strong></td>'
                      f'<td class="mcl-number">{companion}</td><td>{period}</td><td>{source_id}</td></tr>')
    return '\n'.join(result)


def latest_verified(rows: list[dict]) -> str:
    valid = sorted(str(x.get('verifiedAt')) for x in rows if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(x.get('verifiedAt', ''))))
    return valid[-1] if valid else '確認日未記録'


def make_head(slug: str, title: str, description: str, section: str, mod_date: str) -> str:
    uri = BASE + 'articles/' + slug
    ld = json.dumps({'@context': 'https://schema.org', '@type': 'Article',
         'headline': title, 'inLanguage': 'ja', 'datePublished': LAUNCH_DATE,
         'dateModified': mod_date,
         'author': {'@type': 'Organization', 'name': 'メーカーキャリアラボ編集部'},
         'publisher': {'@type': 'Organization', 'name': 'メーカーキャリアラボ編集部'},
         'mainEntityOfPage': uri}, ensure_ascii=False, separators=(',', ':'))
    crumbs = json.dumps({'@context': 'https://schema.org','@type':'BreadcrumbList',
         'itemListElement': [{'@type':'ListItem','position':1,'name':'ホーム','item':BASE},
                             {'@type':'ListItem','position':2,'name':title,'item':uri}]}, ensure_ascii=False, separators=(',', ':'))
    return f'''<!doctype html><html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#087c72"><title>{html.escape(title)} | メーカーキャリアラボ</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="{uri}">
<link rel="stylesheet" href="../style.css"><link rel="stylesheet" href="../mcl-revenue.css"><link rel="stylesheet" href="../mcl-seo.css">
<link rel="icon" href="../favicon.ico" sizes="any"><link rel="apple-touch-icon" href="../apple-touch-icon.png">
<meta property="og:type" content="article"><meta property="og:site_name" content="メーカーキャリアラボ">
<meta property="og:url" content="{uri}"><meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:image" content="{BASE}og-image.png">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-G3EBC7ZZQ9"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','G-G3EBC7ZZQ9');</script>
<script src="../analytics-events.js" defer></script><script src="../mcl-seo.js" defer></script>
<script type="application/ld+json">{ld}</script><script type="application/ld+json">{crumbs}</script>
</head><body>
<header class="site-header"><div class="container nav"><a class="brand" href="../">メーカー<span>キャリアラボ</span></a><nav aria-label="主要メニュー"><a href="../">ホーム</a><a href="../#articles">記事</a><a href="../company-check">企業分析</a><a href="../about">運営方針</a></nav></div></header>
<main class="container"><article class="article mcl-seo-article">
<nav class="mcl-seo-breadcrumb" aria-label="パンくずリスト"><a href="../">ホーム</a> / <span>{html.escape(section)}</span></nav>
<span class="tag">{html.escape(section)}</span>
'''


def make_footer() -> str:
    return '''</article></main>
<footer class="footer"><div class="container"><strong>メーカーキャリアラボ</strong><p>働く市場を知り、キャリアを自分で選ぶ。</p><div class="footer-links"><a href="../about">運営方針</a><a href="../privacy">プライバシー</a><a href="../disclosure">広告掲載方針</a><a href="../contact">お問い合わせ</a></div><small>© 2026 メーカーキャリアラボ。</small></div></footer>
</body></html>'''


HOME_SECTION = '''<section class="mcl-seo-home" id="seo-guides" aria-label="年収・利益率・AIの特集記事"><div class="container">
<div class="eyebrow">EXPLORE BY QUESTION</div><h2>年収・収益力・AIから、メーカーの仕事を調べる</h2>
<p>1,000社以上の検証済みEDINETデータと、技術変化の一次資料を使った4つの入口です。</p>
<div class="mcl-seo-home-grid">
<a href="articles/manufacturer-salary-ranking-2026"><span>給与・企業研究</span><strong>メーカー年収ランキング2026</strong><small>提出会社の平均年間給与を比べる</small></a>
<a href="articles/manufacturer-operating-margin-ranking"><span>企業の収益力</span><strong>営業利益率が高いメーカー</strong><small>企業が利益を生む仕組みを考える</small></a>
<a href="articles/manufacturing-generative-ai"><span>生成AI・DX</span><strong>製造業の生成AI活用事例</strong><small>品質保証・設計・生産管理を整理</small></a>
<a href="articles/manufacturing-ai-careers"><span>職種別キャリア</span><strong>AIで製造業の仕事はなくなる？</strong><small>仕事の変化と身につける力</small></a>
</div></div></section>'''


def inject_link_sections(out: Path) -> None:
    home = out / 'index.html'
    source = home.read_text(encoding='utf-8')
    needle = '<section id="start-here"'
    if source.count(needle) != 1:
        raise RuntimeError('SEO: トップページの新規導線位置が不明')
    if 'id="seo-guides"' not in source:
        source = source.replace(needle, HOME_SECTION + '\n' + needle, 1)
    if 'mcl-seo.css' not in source:
        source = source.replace('</head>', '<link rel="stylesheet" href="mcl-seo.css"></head>', 1)
    home.write_text(source, encoding='utf-8')

    comp = out / 'company-check.html'
    source = comp.read_text(encoding='utf-8')
    link = '''<aside id="mcl-seo-compare" class="mcl-seo-related"><strong>一覧から比較する：</strong>
    <a href="articles/manufacturer-salary-ranking-2026">メーカー年収ランキング</a> ／
    <a href="articles/manufacturer-operating-margin-ranking">営業利益率ランキング</a></aside>'''
    needle = '<section id="mcl-after-comparison"'
    if source.count(needle) != 1:
        raise RuntimeError('SEO: 既存の比較後導線位置が不明')
    if 'id="mcl-seo-compare"' not in source:
        source = source.replace(needle, link + '\n' + needle, 1)
    if 'mcl-seo.css' not in source:
        source = source.replace('</head>', '<link rel="stylesheet" href="mcl-seo.css"></head>', 1)
    comp.write_text(source, encoding='utf-8')

    targets = {
        'articles/salary-market.html': ('manufacturer-salary-ranking-2026', 'メーカー年収ランキングを確認する'),
        'articles/manufacturer-profit.html': ('manufacturer-operating-margin-ranking', '営業利益率ランキングを見る'),
        'articles/salary-correlation.html': ('manufacturer-salary-ranking-2026', '給与ランキングの対象企業を見る'),
        'articles/it-scm-career.html': ('manufacturing-ai-careers', 'AIで変わる製造業の職種を読む'),
        'articles/industry-compare.html': ('manufacturing-generative-ai', '製造業での生成AI活用を読む'),
        'articles/science-career-market.html': ('manufacturer-salary-ranking-2026', 'メーカーの平均年間給与を比較する'),
    }
    for rel, (slug, caption) in targets.items():
        file = out / rel
        content = file.read_text(encoding='utf-8')
        link = f'<aside class="mcl-seo-related" data-mcl-seo-related="{slug}"><strong>関連記事：</strong> <a href="{slug}">{caption}</a>。数字だけで結論を出さず、求人条件も確認しましょう。</aside>'
        if f'data-mcl-seo-related="{slug}"' not in content:
            if content.count('</article>') != 1:
                raise RuntimeError(f'SEO: {rel} articleタグ構造が想定外')
            content = content.replace('</article>', link + '\n</article>', 1)
        if 'mcl-seo.css' not in content:
            content = content.replace('</head>', '<link rel="stylesheet" href="../mcl-seo.css"></head>', 1)
        file.write_text(content, encoding='utf-8')


def append_sitemap(out: Path, mod_date: str, copied_html: list[str]) -> None:
    file = out / 'sitemap.xml'
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    root = ET.parse(file).getroot()
    existing = [n.text for n in root.findall(f'.//{{{ns}}}loc')]
    if len(existing) != len(set(existing)):
        raise RuntimeError('SEO: 既存sitemapが重複しています')
    if any(not (x or '').startswith(BASE) for x in existing):
        raise RuntimeError('SEO: sitemapに非正規ドメインが含まれます')
    for slug, *_ in PAGES:
        url = BASE + 'articles/' + slug
        if url not in existing:
            node = ET.SubElement(root, f'{{{ns}}}url')
            ET.SubElement(node, f'{{{ns}}}loc').text = url
            ET.SubElement(node, f'{{{ns}}}lastmod').text = mod_date
            existing.append(url)
    if len(existing) != len(set(existing)):
        raise RuntimeError('SEO: sitemap追加後にURLが重複しました')
    expected = {BASE if path == 'index.html' else BASE + path[:-5] for path in copied_html}
    expected.update(BASE + 'articles/' + slug for slug, *_ in PAGES)
    if set(existing) != expected:
        raise RuntimeError(f'SEO: sitemapと公開HTMLが不整合: {sorted(set(existing) ^ expected)}')
    file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode') + '\n', encoding='utf-8')


def augment_seo_output(out: Path, copied_html: list[str], root: Path) -> None:
    rows = company_records(root / 'company-data.js')
    salary, over1000 = calc_salary(rows)
    margin = calc_margin(rows)
    if len(salary) < 1000 or len(margin) < 1000:
        raise RuntimeError('SEO: 給与・利益率ランキング対象数が想定より少ない')
    # Keep every company in the source; only format the first 100 on the public pages.
    verified = latest_verified(rows)
    mod_date = max(LAUNCH_DATE, verified) if verified != '確認日未記録' else LAUNCH_DATE
    tokens = {
        '{{DATA_TOTAL}}': f'{len(rows):,}',
        '{{SALARY_COUNT}}': f'{len(salary):,}',
        '{{MARGIN_COUNT}}': f'{len(margin):,}',
        '{{OVER_1000}}': str(over1000),
        '{{VERIFIED_AT}}': verified,
        '{{SALARY_ROWS}}': render_rows(salary, 'salary'),
        '{{MARGIN_ROWS}}': render_rows(margin, 'margin'),
        '{{DATA_MODIFIED}}': mod_date,
    }
    folder = out / 'articles'
    folder.mkdir(parents=True, exist_ok=True)
    for slug, title, description, section in PAGES:
        template = root / 'seo-pages' / (slug + '.html')
        if not template.is_file():
            raise RuntimeError(f'SEO: ページテンプレートが存在しません: {template}')
        body = template.read_text(encoding='utf-8')
        for key, value in tokens.items():
            body = body.replace(key, value)
        if re.search(r'\{\{[A-Z0-9_]+\}\}', body):
            raise RuntimeError(f'SEO: {slug} に未処理のプレースホルダがあります')
        finished = make_head(slug, title, description, section, mod_date) + body + make_footer()
        if finished.count('<h1') != 1 or finished.count('rel="canonical"') != 1:
            raise RuntimeError(f'SEO: {slug} のHTML構造が不正')
        (folder / (slug + '.html')).write_text(finished, encoding='utf-8')
    for asset in ('mcl-seo.css', 'mcl-seo.js'):
        shutil.copyfile(root / asset, out / asset)
    inject_link_sections(out)
    append_sitemap(out, mod_date, copied_html)
    for slug, *_ in PAGES:
        url = BASE + 'articles/' + slug
        built = (folder / (slug + '.html')).read_text(encoding='utf-8')
        if f'rel="canonical" href="{url}"' not in built:
            raise RuntimeError(f'SEO: {slug} canonicalが不正')
    print(f'[OK] SEO: {len(rows)}社、給与1,000万円以上{over1000}社、生成HTML4件、sitemap4件追加')
