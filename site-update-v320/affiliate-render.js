/* v3.20 A8 ad renderer. Ad content never changes company rankings or metrics. */
(()=>{'use strict';
 const approvedHosts=new Set(['px.a8.net','www.a8.net','a8.net']);
 const cfg=window.MCL_ADS;
 if(!cfg||cfg.version!=='3.20'||cfg.enabled!==true||!Array.isArray(cfg.placements))return;
 function safe(a){
  if(!a||a.slot!=='compare-below-results'||typeof a.label!=='string'||typeof a.sponsor!=='string'||typeof a.url!=='string')return false;
  if(!a.label.trim()||!a.sponsor.trim()||a.label.length>100||a.sponsor.length>100||/[<>]/.test(a.label+a.sponsor))return false;
  try{const u=new URL(a.url);return u.protocol==='https:'&&approvedHosts.has(u.hostname)&&!u.username&&!u.password;}catch(e){return false;}
 }
 function write(){
  const ad=cfg.placements.find(safe), slot=document.getElementById('affiliate-slot'),notice=document.getElementById('affiliate-disclosure');
  if(!ad||!slot||!notice)return;
  const tag=document.createElement('p');tag.className='mcl-ad-label';tag.textContent='PR｜アフィリエイト広告';
  const desc=document.createElement('p');desc.textContent=ad.sponsor+'のサービス紹介です。比較結果や企業掲載順には影響しません。';
  const a=document.createElement('a');a.href=ad.url;a.textContent=ad.label;a.target='_blank';a.rel='sponsored nofollow noopener noreferrer';
  slot.replaceChildren(tag,desc,a);slot.hidden=false;notice.hidden=false;
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',write);else write();
})();
