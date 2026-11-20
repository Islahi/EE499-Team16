"""Regenerate all reports exclusively from local measured CSVs; no synthetic benchmark results."""
from pathlib import Path
from collections import defaultdict
from html import escape
import json, math, csv
import numpy as np
from benchmark_core import readcsv,writecsv,BASE,SOURCE,comparison

def f(x):
 try:return float(x)
 except (TypeError,ValueError):return None

def valid(x):return x is not None and np.isfinite(x)
def fmt(x,unit='',dec=5):return f'{x:.{dec}f}{unit}' if valid(x) else '—'

def build_cross(summaries,voltages):
 grouped=defaultdict(dict)
 for r in voltages:grouped[(r['network'],r['solver'])][int(r['bus_id'])]=(f(r['v_pu']),f(r['angle_deg']))
 summaries_by={(r['network'],r['solver']):r for r in summaries};ans=[]
 for (name,solver),arr in grouped.items():
  if solver=='fbs_python':continue
  baseline=grouped.get((name,'fbs_python'))
  if not baseline:continue
  overlap=sorted(set(arr)&set(baseline));ref=np.array([baseline[b][0] for b in overlap]);v=np.array([arr[b][0] for b in overlap]);angle=np.array([arr[b][1]-baseline[b][1] for b in overlap]);angle=(angle+180)%360-180
  if not len(overlap):continue
  j=int(np.argmax(abs(v-ref)));case=summaries_by.get((name,solver),{});base=summaries_by.get((name,'fbs_python'),{})
  ans.append({'network':name,'solver':solver,'max_voltage_difference_pu':float(np.max(abs(v-ref))),'rms_voltage_difference_pu':float(np.sqrt(np.mean((v-ref)**2))),'max_angle_difference_deg':float(np.max(abs(angle))),'worst_bus_id':overlap[j],'loss_p_difference_kw':f(case.get('loss_p_kw'))-f(base.get('loss_p_kw')) if f(case.get('loss_p_kw')) is not None and f(base.get('loss_p_kw')) is not None else None,'loss_q_difference_kvar':f(case.get('loss_q_kvar'))-f(base.get('loss_q_kvar')) if f(case.get('loss_q_kvar')) is not None and f(base.get('loss_q_kvar')) is not None else None})
 return ans

def rank_sol(summaries,timings,cross,limit_v=1e-6,limit_mis=1e-3):
 warmed={(r['network'],r['solver']):r for r in timings if r.get('test')=='warm_repeated'};refs={(r['network'],r['solver']):r for r in cross};rows=[]
 for r in summaries:
  n,s=r['network'],r['solver'];w=warmed.get((n,s),{});x=refs.get((n,s),{});mis=f(r.get('max_nodal_mismatch_kw_kvar'));voltage=f(x.get('max_voltage_difference_pu'))
  acceptable=(str(r.get('converged')).lower()=='true' and valid(mis) and mis<=limit_mis and (s=='fbs_python' or valid(voltage) and voltage<=limit_v) and (not w or int(f(w.get('failed_solves')) or 0)==0))
  row={'network':n,'solver':s,'accuracy_qualified':acceptable,'nodal_mismatch_kw_kvar':mis,'max_vdiff_pu':voltage,'median_warm_s':f(w.get('median_s')),'p95_warm_s':f(w.get('p95_s')),'throughput_solves_per_s':f(w.get('throughput_solve_per_s')),'loss_p_kw':f(r.get('loss_p_kw')),'coverage':'nominal only qualified' if acceptable else 'NOT QUALIFIED / REVIEW'}
  rows.append(row)
 base={(r['network']):r['median_warm_s'] for r in rows if r['solver']=='fbs_python'}
 for r in rows:
  b=base.get(r['network']);r['speedup_vs_original']=b/r['median_warm_s'] if valid(b) and valid(r['median_warm_s']) and r['median_warm_s']>0 else None
 rows.sort(key=lambda r:(r['network'],not r['accuracy_qualified'],r['median_warm_s'] if r['accuracy_qualified'] and valid(r['median_warm_s']) else float('inf')))
 current=None;rank=0
 for r in rows:
  if r['network']!=current:current=r['network'];rank=0
  if r['accuracy_qualified'] and valid(r['median_warm_s']):rank+=1;r['speed_rank']=rank
  else:r['speed_rank']=''
 return rows

