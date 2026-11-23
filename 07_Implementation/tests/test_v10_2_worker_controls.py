"""CPU-worker configuration and Qt Designer integration; no PySide6 required."""
import unittest
from pathlib import Path
from xml.etree import ElementTree
from src.approved_methodology import auto_workers, normalize_settings

BASE = Path(__file__).resolve().parents[1]
ASSET = BASE / 'src/assets/settings_dialog.ui'
STAGES = (BASE/'src/sequential_multi.py').read_text(encoding='utf-8')
WORKFLOW = (BASE/'src/ui_workflow.py').read_text(encoding='utf-8')


class V102WorkerSettings(unittest.TestCase):
    def test_16_logical_auto_sane_for_16gb(self):
        values = normalize_settings({}, cpu_total=16)
        self.assertTrue(values['chk_auto_cpu_workers'])
        self.assertEqual(values['spin_cpu_workers'], 4)
        self.assertEqual(values['spin_annual_workers'], 2)

    def test_manual_saves_and_is_not_overridden(self):
        original = {'chk_auto_cpu_workers': False, 'spin_cpu_workers': 6,
                    'spin_annual_workers': 2, 'spin_gwo_population': 12}
        saved = normalize_settings(original, cpu_total=16)
        self.assertEqual(saved['spin_cpu_workers'], 6)
        self.assertEqual(saved['spin_annual_workers'], 2)
        self.assertFalse(saved['chk_auto_cpu_workers'])
        self.assertEqual(normalize_settings(saved, cpu_total=16), saved)

    def test_user_specified_single_annual_worker_is_not_discarded(self):
        values = normalize_settings({'chk_auto_cpu_workers': False,
                                     'spin_cpu_workers': 8, 'spin_annual_workers': 1}, cpu_total=16)
        self.assertEqual((values['spin_cpu_workers'], values['spin_annual_workers']), (8,1))

    def test_manual_workers_validate_cpu_and_memory_limit(self):
        for name, value in [('spin_cpu_workers',9), ('spin_cpu_workers',0),
                            ('spin_annual_workers',3), ('spin_annual_workers',0)]:
            settings = {'chk_auto_cpu_workers':False, 'spin_cpu_workers':4,'spin_annual_workers':2}
            settings[name] = value
            with self.subTest(name=name,value=value), self.assertRaises(ValueError):
                normalize_settings(settings, cpu_total=16)
        with self.assertRaises(ValueError):
            normalize_settings({'chk_auto_cpu_workers':False, 'spin_cpu_workers':8,
                                'spin_annual_workers':2}, cpu_total=4)


    def test_legacy_worker_controls_removed_from_desktop(self):
        tree = ElementTree.parse(ASSET)
        for name in ('chk_auto_cpu_workers','spin_cpu_workers','spin_annual_workers','lbl_worker_hint'):
            self.assertIsNone(tree.find(f".//widget[@name='{name}']"), name)


    def test_desktop_worker_policy_preserves_v156_defaults(self):
        from unittest.mock import patch
        from src.planning_policy import joint_search_policy
        with patch("src.planning_policy.auto_workers", return_value=4):
            effective=joint_search_policy(32)
        self.assertEqual((effective.population,effective.workers,effective.annual_workers),(12,4,1))

    def test_config_reaches_actual_workers_not_just_gui(self):
        self.assertIn('annual_workers=annual_workers',WORKFLOW)
        self.assertIn('workers=min(config.workers, 8)',STAGES)
        self.assertIn('rules, workers=annual_workers)',STAGES)
        self.assertIn("'parallel_annual_workers': annual_workers",STAGES)
        self.assertIn("'parallel_gwo_workers': min(config.workers,8)",STAGES)


if __name__=='__main__': unittest.main()
