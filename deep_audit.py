from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json,re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('layer',root/'mcl_editorial_layer.py')
layer=importlib.util.module_from_spec(spec);spec.loader.exec_module(layer)
CSS=(root/'mcl-editorial.css').read_text()
JS=(root/'mcl-editorial.js').read_text()
BASE='''
:root{--ink:#172f3b;--sub:#506875;--green:#087c72;--light:#eaf7f2;--line:#dce8e6;--soft:#f5faf8}
*{box-sizing:border-box}body{margin:0;font-family:'Noto Sans CJK JP',sans-serif;font-size:16px;line-height:1.85;color:var(--ink)}
.container{width:min(1100px,calc(100% - 48px));margin-inline:auto}
.site-header{border-bottom:1px solid #ddd}.nav{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;padding:22px 0}.brand{font-weight:800}.nav nav{display:flex;gap:16px;flex-wrap:wrap}.nav nav a{font-size:14px}
.hero{padding:70px 0;background:#eaf7f2}.hero h1{font-size:clamp(1.7rem,5vw,3.4rem)}.lead{max-width:680px}.btn{display:inline-block;background:var(--green);color:white;padding:12px 20px;text-decoration:none;border-radius:10px}
.section{padding:60px 0}.section.soft{background:var(--soft)}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{padding:20px;border:1px solid var(--line);border-radius:15px}
.article{max-width:790px;margin:0 auto;padding:44px 0 80px}.article h1{font-size:2.2rem}.article h2{font-size:1.6rem;margin-top:2em}.article p{line-height:2}
.table-scroll{max-width:100%;overflow-x:auto}.article table{border-collapse:collapse;min-width:690px;width:100%;font-size:14px}.article th,.article td{border:1px solid var(--line);padding:10px}
.compare-wrap{max-width:900px;margin:auto;padding:30px 0}.compare-panel{border:1px solid var(--line);padding:22px;border-radius:16px}.compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.compare-panel input{width:100%}.compare-table{min-width:390px;width:100%;border-collapse:collapse}.compare-table th,.compare-table td{border:1px solid var(--line);padding:11px}.compare-table thead th{background:var(--light)}.compare-result .compare-table td:nth-child(3) small{display:block}
@media(max-width:720px){.grid,.compare-grid{grid-template-columns:1fr}.section{padding:38px 0}.article h1{font-size:1.85rem}.article{padding-top:25px}}
'''
HEAD='<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>監査専用のローカル再現画面</title></head><body>'
NAV='<header class="site-header"><div class="container nav"><a class="brand">メーカーキャリアラボ</a><nav><a href="#top">ホーム</a><a href="#articles">記事</a><a href="#compare">企業分析</a><a href="#about">運営方針</a></nav></div></header>'
END='</body></html>'
FIGURE_PATHS=['index.html','company-check.html','articles/industry-compare.html','articles/it-scm-career.html','articles/manufacturer-profit.html','articles/semiconductor-equipment-salary-profit.html']
with TemporaryDirectory() as td:
 p=Path(td);(p/'articles').mkdir()
 for v in ['mcl-editorial.css','mcl-editorial.js']:(p/v).write_text((root/v).read_text())
 home='''<section class="hero"><div class="container"><div class="eyebrow">MANUFACTURING × MARKET × CAREER</div><h1>メーカー転職・就職を、<br>企業の稼ぐ力から考える。</h1><p class="lead">同じ努力でも、働く市場が変われば、年収の可能性は変わる。</p><p><a class="btn" href="#compare">1,000社以上の企業を比較する</a></p></div></section><section class="section"><div class="container"><div class="eyebrow">WHY IT MATTERS</div><h2>給与は、個人の能力だけで決まらない。</h2><div class="grid"><div class="card"><h3>利益を生む市場か</h3></div><div class="card"><h3>企業が稼ぎ続けられるか</h3></div><div class="card"><h3>経験が評価されるか</h3></div></div></div></section>'''
 (p/'index.html').write_text(HEAD+NAV+home+END)
 metrics=[('営業利益率','42.3%','25.6%','差 -16.7%'),('売上成長率','11.1%','0.5%','差 -10.6%'),('営業CF／売上高','30.6%','22.1%','差 -8.5%'),('自己資本比率','78.9%','71.5%','差 -7.4%'),('平均年間給与','1,879.6万円','1,380.4万円','差 -499.2万円')]
 rowhtml=''.join('<tr><td>'+label+'</td><td>'+va+'</td><td>'+vb+'<small class="mcl-metric-delta">'+delta+'</small></td></tr>' for label,va,vb,delta in metrics)
 compare=f'''<main class="container"><div class="compare-wrap"><h1>今の会社と、気になる会社を比較する</h1><form class="compare-panel"><div class="compare-grid"><div><label>企業A<input id="name-a" value="株式会社ディスコ"></label></div><div><label>企業B<input id="name-b" value="東京エレクトロン株式会社"></label></div></div><button class="btn">比較する</button></form><section id="results" class="compare-panel compare-result"><h2 id="compare-title">株式会社ディスコ と 東京エレクトロン株式会社</h2><div class="table-scroll"><table class="compare-table"><thead><tr><th>指標</th><th>現職</th><th>検討先</th></tr></thead><tbody id="metrics-body">{rowhtml}</tbody></table></div><div class="source-card">出典：EDINET 有価証券報告書。給与は提出会社単体。</div></section></div></main>'''
 (p/'company-check.html').write_text(HEAD+NAV+compare+END)
 for target in FIGURE_PATHS[2:]:
  article='''<main class="container"><article class="article"><p>【PR】この記事には広告が含まれます</p><h1>業界ごとに異なる製造業の製品・工程・職種</h1><p>同じ仕事であっても製品寿命、調達リードタイム、需要変動によって仕事は変わります。</p><h2>STEP 1｜業界と実務を知る</h2><p>製造業の工程と役割を具体的に考えます。</p><div class="table-scroll"><table><thead><tr><th>業界</th><th>製品・市場</th><th>調達</th><th>供給リスク</th><th>関係する仕事</th></tr></thead><tbody><tr><td>半導体装置・材料</td><td>高度な技術と顧客工程への適合</td><td>長期部材調達</td><td>設備投資サイクル</td><td>生産管理・調達・品質管理</td></tr><tr><td>自動車部品</td><td>量産効率と品質</td><td>多拠点調達</td><td>原価・納期改善</td><td>品質保証・生産技術</td></tr></tbody></table></div></article></main>'''
  f=p/target;f.write_text(HEAD+NAV+article+END)
 (p/'google1234.html').write_text('google-site-verification: google1234.html\n'); (p/'404.html').write_text('not found')
 layer.augment_editorial_output(p,root)
 assert '製造業の企業・仕事・キャリア' in (p/'index.html').read_text()
 assert 'MANUFACTURING × MARKET × CAREER' not in (p/'index.html').read_text()
 assert (p/'google1234.html').read_text()=='google-site-verification: google1234.html\n'
 assert '測定・検査</b>' in (p/'articles/semiconductor-equipment-salary-profit.html').read_text()
 screenshot_dir=root/'verified-previews';screenshot_dir.mkdir(exist_ok=True)
 stats=[]; errors=[];mobile_num=0;desktop_num=0
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-gpu'])
  for width in (320,375,390,430,1024,1440):
   for path in FIGURE_PATHS:
    browser_context=browser.new_context(viewport={'width':width,'height':850},device_scale_factor=1, is_mobile=width<=430, has_touch=width<=430)
    page=browser_context.new_page()
    html=(p/path).read_text()
    html=re.sub(r'<link[^>]+mcl-editorial.css[^>]*>', lambda m:'<style>'+BASE+'\n'+CSS+'</style>',html)
    html=re.sub(r'<script[^>]+mcl-editorial.js[^>]*></script>', lambda m:'<script>'+JS+'</script>',html)
    # set_content executes script; no external connections.
    page.set_content(html,wait_until='load')
    page.wait_for_timeout(90)
    info=page.evaluate('''() => ({
       innerWidth:window.innerWidth, scrollWidth:document.documentElement.scrollWidth,
       bodyWidth:document.body.scrollWidth,
       navMinHeights:[...document.querySelectorAll('.site-header nav a')].map(e=>Math.round(e.getBoundingClientRect().height)),
       figureCount:document.querySelectorAll('figure[data-mcl-figure], section[data-mcl-figure]').length,
       labelCompany:document.querySelector('#metrics-body tr td:nth-child(2)') ? getComputedStyle(document.querySelector('#metrics-body tr td:nth-child(2)'),'::before').content : null,
       tableHint:document.querySelector('.mcl-table-swipe-hint')?.hidden===false,
       figcaptionFont:document.querySelector('.mcl-map-figure figcaption')?parseFloat(getComputedStyle(document.querySelector('.mcl-map-figure figcaption')).fontSize):null,
       tableHeaders:[...document.querySelectorAll('#metrics-body th[scope=row]')].length,
       rateDelta:document.querySelector('#metrics-body tr .mcl-metric-delta')?.textContent
    })''')
    stats.append({'screen':width,'path':path,**info})
    if max(info['scrollWidth'],info['bodyWidth'])>width+2:errors.append(('body_overflow',width,path,info))
    if width<=430:
     mobile_num+=1
     if min(info['navMinHeights'])<43:errors.append(('nav_too_short',width,path,info))
     if info['figcaptionFont'] and info['figcaptionFont']<13.5:errors.append(('figcaption_too_small',width,path,info))
    else:desktop_num+=1
    if path=='company-check.html':
      if info['tableHeaders'] != 5:errors.append(('invalid_semantics',width,path,info))
      if info['rateDelta'] != '差 -16.7ポイント':errors.append(('percentage_points',width,path,info))
      if width<=430 and 'ディスコ' not in (info['labelCompany'] or ''):
       errors.append(('missing_company',width,path,info))
    if path.startswith('articles/') and width<=430 and not info['tableHint']:
      errors.append(('table_scroll_hint',width,path,info))
    if width in [390,1440] and path in ['index.html','company-check.html','articles/industry-compare.html']:
      f=screenshot_dir/(str(width)+'-'+path.replace('/','-').replace('.html','.png'))
      page.screenshot(path=str(f),full_page=True)
    page.close();browser_context.close()
  browser.close()
 (root/'audit-browser-results.json').write_text(json.dumps({'total':len(stats),'mobile':mobile_num,'desktop':desktop_num,'errors':errors,'results':stats},ensure_ascii=False,indent=2))
 print('TEST:',len(stats),'screens',mobile_num,'mobile',desktop_num,'desktop')
 print('ERRORS:',len(errors));print(json.dumps(errors[:15],ensure_ascii=False,indent=2))
 if errors:raise SystemExit(1)
