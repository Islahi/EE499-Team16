"""Derived electrical readings in source-rooted FBS orientation."""
from math import hypot


def line_ends(network):
    order = network.radial_order()
    return {line: (order.parent_bus_by_bus[child], child)
            for child, line in order.parent_line_by_bus.items()}


def branch_readings(flow, line, ends):
    parent, child = ends
    values = dict(from_bus=parent, to_bus=child, resistance_ohm=line.r_ohm,
                  reactance_ohm=line.x_ohm, ampacity_a=line.ampacity_a)
    current = flow.branch_current_a.get(line.line_id)
    voltage, angle = flow.voltage_mag_pu, flow.voltage_angle_deg
    valid = flow.converged and parent in voltage and child in voltage
    values.update(
        loading_percent=100 * current / line.ampacity_a if valid and current is not None and line.ampacity_a else None,
        from_voltage_pu=voltage[parent] if valid else None, to_voltage_pu=voltage[child] if valid else None,
        from_angle_deg=angle[parent] if valid else None, to_angle_deg=angle[child] if valid else None,
        angle_difference_deg=angle[parent] - angle[child] if valid else None,
        receiving_p_kw=flow.branch_p_kw[line.line_id] - flow.line_loss_p_kw[line.line_id] if valid else None,
        receiving_q_kvar=flow.branch_q_kvar[line.line_id] - flow.line_loss_q_kvar[line.line_id] if valid else None,
        overloaded=current > line.ampacity_a + 1e-6 if valid and current is not None and line.ampacity_a else None)
    return values


BRANCH_FIELDS = ("from_bus", "to_bus", "resistance_ohm", "reactance_ohm", "ampacity_a",
                 "loading_percent", "from_voltage_pu", "to_voltage_pu", "from_angle_deg",
                 "to_angle_deg", "angle_difference_deg", "receiving_p_kw", "receiving_q_kvar", "overloaded")
BUS_FIELDS = ("base_kv", "voltage_kv", "slack_setpoint_pu", "voltage_margin_pu", "installed_pv_kw",
              "bess_s_kva", "bess_soc_percent", "bess_energy_kwh", "bess_rating_kw", "bess_capacity_kwh",
              "inverter_rating_kva", "inverter_loading_percent", "uncontrolled_voltage_pu", "before_correction_voltage_pu")


def battery_ratings(context):
    manual = context.get("Manual BESS")
    units = [manual] if isinstance(manual, dict) else context.get("Selected BESS fleet", ())
    ratio = context.get("Effective inverter sizing (kVA/kW)")
    return {unit["bus_id"]: (unit["power_rating_kw"], unit["energy_capacity_kwh"],
                             unit["power_rating_kw"] * ratio if ratio is not None else None)
            for unit in units}


def bus_readings(step, bus, pv_rating, bounds, battery=None):
    flow = step.power_flow
    voltage = flow.voltage_mag_pu.get(bus.bus_id) if flow.converged else None
    point = step.operating_point
    state = (getattr(step, "fleet_states", None) or {}).get(bus.bus_id)
    event = getattr(step, "dispatch", None)
    if state is None and event and event.bus_id == bus.bus_id:
        state = step.bess_state
    s = hypot(point.p_bess_kw[bus.bus_id], point.q_bess_kvar[bus.bus_id]) if flow.converged else None
    rating_kw, capacity, inverter = battery if battery and state is not None else (None, None, None)
    return dict(base_kv=bus.base_kv, voltage_kv=voltage * bus.base_kv if voltage is not None else None,
                slack_setpoint_pu=bus.v_set_pu if bus.is_slack else None,
                voltage_margin_pu=min(voltage - bounds[0], bounds[1] - voltage) if voltage is not None and bounds else None,
                installed_pv_kw=pv_rating, bess_s_kva=s if state is not None else None,
                bess_soc_percent=state.soc * 100 if state and flow.converged else None,
                bess_energy_kwh=state.energy_kwh if state and flow.converged else None,
                bess_rating_kw=rating_kw, bess_capacity_kwh=capacity, inverter_rating_kva=inverter,
                inverter_loading_percent=100*s/inverter if inverter and s is not None else None,
                uncontrolled_voltage_pu=(getattr(step, "uncontrolled_voltage_pu", None) or {}).get(bus.bus_id),
                before_correction_voltage_pu=(getattr(step, "before_correction_voltage_pu", None) or {}).get(bus.bus_id))

