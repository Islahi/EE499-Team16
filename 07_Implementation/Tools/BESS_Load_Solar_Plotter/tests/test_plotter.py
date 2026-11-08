"""Functional tests; run: python -m unittest discover -s tests -v"""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import numpy as np

from data_engine import (discover_networks,aggregate_distributed,nasa_power_csv_to_hourly,
    merge_nasa_monthly,slice_period,aggregate_period,load_aggregated_csv)
from plot_engine import interval_plan,plot_dashboard
from matplotlib.figure import Figure


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def _network_zip(self):
        path=self.root/'example.zip'
        assignment='bus_id,category\n2,residential\n3,commercial\n4,manufacturing\n'
        load='timestamp,bus_id,p_kw,q_kvar\n'
        for h in range(48):
            dt=pd.Timestamp('2018-05-01')+pd.Timedelta(hours=h)
            for bid,p in [(1,0),(2,1+h),(3,2),(4,3)]:
                load+=f'{dt},{bid},{p},0\n'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('CaseA/bus_assignments_used.csv',assignment)
            z.writestr('CaseA/load_profile.csv',load)
            z.writestr('CaseA/manifest.json',json.dumps({'bus_count':4}))
        return path
    def test_exact_hourly_sectors(self):
        path=self._network_zip()
        entries=discover_networks(path)
        self.assertEqual(len(entries),1)
        # Small chunk means split hours across chunks; must recombine correctly.
        data,meta=aggregate_distributed(path,entries[0],chunksize=5)
        self.assertEqual(len(data),48)
        self.assertEqual(data.iloc[0]['residential'],1.)
        self.assertEqual(data.iloc[0]['commercial'],2.)
        self.assertEqual(data.iloc[0]['manufacturing'],3.)
        self.assertEqual(data.iloc[0]['total'],6.)
        self.assertEqual(float(data.iloc[1]['total']),7.)
        self.assertEqual(meta['bus_count'],4)
    def test_weekly_monthly_daily_consistency(self):
        path=self._network_zip()
        data,_=aggregate_distributed(path,discover_networks(path)[0],chunksize=5)
        self.assertEqual(len(slice_period(data,'Daily','2018-05-01')),24)
        self.assertEqual(len(slice_period(data,'Monthly','2018-05-01')),48)
        daily=aggregate_period(data,'Daily')
        weekly=aggregate_period(data,'Weekly')
        monthly=aggregate_period(data,'Monthly')
        self.assertAlmostEqual(daily.total.sum(),data.total.sum())
        self.assertAlmostEqual(weekly.total.sum(),data.total.sum())
        self.assertAlmostEqual(monthly.total.sum(),data.total.sum())
        self.assertEqual(interval_plan('Monthly','Default'),['Weekly'])
        self.assertEqual(interval_plan('Yearly','Default'),['Monthly'])
        self.assertEqual(interval_plan('Monthly','Monthly'),['Monthly'])
        self.assertEqual(interval_plan('Yearly','Weekly'),['Weekly'])
        self.assertEqual(interval_plan('Yearly','Daily'),['Daily'])
        self.assertEqual(interval_plan('Daily','Default'),['Hourly'])
        self.assertEqual(interval_plan('Weekly','Default'),['Daily'])
        self.assertEqual(interval_plan('Yearly','Hourly'),['Hourly'])
    def test_monthly_plot_weekly_only(self):
        path=self._network_zip()
        data,_=aggregate_distributed(path,discover_networks(path)[0])
        f=Figure(figsize=(8,6))
        result=plot_dashboard(f,load=data,nasa=None,period='Monthly',selected='2018-05-10')
        self.assertEqual(len(f.axes),1)
        self.assertEqual(set(result),{'load_weekly'})
        f.savefig(self.root/'test_plot.png')
        self.assertTrue((self.root/'test_plot.png').stat().st_size>1000)
    def test_nasa_metadata_and_unit_conversions(self):
        p=self.root/'nasa.csv'
        p.write_text('-BEGIN HEADER-\nNASA POWER hourly data\n-END HEADER-\nYEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DIFF,ALLSKY_SFC_SW_DNI,T2M\n2018,1,1,0,0,0,0,7\n2018,1,1,1,500,100,650,8\n2018,1,1,2,500,100,650,9\n')
        solar=nasa_power_csv_to_hourly(p)
        self.assertEqual(len(solar),3)
        self.assertEqual(solar.iloc[1].GHI,500)
        day=aggregate_period(solar,'Daily',quantity='irradiance')
        self.assertEqual(day.GHI.iloc[0],1.0)
        self.assertEqual(day.T2M.iloc[0],8.)
    def test_nasa_monthly_merge_no_double_count(self):
        paths=[]
        for suffix in ['jan','feb']:
            p=self.root/f'{suffix}.csv'
            p.write_text('YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN\n2018,1,1,0,600\n2018,1,1,1,800\n')
            paths.append(p)
        solar=merge_nasa_monthly(paths,time_mode='as_is')
        self.assertEqual(len(solar),2)
        self.assertEqual(solar.GHI.sum(),1400)
    def test_nasa_convert_spain(self):
        p=self.root/'nasa.csv';p.write_text('YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN\n2018,6,1,0,200\n')
        out=merge_nasa_monthly([p],time_mode='utc_to_spain')
        self.assertEqual(out.index[0].hour,2)
    def test_compare_monthly_plot_two_panels(self):
        path=self._network_zip()
        data,_=aggregate_distributed(path,discover_networks(path)[0])
        solar=pd.DataFrame({'GHI':[300]*len(data),'DHI':[100]*len(data),'DNI':[400]*len(data)},index=data.index)
        fig=Figure(figsize=(9,7))
        tables=plot_dashboard(fig,load=data,nasa=solar,period='Monthly',selected='2018-05-01',mode='Compare')
        self.assertEqual(len(fig.axes),2)
        self.assertEqual(set(tables),{'load_weekly','nasa_weekly'})


