from pathlib import Path
import io
import json
import sys
import tarfile
import tempfile
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from goiener_prepare import classify_cnae, clean_customer, classification, prepare


def test_classification():
    assert classify_cnae('4711') == 'commercial'
    assert classify_cnae('1041') == 'manufacturing'
    assert classify_cnae('9700') == 'residential'
    assert classify_cnae('99') is None
    df = pd.DataFrame({'user': ['a','b','c','d'], 'cnae': ['9700','4711','1041', pd.NA],
                       'contracted_tariff':['2.0','3.0','3.0','2.0']})
    result = classification(df, residential_tariff_proxy=False)
    assert result['sector'].tolist()[:3] == ['residential','commercial','manufacturing']
    assert pd.isna(result['sector'].iloc[3])
    result2 = classification(df, residential_tariff_proxy=True)
    assert result2['sector'].iloc[3] == 'residential'
    assert result2['classification_basis'].iloc[3].startswith('UNVERIFIED')


def make_archive(root: Path):
    start = pd.Timestamp('2017-01-01 00:00:00')
    dates = pd.date_range(start, periods=72, freq='h')
    ids = {'residential': 'a'*64, 'commercial': 'b'*64,
           'manufacturing': 'c'*64, 'unclassified': 'd'*64}
    cnae = {'residential':'9700','commercial':'4711','manufacturing':'1041','unclassified':''}
    meta = pd.DataFrame({'user':list(ids.values()), 'cnae':list(cnae.values()),
                         'contracted_tariff':['3.0','3.0','3.0','2.0'],
                         'start_date':[str(dates[0])]*4,'end_date':[str(dates[-1])]*4})
    meta.to_csv(root/'metadata.csv',index=False)
    with tarfile.open(root/'imp-pre.tar', 'w') as tar:
        for n,(category, ident) in enumerate(ids.items()):
            raw = pd.DataFrame({'timestamp': dates.astype(str),
                                'kWh': [float(n+1)]*len(dates),
                                'imputed':[0]*len(dates)})
            if category == 'residential':
                raw = raw.drop(index=[24,25,26])  # 3-hour internal interpolation
            if category == 'commercial':
                raw.loc[12,'kWh'] = np.nan  # invalid/missing
            content = raw.to_csv(index=False).encode('utf-8')
            info = tarfile.TarInfo(f'data/{ident}.csv')
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return root/'metadata.csv',root/'imp-pre.tar'


def test_real_archive_processing(tmp_path):
    metadata, archive=make_archive(tmp_path)
    dest=tmp_path/'prepared'
    result=prepare(metadata,archive,dest,wide_value='sum',logger=lambda _:None)
    assert result['hours_in_union']==72
    assert result['longest_common_overlap_hours']==72
    assert result['sector_statistics']['residential']['customers_with_data']==1
    assert (dest/'goiener_distributor_ready.csv').exists()
    assert (dest/'residential.csv').exists()
    assert (dest/'commercial.csv').exists()
    assert (dest/'manufacturing.csv').exists()
    assert (dest/'customer_quality_manifest.csv').exists()
    r=pd.read_csv(dest/'residential.csv')
    assert len(r)==72
    assert r.loc[24,'load_kw']==1.0
    assert r.active_customers.eq(1).all()
    mf=pd.read_csv(dest/'customer_quality_manifest.csv')
    assert mf.loc[mf.sector=='residential','missing_hours_interpolated'].iloc[0]==3
    wide=pd.read_csv(dest/'goiener_distributor_ready.csv')
    assert wide.shape==(72,4)
    assert set(wide.columns)=={'timestamp', 'Residential-GoiEner-Aggregate','Commercial-GoiEner-Aggregate','Industrial-GoiEner-Aggregate'}
    assert wide['Commercial-GoiEner-Aggregate'].iloc[12]==2.0


def test_tariff_fallback(tmp_path):
    metadata,archive=make_archive(tmp_path)
    dest=tmp_path/'with_fallback'
    result=prepare(metadata,archive,dest,residential_tariff_proxy=True,logger=lambda _:None)
    assert result['sector_statistics']['residential']['customers_with_data']==2
    manifest=pd.read_csv(dest/'customer_quality_manifest.csv')
    assert 'UNVERIFIED_2x_tariff_proxy' in set(manifest.classification_basis)
