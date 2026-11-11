#!/usr/bin/env python3
"""Offline regression check of the editorial transformation and mobile tables.
Run: python3 test_editorial_release.py [--screenshots /tmp/screenshots]
"""
from __future__ import annotations
import argparse
import importlib.util
import shutil
import tempfile
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load_module(path: Path):
    spec=importlib.util.spec_from_file_location(path.stem,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def fake_html(body: str, title: str) -> str:
    return f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="style.css"></head><body><header class="site-header"><div class="container nav"><a class="brand">メーカーキャリアラボ</a></div></header>{body}</body></html>'

def run(screenshots: Path | None = None):
    from bs4 import BeautifulSoup
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        shutil.copyfile(HERE/'mcl-editorial.css',root/'mcl-editorial.css')
        shutil.copyfile(HERE/'mcl-editorial.js',root/'mcl-editorial.js')
        shutil.copyfile(HERE/'mcl-editorial.css',root/'style.css')
        (root/'articles').mkdir()
        (root/'index.html').write_text(fake_html('<section class="hero"><div class="container"><h1>メーカーの企業と仕事を理解する</h1></div></section><section class="section"><div class="container"><h2>企業を測る</h2></div></section>','トップ'),encoding='utf-8')
        metrics=''.join(f'<tr><td>{label}</td><td>{a}</td><td>{b}</td></tr>' for label,a,b in [
            ('営業利益率','42.3%','25.6%'),('売上成長率','11.1%','0.5%'),('営業CF／売上高','30.6%','22.1%'),('自己資本比率','78.9%','71.5%'),('平均年間給与','1,879.6万円','1,380.4万円')])
        body=f'<main class="container"><div class="compare-wrap"><h1>企業比較ツール</h1><section class="compare-panel compare-result"><h2>ディスコ と 東京エレクトロン</h2><div class="table-scroll"><table class="compare-table"><thead><tr><th>指標</th><th>現職</th><th>検討先</th></tr></thead><tbody id="metrics-body">{metrics}</tbody></table></div><section class="source-card">給与は提出会社単体の平均</section></section></div></main>'
        (root/'company-check.html').write_text(fake_html(body,'企業比較'),encoding='utf-8')
        for p in ['industry-compare.html','it-scm-career.html','manufacturer-profit.html','semiconductor-equipment-salary-profit.html']:
            (root/'articles'/p).write_text(fake_html(f'<main class="container"><article class="article"><h1>{p}</h1><p>本文の冒頭説明です。製造業の実務と数字を確認します。</p><h2>STEP 1｜工程の違いを知る</h2><p>本文は省略せず、この見出しから引き続き表示します。</p></article></main>',p),encoding='utf-8')
        m=load_module(HERE/'mcl_editorial_layer.py')
        m.augment_editorial_output(root,HERE)
        assert len(list(root.rglob('*.html')))==6
        assert (root/'index.html').read_text().count('data-mcl-figure="home"')==1
        for name in ['industry-compare','it-scm-career','manufacturer-profit','semiconductor-equipment-salary-profit']:
            text=(root/'articles'/f'{name}.html').read_text()
            soup=BeautifulSoup(text,'html.parser')
            assert soup.select_one('article figure figcaption') is not None
            assert '本文は省略せず' in text
            assert text.count('mcl-editorial.css')==1
            assert text.count('mcl-editorial.js')==1
        assert (root/'company-check.html').read_text().count('mcl-editorial.js')==1
        # Re-invocation should not create duplicates.
        m.augment_editorial_output(root,HERE)
        assert (root/'index.html').read_text().count('data-mcl-figure="home"')==1
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-gpu'])
            try:
                failures=[]
                for width in (320,375,390,430):
                    page=browser.new_page(viewport={'width':width,'height':850},device_scale_factor=1,is_mobile=True,has_touch=True)
                    for relative in ['index.html','company-check.html','articles/industry-compare.html','articles/it-scm-career.html','articles/manufacturer-profit.html','articles/semiconductor-equipment-salary-profit.html']:
                        html=(root/relative).read_text(encoding='utf-8')
                        css=(HERE/'mcl-editorial.css').read_text(encoding='utf-8')
                        js=(HERE/'mcl-editorial.js').read_text(encoding='utf-8')
                        html=re.sub(r'<link[^>]+mcl-editorial\.css[^>]*>', lambda _: '<style>'+css+'</style>', html)
                        html=re.sub(r'<script[^>]+mcl-editorial\.js[^>]*></script>', lambda _: '<script>'+js+'</script>', html)
                        page.set_content(html,wait_until='load')
                        page.wait_for_timeout(70)
                        info=page.evaluate('''() => ({screen:window.innerWidth, html:document.documentElement.scrollWidth,body:document.body.scrollWidth, figs:document.querySelectorAll('figure[data-mcl-figure], section[data-mcl-figure]').length, rows:document.querySelectorAll('#metrics-body tr').length, table:document.querySelector('.compare-table')?.getBoundingClientRect().width || null})''')
                        if max(info['html'],info['body'])>width+2:failures.append((width,relative,info))
                        if relative=='company-check.html':
                            assert info['rows']==5
                            assert page.locator('#metrics-body th[scope="row"]').count()==5
                        if screenshots and width==390:
                            target=screenshots/(relative.replace('/','-').replace('.html','.png'))
                            target.parent.mkdir(parents=True,exist_ok=True)
                            page.screenshot(path=str(target),full_page=True)
                    page.close()
                assert not failures, f'Horizontal overflow: {failures}'
                print('[OK] Responsive screens: 6 pages x 4 widths = 24 checks; no overflow')
                print('[OK] 5 actual-format comparison metrics; all row headings semantic')
                print('[OK] All 5 diagrams inserted; article content preserved; re-run idempotent')
            finally:browser.close()
    return True

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--screenshots',type=Path)
    run(parser.parse_args().screenshots)
