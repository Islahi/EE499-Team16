"""Qt-free work counters and throttled progress snapshots, not time estimates."""
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    completed: int
    total: int
    detail: str = ""
    log: bool = False

    @property
    def percent(self):
        return 100 * self.completed / self.total if self.total else 0.0

    def text(self):
        return f"{self.phase} {self.completed}/{self.total}: {self.detail}"


class StageReporter:
    """Keep the existing stage(message) interface and expose stage.progress(event).

    Numerical hooks update the latest nested counters. Only snapshots at most
    four times per second (plus explicit boundaries) enter the GUI event queue.
    """
    levels = ("GWO", "Candidate", "Scenario", "Simulation", "Control", "FBS")

    def __init__(self, stage_callback, progress_callback, interval=0.25):
        self.stage_callback = stage_callback
        self.progress_callback = progress_callback
        self.interval = interval
        self.events = {}
        self.last_sent = 0.0

    def __call__(self, message):
        self.events.clear()
        self.stage_callback(message)

    def progress(self, event):
        if event.phase in ("ARIMA", "Scenarios", "GWO") and event.phase not in self.events:
            self.events.clear()
        if event.phase in self.levels:
            index = self.levels.index(event.phase)
            for child in self.levels[index + 1:]:
                self.events.pop(child, None)
        self.events[event.phase] = event
        now = perf_counter()
        if event.log or now - self.last_sent >= self.interval:
            self.progress_callback((dict(self.events), event.log))
            self.last_sent = now


def format_duration(seconds):
    seconds = max(0, int(seconds))
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
