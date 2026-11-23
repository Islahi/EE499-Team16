"""V14.1 regressions for V14 annual finalist rejection and oversized dashboard."""
import base64
import csv
import gzip
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from src.feeder_aware import ImprovementRules, incremental_and_cumulative_improvement
from src.dashboard import regenerate_dashboard


def metric(shedding, voltage):
    return {'shedding_kwh': shedding, 'voltage_deficit_pu_hours': voltage, 'buses': [2]}


class AcceptanceRegressions(unittest.TestCase):
    def test_shedding_relief_not_vetoed_by_precontrol_voltage(self):
        # The full-year feasibility and final voltage constraints are checked
        # by _full_year_candidate *before* this acceptance function is used.
        before = {'A': metric(100, 10), 'B': metric(100, 10)}
        after = {'A': metric(0.01, 11), 'B': metric(100, 11)}
        result = incremental_and_cumulative_improvement(before, after, before, 'A', ImprovementRules())
        self.assertTrue(result['acceptable'], result)
        self.assertEqual(result['acceptance_basis'], 'shedding_relief')
        self.assertAlmostEqual(result['pre_control_voltage_deterioration_pu_hours'], 2)

    def test_other_lateral_shedding_damage_remains_rejected(self):
        before = {'A': metric(100, 10), 'B': metric(100, 10)}
        after = {'A': metric(0, 11), 'B': metric(110, 10)}
        result = incremental_and_cumulative_improvement(before, after, before, 'A', ImprovementRules())
        self.assertFalse(result['acceptable'])
        self.assertIn('shedding_kwh worsened', result['reason'])

    def test_voltage_only_path_still_protects_precontrol_voltage(self):
        before = {'A': metric(0, 10), 'B': metric(0, 10)}
        after = {'A': metric(0, 9), 'B': metric(0, 12)}
        result = incremental_and_cumulative_improvement(before, after, before, 'A', ImprovementRules())
        self.assertFalse(result['acceptable'])
        self.assertEqual(result['acceptance_basis'], 'pre_control_voltage_relief')

    def test_voltage_improvement_cannot_mask_more_shedding(self):
        before = {'A': metric(100, 10), 'B': metric(0, 0)}
        after = {'A': metric(101, 0), 'B': metric(0, 0)}
        result = incremental_and_cumulative_improvement(before, after, before, 'A', ImprovementRules())
        self.assertFalse(result['acceptable'])
        self.assertIn('target shedding increased', result['reason'])


class DashboardRegressions(unittest.TestCase):
    def test_offline_report_ignores_unused_large_event_and_branch_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with (folder/'hourly.csv').open('w', newline='', encoding='utf-8') as f:
                w=csv.DictWriter(f, fieldnames=['timestamp','voltage_min_pu','converged','feasible',
                                                 'shedding_kw','load_input_kw']);w.writeheader()
                w.writerow({'timestamp':'2021-01-01 00:00:00','voltage_min_pu':.952,'converged':'True',
                            'feasible':'True','shedding_kw':5,'load_input_kw':100})
                w.writerow({'timestamp':'2021-01-01 01:00:00','voltage_min_pu':.950,'converged':'True',
                            'feasible':'True','shedding_kw':0,'load_input_kw':100})
            with (folder/'buses.csv').open('w', newline='', encoding='utf-8') as f:
                w=csv.DictWriter(f, fieldnames=['timestamp','bus_id','voltage_pu']);w.writeheader()
                for timestamp, vals in [('2021-01-01 00:00:00',(1,.98)),
                                        ('2021-01-01 01:00:00',(1,.95))]:
                    w.writerow({'timestamp':timestamp,'bus_id':2,'voltage_pu':vals[1]})
            # Simulate a large irrelevant canonical event log that the HTML
            # builder must not parse or embed in the simplified 3-tab report.
            (folder/'dispatch_events.jsonl').write_text('not JSON\n'*20000, encoding='utf-8')
            (folder/'branches.csv').write_text('line_id,current_a\nL1,3.14\n', encoding='utf-8')
            output=regenerate_dashboard(folder)
            html=output.read_text(encoding='utf-8')
            self.assertLess(len(html), 40000)
            manifest=json.loads((folder/'dashboard_manifest.json').read_text())
            self.assertEqual(manifest['html_sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
            match=re.search(r'<script id="report-data"[^>]*>([^<]+)</script>',html)
            self.assertIsNotNone(match)
            payload=json.loads(gzip.decompress(base64.b64decode(match.group(1))))
            sc=payload['scenarios']['.']
            self.assertAlmostEqual(sc['worst_bus_voltages']['2'],.95)
            self.assertNotIn('event_blocks',sc)
            self.assertNotIn('network_blocks',sc)
            self.assertNotIn('branch_blocks',sc)
            self.assertIn('hours_block',sc)


if __name__ == '__main__':
    unittest.main()
