"""V16 semantic workbook compatibility, retained electrical evidence and Joint GA settings."""
from dataclasses import replace
from hashlib import sha256
from math import degrees
import cmath
import csv
import json
from unittest.mock import patch

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from src import fleet_ga_optimizer as ga
from src.bess import BESSConfig
from src.control_audit import ledger_hours
from src.dashboard_series import catalogue
from src.data_loader import profile_at
from src.electrical_details import line_ends
from src.fbs import FBSConfig, run_fbs
from src.metrics import EconomicConfig, evaluate_results
from src.optimizer import OptimizationBounds
from src.planning_policy import effective_joint_search
from src.results import export_results
from src.simulation import SimulationConfig, _operating_point, simulate_timeseries
from src.study_session import study_fingerprint
from src.study_setup import save_study_setup, open_study_setup
from src.ui_workflow import DataRequest, prepare_study, RunSettings, run_base_case
from tests.test_v13_coordinated_opf import stressed_case


@pytest.fixture
def case(tmp_path):
    folder = tmp_path / "case"
    folder.mkdir()
    path = tmp_path / "network.xlsx"
    book = Workbook()
    book.active.title = "Network"
    book.active.append(("parameter", "value"))
    book.active.append(("base_power_kva", 1000))
    book.active.append(("frequency_hz", 60))
    sheets = {
        "Buses":[("bus_id","base_kv","is_slack","v_set_pu"), (1,12.66,True,1), (2,12.66,False,1)],
        "Loads":[("load_id","bus_id","p_base_kw","q_base_kvar"), ("D",2,200,80)],
        "Lines":[("line_id","from_bus","to_bus","r_ohm","x_ohm","ampacity_a"), ("L",2,1,.35,.14,100)],
    }
    for key, rows in sheets.items():
        sheet = book.create_sheet(key)
        for row in rows:
            sheet.append(row)
    book.save(path)
    times = pd.date_range("2021-01-01", periods=3, freq="h")
    load = pd.DataFrame({"timestamp":times, "bus_id":2, "p_kw":[80,90,100], "q_kvar":[4,5,6]})
    load.to_csv(folder/"load_profile.csv", index=False)
    (folder/"bus_assignments_used.csv").write_text("bus_id,category\n2,commercial\n")
    manifest = {"clock":"UTC", "network_sha256":sha256(path.read_bytes()).hexdigest(),
                "profile_hashes_sha256":{"load_profile.csv":sha256((folder/"load_profile.csv").read_bytes()).hexdigest()}}
    (folder/"manifest.json").write_text(json.dumps(manifest))
    return DataRequest(path, None, "auto", None, 1, "none", load_source="distributed", dataset_folder=folder)


def first_flow(study):
    return run_fbs(study.network, _operating_point(study.network, profile_at(study.profiles,0)), FBSConfig())


def test_electrical_edits_keep_absolute_profiles_and_fingerprint_saved_setup(case, tmp_path):
    original = prepare_study(case)
    saved = save_study_setup(tmp_path/"setup.json", original, {})
    assert open_study_setup(saved)[1]["spin_ga_stall_generations"] == 6
    original_hash = original.context["Network SHA256"]
    original_v = first_flow(original).voltage_mag_pu[2]
    book = load_workbook(case.network_path)
    book["Buses"]["D2"] = 1.05
    book.save(case.network_path)
    changed = prepare_study(case)
    assert changed.context["Distributor network SHA256"] == original_hash != changed.context["Network SHA256"]
    assert study_fingerprint(original) != study_fingerprint(changed)
    assert first_flow(changed).voltage_mag_pu[1] == 1.05
    assert first_flow(changed).voltage_mag_pu[2] > original_v
    with pytest.raises(ValueError, match="source changed"):
        open_study_setup(saved)
    book["Loads"]["C2"] = 400
    book["Lines"]["D2"] = .8
    book["Lines"]["E2"] = .3
    book["Lines"]["F2"] = 2
    book.save(case.network_path)
    new = prepare_study(case)
    assert new.profiles.load_p_kw == original.profiles.load_p_kw
    assert new.profiles.load_q_kvar == original.profiles.load_q_kvar
    assert first_flow(new).total_loss_p_kw > first_flow(changed).total_loss_p_kw
    assert new.network.lines[0].ampacity_a == 2
    settings = RunSettings(SimulationConfig(), EconomicConfig(), None, {})
    assert run_base_case(new,settings).step.operating_point.p_load_kw[2] == 400
    assert new.profiles.load_p_kw[2][0] == 80


