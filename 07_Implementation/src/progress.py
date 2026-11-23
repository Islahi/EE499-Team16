"""Qt-free work counters and throttled progress snapshots, not time estimates."""
from dataclasses import dataclass
from time import perf_counter

RUN_LOG_INTERVAL_SECONDS = 5.0
RUN_HEARTBEAT_SECONDS = 30.0


class RunCancelled(Exception):
    """Cooperative cancellation at a numerical phase boundary."""


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    completed: int
    total: int
    detail: str = ""
    log: bool = False
    hour_finished: bool = False

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
    levels = ("GWO", "GA", "Candidate", "Forecast", "Simulation", "Base case", "Control", "FBS")

    def __init__(self, stage_callback, progress_callback, interval=0.25, *,
                 hourly_log=None, cancelled=None):
        self.stage_callback = stage_callback
        self.progress_callback = progress_callback
        self.interval = interval
        self.events = {}
        self.last_sent = 0.0
        self.hourly_log = hourly_log
        self.pending_hours = []
        self.cancelled = cancelled
        self.last_stage = "Operation"

    def check_cancelled(self):
        if self.cancelled is not None and self.cancelled():
            raise RunCancelled()

    def begin_commit(self):
        self.check_cancelled()
        self.cancelled = None

    def __call__(self, message):
        self.check_cancelled()
        self.flush()
        self.events.clear()
        self.last_stage = message
        self.stage_callback(message)

    def flush(self):
        """Retain the latest timestep even when work finishes between UI ticks."""
        self.flush_hours()
        if self.events:
            self.progress_callback((dict(self.events),True))
            self.last_sent = perf_counter()

    def flush_hours(self):
        if self.pending_hours:
            self.hourly_log(tuple(self.pending_hours))
            self.pending_hours.clear()

    def progress(self, event):
        self.check_cancelled()
        if event.phase in ("Forecast", "GWO", "GA") and event.phase not in self.events:
            self.events.clear()
        if event.phase in self.levels:
            index = self.levels.index(event.phase)
            for child in self.levels[index + 1:]:
                self.events.pop(child, None)
        self.events[event.phase] = event
        now = perf_counter()
        if self.hourly_log is not None and event.hour_finished:
            self.pending_hours.append(f"Time step {event.completed}/{event.total} | {event.detail}")
            if len(self.pending_hours) >= 128:
                self.flush_hours()
        if event.log or now - self.last_sent >= self.interval:
            self.flush_hours()
            self.progress_callback((dict(self.events), event.log))
            self.last_sent = now


def format_duration(seconds):
    seconds = max(0, int(seconds))
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
