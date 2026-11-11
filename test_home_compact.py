"""Offline build + mobile/desktop browser audit for revised home.
Run: python test_home_compact.py
Synthetic DOM fixtures reproduce the current source structure; not a live deployment test.
"""
from __future__ import annotations
import tempfile, importlib.util, re, json, shutil
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('editorial',R/'mcl_editorial_layer.py')
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

head='''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>メーカーキャリアラボ｜検証</title><link rel="canonical" href="https://maker-career-lab.com/"></head><body>'''
nav='''<header class="site-header"><div class="container nav"><a class="brand" href="/">メーカーキャリアラボ</a><nav><a href="/">ホーム</a><a href="/#articles">記事</a><a href="/company-check">企業分析</a><a href="/about">運営方針</a></nav></div></header>'''
hero='''<section class="hero"><div class="container"><div class="eyebrow">MANUFACTURING × MARKET × CAREER</div><h1>メーカー転職・就職を、<br><em>企業の稼ぐ力から考える。</em></h1><p class="lead"><strong>同じ努力でも、働く市場が変われば、年収の可能性は変わる。</strong> 日本には技術力や参入障壁を背景に利益を生み出すメーカーがあります。1,000社以上の財務データと就職・転職記事から、自分に合う企業を探しましょう。</p><div class="hero-actions"><a class="btn" href="company-check.html">1,000社以上の企業を比較する →</a><a class="btn btn-outline" href="articles/salary-market.html">最初の記事を読む</a></div><p class="micro">比較はキャリア判断の材料です。高収益企業への転職が年収上昇を保証するものではありません。</p></div></section>'''
extra='''<section class="section"><div class="container"><div class="eyebrow">WHY IT MATTERS</div><h2>給与は、個人の能力だけで決まらない。</h2><div class="grid"><div class="card"><h3>利益を生む市場か</h3></div></div></div></section><section class="section soft"><div class="container"><h2>営業利益率30%以上のメーカー、給与中央値は約908万円。</h2><p>詳細な統計説明</p></div></section><section class="section"><div class="container"><h2>いまの会社と、気になる会社を比べてみよう。</h2></div></section><section class="mcl-revenue-section" id="career-next-step"><div class="container"><h2>調べた後に確認する</h2></div></section><section class="mcl-seo-home"><div class="container"><h2>公開データから考える</h2></div></section><section id="start-here" class="mcl329-audience-section"><div class="container"><h2>まずどこから調べる</h2><section class="nested"><h3>リンク導線</h3></section></div></section>'''
anchors=''.join(f'''<a class="article-tile" href="articles/{slug}.html"><span class="tag">{cat}</span><h3>{title}</h3><p>{title}について解説する記事です。</p></a>''' for slug,cat,title in [
 ('salary-market','給与','同じ仕事でも年収が違うのはなぜ？'),('manufacturer-profit','企業','収益力のあるメーカーを見極める'),('industry-compare','市場','業界を変えたらスキルは活きる？'),('it-scm-career','職種','今の仕事の専門性は他社でも活かせる？'),('science-career-market','理系','理系学生が企業を選ぶとき'),('semiconductor-equipment-salary-profit','半導体','半導体製造装置メーカーの年収'),('auto-parts-salary-profit','自動車','自動車部品メーカーの年収'),('salary-correlation','データ','平均年収と売上の相関分析'),('agent-guide','転職','転職相談の前に決めたいこと')])
