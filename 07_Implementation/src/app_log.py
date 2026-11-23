"""Persistent diagnostics available before a study session is created."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


desktop_log = logging.getLogger("bess_planning.desktop")


def configure_desktop_log() -> None:
    if desktop_log.handlers:
        return
    path = Path(__file__).resolve().parent / "Results" / "application.log"
    try:
        path.parent.mkdir(exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    desktop_log.addHandler(handler)
    desktop_log.setLevel(logging.DEBUG)
    desktop_log.propagate = False
