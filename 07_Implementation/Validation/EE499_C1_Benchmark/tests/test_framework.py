"""Only small functional checks; never interpreted as benchmark measurements."""
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from benchmark_core import INPUTS,canonical,fbs_point,scenarios,get_op,ybus,scipy_nr,project_fbs,power_residual
from C1_Simple_Test.src_accelerated.network_loader import load_network

def network():return load_network(INPUTS/'Guide_5Bus_Radial_Test.xlsx',workbook_format='auto',frequency_hz=60)
def test_canonical_topology():
 n=network();c=canonical(n);assert len(c['lines'])==len(c['buses'])-1
 assert c['slack'] in c['buses']
def test_deterministic_scenarios():
 n=network();a=scenarios(n);assert a==scenarios(n);assert len(a)>=24
 assert get_op(n,a[0]).p_load_kw==fbs_point(n).p_load_kw

def test_five_bus_independent_ac_check():
 n=network();op=fbs_point(n);original=project_fbs(n,op,'fbs_python',{'max_iterations':100,'voltage_tolerance_pu':1e-9});independent=scipy_nr(n,op)
 assert original.converged and independent.converged
 assert max(abs(original.voltage[b]-independent.voltage[b]) for b in original.voltage)<1e-6
 assert power_residual(n,op,independent)[0]<1e-3

def test_nominal_generator_sign():
 n=network();op=fbs_point(n);sc=get_op(n,{'name':'discharge','load_scale':1,'pv_fraction':0,'bess_fraction':.1,'bus_index':0})
 assert sum(sc.p_bess_kw.values())>0
