"""One-step current-summation FBS for balanced constant-power radial feeders."""
import cmath
from dataclasses import dataclass, field
from math import degrees, isfinite, sqrt
from .network_model import NetworkModel, _finite


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
            config: FBSConfig) -> PowerFlowResult:
    order = network.radial_order()
    ids = {b.bus_id for b in network.buses}
    if (not isinstance(config.max_iterations, int) or isinstance(config.max_iterations, bool)
            or config.max_iterations < 1):
        raise ValueError("max_iterations must be a positive integer")
    _finite(config.voltage_tolerance_pu, "voltage_tolerance_pu", positive=True)
    _finite(config.slack_angle_deg, "slack_angle_deg")
    for name in operating_point.__dataclass_fields__:
        values = getattr(operating_point, name)
        if set(values) != ids:
            raise ValueError(f"{name} must contain exactly every network bus (explicit zeros)")
        for value in values.values():
            _finite(value, name, minimum=0 if name in ("p_load_kw", "q_load_kvar", "p_pv_kw") else None)
    slack = next(b for b in network.buses if b.bus_id == order.slack_bus_id)
    sbase = network.base_power_kva
    zbase = slack.base_kv ** 2 / (sbase / 1000)
    ibase = sbase / (sqrt(3) * slack.base_kv)
    impedances = {l.line_id: complex(l.r_ohm, l.x_ohm) / zbase for l in network.lines}
    children = {line_id: bus for bus, line_id in order.parent_line_by_bus.items()}
    op = operating_point
    demand = {i: complex(op.p_load_kw[i] - op.p_pv_kw[i] - op.p_bess_kw[i],
                         op.q_load_kvar[i] - op.q_pv_kvar[i] - op.q_bess_kvar[i]) / sbase for i in ids}
    reference = cmath.rect(slack.v_set_pu, config.slack_angle_deg * cmath.pi / 180)
    voltages = {i: reference for i in ids}
    currents = {l.line_id: 0j for l in network.lines}
    history = [voltages.copy()] if config.record_history else []
    converged, delta = False, float("inf")
    completed_sweeps = 0
    message = "Maximum iterations reached; last iterate is diagnostic only"
    for iteration in range(1, config.max_iterations + 1):
        if any(abs(v) < 1e-12 for v in voltages.values()):
            message = "Near-zero bus voltage; constant-power current is undefined"
            break
        injections = {i: (demand[i] / voltages[i]).conjugate() for i in ids}
        new_currents = {}
        for line_id in order.backward_line_ids:
            bus = children[line_id]
            new_currents[line_id] = injections[bus] + sum(
                (new_currents[order.parent_line_by_bus[c]] for c in order.children_by_bus[bus]), 0j)
        new_voltages = {order.slack_bus_id: reference}
        for line_id in order.forward_line_ids:
            bus = children[line_id]
            new_voltages[bus] = new_voltages[order.parent_bus_by_bus[bus]] - impedances[line_id] * new_currents[line_id]
        if any(not isfinite(v.real) or not isfinite(v.imag) for v in [*new_currents.values(), *new_voltages.values()]):
            message = "Non-finite numerical iterate; power flow failed"
            break
        delta = max(abs(new_voltages[i] - voltages[i]) for i in ids)
        voltages, currents = new_voltages, new_currents
        completed_sweeps = iteration
        if config.record_history:
            history.append(voltages.copy())
        if delta <= config.voltage_tolerance_pu:
            converged, message = True, "Converged"
            break
    # Retain voltage/current from the same completed sweep for Ohm's law.
    sending = {l: voltages[order.parent_bus_by_bus[children[l]]] * currents[l].conjugate() * sbase for l in currents}
    losses = {l: abs(currents[l]) ** 2 * impedances[l] * sbase for l in currents}
    slack_power = demand[order.slack_bus_id] * sbase + sum(
        (sending[order.parent_line_by_bus[c]] for c in order.children_by_bus[order.slack_bus_id]), 0j)
    return PowerFlowResult(
        voltages, {i: abs(v) for i, v in voltages.items()},
        {i: degrees(cmath.phase(v)) for i, v in voltages.items()},
        {l: abs(i) * ibase for l, i in currents.items()},
        {l: s.real for l, s in sending.items()}, {l: s.imag for l, s in sending.items()},
        {l: s.real for l, s in losses.items()}, {l: s.imag for l, s in losses.items()},
        sum(s.real for s in losses.values()), sum(s.imag for s in losses.values()),
        slack_power.real, slack_power.imag, converged, completed_sweeps, delta, message, currents, history)
