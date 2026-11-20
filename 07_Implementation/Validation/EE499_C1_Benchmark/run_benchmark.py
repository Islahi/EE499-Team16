"""CLI: python run_benchmark.py check|quick|accuracy|speed|full|reports|failed --case T04 --solver fbs_python"""
import argparse,csv,json,os,sys,time,traceback,statistics,platform,importlib.metadata
from pathlib import Path
import numpy as np
from benchmark_core import *

def arguments():
 p=argparse.ArgumentParser(description='EE499 C1 power flow accuracy and speed comparison')
 p.add_argument('command',choices=['check','quick','accuracy','speed','full','failed','reports'])
 p.add_argument('--case',default='all',help='Case filename substring or all')
 p.add_argument('--solver',default='all',help='Solver or comma separated names')
 p.add_argument('--out',default='results')
 p.add_argument('--config',default='config.json')
 p.add_argument('--force',action='store_true')
 return p.parse_args()
def row_numeric(row,k):
 try:return float(row[k])
 except (ValueError,TypeError,KeyError):return None

def network_audit(n,name,point):
 c=canonical(n);data={'network':name,**c,'net_demand_kw':{str(i):list(v) for i,v in case_load(n,point).items()},'base_assumptions':['constant-PQ','balanced three-phase positive sequence','one slack','zero line shunt and charging','no transformer/tap/control model'],'source_workbook_sha256':fingerprint(INPUTS/(name+'.xlsx'))}
 return data

def published(n,name,sol,paper_rows,paper_lines):
 catalog={Path(x['workbook']).stem:x for x in readcsv(REFS/'workbook_to_paper_case_catalog.csv')};c=catalog.get(name,{});t=c.get('paper_table');tab=int(t) if t else None
 ref=paper_rows.get(tab);v={int(r['bus_to']):row_numeric(r,'v_pqsum_pu') for r in paper_lines.get(tab,[]) if r.get('bus_to')}
 cases= []
 for b,complexv in sorted(sol.voltage.items()):
  r={'network':name,'bus_id':b,'paper_voltage_pu':v.get(b),'computed_voltage_pu':abs(complexv),'error_pu':abs(abs(complexv)-v[b]) if v.get(b) is not None else None}
  cases.append(r)
 zbase=n.buses[0].base_kv**2/(n.base_power_kva/1000);rmap={frozenset((int(r['bus_from']),int(r['bus_to']))):r for r in paper_lines.get(tab,[])};mismatch=0
 if tab:
  for l in n.lines:
   br=rmap.get(frozenset((l.from_bus,l.to_bus)))
   if not br or abs(l.r_ohm/zbase-float(br['r_pu_reported']))>.0002 or abs(l.x_ohm/zbase-float(br['x_pu_reported']))>.0002:mismatch+=1
 out={'network':name,'reference_table':tab,'published_p_loss_kw':row_numeric(ref,'p_loss_kw') if ref else None,'computed_p_loss_kw':sol.loss_p,'published_vmin_pu':row_numeric(ref,'v_min_pu') if ref else None,'computed_vmin_pu':min(abs(v) for v in sol.voltage.values()),'max_paper_voltage_error_pu':max((r['error_pu'] for r in cases if r['error_pu'] is not None),default=None),'impedance_mismatch_count':mismatch if tab else None,'published_pages':ref.get('pdf_pages') if ref else None,'published_data_warning':'T18 published two-substation aggregate, workbook is one feeder only' if tab==18 else ('Mismatch with published impedance data' if mismatch else '')}
 return out,cases