@pytest.mark.parametrize("problem,match", [("unknown","99"),("gap","hourly"),("hash","hash mismatch"),
    ("timezone","clock"),("missing_clock","clock"),("units","units"),("topology","endpoint"),
    ("duplicate","Duplicate"),("negative","nonnegative"),("negative_q","q_kvar"),("invalid_clock","clock"),
    ("pv","nameplate"),("unrated_pv","nameplate"),("missing","Missing load profiles")])
def test_invalid_imports(case, problem, match):
    folder = case.dataset_folder
    path = folder/"load_profile.csv"
    load = pd.read_csv(path)
    manifest = json.loads((folder/"manifest.json").read_text())
    if problem == "unknown":
        load["bus_id"] = 99
    elif problem == "missing":
        load["bus_id"],load["p_kw"],load["q_kvar"] = 1,0,0
    elif problem == "gap":
        load = load.drop(1)
    elif problem == "duplicate":
        load = pd.concat((load,load.iloc[:1]))
    elif problem == "negative":
        load.loc[1,"p_kw"] = -10
    elif problem == "negative_q":
        load.loc[1,"q_kvar"] = -2
    elif problem == "invalid_clock":
        manifest["clock"] = "Unknown/City"
    elif problem == "timezone":
        case = replace(case, clock="Europe/Madrid")
    elif problem == "missing_clock":
        del manifest["clock"]
    elif problem == "units":
        manifest["simulation_units"] = "P MW, Q Mvar"
    elif problem == "topology":
        book = load_workbook(case.network_path)
        book["Lines"]["B2"] = 99
        book.save(case.network_path)
    elif problem in ("pv", "unrated_pv"):
        load.assign(p_kw=30,q_kvar=0).to_csv(folder/"pv_profile.csv",index=False)
        if problem == "pv":
            (folder/"bus_summary.csv").write_text("bus_id,pv_rated_kw\n2,10\n")
        manifest["pv_reference"] = {"clock":"UTC","units":"kW","common_source":True}
        case = replace(case, pv_source="dataset")
    load.to_csv(path,index=False)
    manifest["profile_hashes_sha256"]["load_profile.csv"] = (
        "0"*64 if problem == "hash" else sha256(path.read_bytes()).hexdigest())
    (folder/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=match):
        prepare_study(case)


def test_branch_signs_angles_and_saved_series(case, tmp_path):
    study = prepare_study(case)
    result = simulate_timeseries(study.network,study.profiles,SimulationConfig())
    folder = tmp_path/"run"
    export_results(result,folder,network=study.network,voltage_bounds=(.95,1.05),
                   input_snapshot={"profiles":study.profiles,"metadata":{},"workbook":case.network_path})
    buses = pd.read_csv(folder/"buses.csv")
    lines = pd.read_csv(folder/"branches.csv")
    assert line_ends(study.network)["L"] == (1,2)
    for index, step in enumerate(result.steps):
        flow = step.power_flow
        v, current = flow.voltage_complex_pu, flow.branch_current_pu["L"]
        send, receive = (v[bus] * current.conjugate() * study.network.base_power_kva for bus in (1,2))
        row = lines.iloc[index]
        assert complex(row.sending_p_kw,row.sending_q_kvar) == pytest.approx(send)
        assert complex(row.receiving_p_kw,row.receiving_q_kvar) == pytest.approx(receive)
        assert complex(row.loss_p_kw,row.loss_q_kvar) == pytest.approx(send-receive)
        saved = buses[(buses.bus_id==2)&(buses.step_index==index)].iloc[0]
        assert saved.voltage_angle_deg == pytest.approx(degrees(cmath.phase(v[2])))
        assert row.to_angle_deg == pytest.approx(saved.voltage_angle_deg)
    blocks = []
    def add(data):
        blocks.append(data)
        return len(blocks)-1
    gallery = catalogue(folder, list(csv.DictReader((folder/"hourly.csv").read_text(encoding="utf-8-sig").splitlines())),
                        add, root=folder, snapshot={},inputs_cache={})
    _,_,block = gallery["groups"]["bus"]["entities"]["2"][0]
    assert blocks[block][1]["voltage_angle_deg"] == pytest.approx(buses[buses.bus_id==2].voltage_angle_deg)
    assert not (folder/"control_decisions.jsonl").read_text()