articles='<section class="section soft" id="articles"><div class="container"><div class="eyebrow">EDITORIAL</div><h2>読むだけで終わらない、9つの分析記事</h2><div class="article-list">'+anchors+'</div></div></section>'
footer='''<footer class="footer"><div class="container"><strong>メーカーキャリアラボ</strong><p>働く市場を知り、キャリアを自分で選ぶ。</p><a href="/privacy">プライバシー</a>　<a href="/disclosure">広告掲載方針</a></div></footer>'''
# Simulate dynamic library created by existing revenue.js on load.
revenue_sim='''<script>
document.addEventListener('DOMContentLoaded',()=>{
 const a=document.querySelector('#articles');if(!a)return;
 a.querySelector('h2').textContent='年収・企業研究・キャリアの記事を探す';
 const lead=document.createElement('p');lead.className='mcl-discovery-lead';lead.textContent='働く市場を知るための解説から、転職前の実践ガイドまで。';
 a.querySelector('h2').insertAdjacentElement('afterend',lead);
 const rail=a.querySelector('.article-list');rail.id='mcl-article-rail';
 const top=document.createElement('div');top.className='mcl-rail-top';top.innerHTML='<div><h3>まず読む・注目記事</h3><p class="mcl-rail-hint">スマホではカードを左右にスワイプできます</p></div><div class="mcl-rail-controls"><span class="mcl-rail-status">1 / 6</span><button class="mcl-rail-button" aria-label="前の記事へ">‹</button><button class="mcl-rail-button" aria-label="次の記事へ">›</button></div>';
 rail.insertAdjacentElement('beforebegin',top);
 const lib=document.createElement('section');lib.className='mcl-library';lib.id='mcl-article-library';lib.innerHTML='<div class="mcl-library-heading"><h3>すべての記事から探す</h3></div><div class="mcl-library-toolbar"><div class="mcl-filters"><button>すべて</button></div><label>記事タイトル・キーワードで探す<input class="mcl-library-search" type="search"></label></div><div class="mcl-library-grid"><a href="articles/factory-job-guide">工場求人の確認ポイント</a></div>';
 rail.insertAdjacentElement('afterend',lib);
});
</script>'''

