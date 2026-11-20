from prepare import *
import re
t=Path('scripts/dashboard.template.html').read_text()
t=t.replace('Compare top five','Actual + ARIMA + top 3').replace('<option>Full year</option>','<option>Standard range</option><option>Full year</option><option>Custom dates</option>')
t=t.replace('<button id="reset">Reset zoom</button>','<label id="fromlabel" hidden>From<input id="from" type="date" value="2021-07-01" min="2021-01-01" max="2021-12-31"></label><label id="tolabel" hidden>Through<input id="through" type="date" value="2021-07-14" min="2021-01-01" max="2021-12-31"></label><button id="reset">Reset view</button>')
t=t.replace('<span id="status"></span>','<span id="status" role="status"></span>').replace('<section><h2 id="ct">','<noscript>Enable JavaScript in your browser to display this offline dashboard.</noscript><section><h2 id="ct">')
t=t.replace('<small>Wheel to zoom','<small>Click legend entries to show or hide traces. Wheel to zoom').replace('<section><h2>Hourly configuration rankings','<section><h2>Performance against daily AutoARIMA</h2><p class="note">Full-year hourly errors. Positive improvement means less error than the baseline. Percentage improvement is undefined when baseline error is zero.</p><div class="scroll"><table><thead><tr><th>Rank</th><th>Displayed forecast</th><th>Score</th><th>MAE ↓ %</th><th>RMSE ↓ %</th><th>WAPE ↓ %</th><th>MASE ↓ %</th><th>|Bias| ↓ %</th><th>sMAPE ↓ %</th></tr></thead><tbody id="comparison"></tbody></table></div></section><section><h2>Hourly configuration rankings')
t=t.replace('Only complete, finite hourly records','The design reference is AutoARIMA__daily. The project catalog’s explicitly tagged controls and AutoARIMA variants are excluded from the three candidate slots. All eligible configurations retain their official rankings. Only complete, finite hourly records')
t=t.replace('</style>','label[hidden]{display:none}#legend button{font-size:12px;padding:4px 7px;background:#fff;border-color:#cfddda}#legend button[aria-pressed="false"]{opacity:.5;text-decoration:line-through}#ct{font-size:18px}</style>')
t=t.replace("colors=['#243a4a','#008579','#bd5c13','#8663a4','#3e74ad','#ae3e5e']","colors=['#16374a','#be5527','#007f75','#8055a8','#397abb','#ae3e5e']")
t=t.replace("let arrays=[]","let hiddenSeries=new Set();let arrays=[]")
t=t.replace("let my=++token;", "hiddenSeries.clear();let my=++token;")
t=t.replace("let aa=await Promise.all(nn.map(n=>decode(meta[target].series[n])));","let aa;try{aa=await Promise.all(nn.map(n=>decode(meta[target].series[n])))}catch(err){if(my===token)$('status').textContent='Could not decode forecast data. Open the full downloaded HTML in current Edge, Chrome or Firefox. '+err.message;return;}")
t=t.replace("+'s':'')","+'s':'')") # Main and single views share the same measured series.
a=t.index('function change()');b=t.index('function groups',a)
t=t[:a]+'''function change(){target=ds.value;cache.clear();single.innerHTML='';for(let row of meta[target].rows)option(single,row[1]);$('period').value='Standard range';table();load(meta[target].main.slice(1))}
function comparison(){let rows=meta[target].rows, baseline=rows.find(r=>r[1]==='AutoARIMA__daily');let body=$('comparison');body.innerHTML='';let group=[...new Set(['AutoARIMA__daily',...names.slice(1)])];for(let name of group){let r=rows.find(v=>v[1]===name),tr=body.insertRow();for(let v of [r[0],name,r[2],...[3,4,5,6,7,8].map(j=>baseline[j]===null||baseline[j]===0||r[j]===null?null:100*(Math.abs(baseline[j])-Math.abs(r[j]))/Math.abs(baseline[j]))]){tr.insertCell().textContent=typeof v==='string'?v:pretty(v)}}}
'''+t[b:]
t=t.replace("let fix={'Full year'", """let hourly=$('res').value==='Hourly'&&!['Error distribution','Seasonal profile'].includes($('mode').value);
$('fromlabel').hidden=$('tolabel').hidden=p!=='Custom dates';
if(p==='Custom dates'){let a=(Date.parse($('from').value+'T00:00:00Z')-base)/H,b=(Date.parse($('through').value+'T00:00:00Z')-base)/H+24;if(Number.isInteger(a)&&Number.isInteger(b)&&0<=a&&a<b&&b<=N)return [a,b];return null}
let fix={'Standard range':hourly?[4344,4680]:[0,N],'Full year'""")
t=t.replace("u=meta[target].unit;let energy", """u=meta[target].unit;if(sel===null){$('status').textContent='Choose a valid range within 2021; the end must follow or equal the start.';return}
$('status').textContent=stamp(sel[0]).slice(0,10)+' to '+stamp(sel[1]-1).slice(0,10)+' · '+(sel[1]-sel[0]).toLocaleString()+' hourly samples';comparison();let energy""")
a=t.index("nms.forEach((n,j)=>{let e=document.createElement('span')")
b=t.index('function paint()',a)
t=t[:a]+'''nms.forEach((n,j)=>{let e=document.createElement('button');e.setAttribute('aria-pressed',String(!hiddenSeries.has(n)));e.innerHTML='<i class="swatch" style="border-color:'+cs[j]+'"></i>';e.append(n);e.onclick=()=>{if(hiddenSeries.has(n))hiddenSeries.delete(n);else hiddenSeries.add(n);e.setAttribute('aria-pressed',String(!hiddenSeries.has(n)));paint()};$('legend').append(e)});paint()}
'''+t[b:]
t=t.replace('for(let f of ys)for(let i=st;', 'for(let f of ys.filter((_,j)=>!hiddenSeries.has(nms[j])))for(let i=st;').replace('if(lo===hi){lo-=.5;',"""if(!Number.isFinite(lo)){$('readout').textContent='Choose a legend entry to display a series.';return}if(lo===hi){lo-=.5;""")
t=t.replace('ys.forEach((f,j)=>{ctx.strokeStyle','ys.forEach((f,j)=>{if(hiddenSeries.has(nms[j]))return;ctx.strokeStyle').replace("ys.map((f,j)=>nms[j]+' '+pretty(f[hover])+' '+u).join", "ys.map((f,j)=>hiddenSeries.has(nms[j])?null:nms[j]+' '+pretty(f[hover])+' '+u).filter(Boolean).join")
t=t.replace("if(en-st===1)ctx.fillRect", "if(en-st===1)ctx.fillRect")
t=t.replace("$('period').value='Full year';update()", "$('period').value='Standard range';update()")
t=t.replace("load(meta[target].rows.slice(0,5).map(r=>r[1]))","load(meta[target].main.slice(1))")
t=t.replace("['mode','res','quantity','period']", "['mode','res','quantity','period','from','through']")
t=t.replace("cs=colors;let title", "cs=names.length===2&&names[1]!=='AutoARIMA__daily'?[colors[0],colors[2]]:colors;let title").replace("cs=colors.slice(1)","cs=cs.slice(1)")
# Yearly source payload and rankings are kept exactly as delivered.
old=(SRC/'00_Overview/C2_Forecast_Explorer.html').read_text()
m=json.loads(re.search(r'<script id="catalog" type="application/json">(.*?)</script>',old)[1])
sel=json.loads((TMP/'selection.json').read_text())
for k in m:m[k]['main']=sel[k]['names']
blob=re.search(r'<script id="payload" type="application/json">(.*?)</script>',old)[1]
(OUT/'00_Overview/C2_Forecast_Explorer.html').write_text(t.replace('CATALOG_JSON',json.dumps(m,separators=(',',':'))).replace('PAYLOAD_JSON',blob))
