"""EE499 C1 benchmark: canonical balanced constant-power radial feeder comparison.
No solver is treated as ground truth. All results generated on execution.
"""
from __future__ import annotations
import csv, json, math, os, platform, sys, time, hashlib, traceback, importlib.util
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict
import numpy as np
from scipy.optimize import root
from C1_Simple_Test.src_accelerated.network_loader import load_network
from C1_Simple_Test.src_accelerated.fbs import OperatingPoint,FBSConfig,run_fbs,backend_available

BASE=Path(__file__).resolve().parent
SOURCE=BASE/'C1_Simple_Test'; INPUTS=SOURCE/'Working_RDS'; REFS=SOURCE/'references'
SOLVERS=['fbs_python','fbs_numpy','fbs_numba','scipy_nr','pandapower_bfsw','pandapower_nr','opendss','matpower_matlab']

def readcsv(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(path, rows, cols=None):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if not cols: cols=list(dict.fromkeys(k for r in rows for k in r)) if rows else ['status']
 with open(path,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
def fingerprint(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def config_json(config):return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
def fbs_point(n):
 ids=[b.bus_id for b in n.buses];p={i:0.0 for i in ids};q=p.copy();z=p.copy()
 for ld in n.loads:p[ld.bus_id]+=ld.p_base_kw;q[ld.bus_id]+=ld.q_base_kvar
 return OperatingPoint(p,q,z.copy(),z.copy(),z.copy(),z.copy())
def case_load(n,point):
 return {i:(point.p_load_kw[i]-point.p_pv_kw[i]-point.p_bess_kw[i],point.q_load_kvar[i]-point.q_pv_kvar[i]-point.q_bess_kvar[i]) for i in point.p_load_kw}
def get_op(n,scenario):
 op=fbs_point(n); ids=sorted(op.p_load_kw);slack=n.slack_bus_id();nons=[i for i in ids if i!=slack]
 sc=scenario.copy();lp=float(sc.get('load_scale',1));op.p_load_kw={i:p*lp for i,p in op.p_load_kw.items()};op.q_load_kvar={i:q*lp for i,q in op.q_load_kvar.items()}
 largest=max(nons,key=lambda i:op.p_load_kw[i]);target=nons[int(sc.get('bus_index',0))%len(nons)]
 pv=float(sc.get('pv_fraction',0))*sum(op.p_load_kw.values()); bess=float(sc.get('bess_fraction',0))*sum(op.p_load_kw.values())
 # Explicit injections: BESS positive = discharging, negative = charging.
 op.p_pv_kw[target]=pv;op.p_bess_kw[largest]=bess
 return op

def scenarios(n, count=24, seed=42):
 # Stable deterministic sequence containing identical, small/large and reverse-power variations.
 names=['nominal','nominal_repeat','light','heavy','solar_day','high_pv','bess_charge','bess_discharge','reverse_flow','low_voltage_stress']
 sets=[(1,0,0),(1,0,0),(.6,0,0),(1.4,0,0),(1,.4,0),(.8,.9,0),(1,0,-.3),(1,0,.3),(.5,1.35,.3),(1.7,0,-.3)]
 result=[]
 for i in range(count):
  if i<len(sets):scale,pv,bess=sets[i];name=names[i]
  else:
   h=i%24;scale=.8+.35*math.sin(2*math.pi*(h-7)/24)**2;pv=.7*max(0,math.sin(math.pi*(h-6)/12));bess=.18*math.sin(2*math.pi*(h-12)/24);name=f'hour_{i:03d}'
  result.append(dict(name=name,load_scale=scale,pv_fraction=pv,bess_fraction=bess,bus_index=(i*7+seed)%max(1,len(n.buses)-1)))
 return result

def availability(name):
 mods={'fbs_numba':'numba','scipy_nr':'scipy','pandapower_bfsw':'pandapower','pandapower_nr':'pandapower','opendss':'opendssdirect','matpower_matlab':'matlab.engine'}
 if name in ('fbs_python','fbs_numpy'):return 'available','bundled C1 solver'
 if name=='matpower_matlab':
  try:
   import matlab.engine
   return 'available','MATLAB engine import available; MATPOWER path still required'
  except Exception:return 'missing dependency','MATLAB Engine for Python (and MATPOWER) not installed'
 mod=mods.get(name)
 try:ok=importlib.util.find_spec(mod) is not None
 except (ImportError,ModuleNotFoundError):ok=False
 return ('available','dependency found') if ok else ('missing dependency',f'Install {mod}')

@dataclass
class Solution:
 voltage:dict
 loss_p:float
 loss_q:float
 slack_p:float
 slack_q:float
 converged:bool
 iterations:int|None
 solver:str
 branch_current:dict|None=None
 branch_p:dict|None=None
 message:str=''

def canonical(n):
 n.validate();ids=sorted(b.bus_id for b in n.buses);slack=n.slack_bus_id();kv=next(b.base_kv for b in n.buses if b.bus_id==slack);sb=n.base_power_kva
 return {'buses':ids,'slack':slack,'kv_ll':kv,'base_kva':sb,'v_set_pu':next(b.v_set_pu for b in n.buses if b.bus_id==slack),'lines':[{'id':l.line_id,'from':l.from_bus,'to':l.to_bus,'r_ohm':l.r_ohm,'x_ohm':l.x_ohm} for l in n.lines], 'model':'balanced three-phase total kW/kvar, wye-equivalent positive sequence; constant PQ; no shunts, transformers, tap changers, or line charging'}

def ybus(n):
 c=canonical(n);ids=c['buses'];ind={i:j for j,i in enumerate(ids)};zbase=c['kv_ll']**2/(c['base_kva']/1000)
 y=np.zeros((len(ids),len(ids)),complex)
 for line in n.lines:
  a,b=ind[line.from_bus],ind[line.to_bus];z=complex(line.r_ohm,line.x_ohm)/zbase
  if abs(z)<1e-14:raise ValueError('Zero-impedance line not suitable for independent NR')
  adm=1/z;y[a,a]+=adm;y[b,b]+=adm;y[a,b]-=adm;y[b,a]-=adm
 return y,ids,ind

def power_residual(n,op,sol):
 if not sol.voltage:return float('nan'),float('nan'),float('nan')
 y,ids,ind=ybus(n)
 if set(sol.voltage)!=set(ids):return float('nan'),float('nan'),float('nan')
 v=np.array([sol.voltage[i] for i in ids]);s=v*np.conj(y@v)*n.base_power_kva
 net=case_load(n,op);k=[ind[i] for i in ids if i!=n.slack_bus_id()]
 errs=np.array([s[ind[i]]+complex(*net[i]) for i in ids if i!=n.slack_bus_id()]);balance=(sol.slack_p+1j*sol.slack_q)-(sum(complex(*net[i]) for i in ids)+sol.loss_p+1j*sol.loss_q)
 return float(max(abs(errs.real).max(initial=0),abs(errs.imag).max(initial=0))),float(abs(balance.real)),float(abs(balance.imag))

def scipy_nr(n,op,init='flat',tol=1e-9):
    """Independent damped Newton–Raphson AC solver, exact rectangular Jacobian.

    All residuals are per-unit complex nodal power imbalance; slack voltage is
    fixed. Uses SciPy dense linear solve for the explicitly assembled Jacobian.
    """
    from scipy.linalg import solve as linear_solve
    y,ids,ind=ybus(n)
    c=canonical(n);slack=ind[c['slack']]
    others=np.array([j for j in range(len(ids)) if j!=slack],dtype=int)
    net=case_load(n,op);sb=n.base_power_kva
    demand=np.array([complex(*net[i])/sb for i in ids])
    v=np.full(len(ids),complex(c['v_set_pu']))
    converged=False;iterations=0;reason='iteration limit'
    for iteration in range(1,101):
        cur=y@v
        mismatch=v*np.conj(cur)+demand
        err=np.r_[mismatch[others].real,mismatch[others].imag]
        maxerr=float(np.max(np.abs(err)))
        if maxerr<=tol:
            converged=True;reason='converged';iterations=iteration-1;break
        # dS_i/d(Re V_k) = δ_ik conj(I_i) + V_i conj(Y_ik)
        # dS_i/d(Im V_k) = j δ_ik conj(I_i) - j V_i conj(Y_ik)
        a=v[others,None]*np.conj(y[np.ix_(others,others)])
        diagonal=np.diag(np.conj(cur[others]))
        derivative_real=a+diagonal
        derivative_imag=1j*(diagonal-a)
        jac=np.block([[derivative_real.real,derivative_imag.real],
                      [derivative_real.imag,derivative_imag.imag]])
        try:step=linear_solve(jac,err,assume_a='gen',check_finite=False)
        except Exception as exc:
            reason=f'singular Jacobian: {exc}';iterations=iteration;break
        # Damping guards stressed radial cases without modifying the equations.
        rate=1.0;old=np.max(abs(err));accepted=False
        while rate>=1/128:
            trial=v.copy()
            trial[others]-=rate*(step[:len(others)]+1j*step[len(others):])
            if np.min(np.abs(trial))>1e-6:
                residual=trial*np.conj(y@trial)+demand
                r=np.r_[residual[others].real,residual[others].imag]
                if np.all(np.isfinite(r)) and np.max(abs(r))<old:
                    v=trial;accepted=True;break
            rate*=0.5
        iterations=iteration
        if not accepted:
            reason='damped NR stalled';break
    else:
        mismatch=v*np.conj(y@v)+demand
        converged=float(max(np.max(abs(mismatch[others].real)),np.max(abs(mismatch[others].imag))))<=tol
        reason='converged' if converged else 'iteration limit'
    injection=v*np.conj(y@v)
    loss=injection.sum()*sb
    slack_power=injection[slack]*sb+complex(*net[c['slack']])
    return Solution(dict(zip(ids,v)),float(loss.real),float(loss.imag),float(slack_power.real),float(slack_power.imag),converged,iterations,'scipy_nr',message=reason)

def project_fbs(n,op,solver,cfg):
 backend=solver.partition('_')[2];r=run_fbs(n,op,FBSConfig(backend=backend,max_iterations=cfg['max_iterations'],voltage_tolerance_pu=cfg['voltage_tolerance_pu']))
 return Solution(r.voltage_complex_pu,r.total_loss_p_kw,r.total_loss_q_kvar,r.slack_p_kw,r.slack_q_kvar,r.converged,r.iterations,solver,r.branch_current_a,r.branch_p_kw,r.message)

def pandapower_prepare(n):
 import pandapower as pp
 c=canonical(n);net=pp.create_empty_network(sn_mva=c['base_kva']/1000,f_hz=n.frequency_hz);busidx={}
 for b in n.buses:busidx[b.bus_id]=pp.create_bus(net,vn_kv=b.base_kv,name=str(b.bus_id))
 pp.create_ext_grid(net,busidx[c['slack']],vm_pu=c['v_set_pu'])
 for l in n.lines:
  pp.create_line_from_parameters(net,busidx[l.from_bus],busidx[l.to_bus],length_km=1,r_ohm_per_km=l.r_ohm,x_ohm_per_km=l.x_ohm,c_nf_per_km=0,max_i_ka=max(.001,(l.ampacity_a or 1e9)/1000),name=l.line_id,g_us_per_km=0)
 loads={}
 for b in n.buses:loads[b.bus_id]=pp.create_load(net,busidx[b.bus_id],p_mw=0,q_mvar=0,const_z_percent=0,const_i_percent=0)
 return (net,busidx,loads)

def pandapower_solve(n,op,solver,state,cfg):
 import pandapower as pp
 net,idx,loadidx=state
 net.load.loc[list(loadidx.values()),'p_mw']=[case_load(n,op)[i][0]/1000 for i in loadidx]
 net.load.loc[list(loadidx.values()),'q_mvar']=[case_load(n,op)[i][1]/1000 for i in loadidx]
 algo='nr' if solver.endswith('_nr') else 'bfsw'
 try:pp.runpp(net,algorithm=algo,init='flat',max_iteration=cfg['max_iterations'],tolerance_mva=cfg['voltage_tolerance_pu']*n.base_power_kva/1000,calculate_voltage_angles=True,voltage_depend_loads=False,numba=False,check_connectivity=False)
 except Exception as e:raise RuntimeError(f'pandapower runpp: {e}') from e
 v={i:float(net.res_bus.at[j,'vm_pu'])*np.exp(1j*np.deg2rad(float(net.res_bus.at[j,'va_degree']))) for i,j in idx.items()}
 return Solution(v,float(net.res_line.pl_mw.sum()*1000),float(net.res_line.ql_mvar.sum()*1000),float(net.res_ext_grid.p_mw.sum()*1000),float(net.res_ext_grid.q_mvar.sum()*1000),bool(net.converged),None,solver)

def dss_prepare(n):
 import opendssdirect as dss
 # Global DSS engine must not be used concurrently with another DSS study.
 dss.Basic.ClearAll();c=canonical(n);kv=c['kv_ll'];slack=c['slack']
 dss.Text.Command(f'New Circuit.C1 phases=3 bus1=b{slack} basekv={kv:.12g} pu={c["v_set_pu"]:.12g} angle=0 frequency={n.frequency_hz:.12g}')
 for j,l in enumerate(n.lines):
  dss.Text.Command(f'New Line.L{j} bus1=b{l.from_bus}.1.2.3 bus2=b{l.to_bus}.1.2.3 phases=3 r1={l.r_ohm:.15g} x1={l.x_ohm:.15g} r0={l.r_ohm:.15g} x0={l.x_ohm:.15g} c1=0 c0=0 length=1 units=km')
 for b in n.buses:
  if b.is_slack:continue
  dss.Text.Command(f'New Load.B{b.bus_id} phases=3 bus1=b{b.bus_id}.1.2.3 conn=wye kv={kv:.12g} kW=0 kvar=0 model=1')
 dss.Text.Command(f'Set VoltageBases=[{kv:.12g}]');dss.Text.Command('CalcVoltageBases')
 # The benchmark has no regulator or switching controls. Do not force
 # maxcontroliter=1; some DSS releases then raise warning #485.
 dss.Text.Command('Set controlmode=off')
 return dss

def dss_solve(n,op,dss,cfg):
 net=case_load(n,op);slack=n.slack_bus_id()
 for bus,(p,q) in net.items():
  if bus==slack:continue
  dss.Loads.Name(f'B{bus}');dss.Loads.kW(float(p));dss.Loads.kvar(float(q))
 dss.Solution.MaxIterations(cfg['max_iterations']);dss.Solution.Convergence(cfg['voltage_tolerance_pu'])
 # Steady-state AC power flow only: bypass device control iterations.
 dss.Solution.SolveNoControl()
 voltage={}
 for b in n.buses:
  dss.Circuit.SetActiveBus('b'+str(b.bus_id));angles=dss.Bus.puVmagAngle();mags=angles[0::2];degs=angles[1::2]
  if not mags:raise RuntimeError('Missing OpenDSS bus '+str(b.bus_id))
  # Positive-sequence equivalent angle from first phase. Slack reference is aligned later.
  voltage[b.bus_id]=float(mags[0])*np.exp(1j*np.deg2rad(float(degs[0])))
 loss=dss.Circuit.Losses();total=dss.Circuit.TotalPower() # TotalPower is signed power absorbed from source
 return Solution(voltage,float(loss[0])/1000,float(loss[1])/1000,-float(total[0]),-float(total[1]),bool(dss.Solution.Converged()),int(dss.Solution.Iterations()),'opendss',message='Balanced 3-phase, sequence equivalent; check DSS line and load warnings')

def matlab_prepare(n):
 import matlab.engine
 eng=matlab.engine.start_matlab();count=float(eng.exist('runpf','file',nargout=1))
 if count==0:
  eng.quit();raise RuntimeError('MATPOWER runpf not on MATLAB path; addpath(genpath(MATPOWER_ROOT))')
 return eng

def matlab_solve(n,op,eng,cfg):
 # MATLAB engine accepts flattened MATPOWER case via doubles, preserving actual bus IDs.
 import matlab
 c=canonical(n);ids=c['buses'];slack=c['slack'];net=case_load(n,op);kv=c['kv_ll'];sb=c['base_kva']/1000
 bus=[]
 for i in ids:
  p,q=net[i];bus.append([i,3 if i==slack else 1,p/1000,q/1000,0,0,1,c['v_set_pu'],0,kv,1,1.1,.9])
 gen=[[slack,0,0,999999,-999999,c['v_set_pu'],sb,1,999999,0]]
 branch=[]
 for l in n.lines:
  branch.append([l.from_bus,l.to_bus,l.r_ohm/(kv*kv/sb),l.x_ohm/(kv*kv/sb),0,9999,9999,9999,0,0,1,-360,360])
 # Simpler, explicit engine memory isolation: run via mpc built from MATLAB arrays.
 eng.workspace['c1_bus']=matlab.double(bus);eng.workspace['c1_gen']=matlab.double(gen);eng.workspace['c1_branch']=matlab.double(branch);eng.workspace['c1_base']=float(sb)
 eng.eval("c1mpc=struct('version','2','baseMVA',c1_base,'bus',c1_bus,'gen',c1_gen,'branch',c1_branch);",nargout=0)
 eng.eval("c1res=runpf(c1mpc,mpoption('verbose',0,'out.all',0,'pf.alg','NR'));",nargout=0)
 converged=bool(eng.eval('c1res.success',nargout=1));vr=eng.eval('c1res.bus(:,[1 8 9])',nargout=1)
 vals={int(row[0]):float(row[1])*np.exp(1j*np.deg2rad(float(row[2]))) for row in vr}
 line=eng.eval('c1res.branch(:,[14 15 16 17])',nargout=1);loss=sum(float(row[0])+float(row[2]) for row in line)*1000;lossq=sum(float(row[1])+float(row[3]) for row in line)*1000
 source=eng.eval('c1res.gen(:,[2 3])',nargout=1)
 return Solution(vals,loss,lossq,float(source[0][0])*1000,float(source[0][1])*1000,converged,None,'matpower_matlab')

def prepare_solver(n,solver):
 if solver.startswith('pandapower'):return pandapower_prepare(n)
 if solver=='opendss':return dss_prepare(n)
 if solver=='matpower_matlab':return matlab_prepare(n)
 return None

def solve(n,op,solver,state,cfg):
 if solver.startswith('fbs_'):return project_fbs(n,op,solver,cfg)
 if solver=='scipy_nr':return scipy_nr(n,op,tol=cfg['voltage_tolerance_pu']*.1)
 if solver.startswith('pandapower'):return pandapower_solve(n,op,solver,state,cfg)
 if solver=='opendss':return dss_solve(n,op,state,cfg)
 if solver=='matpower_matlab':return matlab_solve(n,op,state,cfg)
 raise ValueError(solver)

def comparison(reference, candidate, slack):
 if not reference or not candidate:return {}
 keys=sorted(set(reference.voltage)&set(candidate.voltage));ref=np.array([reference.voltage[i] for i in keys]);actual=np.array([candidate.voltage[i] for i in keys]);
 # Align global reference phase (especially OpenDSS phase-A coordinate system).
 if abs(actual[keys.index(slack)])>0:
  rot=np.angle(ref[keys.index(slack)])-np.angle(actual[keys.index(slack)]);actual*=np.exp(1j*rot)
 delta=np.abs(np.abs(actual)-np.abs(ref));angle=np.rad2deg(np.angle(actual/ref));angle=(angle+180)%360-180
 m=int(np.argmax(delta));return {'max_voltage_error_pu':float(delta[m]),'rms_voltage_error_pu':float(np.sqrt(np.mean(delta**2))),'max_angle_error_deg':float(np.max(np.abs(angle))),'worst_bus':keys[m],'loss_p_difference_kw':float(candidate.loss_p-reference.loss_p),'loss_q_difference_kvar':float(candidate.loss_q-reference.loss_q),'slack_p_difference_kw':float(candidate.slack_p-reference.slack_p)}

def machine_info():
 import scipy
 return {'platform':platform.platform(),'python':sys.version,'cpu':platform.processor(),'logical_cpus':os.cpu_count(),'numpy':np.__version__,'scipy':scipy.__version__,'versions':{}}