def test_snapshot_rejects_workbook_edited_after_preparation(case, tmp_path):
    from src.study_session import StudySession
    study = prepare_study(case)
    book = load_workbook(case.network_path)
    book["Buses"]["D2"] = 1.05
    book.save(case.network_path)
    with pytest.raises(ValueError, match="changed after preparation"):
        StudySession.create(study, tmp_path/"results")
    assert not (tmp_path/"results").exists()


def test_reference_workbook_with_branch_rating_and_disabled_pv(case):
    from tests.test_v15_6_desktop_cleanup import _source_workbook
    _source_workbook(case.network_path)
    book = load_workbook(case.network_path)
    book["Branch Data"]["H1"] = "ampacity_a"
    book["Branch Data"]["H2"] = 4
    sheet = book.create_sheet("PV")
    sheet.append(["pv_id","bus_id","p_rated_kw"])
    sheet.append(["off",2,0])
    book.save(case.network_path)
    (case.dataset_folder/"bus_summary.csv").write_text("bus_id,pv_rated_kw\n2,10\n")
    study = prepare_study(replace(case,frequency_hz=60,pv_source="dataset"))
    assert not study.network.pv_units and study.context["PV rating selection"] == "Workbook"
    assert study.network.lines[0].ampacity_a == 4
    assert first_flow(study).branch_current_a["L1"] > 0


@pytest.mark.parametrize("pv,limit_kw,amps,unresolved",[(0,800,30,False),(3500,None,None,False),(0,10,1,True)])
def test_ledger_network_triggers_and_energy(pv, limit_kw, amps, unresolved, tmp_path):
    net, prof = stressed_case(2,pv)
    net.lines = [replace(net.lines[0], ampacity_a=amps)]
    config=SimulationConfig(grid_import_limit_kw=limit_kw,grid_export_limit_kw=50,
                            allow_load_shedding=not unresolved)
    result=simulate_timeseries(net,prof,config)
    export_results(result,tmp_path/"run",network=net,context={"Run ID":"audit","Alternative":"No BESS"})
    rows=[json.loads(line) for line in (tmp_path/"run/control_decisions.jsonl").read_text().splitlines()]
    assert rows
    series=pd.read_csv(tmp_path/"run/hourly.csv")
    for hour in rows:
        assert hour["outcome"] == ("unresolved" if unresolved else "feasible")
        assert hour["triggers"]
        for c in hour["constraints"]:
            if c["type"]=="ampacity":
                assert c["final"]["measured"] == pytest.approx(result.steps[hour["step_index"]].power_flow.branch_current_a[c["entity"]])
            if c["type"] in ("undervoltage","overvoltage"):
                assert c["final"]["measured"] == pytest.approx(result.steps[hour["step_index"]].power_flow.voltage_mag_pu[int(c["entity"])])
        if len(hour["triggers"])>1: assert hour["attribution"]=="reason_not_unique"
    m=evaluate_results(result,EconomicConfig())
    for action,column,energy in (("load_shed","shedding_kw",m.load_shedding_energy_kwh),
                                 ("pv_curtail","curtailment_kw",m.curtailment_energy_kwh)):
        total=sum(a["accepted"]*h["dt_hours"] for h in rows for a in h["actions"] if a["action"]==action)
        assert total == pytest.approx(series[column].sum())
        if energy is not None: assert total == pytest.approx(energy)


def test_explicit_battery_and_lean_audit(case):
    study=prepare_study(case)
    battery=BESSConfig(2,150,25,.1,.9,.5,.95,.95)
    cfg=SimulationConfig()
    request=lambda i,_,state:[-15,60,0][i]
    result=simulate_timeseries(study.network,study.profiles,cfg,battery,request)
    actions=[a for h in ledger_hours(result,{}) for a in h["actions"]]
    assert [(a["action"],a["status"]) for a in actions]==[("bess_charge","accepted"),("bess_discharge","clipped")]
    assert actions[0]["accepted"]==-15 and actions[1]["requested"]==60 and actions[1]["accepted"]==25
    lean=simulate_timeseries(study.network,study.profiles,cfg,battery,request,capture_dispatch=False)
    assert list(ledger_hours(lean,{}))==[]
    assert [s.power_flow.slack_p_kw for s in lean.steps]==[s.power_flow.slack_p_kw for s in result.steps]


