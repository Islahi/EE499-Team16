"""One isolated fit/predict process to protect the benchmark from model OOM errors."""
import json
import sys
import time
import traceback
import warnings
from pathlib import Path
import numpy as np

import c2_benchmark_settings as S
from c2_benchmark_core import make_model, predict_model, seasonal_naive_numpy

def main():
    spec=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    y=np.load(spec['training_file'])
    target=Path(spec['output_file']); target.parent.mkdir(parents=True,exist_ok=True)
    result=Path(spec['status_file'])
    warnings_seen=[]
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('once')
            if spec['model']=='SeasonalNaive':
                t=time.perf_counter()
                fc=seasonal_naive_numpy(y,spec['periods'][0],spec['forecast_hours'])
                fit=0.;predict=time.perf_counter()-t
            else:
                model=make_model(spec['model'],spec['periods'],len(y))
                fc,fit,predict=predict_model(model,y,spec['forecast_hours'])
            for warn in caught:
                if len(warnings_seen)<25:
                    warnings_seen.append(f'{warn.category.__name__}: {str(warn.message)}')
        if not np.all(np.isfinite(fc)):
            raise ValueError('Model output is nonfinite')
        np.save(target,fc)
        state={'status':'OK','fit_seconds':fit,'forecast_seconds':predict,
               'warning_count':len(caught),'warning_examples':warnings_seen}
    except BaseException as e:
        state={'status':'FAILED','reason':f'{type(e).__name__}: {e}',
               'traceback':traceback.format_exc(limit=12),'warning_examples':warnings_seen}
    result.write_text(json.dumps(state,indent=2),encoding='utf-8')
    if state['status']!='OK':sys.exit(1)

if __name__=='__main__':main()
