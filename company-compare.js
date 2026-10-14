(()=>{'use strict';
const $=id=>document.getElementById(id), data=Array.isArray(window.MCL_COMPANIES)?window.MCL_COMPANIES:[];
const metricNames={revenue:'売上高',operatingProfit:'営業利益',revenuePrev:'前期売上高',operatingCashFlow:'営業キャッシュフロー',equityRatio:'自己資本比率',averageSalary:'平均年間給与'};
const keys=Object.keys(metricNames);
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
const norm=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[\s　株式会社（()）・]/g,'');
const lookup=name=>data.find(c=>norm(c.name)===norm(name)||c.aliases?.some(a=>norm(a)===norm(name)));
const fmt=(v,unit='',dec=1)=>number(v)===null?'情報なし':v.toLocaleString('ja-JP',{maximumFractionDigits:dec,minimumFractionDigits:dec})+unit;
const pct=(a,b)=>number(a)!==null&&number(b)!==null&&b!==0?100*a/b:null;
const growth=(a,b)=>number(a)!==null&&number(b)!==null&&b!==0?100*(a/b-1):null;
const compute=c=>({...c,operatingMargin:pct(c.operatingProfit,c.revenue),revenueGrowth:growth(c.revenue,c.revenuePrev),cashFlowMargin:pct(c.operatingCashFlow,c.revenue)});
function formValue(id){const val=$(id).value.trim();return val===''?null:Number(val)}
function fromForm(side){const name=$('name-'+side).value.trim();const c=lookup(name);if(c)return compute(c);const obj={name:name||'未入力',period:$('period-'+side).value.trim()||'決算期未入力',scope:$('scope-'+side).value,sector:'',sourceLabel:$('source-'+side).value.trim()?'入力者が指定した資料':'出典未入力',sourceUrl:$('source-'+side).value.trim(),salaryScope:$('salary-scope-'+side).value.trim()||'対象範囲未入力',demo:false,manual:true};for(const k of keys)obj[k]=formValue(k+'-'+side);return compute(obj)}
function populate(side,c){if(!c)return;for(const k of keys)$(k+'-'+side).value=number(c[k])===null?'':c[k];$('period-'+side).value=c.demo?'':c.period;$('scope-'+side).value=c.demo?'連結':(c.scope?.includes('単体')?'単体':'連結');$('source-'+side).value=c.sourceUrl||'';$('salary-scope-'+side).value=c.demo?'':c.salaryScope||''}
function clearFields(side){for(const k of keys)$(k+'-'+side).value='';$('period-'+side).value='';$('source-'+side).value='';$('salary-scope-'+side).value=''}
function noteFor(label,a,b){const x=number(a),y=number(b);if(x===null||y===null)return '一方または両方の数値が未取得です。数値の欠落は評価に含めません。';if(label==='営業利益率')return y>x?'検討先は当該決算期の売上高に対する営業利益の割合が高くなっています。給与水準や将来の成長を直接示すものではありません。':y<x?'現職側の営業利益率が高くなっています。利益率は業界構造・会計基準・事業構成によって異なります。':'当該決算期の営業利益率は同水準です。事業別の収益性や数年の推移も確認しましょう。';if(label==='平均年間給与')return y>x?'検討先の開示平均給与が高くなっています。ただし対象会社、平均年齢、職種、役職が違う可能性があります。':'開示平均給与だけで転職後の個別年収は判断できません。求人票の職種別レンジを確認しましょう。';if(label==='売上成長率')return '成長率は前期売上高を基準にした単年度比較です。買収・為替・会計変更の影響と3〜5年推移を確認しましょう。';return 'この指標だけで働く価値は判断できません。比較範囲と決算期を確認してください。'}
const metrics=[['営業利益率','operatingMargin','%'],['売上成長率','revenueGrowth','%'],['営業CF／売上高','cashFlowMargin','%'],['自己資本比率','equityRatio','%'],['平均年間給与','averageSalary','万円']];
function compare(){const a=fromForm('a'),b=fromForm('b');if(a.name==='未入力'||b.name==='未入力'){$('status').textContent='2社の企業名を入力してください。';return}const demo=a.demo||b.demo;const manual=a.manual||b.manual;
$('status').textContent=demo?'架空データを使用した操作デモです。実在企業の評価には使用できません。':manual?'手入力したデータによる比較です。数値・出典の正確性は入力者が確認してください。':'公開資料をもとにした比較です。';
$('results').hidden=false;$('compare-title').textContent=`${a.name} と ${b.name}`;
$('result-context').textContent=`現職：${a.period}／${a.scope||'範囲不明'}　｜　検討先：${b.period}／${b.scope||'範囲不明'}`;
const tbody=$('metrics-body');tbody.replaceChildren();const insights=$('insights');insights.replaceChildren();
for(const [label,key,unit] of metrics){const x=number(a[key]),y=number(b[key]);const tr=document.createElement('tr');const vals=[label,fmt(x,unit),fmt(y,unit),x===null||y===null?'比較不可':fmt(y-x,unit)];for(const v of vals){const td=document.createElement('td');td.textContent=v;tr.append(td)}tbody.append(tr);const item=document.createElement('li');const strong=document.createElement('strong');strong.textContent=label+'：';item.append(strong,document.createTextNode(noteFor(label,x,y)));insights.append(item)}
const salary=$('salary-warning');salary.textContent=`平均給与の対象：現職「${a.salaryScope||'不明'}」、検討先「${b.salaryScope||'不明'}」。対象・年齢・雇用形態が異なる場合は直接比較に注意。`;
const sources=$('sources');sources.replaceChildren();for(const c of [a,b]){const li=document.createElement('li');li.append(document.createTextNode(c.name+'：'+c.sourceLabel+'／'+c.period+'。 '));if(/^https:\/\//.test(c.sourceUrl||'')){const link=document.createElement('a');link.href=c.sourceUrl;link.target='_blank';link.rel='noopener noreferrer';link.textContent='出典を開く';li.append(link)}sources.append(li)}
$('results').scrollIntoView({behavior:'smooth',block:'start'});
}
function attach(){for(const side of ['a','b']){$('name-'+side).addEventListener('change',()=>{const c=lookup($('name-'+side).value.trim());if(c)populate(side,c);else clearFields(side)});$('name-'+side).addEventListener('input',()=>{const q=norm($('name-'+side).value);const matches=data.filter(c=>norm(c.name).includes(q)||c.aliases?.some(a=>norm(a).includes(q))).slice(0,5);const box=$('suggest-'+side);box.replaceChildren();if(q.length<2)return;for(const c of matches){const btn=document.createElement('button');btn.type='button';btn.className='suggest-item';btn.textContent=c.name;btn.addEventListener('click',()=>{$('name-'+side).value=c.name;populate(side,c);box.replaceChildren()});box.append(btn)}})}$('compare-form').addEventListener('submit',e=>{e.preventDefault();compare()});$('demo').addEventListener('click',()=>{$('name-a').value=data[0].name;$('name-b').value=data[1].name;populate('a',data[0]);populate('b',data[1]);compare()});$('reset').addEventListener('click',()=>{for(const s of ['a','b']){$('name-'+s).value='';clearFields(s)}$('results').hidden=true;$('status').textContent='入力内容は送信・保存されません。'});}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach);else attach();
})();
