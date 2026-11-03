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