def plot_results(out,summaries,timings,cross,rank,voltages):
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 folder=out/'figures';folder.mkdir(exist_ok=True)
 bysize=defaultdict(list)
 for r in rank:
  if r['accuracy_qualified'] and valid(r['median_warm_s']):
   bc=next((int(s['bus_count']) for s in summaries if s['network']==r['network']),None)
   if bc:bysize[r['solver']].append((bc,r['median_warm_s']))
 if bysize:
  plt.figure(figsize=(9,5))
  for solver,points in bysize.items():
   points.sort();plt.plot([a for a,b in points],[b*1000 for a,b in points],'.-',label=solver)
  plt.yscale('log');plt.xlabel('Bus count');plt.ylabel('Median warm solve (ms, logarithmic)');plt.title('Qualified solver speed versus feeder size');plt.grid(alpha=.25);plt.legend(fontsize=7);plt.tight_layout();plt.savefig(folder/'qualified_speed_vs_bus_count.png',dpi=160);plt.close()
 by=defaultdict(dict)
 for r in summaries:by[r['network']][r['solver']]=f(r.get('min_voltage_pu'))
 for name,solver_map in by.items():
  if len(solver_map)<1:continue
  ss=list(solver_map);vals=[solver_map[x] or 0 for x in ss]
  plt.figure(figsize=(9,4));plt.bar(ss,vals);plt.xticks(rotation=35,ha='right',fontsize=8);plt.ylabel('Minimum bus voltage (pu)');plt.title('Minimum voltage — '+name);plt.tight_layout();plt.savefig(folder/f'{name}_minimum_voltage.png',dpi=150);plt.close()
 for name in sorted({r['network'] for r in cross}):
  x=[r for r in cross if r['network']==name];labels=[r['solver'] for r in x];v=[f(r.get('max_voltage_difference_pu')) or 0 for r in x]
  if not x:continue
  plt.figure(figsize=(9,4));plt.bar(labels,v);plt.yscale('symlog',linthresh=1e-10);plt.xticks(rotation=35,ha='right',fontsize=8);plt.ylabel('Max |ΔV| (pu)');plt.title('Comparison to original FBS — '+name);plt.tight_layout();plt.savefig(folder/f'{name}_voltage_differences.png',dpi=150);plt.close()

 # Bus-voltage and angle profiles for every case; compare independent solvers on identical IDs.
 bus_groups=defaultdict(lambda:defaultdict(list))
 for r in voltages:
  if valid(f(r.get('v_pu'))):bus_groups[r['network']][r['solver']].append((int(r['bus_id']),f(r.get('v_pu')),f(r.get('angle_deg'))))
 for name,groups in bus_groups.items():
  if not groups:continue
  plt.figure(figsize=(10,5))
  for sol,points in groups.items():
   points.sort();plt.plot([p[0] for p in points],[p[1] for p in points],label=sol,lw=1.3)
  plt.title('Bus voltage profile — '+name);plt.xlabel('Bus ID');plt.ylabel('Voltage (pu)');plt.grid(alpha=.2);plt.legend(fontsize=7);plt.tight_layout();plt.savefig(folder/f'{name}_bus_voltage_profile.png',dpi=160);plt.close()
  original={p[0]:p for p in groups.get('fbs_python',[])}
  if not original:continue
  plt.figure(figsize=(10,5))
  for sol,points in groups.items():
   if sol=='fbs_python':continue
   arr=[(p[0],p[1]-original[p[0]][1]) for p in points if p[0] in original]
   if arr:plt.plot([p[0] for p in arr],[p[1] for p in arr],label=sol,lw=1.3)
  plt.title('Bus voltage deviations from original FBS — '+name);plt.xlabel('Bus ID');plt.ylabel('Δ|V| (pu)');plt.grid(alpha=.2);plt.legend(fontsize=7);plt.tight_layout();plt.savefig(folder/f'{name}_bus_voltage_errors.png',dpi=160);plt.close()
  plt.figure(figsize=(10,5))
  for sol,points in groups.items():
   if sol=='fbs_python':continue
   arr=[(p[0],((p[2]-original[p[0]][2]+180)%360)-180) for p in points if p[0] in original and valid(p[2])]
   if arr:plt.plot([p[0] for p in arr],[p[1] for p in arr],label=sol,lw=1.3)
  plt.title('Voltage-angle deviations from original FBS — '+name);plt.xlabel('Bus ID');plt.ylabel('Δ angle (degrees)');plt.grid(alpha=.2);plt.legend(fontsize=7);plt.tight_layout();plt.savefig(folder/f'{name}_bus_angle_errors.png',dpi=160);plt.close()
 # Active and reactive line losses, side by side by solver (separate PNG per physical quantity).
 for name in sorted({r['network'] for r in summaries}):
  data=[r for r in summaries if r['network']==name]
  for k,label,suffix in [('loss_p_kw','Active loss (kW)','active_losses'),('loss_q_kvar','Reactive loss (kvar)','reactive_losses')]:
   rows=[(r['solver'],f(r.get(k))) for r in data if valid(f(r.get(k)))]
   if not rows:continue
   plt.figure(figsize=(9,4));plt.bar([x[0] for x in rows],[x[1] for x in rows]);plt.xticks(rotation=35,ha='right',fontsize=8);plt.ylabel(label);plt.title(label+' — '+name);plt.tight_layout();plt.savefig(folder/f'{name}_{suffix}.png',dpi=150);plt.close()
 # Actual timing samples from the disk. No precomputed or invented latency.
 for name in sorted({r['network'] for r in timings}):
  distributions=[];labels=[]
  for path in sorted((out/'raw_timings').glob(name+'__*.csv')) if (out/'raw_timings').exists() else []:
   sample=readcsv(path);values=[f(r.get('latency_seconds'))*1000 for r in sample if r.get('valid')=='True' and valid(f(r.get('latency_seconds')))]
   if values:labels.append(path.stem.split('__')[-1]);distributions.append(values)
  if distributions:
   plt.figure(figsize=(9,4.5));plt.boxplot(distributions,showfliers=False);plt.yscale('log');plt.xticks(range(1,len(labels)+1),labels,rotation=35,ha='right',fontsize=8);plt.ylabel('Warm solve latency (ms, log)');plt.title('Timing distribution — '+name);plt.tight_layout();plt.savefig(folder/f'{name}_timing_distribution.png',dpi=150);plt.close()

