/* Privacy-preserving events: no company names, input text, salary, or browser storage. */
(function(){
 'use strict';
 const allowed = new Set([
  'home_checklist','home_engineer','compare_checklist','compare_engineer',
  'student_services',
  'article_checklist','article_engineer','checklist_compare','checklist_services',
  'engineer_compare','engineer_checklist','checklist_print','checklist_copy',
  'checklist_clear'
 ]);
 function event(kind){
  if (!allowed.has(kind) || typeof window.gtag !== 'function') return;
  window.gtag('event','mcl_funnel_action',{
   funnel_action:kind, content_group:'career_decision', transport_type:'beacon'
  });
 }
 document.addEventListener('click',function(evt){
  const el=evt.target.closest && evt.target.closest('[data-mcl-funnel]');
  if (el) event(el.getAttribute('data-mcl-funnel'));
 });
 const box=document.getElementById('mcl-career-checklist');
 if(!box) return;
 const checks=Array.from(box.querySelectorAll('input[type=checkbox]'));
 const status=box.querySelector('[data-mcl-count]');
 const alert=box.querySelector('[role=status]');
 const copy=box.querySelector('[data-mcl-copy]');
 const clear=box.querySelector('[data-mcl-clear]');
 const print=box.querySelector('[data-mcl-print]');
 function refresh(){if(status)status.textContent=checks.filter(x=>x.checked).length+' / '+checks.length+' 項目を確認';}
 checks.forEach(x=>x.addEventListener('change',refresh));refresh();
 if(clear)clear.addEventListener('click',function(){checks.forEach(x=>x.checked=false);refresh();if(alert)alert.textContent='チェックを解除しました。';event('checklist_clear');});
 if(print)print.addEventListener('click',function(){event('checklist_print');window.print();});
 if(copy)copy.addEventListener('click',async function(){
  const lines=['メーカー転職の確認メモ','確認日：＿＿＿＿','候補企業：＿＿＿＿'];
  checks.forEach(x=>lines.push((x.checked?'[確認済] ':'[未確認] ')+x.dataset.label));
  lines.push('出典と求人票の条件は必ず個別に確認してください。');
  try{
   if(!navigator.clipboard || !navigator.clipboard.writeText)throw Error('unsupported');
   await navigator.clipboard.writeText(lines.join('\n'));
   if(alert)alert.textContent='確認項目だけをコピーしました。個人情報は送信されません。';
   event('checklist_copy');
  }catch(e){if(alert)alert.textContent='コピーできませんでした。ブラウザーの印刷・保存機能をご利用ください。';}
 });
})();

/* Article discovery is progressive enhancement. Server-rendered article links
 * remain visible if this script is blocked. No user input is sent to analytics. */
