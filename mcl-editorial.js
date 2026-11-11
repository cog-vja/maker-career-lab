/* Maker Career Lab | accessible responsive comparison table enhancements.
   No analytics or affiliate code is changed, no network requests are made. */
(()=>{'use strict';
 const rows=document.getElementById('metrics-body');
 if(!rows)return;
 function decorate(){
  for(const tr of rows.querySelectorAll('tr')){
   const first=tr.firstElementChild;
   if(first&&first.tagName==='TD'){
    const heading=document.createElement('th');heading.scope='row';
    heading.textContent=first.textContent;
    tr.replaceChild(heading,first);
   }
  }
 }
 const observer=new MutationObserver(decorate);
 observer.observe(rows,{childList:true});decorate();
})();
