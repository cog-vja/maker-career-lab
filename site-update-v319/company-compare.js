/* Maker Career Lab v3.19. Only source-verified, release-staged companies are displayed.
 * Additional discovery and incomplete issuer data are deliberately NOT loaded here.
 */
(()=>{'use strict';
const $=id=>document.getElementById(id);
const actual=Array.isArray(window.MCL_COMPANIES)?window.MCL_COMPANIES:[];
const demos=Array.isArray(window.MCL_DEMOS)?window.MCL_DEMOS:[];
const normalized=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[\s　・（）()]/g,'').replace(/株式会社/g,'');
const get=name=>actual.find(c=>normalized(c.name)===normalized(name)||c.aliases?.some(a=>normalized(a)===normalized(name)));
const n=x=>typeof x==='number'&&Number.isFinite(x)?x:null;
const ratio=(x,y)=>n(x)!==null&&n(y)!==null&&y!==0?100*x/y:null;
const calc=c=>({...c,margin:ratio(c.operatingProfit,c.revenue),growth:n(c.revenue)!==null&&n(c.revenuePrev)!==null&&c.revenuePrev!==0?100*(c.revenue/c.revenuePrev-1):null,cfRatio:ratio(c.operatingCashFlow,c.revenue)});
const fmt=(x,unit)=>n(x)===null?'未取得':x.toLocaleString('ja-JP',{maximumFractionDigits:unit==='%'?2:1,minimumFractionDigits:1})+unit;
const fields=[['営業利益率','margin','%'],['売上成長率','growth','%'],['営業CF／売上高','cfRatio','%'],['自己資本比率','equityRatio','%'],['平均年間給与','averageSalary','万円']];
function text(tag,value){const el=document.createElement(tag);el.textContent=value;return el;}
function addWarning(el,message){el.append(text('p',message));}
function show(a,b){
 const demo=!!(a.demo||b.demo);a=calc(a);b=calc(b);
 $('results').hidden=false;$('result-label').textContent=demo?'架空データ・操作デモ':'原本照合・公開承認済み';
 $('compare-title').textContent=a.name+' と '+b.name;
 $('result-context').textContent='現職：'+(a.period||'不明')+'／'+(a.scope||'不明')+'　検討先：'+(b.period||'不明')+'／'+(b.scope||'不明');
 const warnings=[];
 if(demo)warnings.push('この比較は架空データです。実在企業の評価には使用できません。');
 if(a.period!==b.period)warnings.push('決算期が異なります。単年度の差を直接比較する際は注意してください。');
 if(a.scope!==b.scope)warnings.push('連結・単体の対象範囲が異なります。');
 if(a.accountingStandard&&b.accountingStandard&&a.accountingStandard!==b.accountingStandard)warnings.push('会計基準が異なります。利益等の定義・認識基準を確認してください。');
 warnings.push('平均給与は主に提出会社単体の平均値で、連結指標とは対象が異なります。個別の転職年収ではありません。');
 $('result-warnings').replaceChildren(...warnings.map(w=>text('p',w)));
 $('metrics-body').replaceChildren();$('insights').replaceChildren();
 for(const [label,key,unit] of fields){
   const x=n(a[key]),y=n(b[key]),tr=document.createElement('tr');
   tr.append(text('td',label),text('td',fmt(x,unit)));
   const last=text('td',fmt(y,unit));
   if(x!==null&&y!==null){
     const difference=y-x;
     const suffix=text('small','差 '+(difference>0?'+':'')+fmt(difference,unit));
     suffix.className='mcl-metric-delta';last.append(suffix);
   }
   tr.append(last);$('metrics-body').append(tr);
   const box=document.createElement('div');box.className='insight-item';box.append(text('h3',label));
   let detail='';
   if(x===null||y===null)detail='一方または両方のデータが未取得です。推測で補いません。';
   else if(key==='margin')detail=(y>x?'検討先の営業利益率が高い結果です。':y<x?'現職の営業利益率が高い結果です。':'営業利益率は同水準です。')+' 事業構成・会計基準・3〜5年の推移を確認してください。';
   else if(key==='averageSalary')detail=(y>x?'検討先の開示平均給与が高い結果です。':y<x?'現職の開示平均給与が高い結果です。':'開示平均給与は同水準です。')+' 年齢・職種・単体従業員構成の違いがあり、提示年収を保証しません。';
   else if(key==='growth')detail='単年度の増減です。為替・M&A・事業再編と複数年の推移を確認してください。';
   else if(key==='cfRatio')detail='営業活動による資金創出の参考指標です。設備投資や運転資本の影響を別途確認してください。';
   else detail='財務健全性の一側面です。負債構造や業界特性も確認してください。';
   box.append(text('p',detail));$('insights').append(box);
 }
 $('sources').replaceChildren();
 for(const c of [a,b]){
   const block=document.createElement('div');block.className='source-card';
   block.append(text('strong',c.name),
     text('p','対象：'+(c.period||'不明')+' ／ '+(c.scope||'不明')+' ／ 給与：'+(c.salaryScope||'不明')),
     text('p','会計基準：'+(c.accountingStandard||'不明')+' ／ 出典：'+(c.sourceLabel||'架空デモ')));
   block.append(text('p','原本照合日：'+(c.verifiedAt||'実施日未記録（照合済み）')));
   if(c.sourceDocId&&/^S[A-Z0-9]{7,15}$/.test(c.sourceDocId)){
     const docline=document.createElement('p');docline.className='mcl-source-doc';docline.append(text('span','EDINET書類ID：'+c.sourceDocId+' '));
     const button=text('button','IDをコピー');button.type='button';button.className='mcl-copy-doc';
     button.addEventListener('click',async()=>{
       try{await navigator.clipboard.writeText(c.sourceDocId);button.textContent='コピーしました';}
       catch(e){$('status').textContent='書類ID '+c.sourceDocId+' をコピーしてEDINETで検索してください。';}
     });
     docline.append(button);block.append(docline);
     const link=text('a','金融庁EDINETを開く（書類IDで検索） ↗');
     link.href='https://disclosure2.edinet-fsa.go.jp/';link.target='_blank';link.rel='noopener noreferrer';
     block.append(link);
   }else if(demo){block.append(text('p','架空データにはEDINET原本はありません。'));}
   $('sources').append(block);
 }
 $('status').textContent=demo?'架空データの操作デモを表示しています。':'公開承認済みの財務データを表示しています。';
 $('results').scrollIntoView({behavior:'smooth',block:'start'});
}
function submit(e){
 e?.preventDefault();const a=$('name-a').value.trim(),b=$('name-b').value.trim();
 if(!a||!b){$('status').textContent='2社の名前を入力してください。';return;}
 const ca=get(a),cb=get(b);
 if(!ca||!cb){$('results').hidden=true;const missing=[!ca?a:null,!cb?b:null].filter(Boolean);$('status').textContent='未収録：'+missing.join('、')+'。原本照合・承認前の企業データは表示できません。';return;}
 if(String(ca.id)===String(cb.id)){$('results').hidden=true;$('status').textContent='同じ会社が選択されています。異なる2社を選んでください。';return;}
 show(ca,cb);
}
function init(){
 $('dataset-status').textContent=actual.length+'社（原本照合・公開承認済み）';
 const dl=$('company-list');for(const c of actual)dl.append(text('option',c.name));
 $('compare-form').addEventListener('submit',submit);
 $('demo').addEventListener('click',()=>{
   if(demos.length<2){$('status').textContent='デモデータを読み込めませんでした。';return;}
   $('name-a').value=demos[0].name;$('name-b').value=demos[1].name;show(demos[0],demos[1]);
 });
 $('reset').addEventListener('click',()=>{
   HTMLFormElement.prototype.reset.call($('compare-form'));
   $('results').hidden=true;$('status').textContent='';
   $('hint-a').textContent='';$('hint-b').textContent='';
 });
 for(const s of ['a','b'])$('name-'+s).addEventListener('input',()=>{
   const name=$('name-'+s).value.trim();
   $('hint-'+s).textContent=name&&!get(name)?'候補が見つからない場合は未収録です。':'';
 });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
