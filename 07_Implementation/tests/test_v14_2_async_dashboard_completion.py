"""Numerical run durability and dashboard/GUI lifecycle regression guards."""
import json
from pathlib import Path
from types import SimpleNamespace

from src.study_session import StudySession
from src.ui_workflow import regenerate_saved_dashboard


def test_worker_and_gui_register_same_run_once(tmp_path):
    root = tmp_path / 'a_session'
    output = root / 'optimization' / 'run_001'
    output.mkdir(parents=True)
    initial = {'optimization_runs': [], 'simulation_runs': [], 'session_id': 'a_session'}
    (root/'session.json').write_text(json.dumps(initial), encoding='utf-8')
    worker_session = StudySession.open_for_updates(root)
    gui_session = StudySession(root, initial)  # stale instance, like Qt's GUI
    fake_report = SimpleNamespace(
        context={'Run ID': 'one'}, metrics=None,
        result=SimpleNamespace(metadata={'fleet': []}, success=True))
    worker_session.record_run(output, True, fake_report)
    gui_session.record_run(output, True, fake_report)
    saved = json.loads((root/'session.json').read_text(encoding='utf-8'))
    assert len(saved['optimization_runs']) == 1
    assert saved['optimization_runs'][0]['status'] == 'success'
    assert gui_session.manifest == saved


def test_secondary_dashboard_worker_reports_path(monkeypatch):
    from src import dashboard
    events = []
    monkeypatch.setattr(dashboard, 'regenerate_dashboard', lambda folder: Path(folder)/'dashboard.html')
    value = regenerate_saved_dashboard('/tmp/example', events.append)
    assert value == Path('/tmp/example/dashboard.html')
    assert events == ['Building offline results dashboard', 'Dashboard ready: saved HTML report']


def test_qt_main_thread_does_not_own_dashboard_generation():
    source = (Path(__file__).resolve().parents[1]/'src'/'ui.py').read_text()
    run_source = (Path(__file__).resolve().parents[1]/'src'/'ui_workflow.py').read_text()
    assert 'defer_dashboard=True, session_root=self.session.root' in source
    assert 'self.dashboard_runner.start(partial(regenerate_saved_dashboard, folder))' in source
    assert 'self.worker.finished.connect(self.thread.quit, Qt.ConnectionType.DirectConnection)' in source
    assert 'if defer_html:' in run_source
