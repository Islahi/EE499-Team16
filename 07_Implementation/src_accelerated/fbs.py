"""One-step current-summation FBS for balanced constant-power radial feeders."""
import cmath
from dataclasses import dataclass, field
from math import degrees, isfinite, sqrt

import numpy as np

from .network_model import NetworkModel, _finite
from .progress import ProgressEvent


@dataclass
class OperatingPoint:
    p_load_kw: dict[int, float]
    q_load_kvar: dict[int, float]
    p_pv_kw: dict[int, float]
    q_pv_kvar: dict[int, float]
    p_bess_kw: dict[int, float]
    q_bess_kvar: dict[int, float]


@dataclass(frozen=True)
class FBSConfig:
    max_iterations: int = 100
    voltage_tolerance_pu: float = 1e-6
    slack_angle_deg: float = 0.0
    record_history: bool = False
    backend: str = "numba"

    def __post_init__(self):
        validate_config(self)


@dataclass
class PowerFlowResult:
    voltage_complex_pu: dict[int, complex]
    voltage_mag_pu: dict[int, float]
    voltage_angle_deg: dict[int, float]
    branch_current_a: dict[str, float]
    branch_p_kw: dict[str, float]
    branch_q_kvar: dict[str, float]
    line_loss_p_kw: dict[str, float]
    line_loss_q_kvar: dict[str, float]
    total_loss_p_kw: float
    total_loss_q_kvar: float
    slack_p_kw: float
    slack_q_kvar: float
    converged: bool
    iterations: int
    max_delta_v_pu: float
    message: str
    branch_current_pu: dict[str, complex] = field(default_factory=dict)
    voltage_history: list[dict[int, complex]] = field(default_factory=list)


def run_fbs(network: NetworkModel, operating_point: OperatingPoint,
            config: FBSConfig, *, progress=None) -> PowerFlowResult:
    return run_array_fbs(network, operating_point, config, progress)


def validate_config(config):
    if not isinstance(config, FBSConfig) or config.backend != "numba":
        raise ValueError("Only FBS — Numba (CPU) is supported for new execution")
    if isinstance(config.max_iterations, bool) or not isinstance(config.max_iterations, int) or config.max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    _finite(config.voltage_tolerance_pu, "voltage_tolerance_pu", positive=True)
    _finite(config.slack_angle_deg, "slack_angle_deg")


def backend_status():
    try:
        import numba, llvmlite
        return {"numba": f"available ({numba.__version__}; llvmlite {llvmlite.__version__})"}
    except Exception as error:
        return {"numba": f"unavailable: {error}. Install requirements-accelerated.txt with the application interpreter"}


def backend_available(backend):
    if backend != "numba":
        return False, "Only FBS — Numba (CPU) is supported"
    message = backend_status()["numba"]
    return message.startswith("available"), message


def warm_numba():
    """Compile/execute the production signature off the GUI thread; return measured JIT time."""
    from time import perf_counter
    started = perf_counter()
    values = _numba_sweeps(np.array([0j, .01+.005j]), np.array([.01+.01j]),
        np.array([0], dtype=np.int64), np.array([1], dtype=np.int64),
        complex(1), 100, 1e-8, False)
    if not values[2] or not np.isfinite(values[0]).all():
        raise RuntimeError("Numba readiness case failed to converge")
    readiness = perf_counter()-started
    warm_start = perf_counter()
    _numba_sweeps(np.array([0j, .01+.005j]), np.array([.01+.01j]),
        np.array([0],dtype=np.int64), np.array([1],dtype=np.int64),complex(1),100,1e-8,False)
    return {"jit_readiness_seconds":readiness, "warm_kernel_seconds":perf_counter()-warm_start, "backend":"numba"}


def _cpu_sweeps(demand, impedance, from_bus, to_bus, reference,
                max_iterations, tolerance, record_history):
    voltage = np.full(len(demand), reference, dtype=np.complex128)
    current = np.zeros(len(impedance), dtype=np.complex128)
    history = np.empty((max_iterations + 1, len(demand)), dtype=np.complex128)
    history[0] = voltage
    converged = False
    delta = np.inf
    completed = 0
    status = 0
    for iteration in range(1, max_iterations + 1):
        if np.any(np.abs(voltage) < 1e-12):
            status = 1
            break
        injection = np.conjugate(demand / voltage)
        total = injection.copy()
        for line_index in range(len(impedance) - 1, -1, -1):
            child = to_bus[line_index]
            parent = from_bus[line_index]
            current[line_index] = total[child]
            total[parent] += current[line_index]
        new_voltage = np.empty_like(voltage)
        new_voltage[:] = reference
        for line_index in range(len(impedance)):
            parent = from_bus[line_index]
            child = to_bus[line_index]
            new_voltage[child] = new_voltage[parent] - impedance[line_index] * current[line_index]
        if not (np.all(np.isfinite(new_voltage.real)) and np.all(np.isfinite(new_voltage.imag))
                and np.all(np.isfinite(current.real)) and np.all(np.isfinite(current.imag))):
            status = 2
            break
        delta = float(np.max(np.abs(new_voltage - voltage)))
        voltage = new_voltage
        completed = iteration
        if record_history:
            history[completed] = voltage
        if delta <= tolerance:
            converged = True
            break
    return voltage, current, converged, completed, delta, status, history[:completed + 1]