def excel(out,tables):
 try:
  from artifact_tool import Workbook,SpreadsheetFile
 except ImportError:return 'artifact_tool not installed; CSV files are still available'
 wb=Workbook.create()
 for name,rows in tables.items():
  sh=wb.worksheets.add(name[:31]);sh.get_range('A1').values=[[name]]
  if rows:
   cols=list(dict.fromkeys(k for r in rows for k in r));cols=cols[:35];data=[cols]+[[str(r.get(k,'')) if isinstance(r.get(k),dict) else number_or_text(r.get(k)) for k in cols] for r in rows[:1000]]
   sh.get_range_by_indexes(1,0,len(data),len(cols)).values=data
   sh.get_range_by_indexes(1,0,1,len(cols)).format={'fill':'#15324F','font':{'bold':True,'color':'#FFFFFF'},'row_height':25}
   sh.freeze_panes.freeze_rows(2)
   for k in range(len(cols)):sh.get_range_by_indexes(1,k,min(len(data)+1,1002),1).format.column_width=19
   sh.get_range_by_indexes(0,0,1,min(5,len(cols))).format={'font':{'bold':True,'color':'#15324F'},'row_height':28}
 SpreadsheetFile.export_xlsx(wb).save(str(out/'C1_Results.xlsx'))
 return None

