"""Windows double-click launcher for the accelerated BESS Planning Tool."""
from pathlib import Path
import multiprocessing
import sys
import traceback


def show_startup_error(error):
    """Show a useful error because .pyw launches without a console window."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "BESS Planning Tool", f"The program could not start:\n\n{error}")
        app.processEvents()
    except Exception:
        error_file = Path(__file__).with_name("app_startup_error.txt")
        error_file.write_text(traceback.format_exc(), encoding="utf-8")


def main():
    implementation_folder = Path(__file__).resolve().parents[1]
    if str(implementation_folder) not in sys.path:
        sys.path.insert(0, str(implementation_folder))
    from src_accelerated.ui import main as run_application
    return run_application()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        show_startup_error(error)
