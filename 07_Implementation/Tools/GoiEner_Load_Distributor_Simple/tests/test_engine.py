"""Offline tests: python -m unittest discover -s tests -v."""
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import distribution_engine as e


def create_three(folder, start='2017-01-01', hours=55):
    ts = pd.date_range(start, periods=hours, freq='h')
    for cat, scale in [('residential', 1), ('commercial', 3), ('manufacturing', 7)]:
        t = np.arange(hours)
        if cat == 'manufacturing':
            tvals = np.where((t % 24) < 7, scale * 0.4, scale).astype(float)
        else:
            tvals = scale * (1 + np.sin(2*np.pi*t/24)/3)
        pd.DataFrame({'timestamp':ts,'load_kw':tvals*5,'average_customer_kw':tvals,
                      'active_customers':5}).to_csv(folder/f'{cat}.csv',index=False)
    return ts


class EngineTests(unittest.TestCase):
    def test_source_three_and_wide(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            times = create_three(folder, hours=75)
            source = e.load_profiles(folder,'average')
            self.assertEqual(source.hours,75)
            self.assertEqual(source.frame.timestamp.iloc[-1],times[-1])
            self.assertAlmostEqual(source.frame['manufacturing'].iloc[7],7)
            summed = e.load_profiles(folder,'sum')
            self.assertAlmostEqual(float(summed.frame.residential.iloc[0]),5.0)
            wide = folder/'goiener_distributor_ready.csv'
            source.frame.rename(columns={c:e.PROFILES[c] for c in e.CATEGORIES}).to_csv(wide,index=False)
            loaded = e.load_profiles(wide)
            self.assertEqual(loaded.hours,75)
            self.assertEqual(loaded.value_choice,'upstream-selected')

    def test_gap_handling_only_valid_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            create_three(folder,hours=35)
            path=folder/'commercial.csv'
            frame=pd.read_csv(path)
            frame.loc[:2,'average_customer_kw']=np.nan
            frame.to_csv(path,index=False)
            loaded=e.load_profiles(folder)
            self.assertEqual(loaded.hours,32)
            self.assertEqual(loaded.frame.timestamp.iloc[0],pd.Timestamp('2017-01-01 03:00:00'))

    def test_bus_ranges(self):
        self.assertEqual(e.parse_bus_range('2-4, 11, 16-17'),[2,3,4,11,16,17])
        with self.assertRaises(ValueError):e.parse_bus_range('15-10')

    def test_source_5bus_and_136bus_excel(self):
        for file,expected in [('Guide_5Bus_Radial_Test.xlsx',5),('T23_136-Bus.xlsx',136),('IEEE_33Bus_Network_Data.xlsx',33)]:
            net=e.load_network(ROOT/'examples'/file,frequency_hz=60)
            self.assertEqual(len(net.loads),expected)
            self.assertEqual(net.voltage.is_slack.sum(),1)

    def test_export_full_multiyear_and_voltage_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            create_three(d,start='2017-01-01',hours=365*24*2)
            data=e.load_profiles(d)
            net=e.load_network(ROOT/'examples'/'Guide_5Bus_Radial_Test.xlsx')
            before=(ROOT/'examples'/'Guide_5Bus_Radial_Test.xlsx').read_bytes()
            map=e.demo_cycle(net)
            out=d/'output'
            m=e.export_network(net,data,map,out,anchor='mean',allow_zero_pv=True)
            self.assertEqual(m['hours'],17520)
            self.assertEqual(m['profile_output_rows'],17520*5)
            with (out/'load_profile.csv').open() as f: self.assertEqual(sum(1 for _ in f)-1,17520*5)
            with (out/'pv_profile.csv').open() as f: self.assertEqual(sum(1 for _ in f)-1,17520)
            self.assertEqual(before,(ROOT/'examples'/'Guide_5Bus_Radial_Test.xlsx').read_bytes())
            one=pd.read_csv(out/'load_profile.csv',nrows=10)
            self.assertEqual(one.columns.tolist(),['timestamp','bus_id','p_kw','q_kvar'])
            self.assertEqual(one.bus_id.nunique(),5)
            base=net.loads.set_index('bus_id')
            nonzero=one.loc[one.p_kw>0]
            if len(nonzero):
                r=nonzero.iloc[0]
                self.assertAlmostEqual(r.q_kvar/r.p_kw,base.loc[int(r.bus_id),'q_base_kvar']/base.loc[int(r.bus_id),'p_base_kw'],places=5)

    def test_pv_guard_and_explicit_zero_only(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            create_three(d,hours=26)
            src=e.load_profiles(d)
            base=pd.DataFrame({'bus_id':[1,2,3], 'p_base_kw':[0,100,80],
                'q_base_kvar':[0,40,20], 'pv_rated_kw':[0,20,0],
                'is_slack':[True,False,False], 'base_kv':[12.66]*3,'v_set_pu':[1.01,1,1]})
            base.to_csv(d/'bus.csv',index=False)
            net=e.load_network(d/'bus.csv')
            self.assertEqual(net.pv_count,1)
            with self.assertRaisesRegex(ValueError,'GoiEner contains no PV'):
                e.export_network(net,src,e.all_residential(net),d/'no_pv_permission')
            e.export_network(net,src,e.all_residential(net),d/'yes_pv',allow_zero_pv=True)
            pv=pd.read_csv(d/'yes_pv'/'pv_profile.csv')
            self.assertEqual(pv.bus_id.unique().tolist(),[2])
            self.assertTrue((pv.p_kw==0).all())
            volts=pd.read_csv(d/'yes_pv'/'source_voltage_settings_READ_ONLY.csv')
            self.assertAlmostEqual(volts.loc[volts.is_slack,'source_v_set_pu'].iloc[0],1.01)
            self.assertEqual(volts['base_kv'].tolist(),[12.66]*3)

    def test_136bus_72hours(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            create_three(d,hours=72)
            source=e.load_profiles(d)
            net=e.load_network(ROOT/'examples'/'T23_136-Bus.xlsx')
            out=d/'test136'
            e.export_network(net,source,e.demo_cycle(net),out)
            with (out/'load_profile.csv').open() as f: self.assertEqual(sum(1 for _ in f)-1,136*72)


    def test_clock_and_nasa_pv_export(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            hours = 48
            ts = create_three(d, start='2021-01-01', hours=hours)
            src = e.load_profiles(d)
            net = e.load_network(ROOT/'examples'/'Guide_5Bus_Radial_Test.xlsx')
            nasa = d/'nasa.csv'
            pd.DataFrame({
                'timestamp': ts,
                'irradiance_w_m2': [800 if t.hour == 12 else 0 for t in ts],
                'source_clock': ['UTC'] * hours,
            }).to_csv(nasa, index=False)
            origin = net.source.read_bytes()
            manifest = e.export_network(
                net, src, e.demo_cycle(net), d/'with_pv', source_clock='UTC',
                nasa_irradiance=nasa, pv_ratings_override={2: 100., 4: 80.},
                site_lat=43.263, site_lon=-2.935, clock_confirmed=True)
            self.assertEqual(manifest['clock'], 'UTC')
            self.assertEqual(manifest['pv_bus_count'], 2)
            self.assertEqual(manifest['pv_installed_capacity_kw'], 180.)
            self.assertTrue(manifest['pv_generation_is_modeled'])
            self.assertTrue(manifest['pv_reference']['common_source'])
            pv = pd.read_csv(d/'with_pv'/'pv_profile.csv')
            self.assertEqual(len(pv), hours * 2)
            self.assertEqual(set(pv.bus_id), {2, 4})
            self.assertAlmostEqual(pv.loc[(pv.bus_id == 2) & (pv.timestamp.str.endswith('12:00:00')), 'p_kw'].iloc[0], 80.)
            self.assertTrue((pv.q_kvar == 0).all())
            summary = pd.read_csv(d/'with_pv'/'bus_summary.csv')
            self.assertAlmostEqual(summary.loc[summary.bus_id == 4, 'pv_rated_kw'].iloc[0], 80.)
            self.assertEqual(origin, net.source.read_bytes())
            self.assertTrue((d/'with_pv'/'solar_irradiance.csv').exists())

    def test_nasa_raw_csv_and_missing_hours(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            raw = d/'nasa_power.csv'
            raw.write_text(
                '-BEGIN HEADER-\\nTime Standard: UTC\\n-END HEADER-\\n'
                'YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN\\n'
                '2021,1,1,0,0\\n2021,1,1,1,350\\n',
                encoding='utf-8')
            frame = e.solar_profile.read_nasa_csv(raw)
            self.assertEqual(len(frame), 2)
            self.assertAlmostEqual(frame.irradiance_w_m2.iloc[1], 350.)
            create_three(d, start='2021-01-01', hours=4)
            src = e.load_profiles(d)
            net = e.load_network(ROOT/'examples'/'Guide_5Bus_Radial_Test.xlsx')
            with self.assertRaisesRegex(ValueError, 'missing'):
                e.export_network(net, src, e.demo_cycle(net), d/'missing',
                                 nasa_irradiance=raw, pv_ratings_override={2: 100.})
            self.assertFalse((d/'missing').exists())

    def test_pv_rating_validation_and_clock(self):
        case = e.load_network(ROOT/'examples'/'Guide_5Bus_Radial_Test.xlsx')
        self.assertEqual(
            e.solar_profile.parse_bus_ratings('2:100, 4:80', case.loads.bus_id.tolist(), case.slack),
            {2:100, 4:80})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            e.solar_profile.parse_bus_ratings('2:100,2:90', case.loads.bus_id.tolist(), case.slack)
        with self.assertRaisesRegex(ValueError, 'slack'):
            e.solar_profile.parse_bus_ratings(f'{case.slack}:100', case.loads.bus_id.tolist(), case.slack)
        with self.assertRaisesRegex(ValueError, 'Unknown clock'):
            e.solar_profile.checked_clock('Imaginary/Invalid_Time_Zone')

if __name__=='__main__':unittest.main()