def number_or_text(x):
 if x is None:return ''
 if isinstance(x,(bool,int,float,str)):return x
 return str(x)

def pdf_value(v):
 if v is None:return '—'
 if isinstance(v,float):return f'{v:.7g}'
 return str(v)[:43]

def pdf(out,title,sections,file):
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
 from reportlab.lib.enums import TA_LEFT
 from reportlab.lib.units import cm
 styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='SubSmall',parent=styles['Normal'],fontSize=8,leading=12,spaceAfter=5));styles.add(ParagraphStyle(name='TableHead',parent=styles['SubSmall'],fontSize=8,leading=10,textColor=colors.white))
 document=SimpleDocTemplate(str(out/file),pagesize=(595,842),leftMargin=34,rightMargin=34,topMargin=38,bottomMargin=34)
 story=[Paragraph(escape(title),styles['Title']),Spacer(1,12)]
 for heading,body,rows in sections:
  story.append(Paragraph(escape(heading),styles['Heading2']));story.append(Paragraph(escape(body),styles['SubSmall']))
  if rows:
   cols=list(rows[0]);width=min(len(cols),7);cols=cols[:width]
   widths=[(595-68)/width]*width;data=[[Paragraph(escape(str(h).replace('_',' ')),styles['TableHead']) for h in cols]]
   for r in rows:data.append([Paragraph(escape(pdf_value(r.get(k))),styles['SubSmall']) for k in cols])
   table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT');table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#15324F')),('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F0F4F8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4)]));story.append(table)
  story.append(Spacer(1,12))
 document.build(story)

def dashboard(out,data):
 # Fully offline: embed all serialized rows; no CDN/javascript dependencies.
 s=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
 html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>EE499 C1 Benchmark</title><style>body{font:15px system-ui,sans-serif;background:#f3f6f9;color:#1b2b3d;margin:0}header{background:#132e49;color:white;padding:22px 4vw}main{padding:22px 4vw}select{padding:9px;margin-right:12px}table{width:100%;border-collapse:collapse;background:white;font-size:12px}th,td{padding:8px;text-align:left;border-bottom:1px solid #e1e6ed}th{position:sticky;top:0;background:#183d5d;color:white}.panel{background:white;padding:15px;margin:16px 0;border-radius:8px;overflow:auto}.bad{color:#b92828}.note{color:#546a7c}</style></head><body><header><h2>EE499 · C1 solver test bench</h2><p>Local measurements only · Balanced radial networks · Baseline: original FBS</p></header><main><label>Network <select id="network"></select></label><label>Solver <select id="solver"></select></label><label>View <select id="view"></select></label><div id="info" class="panel"></div><div class="panel" id="table"></div></main><script>const DB=DATA;const N=document.getElementById('network'),V=document.getElementById('view'),S=document.getElementById('solver');const names=[...new Set(DB.summary.map(r=>r.network))].sort();N.innerHTML='<option value="all">All networks</option>'+names.map(x=>`<option>${x}</option>`).join('');const sols=[...new Set(DB.summary.map(r=>r.solver))].sort();S.innerHTML='<option value="all">All solvers</option>'+sols.map(x=>`<option>${x}</option>`).join('');const tables=['summary','cross','timings','rank','published','failures'];V.innerHTML=tables.map(x=>`<option value="${x}">${x}</option>`).join('');function render(){const key=V.value;let rows=DB[key]||[];if(N.value!=='all')rows=rows.filter(r=>r.network===N.value);if(S.value!=='all')rows=rows.filter(r=>r.solver===S.value);document.getElementById('info').textContent=`${rows.length} records in ${key} · ${N.value} · no external connections`;if(!rows.length){document.getElementById('table').textContent='No rows available for this selection.';return}let cols=[...new Set(rows.flatMap(x=>Object.keys(x)))];let html='<table><thead><tr>'+cols.map(x=>`<th>${x}</th>`).join('')+'</tr></thead><tbody>';const safe=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));for(let r of rows)html+='<tr>'+cols.map(x=>`<td>${safe(r[x])}</td>`).join('')+'</tr>';document.getElementById('table').innerHTML=html+'</tbody></table>'}N.onchange=V.onchange=S.onchange=render;render();</script></body></html>'''.replace('DATA',s)
 (out/'dashboard.html').write_text(html,encoding='utf-8')

def generate_reports(out):
 out=Path(out)
 def load(n):return readcsv(out/n) if (out/n).exists() else []
 summaries=load('solver_summary.csv');voltages=load('bus_voltages.csv');timings=load('timing_summary.csv');references=load('published_comparison.csv');failure=load('failures.csv')
 cross=build_cross(summaries,voltages);writecsv(out/'cross_solver_accuracy.csv',cross)
 config=json.loads((BASE/'config.json').read_text());ranking=rank_sol(summaries,timings,cross,config['max_voltage_difference_pu'],config['max_mismatch_kw_kvar']);writecsv(out/'solver_rankings.csv',ranking)
 dashboard(out,dict(summary=summaries,cross=cross,timings=timings,rank=ranking,published=references,failures=failure))
 plot_results(out,summaries,timings,cross,ranking,voltages)
 tables={'Inventory':list({r['network']:dict(network=r['network'],bus_count=r['bus_count']) for r in summaries}.values()),'Availability':load('solver_availability.csv'),'Nominal accuracy':summaries,'Published reference':references,'Bus voltages':voltages[:750],'Cross solver':cross,'Cold warm timing':timings,'Qualified ranking':ranking,'Failures':failure}
 err=excel(out,tables)
 status=f'{len(summaries)} measured nominal solver/case combinations; {len(ranking)} ranked rows; {len(failure)} missing/failed combinations.'
 caveat='Numerical qualification is based on nodal mismatch and agreement with original FBS; review published reference discrepancies before treating FBS as physically correct. All comparisons require identical network assumptions. Repeated timing is valid only on the machine that executed the benchmark.'
 pdf(out,'EE499 Team 16 — C1 Power-Flow Technical Report',[('Executive summary',status,[]),('Evaluation rules',caveat,[]),('Nominal accuracy','Computed voltage/loss, convergence and independent nodal mismatch.',[{k:r.get(k) for k in ('network','solver','converged','loss_p_kw','max_nodal_mismatch_kw_kvar')} for r in summaries[:30]]),('Published reference audit','The original paper is a benchmark, not authoritative if workbook impedances differ. Two feeder roots T18 require separate handling.',[{k:r.get(k) for k in ('network','published_p_loss_kw','computed_p_loss_kw','impedance_mismatch_count')} for r in references[:18]]),('Speed qualification','Only qualified converged measurements may be ranked.',[{k:r.get(k) for k in ('network','solver','accuracy_qualified','median_warm_s','speedup_vs_original')} for r in ranking[:40]]),('Limitations and implementation','Use a solver only after reviewing electrical equivalence, runtime overhead, stress reliability, and production integration. MATPOWER and OpenDSS are optional; missing dependencies are not scored as failures. GPU and VeraGrid are not implemented in this package.',[])],'C1_Technical_Report.pdf')
 pdf(out,'EE499 Team 16 — C1 Complete Solver Ranking',[('Rules','Rank numerically qualified solvers separately per network by median warm latency. Accuracy thresholds: maximum voltage difference 1e-6 pu; max nodal mismatch 1e-3 kW/kvar. Benchmark data generated on user machine.',[]),('Qualified and unqualified ranking',status,[{k:r.get(k) for k in ('network','solver','accuracy_qualified','median_warm_s','speedup_vs_original','speed_rank')} for r in ranking]),('Incomplete or failed cases','Missing dependencies and failures remain visible; they are never assigned artificial latency.',[{k:r.get(k) for k in ('network','solver','status','error')} for r in failure[:65]])],'C1_Complete_Rankings.pdf')
 if err:(out/'report_warnings.txt').write_text(err)
 print('Generated local reports and dashboard in',out)