_NUMBA_SWEEPS = None


def _numba_sweeps(*arguments):
    global _NUMBA_SWEEPS
    if _NUMBA_SWEEPS is None:
        try:
            from numba import njit
        except Exception as error:
            raise RuntimeError("Mandatory Numba import failed. Install requirements-accelerated.txt with the application interpreter: "+str(error)) from error
        _NUMBA_SWEEPS = njit(cache=True)(_cpu_sweeps)
    try:
        return _NUMBA_SWEEPS(*arguments)
    except Exception as error:
        import sys
        raise RuntimeError(f"FBS Numba compilation/execution failed in {sys.executable}: {error}. "
                           "Install compatible numba/numpy/llvmlite using this interpreter; no fallback is enabled") from error


def run_array_fbs(network, operating_point, config, progress=None):
    """Run one array backend and rebuild the public dictionary result."""
    validate_config(config)
    ids = {bus.bus_id for bus in network.buses}
    for name in operating_point.__dataclass_fields__:
        values = getattr(operating_point, name)
        if set(values) != ids:
            raise ValueError(f"{name} must contain exactly every network bus (explicit zeros)")
        for value in values.values():
            _finite(value, name, minimum=0 if name in ("p_load_kw", "q_load_kvar", "p_pv_kw") else None)
    order = network.radial_order()
    buses = sorted(network.buses, key=lambda bus: bus.bus_id)
    bus_ids = [bus.bus_id for bus in buses]
    bus_index = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    line_lookup = {line.line_id: line for line in network.lines}
    line_ids = list(order.forward_line_ids)
    lines = [line_lookup[line_id] for line_id in line_ids]
    child_by_line = {line_id: bus_id for bus_id, line_id in order.parent_line_by_bus.items()}
    child_ids = [child_by_line[line_id] for line_id in line_ids]
    from_bus = np.asarray([
        bus_index[order.parent_bus_by_bus[child_id]] for child_id in child_ids
    ], dtype=np.int64)
    to_bus = np.asarray([bus_index[child_id] for child_id in child_ids], dtype=np.int64)
    slack = next(bus for bus in buses if bus.bus_id == order.slack_bus_id)
    sbase = network.base_power_kva
    zbase = slack.base_kv ** 2 / (sbase / 1000)
    ibase = sbase / (sqrt(3) * slack.base_kv)
    impedance = np.asarray([complex(line.r_ohm, line.x_ohm) / zbase for line in lines])
    demand = np.asarray([
        complex(operating_point.p_load_kw[bus_id] - operating_point.p_pv_kw[bus_id]
                - operating_point.p_bess_kw[bus_id],
                operating_point.q_load_kvar[bus_id] - operating_point.q_pv_kvar[bus_id]
                - operating_point.q_bess_kvar[bus_id]) / sbase
        for bus_id in bus_ids
    ])
    reference = cmath.rect(slack.v_set_pu, config.slack_angle_deg * cmath.pi / 180)
    arguments = (demand, impedance, from_bus, to_bus, reference,
                 config.max_iterations, config.voltage_tolerance_pu, config.record_history)
    if progress is not None:
        progress(ProgressEvent("FBS", 0, config.max_iterations,
                               f"Starting {config.backend} power flow"))
    values = _numba_sweeps(*arguments)
    voltage, current, converged, completed, delta, status, history_array = values
    if progress is not None:
        progress(ProgressEvent("FBS", completed, config.max_iterations,
                               f"{config.backend}; voltage error {delta:.3g} pu"))
    message = ("Converged" if converged else
               "Near-zero bus voltage; constant-power current is undefined" if status == 1 else
               "Non-finite numerical iterate; power flow failed" if status == 2 else
               "Maximum iterations reached; last iterate is diagnostic only")
    sending = voltage[from_bus] * np.conjugate(current) * sbase
    losses = np.abs(current) ** 2 * impedance * sbase
    slack_index = bus_index[order.slack_bus_id]
    slack_power = demand[slack_index] * sbase + sending[from_bus == slack_index].sum()
    voltages = {bus_id: complex(voltage[index]) for index, bus_id in enumerate(bus_ids)}
    currents = {line_id: complex(current[index]) for index, line_id in enumerate(line_ids)}
    histories = [{bus_id: complex(row[index]) for index, bus_id in enumerate(bus_ids)}
                 for row in history_array] if config.record_history else []
    return PowerFlowResult(
        voltages, {bus_id: abs(value) for bus_id, value in voltages.items()},
        {bus_id: degrees(cmath.phase(value)) for bus_id, value in voltages.items()},
        {line_id: abs(currents[line_id]) * ibase for line_id in line_ids},
        {line_id: float(sending[index].real) for index, line_id in enumerate(line_ids)},
        {line_id: float(sending[index].imag) for index, line_id in enumerate(line_ids)},
        {line_id: float(losses[index].real) for index, line_id in enumerate(line_ids)},
        {line_id: float(losses[index].imag) for index, line_id in enumerate(line_ids)},
        float(losses.real.sum()), float(losses.imag.sum()), float(slack_power.real),
        float(slack_power.imag), bool(converged), int(completed), float(delta), message,
        currents, histories)
