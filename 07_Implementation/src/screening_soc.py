"""Fast year-chronological SOC warm-starts for short GWO screening windows.

The proxy is *not* a power-flow calculation or a replacement for annual FBS.
It derives an approximate candidate-specific energy inventory from all earlier
hourly load/PV and the previously verified fleet's pre-control voltage series.
Only the proposed new BESS is approximated; previously installed BESS units
use their actual chronological SOC from the accepted annual run. Every finalist
is independently verified for 8760/8784 consecutive hours with nonlinear FBS.
"""
from dataclasses import dataclass, field

import numpy as np

from .bess import BESSConfig, BESSState, step_bess
from .voltage_dispatch import VoltageSupport


@dataclass
class ChronologicalSOCWarmStarts:
    """Small read-only arrays shared into GWO workers, cached by design tuple."""
    starts: tuple[int, ...]
    net_surplus_kw: np.ndarray
    grid_import_kw: np.ndarray
    shed_kw: np.ndarray
    voltage_deficits: np.ndarray
    voltage_margins: np.ndarray
    observed_bus_ids: tuple[int, ...]
    sensitivity: dict
    grid_import_limit_kw: float | None
    installed_energies_at_start: dict
    dt_hours: float = 1.0
    _cached: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_annual(cls, network, profiles, annual_result, settings, window_indices):
        n = len(profiles.timestamps)
        if len(annual_result.steps) != n or profiles.dt_hours != 1.0:
            raise ValueError('Chronological SOC proxy requires the entire hourly annual reference')
        starts = tuple(int(group[0]) for group in window_indices)
        observed = tuple(sorted(b.bus_id for b in network.buses if not b.is_slack))
        deficits = np.zeros((n, len(observed)), dtype=np.float32)
        margins = np.zeros((n, len(observed)), dtype=np.float32)
        imports = np.zeros(n, dtype=np.float64)
        shed = np.zeros(n, dtype=np.float64)
        for t, step in enumerate(annual_result.steps):
            voltage = step.pre_control_voltage_pu
            if voltage is None:
                raise ValueError('Missing pre-corrective voltage records for annual SOC proxy')
            for j, bus in enumerate(observed):
                v = float(voltage[bus])
                deficits[t, j] = max(0., settings.voltage_min_pu - v)
                margins[t, j] = v - settings.voltage_min_pu
            imports[t] = float(step.power_flow.slack_p_kw)
            shed[t] = float(step.shedding_kw or 0.)
        load = np.zeros(n, dtype=np.float64)
        pv = np.zeros(n, dtype=np.float64)
        for arr in profiles.load_p_kw.values():
            load += np.asarray(arr, dtype=np.float64)
        for arr in profiles.pv_p_kw.values():
            pv += np.asarray(arr, dtype=np.float64)
        installed_at_start = {}
        for idx in starts:
            earlier = annual_result.steps[idx-1] if idx > 0 else None
            if earlier is not None and earlier.fleet_states:
                installed_at_start[idx] = {int(bus): float(state.energy_kwh)
                                           for bus, state in earlier.fleet_states.items()}
            else:
                installed_at_start[idx] = {}
        return cls(starts, np.maximum(0., pv-load), imports, shed,
                   deficits, margins, observed, VoltageSupport(network).sensitivity,
                   settings.grid_import_limit_kw, installed_at_start)

    def candidate_energy_at_windows(self, config: BESSConfig):
        key = (config.bus_id, config.energy_capacity_kwh, config.power_rating_kw,
               config.soc_min, config.soc_max, config.soc_initial,
               config.eta_charge, config.eta_discharge)
        if key in self._cached:
            return self._cached[key]
        sensitivity = np.array([self.sensitivity[config.bus_id].get(b, 0.)
                                for b in self.observed_bus_ids], dtype=np.float64)
        affected = sensitivity > 1e-10
        # How many kW would be needed to close a pre-corrective deficit in the
        # linearized active-power-only feeder approximation? This is diagnostic
        # severity, NOT a promised corrective command.
        if np.any(affected):
            need = np.max(self.voltage_deficits[:, affected] /
                          sensitivity[affected][None, :], axis=1)
            # Voltage margin at sites electrically affected by this battery.
            charge_margin = np.min(self.voltage_margins[:, affected] /
                                   sensitivity[affected][None, :], axis=1)
        else:
            need = np.zeros(len(self.grid_import_kw))
            charge_margin = np.zeros(len(self.grid_import_kw))
        start_set = set(self.starts)
        energy = config.energy_capacity_kwh * config.soc_initial
        state = BESSState(energy, config.soc_initial)
        results = {}
        for t in range(len(self.grid_import_kw)):
            if t in start_set:
                results[t] = float(state.energy_kwh)
            if self.shed_kw[t] > 1e-6 or need[t] > 1e-6:
                # Conservative proxy of electrical shortage; actual MPC can
                # preserve more reserve or choose a different power schedule.
                request = min(config.power_rating_kw,
                              max(.50 * self.shed_kw[t], .75 * need[t]))
            else:
                charge_limit = max(0., float(charge_margin[t]))
                if self.grid_import_limit_kw is not None:
                    grid_headroom = max(0., self.grid_import_limit_kw - max(0., self.grid_import_kw[t]))
                else:
                    grid_headroom = config.power_rating_kw
                # PV surplus is allowed if predicted local voltage permits it;
                # other hours may draw grid energy only with voltage headroom.
                available_kw = max(self.net_surplus_kw[t],
                                   min(grid_headroom, config.power_rating_kw))
                request = -min(config.power_rating_kw, available_kw, charge_limit)
            action = step_bess(config, state, request, self.dt_hours)
            state = BESSState(action.energy_after_kwh, action.soc_after)
        self._cached[key] = results
        return results

    def window_start_energy(self, index, configs, new_config):
        candidate = self.candidate_energy_at_windows(new_config)
        estimates = {}
        for config in configs:
            if config.bus_id == new_config.bus_id:
                estimates[config.bus_id] = candidate[index]
            else:
                estimates[config.bus_id] = self.installed_energies_at_start.get(index, {}).get(
                    config.bus_id, config.energy_capacity_kwh * config.soc_initial)
        return estimates