(function(){
 'use strict';
 const section=document.getElementById('articles');
 if(!section || section.dataset.mclDiscoveryReady==='true') return;
 const container=section.querySelector('.container');
 const rail=section.querySelector('.article-list');
 const heading=section.querySelector('h2');
 if(!container||!rail||!heading||rail.querySelectorAll('a.article-tile').length===0) return;
 section.dataset.mclDiscoveryReady='true';

 // Canonical article slugs; keep this catalog in sync when new articles launch.
 // These are original editorial descriptions, not synthesized user reviews.
 const catalog=[
  ['salary-market','年収・企業','同じ仕事でも年収が違うのはなぜ？','市場・企業・職種の4層から給与を考える'],
  ['manufacturer-salary-ranking-2026','年収・企業','メーカー平均年収ランキング2026','EDINET掲載企業の平均年間給与を比較'],
  ['manufacturer-operating-margin-ranking','年収・企業','営業利益率が高いメーカーランキング','企業の利益を生む構造を比較する'],
  ['manufacturer-profit','年収・企業','収益力のあるメーカーを見極める5つの問い','利益率の先にある競争力を見極める'],
  ['salary-correlation','年収・企業','平均年収と売上・利益は関係する？','掲載企業の相関関係と注意点を検証'],
  ['semiconductor-equipment-salary-profit','年収・企業','半導体製造装置・検査関連9社を比較','半導体装置企業の給与と収益力'],
  ['auto-parts-salary-profit','年収・企業','自動車部品メーカー4社を比較','デンソーなどの年収・利益率を比較'],
  ['industry-compare','年収・企業','業界を変えたらスキルは活きる？','半導体・自動車・食品の業界特性'],
  ['manufacturing-generative-ai','AI・DX','製造業の生成AI活用事例','品質保証・設計・生産管理の実践例'],
  ['manufacturing-ai-careers','AI・DX','AIで製造業の仕事はなくなる？','職種別に変わる仕事と必要な力'],
  ['it-scm-career','AI・DX','今の仕事の専門性は他社でも活かせる？','社内IT・SCMのスキルを棚卸しする'],
  ['agent-guide','キャリア・転職','転職相談の前に決めたいこと','希望する仕事と条件を整理する'],
  ['manufacturer-career-checklist','キャリア・転職','メーカー転職前の7項目チェックリスト','職種・勤務地・働き方を無料で整理'],
  ['manufacturer-engineer-agent-selection','キャリア・転職','メーカー技術職向け転職サービスの選び方','技術職向けの相談先を比較する'],
  ['science-career-market','工場・就活','理系学生がメーカーを選ぶときの考え方','業界と企業の収益力から就職を考える'],
  ['factory-job-guide','工場・就活','工場の仕事を探す前に確認したい7つの条件','給与・夜勤・雇用形態・勤務地を確認']
 ];
 const groups=['すべて','年収・企業','AI・DX','キャリア・転職','工場・就活'];
 const el=(tag,className,text)=>{
   const node=document.createElement(tag);
   if(className)node.className=className;
   if(text!==undefined)node.textContent=text;
   return node;
 };
 const event=(name,params)=>{
   if(typeof window.gtag==='function') window.gtag('event',name,Object.assign({content_group:'article_discovery'},params));
 };

 heading.textContent='年収・企業研究・キャリアの記事を探す';
 const lead=el('p','mcl-discovery-lead','働く市場を知るための解説から、転職前に使える実践ガイドまで。気になるテーマを選んで読めます。');
 heading.insertAdjacentElement('afterend',lead);
 const railTop=el('div','mcl-rail-top');
 const railTitle=el('div');
 railTitle.append(el('h3','','まず読む・注目記事'),el('p','mcl-rail-hint','スマホではカードを左右にスワイプできます'));
 const controls=el('div','mcl-rail-controls');
 const previous=el('button','mcl-rail-button','‹');
 const next=el('button','mcl-rail-button','›');
 const status=el('span','mcl-rail-status');
 previous.type=next.type='button';
 previous.setAttribute('aria-label','前の記事へ');
 next.setAttribute('aria-label','次の記事へ');
 const id='mcl-article-rail';
 rail.id=id;
 rail.setAttribute('role','region');
 rail.setAttribute('aria-label','注目記事一覧・左右にスクロール可能');
 rail.setAttribute('tabindex','0');
 previous.setAttribute('aria-controls',id);
 next.setAttribute('aria-controls',id);
 controls.append(status,previous,next);
 railTop.append(railTitle,controls);
 rail.insertAdjacentElement('beforebegin',railTop);
 // Keep the homepage rail deliberately short. All 16 articles remain
 // accessible through the complete directory below, and in no-JS HTML.
 const featured=new Set([
   'salary-market','manufacturer-profit','industry-compare',
   'it-scm-career','science-career-market','semiconductor-equipment-salary-profit'
 ]);
 rail.querySelectorAll('a.article-tile').forEach(a=>{
   const slug=(a.getAttribute('href')||'').split('/').pop().replace(/\.html$/,'');
   if(!featured.has(slug)) a.remove();
 });
 const cards=Array.from(rail.querySelectorAll('a.article-tile'));
 const updateRail=()=>{
   const max=Math.max(0,rail.scrollWidth-rail.clientWidth);
   const left=Math.max(0,rail.scrollLeft);
   const edge=rail.getBoundingClientRect().left+28;
   const first=cards.findIndex(c=>c.getBoundingClientRect().right>edge);
   status.textContent=(first<0?cards.length:first+1)+' / '+cards.length;
   const canScroll=max>8;
   previous.disabled=!canScroll||left<5;
   next.disabled=!canScroll||left>=max-5;
 };
 const move=(dir)=>{
   const card=cards[0];
   const step=card?card.getBoundingClientRect().width+13:290;
   rail.scrollBy({left:dir*step,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
   event('mcl_article_rail_navigation',{direction:dir<0?'previous':'next'});
 };
 previous.addEventListener('click',()=>move(-1));
 next.addEventListener('click',()=>move(1));
 rail.addEventListener('scroll',updateRail,{passive:true});
 window.addEventListener('resize',updateRail,{passive:true});
 updateRail();

 const library=el('section','mcl-library');
 library.id='mcl-article-library';
 library.setAttribute('aria-labelledby','mcl-library-title');
 const hd=el('div','mcl-library-heading');
 const hdTitle=el('h3','','すべての記事から探す');
 hdTitle.id='mcl-library-title';
 const count=el('span','mcl-library-counter');
 count.setAttribute('role','status');
 count.setAttribute('aria-live','polite');
 hd.append(hdTitle,count);
 const toolbar=el('div','mcl-library-toolbar');
 const filters=el('div','mcl-filters');
 filters.setAttribute('role','group');
 filters.setAttribute('aria-label','記事のテーマで絞り込む');
 const buttons=new Map();
 const searchWrap=el('div');
 const searchLabel=el('label','mcl-search-label','記事タイトル・キーワードで探す');
 searchLabel.setAttribute('for','mcl-article-search');
 const search=el('input','mcl-library-search');
 search.id='mcl-article-search';
 search.type='search';
 search.autocomplete='off';
 search.placeholder='例：年収、AI、生産管理';
 search.setAttribute('aria-controls','mcl-library-grid');
 searchWrap.append(searchLabel,search);
 toolbar.append(filters,searchWrap);
 const grid=el('div','mcl-library-grid');
 grid.id='mcl-library-grid';
 const entries=[];
 catalog.forEach(([slug,category,title,description])=>{
   const item=el('article','mcl-library-item');
   const a=el('a');
   a.href='articles/'+slug;
   a.dataset.articleId=slug;
   a.append(el('span','',category),el('strong','',title),el('small','',description+'  ↗'));
   item.append(a);
   item.dataset.category=category;
   item.dataset.search=(title+' '+description+' '+category).toLocaleLowerCase('ja-JP');
   grid.append(item);
   entries.push(item);
 });
 const empty=el('p','mcl-library-empty','該当する記事がありません。テーマや検索語を変えてください。');
 empty.hidden=true;
 const foot=el('p','mcl-discovery-note','記事内の数値・調査時点・出典は各記事に記載しています。平均年収は個人の提示年収ではありません。');
 library.append(hd,toolbar,grid,empty,foot);
 rail.insertAdjacentElement('afterend',library);
 let active='すべて';
 const refresh=()=>{
   const q=search.value.trim().toLocaleLowerCase('ja-JP');
   let visible=0;
   entries.forEach(item=>{
     const match=(active==='すべて'||item.dataset.category===active)&&item.dataset.search.includes(q);
     item.hidden=!match;
     if(match) visible++;
   });
   empty.hidden=visible>0;
   count.textContent=visible+' / '+entries.length+' 記事';
 };
 groups.forEach(label=>{
   const b=el('button','mcl-filter',label);
   b.type='button';
   b.setAttribute('aria-pressed',label===active?'true':'false');
   b.addEventListener('click',()=>{
     active=label;
     buttons.forEach((button,key)=>button.setAttribute('aria-pressed',key===active?'true':'false'));
     refresh();
     event('mcl_article_filter',{article_category:label});
   });
   filters.append(b);
   buttons.set(label,b);
 });
 search.addEventListener('input',refresh); // Search strings are never sent to GA4.
 grid.addEventListener('click',evt=>{
   const link=evt.target.closest&&evt.target.closest('a[data-article-id]');
   if(link) event('mcl_article_select',{article_slug:link.dataset.articleId});
 });
 refresh();
})();