if __name__=='__main__':unittest.main()


class DateRangeTests(unittest.TestCase):
    """Regression tests for arbitrary calendar spans and immediate visibility filters."""
    def setUp(self):
        self.index=pd.date_range('2017-05-30', '2020-03-01 23:00', freq='h')
        n=len(self.index)
        self.loads=pd.DataFrame({
            'residential':np.full(n,4.), 'commercial':np.full(n,3.),
            'manufacturing':np.full(n,2.), 'total':np.full(n,9.)
        },index=self.index)
        self.sun=pd.DataFrame({'GHI':np.full(n,200.),'DHI':np.full(n,50.),
                               'DNI':np.full(n,250.),'T2M':np.full(n,18.)},index=self.index)

    def test_inclusive_start_end(self):
        from data_engine import slice_date_range
        data=slice_date_range(self.loads,'2017-05-30','2017-05-31')
        self.assertEqual(len(data),48)
        self.assertEqual(data.index[-1].hour,23)
        with self.assertRaises(ValueError):
            slice_date_range(self.loads,'2018-01-01','2017-01-01')
        with self.assertRaises(ValueError):
            slice_date_range(self.loads,'not-a-date','2018-01-01')

    def test_arbitrary_multiyear_yearly_monthly_buckets(self):
        fig=Figure(figsize=(9,5))
        tables=plot_dashboard(fig,load=self.loads,nasa=None,period='Yearly',
                              start_date='2017-05-30',end_date='2020-03-01')
        self.assertGreater(len(tables['load_monthly']),24)
        self.assertEqual(len(tables['load_monthly']),35)
        self.assertEqual(fig.axes[0].get_lines()[0].get_label(),'Residential')

    def test_mixed_multi_month_and_detailed_hourly(self):
        fig=Figure(figsize=(9,6))
        tables=plot_dashboard(fig,load=self.loads,nasa=None,period='Monthly',
                              start_date='2018-11-01',end_date='2019-02-28')
        self.assertEqual(set(tables),{'load_weekly'})
        self.assertEqual(tables['load_weekly'].total.sum(), 9*120*24)
        # Users can explicitly request a daily or monthly view for this same period.
        daily=plot_dashboard(fig,load=self.loads,nasa=None,period='Monthly',
                             start_date='2018-11-01',end_date='2019-02-28',detail='Daily')
        self.assertEqual(len(daily['load_daily']),120)
        monthly=plot_dashboard(fig,load=self.loads,nasa=None,period='Yearly',
                               start_date='2018-11-01',end_date='2019-02-28',detail='Monthly')
        self.assertEqual(len(monthly['load_monthly']),4)
        tables=plot_dashboard(fig,load=self.loads,nasa=None,period='Yearly',
                              start_date='2018-01-01',end_date='2019-12-31',detail='Hourly')
        self.assertEqual(len(tables['load_hourly']), 365*24*2)

    def test_solar_and_total_visibility_and_export_only_visible(self):
        fig=Figure(figsize=(9,6))
        tables=plot_dashboard(fig,load=self.loads,nasa=self.sun,mode='Compare',
                              period='Weekly',start_date='2018-06-01',end_date='2018-06-07',
                              load_cols=('residential','manufacturing'),sun_cols=('DHI',))
        self.assertEqual(list(tables['load_daily']),['residential','manufacturing'])
        self.assertEqual(list(tables['nasa_daily']),['DHI'])
        self.assertEqual(len(fig.axes[0].lines),2)
        self.assertEqual(len(fig.axes[1].lines),1)
        tables=plot_dashboard(fig,load=self.loads,nasa=self.sun,mode='Compare',
                              period='Daily',start_date='2018-06-01',end_date='2018-06-01',
                              load_cols=('total',),sun_cols=('GHI','DNI'),show_temperature=True)
        self.assertEqual(list(tables['load_hourly']),['total'])
        self.assertEqual(list(tables['nasa_hourly']),['GHI','DNI','T2M'])
        self.assertEqual(len(fig.axes),3)  # Load, NASA, temperature twin axis

    def test_empty_selected_channels_is_safe(self):
        fig=Figure(figsize=(9,6))
        tables=plot_dashboard(fig,load=self.loads,nasa=self.sun,mode='Compare',
                              period='Daily',start_date='2018-06-01',end_date='2018-06-01',
                              load_cols=(),sun_cols=())
        self.assertTrue(tables['load_hourly'].empty or tables['load_hourly'].shape[1]==0)
        self.assertEqual(tables['nasa_hourly'].shape[1],0)
