"""Progress is observational: it must not change the numerical result."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.progress import ProgressEvent, StageReporter, format_duration
from src.simulation import SimulationConfig, simulate_timeseries
from test_simulation import make_network, make_profiles


class ProgressTests(unittest.TestCase):
    def test_counts_and_duration_are_not_time_estimates(self):
        self.assertEqual(ProgressEvent("GWO", 2, 8).percent, 25)
        self.assertEqual(ProgressEvent("FBS", 0, 0).percent, 0)
        self.assertEqual(format_duration(3661.9), "01:01:01")

    def test_throttle_boundaries_and_independent_snapshots(self):
        snapshots = []
        stages = []
        reporter = StageReporter(stages.append, snapshots.append)
        with patch("src.progress.perf_counter", side_effect=[1, 1.01, 1.02, 1.03]):
            reporter.progress(ProgressEvent("GWO", 0, 2, log=True))
            reporter.progress(ProgressEvent("Candidate", 0, 3))
            reporter.progress(ProgressEvent("FBS", 1, 100))
            self.assertEqual(len(snapshots), 1)
            reporter.progress(ProgressEvent("GWO", 1, 2, log=True))
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0][0]["GWO"].completed, 0)
        self.assertEqual(set(snapshots[-1][0]), {"GWO"})
        reporter("Metrics")
        self.assertEqual(reporter.events, {})
        self.assertEqual(stages, ["Metrics"])

    def test_simulation_and_fbs_hooks_preserve_results(self):
        events = []
        network, profiles = make_network(), make_profiles()
        config = SimulationConfig(reserve_fraction=0)
        before = simulate_timeseries(network, profiles, config)
        after = simulate_timeseries(network, profiles, config, progress=events.append)
        self.assertEqual(before, after)
        hours = [event for event in events if event.phase == "Simulation"]
        self.assertEqual(hours[-1].completed, 2)
        self.assertEqual(hours[-1].total, 2)
        sweeps = [event for event in events if event.phase == "FBS"]
        self.assertTrue(sweeps)
        self.assertTrue(all(0 <= event.completed <= event.total for event in sweeps))


if __name__ == "__main__":
    unittest.main()
