/* Manufacturing Research Editorial — semantic responsive comparison + table affordance.
 * Does not change data, analytics, affiliate tags, sorting or comparison math. */
(()=>{'use strict';
 const rows=document.getElementById('metrics-body');
 const getCompany = which => document.getElementById(which)?.value.trim() || (which==='name-a'?'企業A':'企業B');
 function decorateResults(){
  if(!rows)return;
  for(const tr of rows.querySelectorAll('tr')){
   const first=tr.firstElementChild;
   if(first?.tagName==='TD'){
    const heading=document.createElement('th'); heading.scope='row';
    heading.textContent=first.textContent;tr.replaceChild(heading,first);
   }
   const cells=tr.children;
   if(cells.length>=3){
    cells[1].dataset.company=getCompany('name-a');
    cells[2].dataset.company=getCompany('name-b');
    // These are absolute differences between two percentage-rate values:
    // display percentage points rather than a misleading relative '%' change.
    const delta=cells[2].querySelector('.mcl-metric-delta');
    if(delta && /%\s*$/.test(delta.textContent)){
      delta.textContent=delta.textContent.replace(/%\s*$/, 'ポイント');
    }
   }
  }
 }
 if(rows){
   const observer=new MutationObserver(decorateResults);
   observer.observe(rows,{childList:true});
   decorateResults();
 }

 // Native, keyboard-accessible scrolling for the wide EDINET and career tables.
 // Add a hint only when the content actually overflows the containing region.
 function decorateArticleTables(){
  for(const frame of document.querySelectorAll('.article .table-scroll, .mcl-seo-table-wrap')){
   if(!frame.querySelector('table'))continue;
   frame.tabIndex=0;
   frame.setAttribute('role','region');
   frame.setAttribute('aria-label','表（横にスクロールしてすべての列を確認できます）');
   const hasOverflow=frame.scrollWidth>frame.clientWidth+4;
   let hint=frame.previousElementSibling;
   if(!hint?.classList.contains('mcl-table-swipe-hint')){
    hint=document.createElement('p');hint.className='mcl-table-swipe-hint';
    hint.textContent='表は左右にスクロールして確認できます';
    hint.hidden=true;frame.parentNode.insertBefore(hint,frame);
   }
   hint.hidden=!hasOverflow;
  }
 }
 decorateArticleTables();
 window.addEventListener('resize',decorateArticleTables,{passive:true});
})();
