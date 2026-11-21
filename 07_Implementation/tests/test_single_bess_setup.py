from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src_accelerated.data_loader import ProfileData
from src_accelerated.network_loader import load_network
from src_accelerated.optimizer import BESSCandidate, CandidateEvaluation
from src_accelerated.single_bess_search import _pick_finalists, baseline_fingerprint, representative_windows
from src_accelerated.study_setup import open_study_setup, save_study_setup
from src_accelerated.ui_workflow import DataRequest, prepare_study
from src_accelerated.metrics import EconomicConfig
from src_accelerated.simulation import SimulationConfig


WORKBOOK = Path(__file__).parents[1] / "Validation/C1_Validation_Test/Working_RDS/IEEE_33Bus_Network_Data.xlsx"


def test_saved_setup_restores_interval_and_reports_changed_source(tmp_path):
    network = load_network(WORKBOOK, frequency_hz=60.)
    times = pd.date_range("2021-01-01", periods=26, freq="h")
    source = tmp_path / "loads.csv"
    rows = [(stamp, load.bus_id, load.p_base_kw, load.q_base_kvar) for stamp in times for load in network.loads]
    pd.DataFrame(rows, columns=("timestamp", "bus_id", "p_kw", "q_kvar")).to_csv(source, index=False)
    study = prepare_study(DataRequest(WORKBOOK, 60., "auto", times[0], 1, "none",
                                       load_source="imported", load_path=source, clock="UTC"))
    study.select_source("historical", times[3], times[10])
    settings = {"shedding_policy": "minimum_energy", "search_mode": "thorough", "spin_gwo_seed": 42}
    path = save_study_setup(tmp_path / "study.json", study, settings)
    opened, controls = open_study_setup(path)
    assert settings == controls and opened.simulation_window == study.simulation_window
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Saved study source changed"):
        open_study_setup(path)


def test_screening_weeks_are_chronological_and_seasonal():
    times = pd.date_range("2021-01-01", "2022-01-01", freq="h", inclusive="left")
    point = SimpleNamespace(p_load_kw={2: 30.})
    steps = [SimpleNamespace(shedding_kw=stamp.hour, curtailment_kw=stamp.month, requested_point=point) for stamp in times]
    windows = representative_windows(SimpleNamespace(steps=steps), SimpleNamespace(timestamps=times), 4)
    assert all(len(week) == 168 and week == list(range(week[0], week[-1] + 1)) for week in windows)
    assert len({(times[week[84]].month - 1) // 3 for week in windows}) == 4
    assert windows == sorted(windows)


def test_finalists_mix_reliability_cost_and_incumbents_and_fingerprint_matches_only_same_inputs():
    candidates = [BESSCandidate(bus, 100., 300.) for bus in range(2, 9)]
    evaluations = [CandidateEvaluation(candidate, i, True, execution_metadata={"screened_shedding_kwh": 9-i})
                   for i, candidate in enumerate(candidates)]
    finalists = _pick_finalists(evaluations, 5, [candidates[3]])
    assert len(finalists) == len(set(finalists)) == 5
    assert {candidates[0], candidates[-1], candidates[3]}.issubset(finalists)
    network = load_network(WORKBOOK, frequency_hz=60.)
    data = ProfileData.from_arrays(pd.date_range("2021-01-01", periods=1, freq="h"), {2: [100.]}, {}, {}, {})
    economics = EconomicConfig()
    original = baseline_fingerprint(network, data, SimulationConfig(), economics, "UTC")
    assert original != baseline_fingerprint(network, data, SimulationConfig(shedding_policy="minimum_energy"), economics, "UTC")
    assert original != baseline_fingerprint(network, data, SimulationConfig(), economics, "UTC+03")