def main():
 args=arguments();out=BASE/args.out;out.mkdir(parents=True,exist_ok=True)
 cfg=json.loads((BASE/args.config).read_text());cfg['benchmark_mode']='full' if args.command=='failed' else args.command
 candidates=SOLVERS if args.solver=='all' else [x.strip() for x in args.solver.split(',')]
 if set(candidates)-set(SOLVERS):raise ValueError('Unknown solvers '+str(set(candidates)-set(SOLVERS)))
 av=[{'solver':name,'status':availability(name)[0],'detail':availability(name)[1]} for name in candidates]
 writecsv(out/'solver_availability.csv',av)
 for r in av:print(f"{r['solver']:20s} {r['status']:20s} {r['detail']}")
 if args.command=='check':return
 if args.command=='reports':
  from reporting import generate_reports
  generate_reports(out);return
 paths=[p for p in sorted(INPUTS.glob('*.xlsx')) if args.case=='all' or args.case.lower() in p.stem.lower()]
 if args.command=='quick':paths=[p for p in paths if 'T04_15-Bus_System_1' in p.name] or paths[:1]
 if not paths:raise RuntimeError('No network files match '+args.case)
 source={'source':'bundled original C1 archive','source_sha256':fingerprint(SOURCE/'run_c1.py'),'git_repo':'https://github.com/Islahi/EE499-Team16.git','git_main_tree_at_preparation':'aaf17445f1a9c97f25f45188dd8053c65c177fb8','config_sha256':config_json(cfg),'config':cfg,'inputs':{p.name:fingerprint(p) for p in paths},'environment':machine_info(),'start_time':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'timing_platform':'THIS MACHINE ONLY; do not merge runtimes across machines'}
 for pkg in ['numba','pandapower','opendssdirect','matlab','scipy','numpy','pandas','matplotlib']:
  try:source['environment']['versions'][pkg]=importlib.metadata.version(pkg)
  except Exception:source['environment']['versions'][pkg]='not installed'
 (out/'manifest.json').write_text(json.dumps(source,indent=2,default=str))
 hresults={x['network']:x for x in readcsv(SOURCE/'C1_results/c1_summary.csv')};hvolts={(x['network'],int(x['bus_id'])):x for x in readcsv(SOURCE/'C1_results/c1_bus_voltages.csv')}
 paper_rows={int(x['table']):x for x in readcsv(REFS/'paper_case_references.csv')};paper_lines={}
 for x in readcsv(REFS/'paper_branch_references.csv'):paper_lines.setdefault(int(x['table']),[]).append(x)
 storage=out/'raw';storage.mkdir(exist_ok=True); failures=[];timings=[];summaries=[];voltages=[];references=[];refbus=[];scrows=[]
 for path in paths:
  name=path.stem;print('\nNETWORK',name,flush=True)
  try:n=load_network(path,workbook_format='auto',frequency_hz=cfg.get('frequency_hz',60.0));base=fbs_point(n)
  except Exception as e:
   failures.append(dict(network=name,solver='ALL',status='invalid input',error=str(e),traceback=traceback.format_exc()));continue
  (out/'input_audits').mkdir(exist_ok=True);(out/'input_audits'/f'{name}.json').write_text(json.dumps(network_audit(n,name,base),indent=2))
  ops=scenarios(n,cfg.get('scenario_hours',24),cfg.get('random_seed',42));writecsv(out/'operating_points'/f'{name}.csv',ops)
  for solver in candidates:
   status,detail=availability(solver);key=hashlib.sha256((source['config_sha256']+fingerprint(path)+solver+args.command).encode()).hexdigest()[:16];cache=storage/f'{name}__{solver}__{key}.json'
   if args.command=='failed' and cache.exists():
    previous=json.loads(cache.read_text());
    if previous.get('status')=='success':continue
   if cache.exists() and not args.force and args.command!='failed':
    print('  cached',solver);saved=json.loads(cache.read_text());summaries+=saved.get('summaries',[]);voltages+=saved.get('voltages',[]);references+=saved.get('published',[]);refbus+=saved.get('paper_buses',[]);timings+=saved.get('timings',[]);scrows+=saved.get('scenarios',[]);failures+=saved.get('failures',[]);continue
   result={'status':'success','summaries':[],'voltages':[],'published':[],'paper_buses':[],'timings':[],'scenarios':[],'failures':[]}
   if status!='available':result['status']=status;result['failures'].append(dict(network=name,solver=solver,status=status,error=detail));
   else:
    state=None
    try:
     cold0=time.perf_counter();state=prepare_solver(n,solver);first=solve(n,base,solver,state,cfg);cold=time.perf_counter()-cold0
     maxp,balp,balq=power_residual(n,base,first)
     hist=hresults.get(path.name,{})
     row={'network':name,'solver':solver,'bus_count':len(n.buses),'converged':first.converged,'iterations':first.iterations,'loss_p_kw':first.loss_p,'loss_q_kvar':first.loss_q,'slack_p_kw':first.slack_p,'slack_q_kvar':first.slack_q,'min_voltage_pu':min(abs(v) for v in first.voltage.values()),'weakest_bus':min(first.voltage,key=lambda b:abs(first.voltage[b])),'max_nodal_mismatch_kw_kvar':maxp,'feeder_balance_p_kw':balp,'feeder_balance_q_kvar':balq,'historical_c1_loss_p_kw':row_numeric(hist,'fbs_loss_p_kw'),'historical_c1_converged':hist.get('converged'),'historical_review_flag':hist.get('status'),'status':'success' if first.converged else 'nonconverged'}
     if first.converged and np.isfinite(maxp) and maxp>cfg['max_mismatch_kw_kvar']:row['status']='inaccurate'
     result['summaries'].append(row)
     result['timings'].append({'network':name,'solver':solver,'test':'cold_start','seconds':cold,'case':name,'status':row['status']})
     for b,v in first.voltage.items():
      old=hvolts.get((path.name,b),{});result['voltages'].append(dict(network=name,solver=solver,bus_id=b,v_pu=abs(v),angle_deg=np.rad2deg(np.angle(v)),historical_c1_v_pu=row_numeric(old,'fbs_voltage_pu')))
     if solver=='fbs_python':
      r,b=published(n,name,first,paper_rows,paper_lines);result['published'].append(r);result['paper_buses']+=b
     if args.command!='accuracy':
      raw=[];seconds=[];fail=0;warm_count=max(1,int(cfg['timing_repetitions'])) if args.command!='quick' else 1
      t_batch=time.perf_counter()
      for rep in range(warm_count):
       for j,sc in enumerate(ops):
        op=get_op(n,sc);t0=time.perf_counter()
        try:
         sol=solve(n,op,solver,state,cfg);elapsed=time.perf_counter()-t0
         mis,bp,bq=power_residual(n,op,sol);valid=sol.converged and mis<=cfg['max_mismatch_kw_kvar'] and np.isfinite(mis)
         if valid:seconds.append(elapsed)
         else:fail+=1
         raw.append({'network':name,'solver':solver,'scenario':sc['name'],'scenario_index':j,'repetition':rep,'latency_seconds':elapsed,'converged':sol.converged,'valid':valid,'mismatch_kw_kvar':mis,'loss_p_kw':sol.loss_p,'vmin_pu':min(abs(v) for v in sol.voltage.values())})
        except Exception as e:
         fail+=1;raw.append({'network':name,'solver':solver,'scenario':sc['name'],'repetition':rep,'valid':False,'error':str(e)})
      batch=time.perf_counter()-t_batch
      writecsv(out/'raw_timings'/f'{name}__{solver}.csv',raw)
      import statistics
      med=statistics.median(seconds) if seconds else None
      result['timings'].append({'network':name,'solver':solver,'test':'warm_repeated','median_s':med,'mean_s':statistics.mean(seconds) if seconds else None,'p95_s':float(np.percentile(seconds,95)) if seconds else None,'std_s':statistics.pstdev(seconds) if len(seconds)>1 else 0 if seconds else None,'batch_s':batch,'valid_solves':len(seconds),'failed_solves':fail,'throughput_solve_per_s':len(seconds)/batch if batch else None,'status':'success' if seconds else 'failed'})
      result['scenarios']+=raw[:len(ops)]
    except Exception as e:
     result['status']='execution failed';result['failures'].append(dict(network=name,solver=solver,status='execution failed',error=str(e),traceback=traceback.format_exc()));print('  FAILED',solver,e,flush=True)
    finally:
     if solver=='matpower_matlab' and state is not None:
      try:state.quit()
      except Exception:pass
   cache.write_text(json.dumps(result,indent=2,default=str));summaries+=result['summaries'];voltages+=result['voltages'];references+=result['published'];refbus+=result['paper_buses'];timings+=result['timings'];scrows+=result['scenarios'];failures+=result['failures']
   print(' ',solver,result['status'],flush=True)
  # Each case is done; flush to survive interruption.
  for f,rows in [('solver_summary.csv',summaries),('bus_voltages.csv',voltages),('published_comparison.csv',references),('published_bus_voltages.csv',refbus),('timing_summary.csv',timings),('scenario_results.csv',scrows),('failures.csv',failures)]:writecsv(out/f,rows)
 if args.command!='failed':
  from reporting import generate_reports
  generate_reports(out)
 print('Completed, results:',out)
if __name__=='__main__':main()
