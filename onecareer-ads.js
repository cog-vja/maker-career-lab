/* ワンキャリア転職 / A8.net: 公式提供コードはこの文字列内で無改変 */
(()=>{
  'use strict';
  const KEY='mcl-onecareer-floating-dismissed';
  let closed=false;
  try{closed=sessionStorage.getItem(KEY)==='yes';}catch(_e){}
  if(closed)return;
  function start(){
    if(document.getElementById('mcl-onecareer-floating'))return;
    const aside=document.createElement('aside');
    aside.id='mcl-onecareer-floating';
    aside.className='mcl-onecareer-floating';
    aside.setAttribute('aria-label','PR：ワンキャリア転職の広告');
    aside.innerHTML=`<div class="mcl-onecareer-floating__header"><span class="mcl-onecareer-floating__label">PR｜広告</span><button type="button" class="mcl-onecareer-floating__close" aria-label="広告を閉じる" title="広告を閉じる">×</button></div><div class="mcl-onecareer-floating__ad">
<a href="https://px.a8.net/svt/ejp?a8mat=4BEHXF+78RXAA+5O7E+BZ8OX" rel="nofollow">
<img border="0" width="100" height="60" alt="" src="https://www21.a8.net/svt/bgt?aid=261016899438&wid=003&eno=01&mid=s00000026465002012000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4BEHXF+78RXAA+5O7E+BZ8OX" alt="">
</div>`;
    const close=aside.querySelector('.mcl-onecareer-floating__close');
    close.addEventListener('click',()=>{
      aside.remove();
      try{sessionStorage.setItem(KEY,'yes');}catch(_e){}
    });
    // 入力中はキーボードと検索・比較操作を遮らない。
    document.addEventListener('focusin',(e)=>{
      if(e.target.matches('input, textarea, select, [contenteditable="true"]'))
        aside.classList.add('is-keyboard-active');
    });
    document.addEventListener('focusout',(e)=>{
      if(e.target.matches('input, textarea, select, [contenteditable="true"]'))
        aside.classList.remove('is-keyboard-active');
    });
    document.body.appendChild(aside);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();
