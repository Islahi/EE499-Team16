"""Offline, reproducible plots, standalone dashboard and PDF summary from saved CSVs."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
SECTORS=('residential','commercial','manufacturing','feeder')

def generate_all():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.dates import DateFormatter,AutoDateLocator
    out=BASE/'results';figdir=BASE/'figures';figdir.mkdir(exist_ok=True)
    annual=pd.read_csv(out/'full_year_metrics.csv')
    month=pd.read_csv(out/'monthly_metrics.csv')
    runtime=json.loads((out/'runtime_summary.json').read_text())
    diag=pd.read_csv(out/'scaling_diagnostics.csv')
    hist={t:pd.read_csv(out/f'{t}_hourly.csv',parse_dates=['timestamp']) for t in SECTORS}
    colors={'actual_kw':'#263D56','forecast_A_kw':'#DD7832','forecast_B_kw':'#268B83'}
    for target,df in hist.items():
        selector=(df.timestamp>=pd.Timestamp('2021-07-01'))&(df.timestamp<pd.Timestamp('2021-07-15'))
        week=df.loc[selector]
        if len(week)!=336:raise ValueError('July 1-14 2021 should be 336 hours')
        fig,ax=plt.subplots(figsize=(13.5,4.5))
        for col,name,style in [('actual_kw','Actual','-'),('forecast_A_kw','A: sum then forecast','--'),
                               ('forecast_B_kw','B: forecast then sum',':')]:
            ax.plot(week.timestamp,week[col],label=name,color=colors[col],lw=1.6 if col=='actual_kw' else 1.3,linestyle=style)
        ax.set_title(f'{target.title()} | Hourly demand | 1-14 July 2021')
        ax.set_ylabel('Active demand (kW)');ax.grid(True,alpha=.22)
        ax.xaxis.set_major_locator(AutoDateLocator());ax.xaxis.set_major_formatter(DateFormatter('%d %b'))
        ax.legend(loc='upper right',ncol=3,fontsize=9)
        fig.autofmt_xdate();fig.tight_layout()
        fig.savefig(figdir/f'{target}_hourly_July01_14.png',dpi=175)
        plt.close(fig)
        fig,ax=plt.subplots(figsize=(13.5,3.3))
        ax.plot(week.timestamp,week['A_minus_B_kw'],lw=1.35,color='#6A56A4')
        ax.axhline(0,color='#2E455C',linewidth=.8,alpha=.7)
        maxdiff=float(np.max(np.abs(week.A_minus_B_kw)))
        ax.set_title(f'{target.title()} | A minus B forecast | 1-14 July 2021 | maximum {maxdiff:.8f} kW')
        ax.set_ylabel('Forecast difference (kW)');ax.grid(True,alpha=.22)
        ax.xaxis.set_major_locator(AutoDateLocator());ax.xaxis.set_major_formatter(DateFormatter('%d %b'))
        fig.autofmt_xdate();fig.tight_layout();fig.savefig(figdir/f'{target}_difference_July01_14.png',dpi=175);plt.close(fig)
        daily=df.set_index('timestamp')[['actual_kw','forecast_A_kw','forecast_B_kw']].resample('MS').mean()
        fig,ax=plt.subplots(figsize=(12,4))
        pos=np.arange(12)
        ax.plot(pos,daily.actual_kw,marker='o',label='Actual',color=colors['actual_kw'])
        ax.plot(pos,daily.forecast_A_kw,marker='s',label='A',color=colors['forecast_A_kw'])
        ax.plot(pos,daily.forecast_B_kw,marker='^',label='B',color=colors['forecast_B_kw'])
        ax.set_xticks(pos,[d.strftime('%b') for d in daily.index]);ax.set_ylabel('Mean hourly kW')
        ax.set_title(f'{target.title()} | Monthly mean active demand, 2021')
        ax.grid(True,alpha=.2);ax.legend(ncol=3);fig.tight_layout()
        fig.savefig(figdir/f'{target}_monthly_2021.png',dpi=175);plt.close(fig)
    # Audit overview: different representative demand patterns without duplicating source profiles.
    inp=pd.read_csv(BASE/'input/load_profile.csv',parse_dates=['timestamp'])
    arr=inp.loc[(inp.timestamp>=pd.Timestamp('2021-07-01'))&(inp.timestamp<pd.Timestamp('2021-07-08'))&inp.bus_id.isin([2,3,4])]
    fig,ax=plt.subplots(figsize=(12,4))
    for b,name in [(2,'Residential bus 2'),(3,'Commercial bus 3'),(4,'Manufacturing bus 4')]:
        q=arr[arr.bus_id==b];ax.plot(q.timestamp,q.p_kw,label=name,lw=1.3)
    ax.legend(ncol=3);ax.set_ylabel('Per-bus kW');ax.set_title('Representative distinct 15-bus demand series | 1-7 July 2021')
    ax.grid(True,alpha=.22);fig.autofmt_xdate();fig.tight_layout()
    fig.savefig(figdir/'variability_three_representative_buses.png',dpi=175);plt.close(fig)
    generate_dashboard(hist,annual,month,runtime)
    make_report(annual,month,runtime,diag)

def generate_dashboard(hist,annual,month,runtime):
    # No CDN, no fetch(), no local webserver and no dependencies: works from file:// on Windows.
    payload={k:{'timestamps':v.timestamp.dt.strftime('%Y-%m-%d %H:%M').tolist(),
        'actual':np.round(v.actual_kw.to_numpy(),6).tolist(),
        'A':np.round(v.forecast_A_kw.to_numpy(),6).tolist(),
        'B':np.round(v.forecast_B_kw.to_numpy(),6).tolist()} for k,v in hist.items()}
    meta={'annual':annual.replace({np.nan:None}).to_dict('records'),
          'monthly':month.replace({np.nan:None}).to_dict('records'),
          'runtime':runtime}
    html=r'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>EE499 | Sector aggregation benchmark</title>
<style>body{font:15px system-ui,-apple-system,sans-serif;background:#f3f6f7;color:#14293a;margin:0}
header{background:#183a4b;color:white;padding:23px 4%}h1{margin:0;font-size:26px}header p{margin:7px 0 0;color:#d5e1e4}
main{max-width:1300px;margin:24px auto;padding:0 18px}section{background:white;border:1px solid #d7e4e8;border-radius:10px;margin-bottom:18px;padding:18px 22px}
.controls{display:flex;gap:16px;flex-wrap:wrap;align-items:end}label{font-size:13px;color:#385668;font-weight:600;display:flex;flex-direction:column;gap:6px}
select,input{font:14px system-ui;border:1px solid #a8babc;border-radius:5px;padding:8px;color:#1d3345;background:#fff}#plot,#diff{width:100%;height:350px;display:block}#diff{height:190px}
.legend{display:flex;gap:18px;flex-wrap:wrap;padding:8px 0;color:#405560;font-size:13px}.legend input{margin-right:6px}
.swatch{width:18px;height:3px;display:inline-block;margin-right:5px;vertical-align:middle}table{width:100%;border-collapse:collapse;font-size:12px;min-width:700px}td,th{padding:8px;border-bottom:1px solid #e2ebee;text-align:right}th{background:#edf5f6}td:first-child,th:first-child{text-align:left}
.scroller{overflow-x:auto}.note{color:#516b7a;font-size:13px}.kpi{font-size:15px;font-weight:600;color:#254b5b}
</style></head><body><header><h1>EE499 Team 16 | Sector aggregation forecasting</h1><p>2021 fixed-origin holdout | 43,921-hour 15-bus source | PV excluded | Offline</p></header>
<main><section><div class="controls"><label>Target<select id="target"><option value="residential">Residential</option><option value="commercial">Commercial</option><option value="manufacturing">Manufacturing</option><option value="feeder">Total feeder</option></select></label>
<label>View<select id="range"><option value="july">Standard July 1–14</option><option value="year">Full-year daily average</option><option value="monthly">Full-year monthly average</option><option value="custom">Custom 2021 dates</option></select></label>
<label id="fromlabel" hidden>Start<input type="date" id="from" value="2021-07-01" min="2021-01-01" max="2021-12-31"/></label>
<label id="tolabel" hidden>End (inclusive)<input type="date" id="to" value="2021-07-14" min="2021-01-01" max="2021-12-31"/></label></div>
<p class="kpi" id="summary"></p><div class="legend"><label><span><input type="checkbox" id="showactual" checked/><i class="swatch" style="background:#21394c"></i>Actual</span></label><label><span><input type="checkbox" id="showa" checked/><i class="swatch" style="background:#de7835"></i>A: sum then forecast</span></label><label><span><input type="checkbox" id="showb" checked/><i class="swatch" style="background:#298d84"></i>B: forecast then sum</span></label></div>
<canvas id="plot"></canvas><p class="note" id="hover">Move the mouse across the plot for exact timestamp and values.</p></section>
<section><h3>A − B forecast difference</h3><canvas id="diff"></canvas><p class="note">This uses a separate vertical scale, so very small discrepancies remain visible.</p></section>
<section><h3>Full-year accuracy comparison</h3><div class="scroller"><table id="scores"></table></div><h3>Month-by-month accuracy comparison</h3><div class="scroller"><table id="monthly"></table></div></section>
<section><h3>Protocol and interpretation</h3><p>Three training-only sector selections are frozen across both approaches. Approach A fits three sector sums; Approach B fits 14 buses independently. Identical buses are independently fitted (no forecast reuse), while calendar features are shared. The archived C2 predictions are supplied only as a reproduction check. The distributor normalization spans 2017–2022, including holdout observations, so this exercise is not a fully prospective evaluation of the upstream distributor.</p>
<p class="note">Source: https://github.com/Islahi/EE499-Team16.git | Demand uses distributed bus kW, not cohort kW/customer. The PV file is a zero placeholder.</p></section></main>
<script id="payload" type="application/json">__DATA__</script><script id="meta" type="application/json">__META__</script>
<script>
'use strict';const DATA=JSON.parse(document.querySelector('#payload').textContent),META=JSON.parse(document.querySelector('#meta').textContent);
const byId=x=>document.getElementById(x),colors=['#21394c','#de7835','#298d84'];let active=[],hover=-1;
function fmt(x){return Number(x).toFixed(Math.abs(x)>=100?2:5)}
function agg(dt,arr,mode){let groups=new Map();for(let i=0;i<dt.length;i++){let ts=dt[i],key=mode==='monthly'?ts.slice(0,7):ts.slice(0,10);if(!groups.has(key))groups.set(key,[0,0,0,0]);let g=groups.get(key);g[0]++;for(let j=0;j<3;j++)g[j+1]+=arr[j][i]}
let keys=[...groups.keys()],means=keys.map(x=>groups.get(x));return {times:keys,vals:[0,1,2].map(j=>means.map(g=>g[j+1]/g[0]))}}
function segment(){let name=byId('target').value,d=DATA[name],mode=byId('range').value,vals=[d.actual,d.A,d.B],t=d.timestamps;
if(mode==='year'||mode==='monthly')return agg(t,vals,mode);
let lo=mode==='july'?'2021-07-01':byId('from').value,hi=mode==='july'?'2021-07-14':byId('to').value;
let ids=[];for(let i=0;i<t.length;i++)if(t[i].slice(0,10)>=lo&&t[i].slice(0,10)<=hi)ids.push(i);
return {times:ids.map(i=>t[i]),vals:vals.map(a=>ids.map(i=>a[i]))}}
function plot(canvas,labels,vals,colorlist){const ctx=canvas.getContext('2d'),dpr=window.devicePixelRatio||1;
let w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
ctx.clearRect(0,0,w,h);let left=66,right=16,top=23,bottom=39,innerW=w-left-right,innerH=h-top-bottom;ctx.strokeStyle='#dbe5e9';ctx.lineWidth=1;
let selected=vals.filter(a=>a!==null);if(!selected.length||!labels.length){ctx.fillStyle='#516e7a';ctx.fillText('No dates or visible traces',left,30);return}
let mn=Math.min(...selected.flat()),mx=Math.max(...selected.flat());let pad=Math.max((mx-mn)*0.07,Math.abs(mx)*1e-8,1e-8);mn-=pad;mx+=pad;
ctx.font='12px system-ui';ctx.fillStyle='#506b78';ctx.textAlign='right';for(let j=0;j<=4;j++){let yy=top+innerH*j/4;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(w-right,yy);ctx.stroke();ctx.fillText(fmt(mx-(mx-mn)*j/4),left-8,yy+4)}
for(let j=0;j<=6;j++){let x=left+innerW*j/6,index=Math.min(labels.length-1,Math.round(j*(labels.length-1)/6));ctx.textAlign='center';ctx.fillText(labels[index].slice(0,10),x,h-13)}
vals.forEach((v,j)=>{if(v===null)return;ctx.beginPath();ctx.lineWidth=1.4;ctx.strokeStyle=colorlist[j];for(let i=0;i<v.length;i++){let xx=left+innerW*i/Math.max(v.length-1,1),yy=top+innerH*(mx-v[i])/(mx-mn);if(i===0)ctx.moveTo(xx,yy);else ctx.lineTo(xx,yy)}ctx.stroke()});
if(hover>=0&&hover<labels.length){let xx=left+innerW*hover/Math.max(labels.length-1,1);ctx.strokeStyle='#777';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(xx,top);ctx.lineTo(xx,top+innerH);ctx.stroke();ctx.setLineDash([])}}
function draw(){let mode=byId('range').value;byId('fromlabel').hidden=byId('tolabel').hidden=mode!=='custom';active=segment();let selected=[byId('showactual').checked,byId('showa').checked,byId('showb').checked];
plot(byId('plot'),active.times,active.vals.map((a,i)=>selected[i]?a:null),colors);
let diff=active.vals[1].map((x,i)=>x-active.vals[2][i]);plot(byId('diff'),active.times,[diff],['#6a55a4']);
let t=byId('target').value,A=META.annual.find(x=>x.target===t&&x.method.startsWith('A')),B=META.annual.find(x=>x.target===t&&x.method.startsWith('B'));
byId('summary').textContent='RMSE: A '+fmt(A.rmse_kw)+' kW · B '+fmt(B.rmse_kw)+' kW | WAPE: A '+fmt(A.wape_pct)+'% · B '+fmt(B.wape_pct)+'%';
function mkTable(items){let h='<tr><th>Target / Month</th><th>Method</th><th>MAE kW</th><th>RMSE kW</th><th>WAPE %</th><th>MASE (168 h)</th><th>Bias kW</th><th>sMAPE %</th></tr>';
for(let r of items)h+='<tr><td>'+(r.month||r.target)+'</td><td>'+(r.method.startsWith('A')?'A':'B')+'</td>'+['mae_kw','rmse_kw','wape_pct','mase_weekly','bias_actual_minus_forecast_kw','smape_pct'].map(k=>'<td>'+fmt(r[k])+'</td>').join('')+'</tr>';return h}
byId('scores').innerHTML=mkTable(META.annual.filter(x=>x.target===t));byId('monthly').innerHTML=mkTable(META.monthly.filter(x=>x.target===t));}
['target','range','from','to','showactual','showa','showb'].forEach(id=>byId(id).addEventListener('change',()=>{hover=-1;draw()}));
byId('plot').addEventListener('mousemove',ev=>{let r=byId('plot').getBoundingClientRect(),x=ev.clientX-r.left;hover=Math.max(0,Math.min(active.times.length-1,Math.round((x-66)/(r.width-82)*(active.times.length-1))));if(!active.times.length)return;
byId('hover').textContent=active.times[hover]+' | Actual: '+fmt(active.vals[0][hover])+' kW | A: '+fmt(active.vals[1][hover])+' kW | B: '+fmt(active.vals[2][hover])+' kW | A−B: '+fmt(active.vals[1][hover]-active.vals[2][hover])+' kW';draw()});
window.addEventListener('resize',draw);draw();
</script></body></html>'''
    # Avoid invalid JSON NaN or Infinity, all test data is finite.
    html=html.replace('__DATA__',json.dumps(payload,separators=(',',':'),allow_nan=False))
    html=html.replace('__META__',json.dumps(meta,separators=(',',':'),allow_nan=False))
    (BASE/'dashboard.html').write_text(html,encoding='utf-8')

def make_report(annual,monthly,runtime,diagnostic):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import landscape,A4
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,KeepTogether
    out=BASE/'results';audit=json.loads((out/'audit_summary.json').read_text())
    styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='ReportTitle',parent=styles['Heading1'],fontSize=20,leading=25,textColor=colors.HexColor('#173a4d'),spaceAfter=13))
    styles.add(ParagraphStyle(name='ReportBody',parent=styles['BodyText'],fontSize=10,leading=14,spaceAfter=8))
    styles.add(ParagraphStyle(name='ReportSmall',parent=styles['BodyText'],fontSize=8.6,leading=12,spaceAfter=7))
    styles.add(ParagraphStyle(name='ReportSub',parent=styles['Heading2'],fontSize=12.4,leading=17,textColor=colors.HexColor('#1c5360'),spaceAfter=8))
    doc=SimpleDocTemplate(str(BASE/'EE499_Sector_Aggregation_Report.pdf'),pagesize=landscape(A4),
       rightMargin=20*mm,leftMargin=20*mm,topMargin=17*mm,bottomMargin=17*mm)
    content=[]
    def p(txt,style='ReportBody'):return Paragraph(txt,styles[style])
    def table(data,widths=None):
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1c4f62')),
          ('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
          ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#edf3f5')]),
          ('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
          ('FONTSIZE',(0,0),(-1,-1),8.5),('LINEBELOW',(0,0),(-1,0),.4,colors.white),
          ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9)]))
        return t
    m=annual.set_index(['target','method']);t=runtime
    tied=all(abs(float(m.loc[(s,'A_sum_then_forecast'),'rmse_kw'])-float(m.loc[(s,'B_forecast_then_sum'),'rmse_kw']))/max(float(m.loc[(s,'B_forecast_then_sum'),'rmse_kw']),1e-10)<.001 for s in SECTORS)
    content.append(p('EE499 Team 16 | Sum-first vs bus-first forecasting','ReportTitle'))
    content.append(p('<b>Purpose.</b> For each load sector, compare A (fit one model to summed bus kW history, predict 2021) against B (fit independently to each bus, predict 2021, then sum). All models use sector-specific winning configurations. Full-year forecast origin is January 1, 2021; the 2021 observations are reserved for scoring.','ReportBody'))
    content.append(p('<b>Dataset audit.</b> Full source: 43,921 contiguous hours (2017-06-01 through 2022-06-05). Training: 31,440 h (through 2020-12-31). Test: 8,760 h (2021). No timestamp gaps, missing p_kw or duplicate (timestamp, bus) rows. Bus 1 is a zero-load slack. Residential buses 2/5/10/13, commercial 3/8/9/12/14 and manufacturing 4/6/7/11/15 are exactly identical within each sector: three distinct nonzero profiles across 14 loaded buses.','ReportBody'))
    content.append(p('Full-year 2021 metrics (errors calculated <i>after</i> aggregation; bias = actual minus forecast):','ReportSub'))
    hdr=['Target','Method','MAE kW','RMSE kW','WAPE %','MASE 168h','Bias kW','sMAPE %']
    data=[hdr]
    for s in SECTORS:
        for method,label in [('A_sum_then_forecast','A'),('B_forecast_then_sum','B')]:
            r=m.loc[(s,method)]
            data.append([s.title(),label]+[f'{r[k]:.4f}' for k in ['mae_kw','rmse_kw','wape_pct','mase_weekly','bias_actual_minus_forecast_kw','smape_pct']])
    content.append(table(data,[87,47,92,93,90,93,91,95]));content.append(Spacer(1,10))
    content.append(p('Detailed monthly results and all 8,760 hourly predictions are provided in CSV. Weekly MASE denominators use the same lag-168 differences of each target\'s training-only sector sum for A and B.','ReportSmall'))
    content.append(PageBreak())
    content.append(p('Execution cost and numerical diagnostics','ReportTitle'))
    content.append(p('All 17 main fits were executed as fresh models: three sector totals for A and fourteen buses for B. Fits were sequential, with two estimator threads per boosting model. Calendar features were shared, but neither models nor predictions were cached. Three training-only tuning passes are separately timed.','ReportBody'))
    rows=[['Method','Fits','Fit sum (s)','Forecast sum (s)','Model total (s)','Outer wall (s)']]
    for name,pre,n in [('Sum first','approach_A',3),('Bus first','approach_B',14)]:
        rows.append([name,str(n),f'{t[pre+"_fit_seconds"]:.3f}',f'{t[pre+"_forecast_seconds"]:.3f}',
                     f'{t[pre+"_model_total_seconds"]:.3f}',f'{t[pre+"_wall_seconds"]:.3f}'])
    content.append(table(rows,[120,75,120,120,125,125]));content.append(Spacer(1,12))
    content.append(p(f'Training-only tuning: {t["tuning_seconds_not_in_A_B_wall"]:.3f} seconds, excluded from both main approach timing totals. Hardware and package versions are recorded in provenance_versions.json.','ReportBody'))
    rows=[['Sector','Mean |A - B| kW','Maximum |A - B| kW','Mean |A - n x representative B| kW']]
    for _,r in diagnostic.iterrows():
        rows.append([str(r.sector).title(),f'{r.mean_abs_A_minus_B_kw:.8f}',
                     f'{r.max_abs_A_minus_B_kw:.8f}',f'{r.mean_abs_A_minus_N_times_rep_B_kw:.8f}'])
    content.append(table(rows,[156,164,170,200]));content.append(Spacer(1,12))
    content.append(p('<b>Bus-level return.</b> Approach B produces individual bus forecasts directly. Approach A uses training-only equal shares (1/4 residential, 1/5 commercial and 1/5 manufacturing), justified by identical histories for this feeder. Every hour, allocated forecasts sum to their original sector totals. This sharing must not be used without checking future input cases.','ReportBody'))
    content.append(p('<b>Historical match.</b> The archived C2 explorer contains bus-level forecasts for comparison. Check archived_reproduction_check.csv for per-bus deviations; this is a matched rerun using the documented old model code, not a certified bitwise historical reproduction because the original selected parameters and binary package versions were not fully preserved.','ReportBody'))
    content.append(PageBreak())
    content.append(p('Recommendation and limitations','ReportTitle'))
    if tied:
        content.append(p('<b>Measured accuracy: effectively tied (&lt;0.1% relative RMSE difference in each sector).</b> For this specific feeder, prefer <b>Approach A (sum first)</b> when execution time is important: it requires three rather than fourteen fits, and equal-share allocation reconstructs usable bus-level kW forecasts without introducing a historical-share mismatch. Approach B remains valuable as the general implementation for independently varying buses or when spatial differences are important.','ReportBody'))
    else:
        content.append(p('Measured accuracy is not uniformly tied across sectors; compare full-year and monthly metrics, then weigh the measured improvement against eleven additional fits and the requirement for direct bus-level results. The recommendation is specific to this duplicated-profile feeder.','ReportBody'))
    content.append(p('<b>Scope limits.</b> The distributor normalized its input across 2017-06-01 to 2022-06-05, which includes 2021. Thus the downstream model fits are training-only, but the upstream network construction is not proven prospective. Historical interpolation near the 2020/2021 boundary was not independently verified. This experiment tests scale and execution on three perfectly duplicated profiles, not spatial variability, customer-specific load behavior or PV forecasts.','ReportBody'))
    content.append(p('<b>PV.</b> Retain XGBoost daily/weekly/monthly/yearly as the selected Bilbao modeled-PV configuration; no PV fit is performed here. Network pv_profile.csv is a zero placeholder. A common irradiance time series is an environmental input; electrical generation at each bus depends on that bus\'s installed PV capacity.','ReportBody'))
    content.append(p('<b>Reproduction.</b> Run RUN_WINDOWS.bat to retrain, or python forecast_bench.py --verify-only to verify the packaged metrics and 8,760-hour series. The interactive dashboard.html runs offline with no server or CDN. Separate PNGs present July 1–14, forecast differences, monthly means and distinct bus profiles.','ReportBody'))
    content.append(p('Project repository (read-only reference): https://github.com/Islahi/EE499-Team16.git','ReportSmall'))
    content.append(Spacer(1,8))
    img=BASE/'figures/variability_three_representative_buses.png'
    if img.exists():content.append(Image(str(img),width=167*mm,height=55*mm))
    def footer(canvas,document):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#657987'))
        canvas.drawString(20*mm,10*mm,'EE499 Team 16 | C2 15-bus sector aggregation | archived reference + measured rerun')
        canvas.drawRightString(277*mm,10*mm,f'Page {document.page}')
    doc.build(content,onFirstPage=footer,onLaterPages=footer)
