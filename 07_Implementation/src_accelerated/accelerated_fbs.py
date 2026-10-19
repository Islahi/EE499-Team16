"""Optional array, Numba and CuPy implementations of one FBS power-flow step."""
import cmath
from math import degrees, sqrt

import numpy as np

from .progress import ProgressEvent


def backend_status():
    status = {
        "python": "available", "numpy": "available",
        "numba": "unavailable", "gpu": "unavailable",
    }
    try:
        import numba  # noqa: F401
        status["numba"] = "available"
    except ImportError:
        status["numba"] = "install numba"
    try:
        import cupy as cp
        count = cp.cuda.runtime.getDeviceCount()
        status["gpu"] = f"available ({count} CUDA device{'s' if count != 1 else ''})" if count else "no CUDA device"
    except (ImportError, RuntimeError) as error:
        status["gpu"] = f"unavailable ({error})"
    return status


def backend_available(backend):
    """Return whether a named backend can run, plus a user-facing reason."""
    if backend in ("python", "numpy"):
        return True, f"{backend.title()} backend is available"
    status = backend_status()
    if backend not in status:
        return False, f"Unknown backend: {backend}"
    message = status[backend]
    return message.startswith("available"), message


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
        except ImportError as error:
            raise RuntimeError("Numba backend selected, but numba is not installed") from error
        _NUMBA_SWEEPS = njit(cache=True)(_cpu_sweeps)
    return _NUMBA_SWEEPS(*arguments)


def _gpu_sweeps(demand, impedance, from_bus, to_bus, reference,
                max_iterations, tolerance, record_history):
    try:
        import cupy as cp
    except ImportError as error:
        raise RuntimeError("GPU backend selected, but CuPy is not installed") from error
    if cp.cuda.runtime.getDeviceCount() < 1:
        raise RuntimeError("GPU backend selected, but no CUDA device is available")
    demand = cp.asarray(demand)
    impedance = cp.asarray(impedance)
    from_bus = cp.asarray(from_bus)
    to_bus = cp.asarray(to_bus)
    voltage = cp.full(len(demand), reference, dtype=cp.complex128)
    current = cp.zeros(len(impedance), dtype=cp.complex128)
    history = [voltage.copy()] if record_history else []
    converged, completed, delta, status = False, 0, float("inf"), 0
    for iteration in range(1, max_iterations + 1):
        if bool(cp.any(cp.abs(voltage) < 1e-12).item()):
            status = 1
            break
        injection = cp.conj(demand / voltage)
        total = injection.copy()
        for line_index in range(len(impedance) - 1, -1, -1):
            child = int(to_bus[line_index].item())
            parent = int(from_bus[line_index].item())
            current[line_index] = total[child]
            total[parent] += current[line_index]
        new_voltage = cp.full_like(voltage, reference)
        for line_index in range(len(impedance)):
            parent = int(from_bus[line_index].item())
            child = int(to_bus[line_index].item())
            new_voltage[child] = new_voltage[parent] - impedance[line_index] * current[line_index]
        if not bool(cp.all(cp.isfinite(new_voltage)).item() and cp.all(cp.isfinite(current)).item()):
            status = 2
            break
        delta = float(cp.max(cp.abs(new_voltage - voltage)).item())
        voltage = new_voltage
        completed = iteration
        if record_history:
            history.append(voltage.copy())
        if delta <= tolerance:
            converged = True
            break
    history_array = cp.stack(history) if history else cp.empty((0, len(demand)), dtype=cp.complex128)
    return (cp.asnumpy(voltage), cp.asnumpy(current), converged, completed,
            delta, status, cp.asnumpy(history_array))


def run_array_fbs(network, operating_point, config, progress=None):
    """Run the selected numeric backend and rebuild the public dictionary result."""
    from .fbs import PowerFlowResult

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
    if config.backend == "numpy":
        values = _cpu_sweeps(*arguments)
    elif config.backend == "numba":
        values = _numba_sweeps(*arguments)
    elif config.backend == "gpu":
        values = _gpu_sweeps(*arguments)
    else:
        raise ValueError(f"Unsupported accelerated FBS backend: {config.backend}")
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
