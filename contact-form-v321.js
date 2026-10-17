(() => {
  'use strict';
  const form = document.getElementById('contact-form');
  if (!form) return;
  const cfg = window.MCL_CONTACT || {};
  const endpoint = String(cfg.endpoint || '');
  const allowed = /^https:\/\/formspree\.io\/f\/[a-zA-Z0-9]+$/.test(endpoint);
  const setup = document.getElementById('contact-setup');
  const button = document.getElementById('contact-submit');
  const status = document.getElementById('form-status');
  const setStatus = (msg,kind='info') => { status.textContent=msg; status.dataset.type=kind; };
  if (!allowed) {
    setup.textContent='フォーム送信先の設定待ちです。現在はお問い合わせを送信できません。';
    button.disabled=true;
    return;
  }
  setup.textContent='お問い合わせをフォームから受け付けています。';
  button.disabled=false;
  form.addEventListener('submit',async e => {
    e.preventDefault();
    const category=form.elements.category.value;
    const email=form.elements.email.value.trim();
    const message=form.elements.message.value.trim();
    const agreed=form.elements.privacy_consent.checked;
    if (!category || message.length<10 || message.length>3000 || !agreed || !form.checkValidity()) {
      setStatus('必須項目と同意欄を確認してください。','error'); form.reportValidity(); return;
    }
    if (form.elements._gotcha.value) { setStatus('送信を受け付けました。','success'); return; }
    button.disabled=true;
    setStatus('送信中です…');
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),20000);
    try {
      const data=new FormData(form);
      const response=await fetch(endpoint,{method:'POST',body:data,headers:{Accept:'application/json'},signal:controller.signal,redirect:'error'});
      if(!response.ok) throw new Error('Formspree returned '+response.status);
      setStatus('お問い合わせを受け付けました。ご連絡ありがとうございます。','success');
      form.reset();
    } catch (err) {
      setStatus('送信できませんでした。時間をおいて再度お試しください。','error');
    } finally { clearTimeout(timeout); button.disabled=false; }
  });
})();
