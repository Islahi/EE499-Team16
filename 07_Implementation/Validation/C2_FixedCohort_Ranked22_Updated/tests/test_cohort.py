"""Small fully synthetic archive tests. Run: python tests/test_cohort.py"""
from pathlib import Path
import io,tarfile,zipfile,tempfile,importlib.util,argparse,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cleaner',ROOT/'01_build_common_cohort.py')
cleaner=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleaner)

def test():
  with tempfile.TemporaryDirectory() as t:
    root=Path(t)
    users={'residential':['aaaa','aaab'],'commercial':['bbbb'],'manufacturing':['cccc']}
    co=[{'user':u,'sector':s,'classification_basis':'cnae_class'} for s,ids in users.items() for u in ids]
    with zipfile.ZipFile(root/'Cleaned.zip','w') as z:
      for p in ['Pre','During','Post']:
        z.writestr(f'Cleaned/{p}/customer_quality_manifest.csv',pd.DataFrame(co).to_csv(index=False))
    for p,base in [('Pre','2020-01-01 00:00'),('During','2020-01-01 03:00'),('Post','2020-01-01 06:00')]:
      with tarfile.open(root/f'{p}.tar','w') as tar:
        for i,c in enumerate(co):
          if p=='Pre': period=pd.date_range(base,periods=4,freq='h')
          elif p=='During':period=pd.date_range(base,periods=4,freq='h')
          else:period=pd.date_range(base,periods=4,freq='h')
          # aaab missing hour 1, to interpolate
          if c['user']=='aaab' and p=='Pre': period=period.delete(1)
          values=np.repeat({'Pre':1,'During':3,'Post':5}[p]+i,len(period))
          b=pd.DataFrame({'timestamp':period,'kWh':values}).to_csv(index=False).encode()
          info=tarfile.TarInfo(name=c['user']+'.csv');info.size=len(b)
          tar.addfile(info,io.BytesIO(b))
    args=argparse.Namespace(manifests_zip=root/'Cleaned.zip',pre=root/'Pre.tar',during=root/'During.tar',post=root/'Post.tar',out=root/'out',work_dir=None,start='2020-01-01 00:00',end='2020-01-01 09:00',max_gap_hours=168,keep_cache=False)
    report=cleaner.run(args)
    assert report['selected_customers']==4
    d=pd.read_csv(args.out/'residential.csv')
    assert len(d)==10
    assert d.loc[1,'interpolated_customer_hours']==1
    # hour 3 new (During) replaces Pre, even though same customer appears in both
    assert abs(d.loc[3,'average_customer_kw']-3.5)<1e-5
    # hour 6 newest Post replaces During
    assert abs(d.loc[6,'average_customer_kw']-5.5)<1e-5
    assert np.allclose(d['active_customers'],2)
    w=pd.read_csv(args.out/'goiener_distributor_ready.csv')
    assert len(w)==10
    assert not list(args.out.glob('goiener_cohort_*'))
    print('PASS: intersection, interpolation, archive overlap priority, total coverage, cache cleanup')

if __name__=='__main__':test()
