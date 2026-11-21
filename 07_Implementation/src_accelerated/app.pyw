"""Windows double-click launcher for the accelerated BESS Planning Tool."""
from pathlib import Path
import multiprocessing
import os
import sys
import traceback


def show_startup_error(error):
    """Show a useful error because .pyw launches without a console window."""
    directory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).parent
    try:
        (directory / "app_startup_error.txt").write_text(
            "".join(traceback.format_exception(error)), encoding="utf-8"
        )
    except OSError:
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "BESS Planning Tool", f"The program could not start:\n\n{error}")
        app.processEvents()
    except ImportError:
        pass


def main():
    implementation_folder = Path(__file__).resolve().parents[1]
    if str(implementation_folder) not in sys.path:
        sys.path.insert(0, str(implementation_folder))
    if len(sys.argv) == 3 and sys.argv[1] == "--check-runtime":
        return check_runtime(Path(sys.argv[2]))
    from src_accelerated.ui import main as run_application
    return run_application()


def check_runtime(report):
    """Record basic portable-build checks without opening an interactive window."""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication
        from src_accelerated.data_loader import ProfileData
        from src_accelerated.fbs import warm_numba
        from src_accelerated.forecast_models import estimator
        from src_accelerated.network_model import Bus, Line, Load, NetworkModel
        from src_accelerated.simulation import SimulationConfig, simulate_timeseries
        from src_accelerated.ui import MainWindow
        import numpy as np
        import pandas as pd

        app = QApplication([])
        window = MainWindow()
        warm_numba()
        feeder = NetworkModel(
            [Bus(1, "Slack", 12.66, is_slack=True), Bus(2, "Remote", 12.66)],
            [Line("Feeder", 1, 2, 90., 12.)],
            [Load("Demand", 2, 250., 50.)], [], 1000., 60.,
        )
        profile = ProfileData.from_arrays([pd.Timestamp("2021-05-27 11:00")],
                                          {2: [250.]}, {2: [50.]}, {}, {})
        step = simulate_timeseries(feeder, profile, SimulationConfig()).steps[0]
        if not step.feasible or step.shedding_by_bus_kw[2] <= 0:
            raise RuntimeError("Coordinated control did not resolve the test bus undervoltage")
        features = np.arange(12, dtype=np.float32).reshape(-1, 1)
        for model_name in ("LightGBM", "XGBoost"):
            model = estimator(model_name, {"selected_hyperparameters": {"n_estimators": 2}})
            model.fit(features, features[:, 0])
            assert np.isfinite(model.predict(features)).all()
        assert QWebEngineView is not None
        window.close()
        app.quit()
    except Exception:
        report.write_text(traceback.format_exc(), encoding="utf-8")
        return 1
    report.write_text(
        "OK: desktop UI, Numba FBS, bus-specific shedding, LightGBM, XGBoost and Qt WebEngine imports.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        installation = Path(sys.executable).resolve().parent
        os.environ.setdefault("NUMBA_CACHE_DIR", str(installation / "Results" / ".numba-cache"))
    multiprocessing.freeze_support()
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        show_startup_error(error)
        raise SystemExit(1)