assert 'company-check.html' in hero
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 (p/'index.html').write_text(head+nav+'<main>'+hero+extra+articles+'<section class="section"><div class="container">工場求人</div></section></main>'+footer+revenue_sim+'</body></html>',encoding='utf-8')
 (p/'404.html').write_text('404')
 (p/'google551bf0fb86f23e67.html').write_text('google-site-verification: google551bf0fb86f23e67.html\n')
 (p/'company-check.html').write_text(head+nav+'<main>企業比較（データは別ファイル）</main>'+footer+'</body></html>')
 (p/'articles').mkdir()
 for k in m.FIGURES:
  (p/k).write_text(head+nav+'<main class="container"><article class="article"><h1>製造業の記事</h1><p>導入</p><h2>本文の見出し</h2><p>専門的な解説</p></article></main>'+footer+'</body></html>')
 m.augment_editorial_output(p,R)
 produced=(p/'index.html').read_text()
 assert 'mcl-home-compact' in produced
 assert '営業利益率30%以上' not in produced
 assert '給与は、個人の能力だけで決まらない。' not in produced
 assert 'data-mcl-figure="home"' not in produced
 assert 'id="articles"' in produced
 assert 'すべての記事を検索する' in produced
 assert len(BeautifulSoup(produced,'html.parser').select('#mcl-home-directory ul li'))==16
 assert len(BeautifulSoup(produced,'html.parser').select('main > section'))==2
 assert (p/'google551bf0fb86f23e67.html').read_text().startswith('google-site-verification:')
 for k in m.FIGURES:assert 'data-mcl-figure' in (p/k).read_text()
 m.augment_editorial_output(p,R)
 assert (p/'index.html').read_text()==produced
 # other pages continue to include content and css
 assert '企業比較（データは別ファイル）' in (p/'company-check.html').read_text()
 # Test script with a minimal inherited baseline and actual design CSS.
 base='''*{box-sizing:border-box}html{width:100%}body{margin:0;font-family:"Noto Sans CJK JP",sans-serif;color:#172f3b;font-size:16px;line-height:1.8}.container{width:min(1100px,calc(100% - 48px));margin:auto}.site-header{border-bottom:1px solid #dce8e6}.nav{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:20px 0}.brand{font-weight:800}.nav nav{display:flex;gap:10px}.nav nav a{font-size:13px}.hero{padding:55px 0;background:linear-gradient(135deg,#eaf7f2,#fff)}h1{font-size:clamp(2rem,5vw,3.2rem)}h2{font-size:1.8rem}.eyebrow{font-size:12px;color:#087c72;font-weight:800}.lead{color:#506875}.hero-actions{display:flex;gap:14px;flex-wrap:wrap}.btn{display:inline-block;text-decoration:none;border-radius:10px;background:#087c72;color:#fff;padding:12px 20px}.micro{font-size:13px;color:#506875}.section{padding:55px 0}.article-list{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.article-tile{padding:20px;border:1px solid #dce8e6;border-radius:15px;text-decoration:none;color:#172f3b}.article-tile h3{font-size:17px}.article-tile p{font-size:13px}.footer{background:#142e39;color:#fff;padding:35px 0}.footer a{color:#fff}#articles .mcl-rail-top{display:flex;justify-content:space-between}.mcl-library{padding:25px;background:#f5faf8}'''
 css=(R/'mcl-editorial.css').read_text()
 js=(R/'mcl-editorial.js').read_text()
 html=produced.replace('<link rel="stylesheet" href="mcl-editorial.css" data-mcl-editorial="2026-11">','<style>'+base+'\n'+css+'</style>')
 html=html.replace('<script src="mcl-editorial.js" defer></script>','<script>'+js+'</script>')
 # Inline script inserted at body end, and helper script executes before DOMContentLoaded.
 checks=[]
 shots=R/'preview';shots.mkdir(exist_ok=True)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-gpu'])
  for width in (320,375,390,430,768,1024,1440):
   context=browser.new_context(viewport={'width':width,'height':844},device_scale_factor=1,is_mobile=width<=430,has_touch=width<=430)
   page=context.new_page();page.set_content(html,wait_until='load');page.wait_for_timeout(120)
   info=page.evaluate('''() => ({
      docWidth:document.documentElement.scrollWidth, bodyWidth:document.body.scrollWidth, viewport:innerWidth,
      heroBottom:Math.round(document.querySelector('.hero').getBoundingClientRect().bottom+scrollY),
      firstCardTop:Math.round(document.querySelector('.article-tile').getBoundingClientRect().top+scrollY),
      mainHeight:Math.round(document.querySelector('main').getBoundingClientRect().height),
      railOverflow:document.querySelector('.article-list').scrollWidth>document.querySelector('.article-list').clientWidth+5,
      directoryClosed:document.querySelector('#mcl-home-directory').open===false,
      libraryInside:!!document.querySelector('#mcl-home-directory #mcl-article-library'),
      fallbackHidden:document.querySelector('.mcl-home-directory-fallback').hidden,
      heading:document.querySelector('#articles h2').textContent,
      mainSections:document.querySelectorAll('main > section').length,
      subnav:document.querySelector('.hero-actions').querySelectorAll('a').length,
      railCards:document.querySelectorAll('#articles .article-list .article-tile').length
    })''')
   checks.append({'width':width,**info})
   assert info['docWidth']<=width+2 and info['bodyWidth']<=width+2,(width,info)
   assert info['railOverflow'],(width,info)
   assert info['mainSections']==2 and info['subnav']==1
   assert info['directoryClosed'] and info['libraryInside'] and info['fallbackHidden']
   assert info['heading']=='記事を探す'
   if width==390:
    page.screenshot(path=str(shots/'home-mobile-390.png'),full_page=True)
    page.locator('#mcl-home-directory > summary').click()
    assert page.locator('#mcl-home-directory').evaluate('(el)=>el.open')
    assert page.locator('#mcl-article-library').is_visible()
    page.screenshot(path=str(shots/'home-directory-390.png'),full_page=True)
   if width==1440:page.screenshot(path=str(shots/'home-desktop-1440.png'),full_page=True)
   page.close();context.close()
  browser.close()
 (R/'TEST-RESULTS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
 print('PASS: build, 4 article diagrams, google verification, idempotency, 16 fallback links, 7 widths, collapsed directory')
 for c in checks:print(c)
