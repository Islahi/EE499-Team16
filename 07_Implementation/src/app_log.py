"""Persistent diagnostics available before a study session is created."""
import json
import logging
from logging.handlers import RotatingFileHandler
from os import getpid
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


def record_opf_pv_boundary(event: dict) -> None:
    """Keep rare worker diagnostics even when candidate traces are disabled."""
    directory = Path(__file__).resolve().parent / "Results" / "Diagnostics"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Separate files avoid concurrent writes from the GA worker pool.
        with (directory / f"opf_pv_boundary_{getpid()}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, allow_nan=False) + "\n")
    except OSError:
        desktop_log.warning("Could not persist OPF PV boundary diagnostic: %s", event)