@pytest.mark.parametrize("stall",[1,2,3,6,10])
def test_joint_ga_stops_at_requested_stall(stall):
    policy=effective_joint_search({"spin_ga_stall_generations":stall,"spin_max_generations":20})
    assert effective_joint_search({}).stall_generations==6
    with pytest.raises(ValueError,match="stall generations"):
        effective_joint_search({"spin_ga_stall_generations":10,"spin_max_generations":4})
    bounds=OptimizationBounds((2,), (5.,), (20.,))
    with patch.object(ga,"evaluate_fleet_on_scenarios", side_effect=lambda n,s,e,f:ga.FleetEvaluation(f,100,True)):
        result=ga.run_joint_fleet_ga(None,None,bounds,None,max_units=1,
            ga_config=ga.FleetGAConfig(population_size=8,max_generations=20,stall_generation_limit=policy.stall_generations))
    assert result["config"]["stall_generation_limit"]==stall
    assert (result["stop_reason"],result["generations"])==("stall_generation_limit",stall+1)



@pytest.mark.parametrize("pv_kw,expected", [(0, {"bess_q"}), (100, {"bess_q", "pv_q"})])
def test_retained_reactive_controls_match_pq_injections(pv_kw, expected):
    net, prof = stressed_case(3, pv_kw)
    batt = BESSConfig(2,1000,500,.2,1.,.2,.9,.9)
    net.pv_units = [replace(net.pv_units[0], q_capability_kvar=200)]
    result = simulate_timeseries(net,prof,SimulationConfig(fleet_dispatch_mode="opf"),bess_fleet=(batt,))
    entries = list(ledger_hours(result,{}))
    actions = {a["action"] for h in entries for a in h["actions"]}
    assert actions.intersection({"bess_q", "pv_q"}) == expected
    for h in entries:
        point = result.steps[h["step_index"]].operating_point
        for a in h["actions"]:
            if a["action"]=="bess_q":
                assert a["accepted"] == pytest.approx(point.q_bess_kvar[a["bus_id"]])
            if a["action"]=="pv_q":
                assert a["accepted"] == pytest.approx(point.q_pv_kvar[a["bus_id"]])


def test_nonconverged_result_remains_unresolved_and_diagnostic(case):
    study=prepare_study(case)
    config=SimulationConfig(fbs_config=FBSConfig(max_iterations=1,voltage_tolerance_pu=1e-15),
                            allow_load_shedding=False,allow_pv_curtailment=False)
    result=simulate_timeseries(study.network,study.profiles,config)
    assert not result.converged
    assert all(h["outcome"]=="unresolved" and not h["converged"] for h in ledger_hours(result,{}))


def test_desktop_selected_entity_timestamp_and_report_link(case, tmp_path, monkeypatch):
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from src.ui import MainWindow, widget
    from src.ui_workflow import RunReport
    app = QApplication.instance() or QApplication([])
    study = prepare_study(case)
    settings = SimulationConfig()
    series = simulate_timeseries(study.network,study.profiles,settings)
    window = MainWindow()
    try:
        window.study = study
        window.report = RunReport(series,None,{"Simulation settings":{"voltage_min_pu":.95,"voltage_max_pu":1.05}})
        window.result_folder = tmp_path
        (tmp_path/"dashboard.html").touch()
        window.result_index = 0
        window.refresh_network()
        window.scene.bus_items[2].setSelected(True)
        assert f"{series.steps[0].power_flow.voltage_angle_deg[2]:.6f}°" in widget(window,"lbl_bus_voltage").text()
        window.result_index = 2
        window.refresh_network()
        window.refresh_selection_details()
        assert str(series.steps[2].timestamp) in widget(window,"lbl_bus_voltage").text()
        window.scene.clearSelection()
        window.scene.line_items["L"].setSelected(True)
        assert "Receiving" in widget(window,"lbl_line_details").text()
        captured = []
        monkeypatch.setattr("src.dashboard_viewer.show_dashboard",lambda parent,path,focus:captured.append(focus))
        window.plot_element.click()
        assert captured==[{"group":"line","entity":"L","timestamp":str(series.steps[2].timestamp),"scenario":"."}]
    finally:
        runner=window.settings_dialog.jit_runner
        if runner.busy:
            loop=QEventLoop()
            runner.busy_changed.connect(lambda busy:None if busy else loop.quit())
            QTimer.singleShot(15000,loop.quit)
            loop.exec()
        window.close()
        app.processEvents()

