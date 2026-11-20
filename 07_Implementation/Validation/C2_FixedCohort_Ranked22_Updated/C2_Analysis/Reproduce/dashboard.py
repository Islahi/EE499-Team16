from numerical import *
import gzip,base64,hashlib
m={};blobs={}
for fp in sorted(C.glob('*.npy')):
 k=fp.stem;names=json.loads(fp.with_suffix('.json').read_text());arr=np.load(fp,mmap_mode='r');series={}
 for name,v in zip(names,arr):
  raw=np.asarray(v,dtype='<f8').tobytes();h=hashlib.sha256(raw).hexdigest()[:24]
  if h not in blobs:blobs[h]=base64.b64encode(gzip.compress(raw,compresslevel=5,mtime=0)).decode()
  series[name]=h
 z=pd.read_csv(dest(k)/'rankings.csv');cols=['rank','config','score','mae','rmse','wape_percent','mase_weekly','bias_actual_minus_forecast','smape_percent','model_seconds']
 m[k]=dict(unit=z.unit.iloc[0],rows=json.loads(z[cols].to_json(orient='values',double_precision=15)),series=series)
t=Path('scripts/dashboard.template.html').read_text().replace('CATALOG_JSON',json.dumps(m,separators=(',',':'))).replace('PAYLOAD_JSON',json.dumps(blobs,separators=(',',':')))
(O/'00_Overview/C2_Forecast_Explorer.html').write_text(t)
