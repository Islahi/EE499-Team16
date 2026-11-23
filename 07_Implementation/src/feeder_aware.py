"""Lateral-aware technical evidence for radial BESS placement.

An IEEE-33 bus network is *one* feeder with multiple laterals. Group buses by
last electrical branching junction on their path from the slack, not by bus IDs.
No hypothetical network geography or fixed IEEE bus numbering is assumed.
"""
from dataclasses import dataclass
from math import ceil, isfinite


@dataclass(frozen=True)
class ImprovementRules:
    minimum_shedding_percent: float = 10.0
    minimum_voltage_percent: float = 10.0
    maximum_worsening_percent: float = 1.0
    exclude_installed_laterals: bool = False

    def __post_init__(self):
        for name in ('minimum_shedding_percent', 'minimum_voltage_percent',
                     'maximum_worsening_percent'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 100:
                raise ValueError(f'{name} must be a percent from 0 to 100')


def lateral_map(network):
    """Group buses below the most recent branching junction, with trunk IDs.

    E.g. in IEEE 33, both 14 and 17 descend from junction 6 via child 7,
    whereas 26..33 descend via child 26. These are electrical laterals, not
    geographically separate distribution feeders.
    """
    order = network.radial_order()
    slack = order.slack_bus_id
    child_counts = {bus: len(children) for bus, children in order.children_by_bus.items()}
    groups = {slack: 'slack'}
    for line_id in order.forward_line_ids:
        # Parent bus is supplied by radial_order; line order is parent-first.
        bus = next(b for b, parent_line in order.parent_line_by_bus.items() if parent_line == line_id)
        parent = order.parent_bus_by_bus[bus]
        if child_counts[parent] > 1:
            groups[bus] = f'{parent}->{bus}'
        else:
            groups[bus] = groups[parent] if parent != slack else f'trunk:{bus}'
    return groups


def summarize_laterals(network, result, voltage_min_pu, *, profiles=None, indices=None):
    """Accumulate pre-shedding voltage deficits and actual shed kWh per lateral."""
    mapping = lateral_map(network)
    groups = {label: {'lateral': label, 'buses': [], 'voltage_deficit_pu_hours': 0.0,
                      'shedding_kwh': 0.0, 'requested_kwh': 0.0,
                      'undervoltage_bus_hours': 0.0}
              for label in sorted(set(mapping.values()) - {'slack'})}
    for bus, label in mapping.items():
        if label != 'slack':
            groups[label]['buses'].append(bus)
    selected = range(len(result.steps)) if indices is None else indices
    for i in selected:
        step = result.steps[i]
        volts = step.pre_control_voltage_pu
        sheds = step.shedding_by_bus_kw
        if not isinstance(volts, dict) or not isinstance(sheds, dict):
            raise ValueError('Lateral metrics require captured pre-correction voltages and per-bus shedding')
        for bus, label in mapping.items():
            if label == 'slack':
                continue
            row = groups[label]
            deficit = max(0.0, voltage_min_pu - float(volts[bus]))
            row['voltage_deficit_pu_hours'] += deficit * result.dt_hours
            row['undervoltage_bus_hours'] += (deficit > 1e-10) * result.dt_hours
            row['shedding_kwh'] += max(0., float(sheds.get(bus, 0.))) * result.dt_hours
            if profiles is not None:
                request = profiles.load_p_kw.get(bus)
                if request is not None:
                    row['requested_kwh'] += float(request[i]) * result.dt_hours
    for row in groups.values():
        row['buses'].sort()
        row['shed_share_percent'] = (100.0 * row['shedding_kwh'] / row['requested_kwh']
                                     if row['requested_kwh'] > 1e-8 else 0.0)
    return groups


def _gain(before, after):
    if before <= 1e-8:
        return 0.0 if after <= 1e-8 else -100.0 * after / max(after, 1.0)
    return 100.0 * (before - after) / before


def technical_improvement(before, after, target, rules):
    """Require a meaningful benefit on target lateral without harming other areas.

    OR criterion: target shedding OR voltage deficit improves by specified %;
    the complementary metric must not deteriorate beyond tolerance. Also
    protect annual system totals and all other lateral metrics from damage.
    """
    if target not in before or target not in after:
        return {'acceptable': False, 'reason': 'target lateral missing from annual assessment'}
    fields = ('shedding_kwh', 'voltage_deficit_pu_hours')
    changes = {}
    for label in before:
        changes[label] = {key: _gain(before[label][key], after[label][key]) for key in fields}
    local = changes[target]
    shed_gain, voltage_gain = local[fields[0]], local[fields[1]]
    limit = rules.maximum_worsening_percent
    sufficient = ((shed_gain >= rules.minimum_shedding_percent and voltage_gain >= -limit)
                  or (voltage_gain >= rules.minimum_voltage_percent and shed_gain >= -limit))
    if not sufficient:
        return {'acceptable': False, 'reason': 'target lateral did not meet either improvement threshold',
                'target': target, 'shedding_improvement_percent': shed_gain,
                'voltage_improvement_percent': voltage_gain, 'by_lateral': changes}
    for key in fields:
        # Global totals should not be sacrificed for gains on a single lateral.
        old = sum(row[key] for row in before.values())
        new = sum(row[key] for row in after.values())
        if new - old > max(1e-6, limit / 100. * max(old, 1e-6)):
            return {'acceptable': False, 'reason': f'network-wide {key} deteriorated',
                    'target': target, 'by_lateral': changes}
        # Restrict damage elsewhere; a practically zero baseline has a small
        # absolute tolerance instead of an unstable percentage ratio.
        for label in before:
            if label == target:
                continue
            baseline = before[label][key]
            tolerance = max(1e-5, baseline * limit / 100., old * 0.0001)
            if after[label][key] - baseline > tolerance:
                return {'acceptable': False, 'reason': f'{key} worsened on lateral {label}',
                        'target': target, 'by_lateral': changes}
    return {'acceptable': True, 'reason': 'verified annual technical improvement',
            'target': target, 'shedding_improvement_percent': shed_gain,
            'voltage_improvement_percent': voltage_gain, 'by_lateral': changes}



def incremental_and_cumulative_improvement(current, proposed, initial, target, rules,
                                           *, incremental_floor_percent=0.5):
    """Accept verified electrical reliability benefits without a 10% voltage hurdle.

    Prefer annual shedding relief, with non-deterioration of shedding across
    laterals. Pre-control undervoltage is diagnostic when more demand is served,
    not an acceptance veto; verified final post-control voltage/current
    constraints are enforced by the caller. For voltage-only gains, preserve
    pre-control voltage non-deterioration checks, and never reward extra shedding.
    Keep reported cumulative shedding target informational, not a stage gate.
    """
    if target not in current or target not in proposed or target not in initial:
        return {'acceptable': False, 'reason': 'annual lateral reference missing'}
    fields = ('shedding_kwh', 'voltage_deficit_pu_hours')
    changes = {label: {key: _gain(current[label][key], proposed[label][key])
                       for key in fields} for label in current}
    local = changes[target]
    shed_gain, voltage_gain = local[fields[0]], local[fields[1]]
    old_shed = current[target]['shedding_kwh']
    new_shed = proposed[target]['shedding_kwh']
    old_deficit = current[target]['voltage_deficit_pu_hours']
    new_deficit = proposed[target]['voltage_deficit_pu_hours']
    # Avoid accepting numerical noise; do not demand an arbitrary percentage
    # voltage improvement when only 0.001 pu is needed for compliance.
    shedding_relief = (old_shed - new_shed > max(1e-4, old_shed*1e-6))
    voltage_relief = (old_deficit - new_deficit > max(1e-6, old_deficit*1e-6))
    voltage_compliant = new_deficit <= 1e-6
    shed_cumulative = _gain(initial[target]['shedding_kwh'], new_shed)
    voltage_cumulative = _gain(initial[target]['voltage_deficit_pu_hours'], new_deficit)
    result = {'acceptable': False, 'target': target, 'by_lateral': changes,
              'shedding_improvement_percent': shed_gain,
              'voltage_improvement_percent': voltage_gain,
              'voltage_compliant_before_shedding': voltage_compliant,
              'voltage_deficit_reduction_pu_hours': old_deficit-new_deficit,
              'shedding_reduction_kwh': old_shed-new_shed,
              'cumulative_shedding_improvement_percent': shed_cumulative,
              'cumulative_voltage_improvement_percent': voltage_cumulative,
              'cumulative_target_met': (shed_cumulative >= rules.minimum_shedding_percent
                                        or (voltage_compliant and initial[target]['voltage_deficit_pu_hours']>1e-6)),
              'cumulative_target_basis': 'original No-BESS annual shedding; absolute voltage compliance',
              'incremental_floor_percent': None}
    if not (shedding_relief or voltage_relief):
        result['reason'] = 'no measurable marginal reduction in shedding or pre-control undervoltage'
        return result
    # Voltage gains caused by disconnecting MORE of the target's demand must
    # not be labeled an improvement. An absolute kWh tolerance guards rounding.
    if new_shed-old_shed > 1e-4:
        result['reason'] = 'target shedding increased despite voltage improvement'
        return result
    # V14's pre-control voltage deficit is a diagnostic, not a final-state
    # violation. Serving previously shed demand can worsen it, while every
    # post-control voltage and line constraint remains satisfied. Allow that
    # trade only when the target actually sheds less and the full annual
    # nonlinear simulation has independently passed its feasibility checks.
    # Still protect every lateral against increased shedding, and preserve
    # the stronger pre-control voltage safeguards for voltage-only benefits.
    limit = rules.maximum_worsening_percent
    fields_to_guard = ('shedding_kwh',) if shedding_relief else fields
    result['acceptance_basis'] = 'shedding_relief' if shedding_relief else 'pre_control_voltage_relief'
    result['pre_control_voltage_deterioration_pu_hours'] = max(0.0, sum(
        proposed[label]['voltage_deficit_pu_hours'] - current[label]['voltage_deficit_pu_hours']
        for label in current))
    for key in fields_to_guard:
        old_total = sum(row[key] for row in current.values())
        new_total = sum(row[key] for row in proposed.values())
        if new_total - old_total > max(1e-6, limit / 100. * max(old_total, 1e-6)):
            result['reason'] = f'network-wide {key} deteriorated'
            return result
        for label in current:
            baseline = current[label][key]
            tolerance = max(1e-5, baseline * limit / 100., old_total * .0001)
            if proposed[label][key] - baseline > tolerance:
                result['reason'] = f'{key} worsened on lateral {label}'
                return result
    result['acceptable'] = True
    result['reason'] = ('verified annual shedding relief; pre-control voltage is diagnostic'
                        if shedding_relief else 'verified annual pre-shedding voltage relief')
    return result


def balanced_shortlist(network, ranking, allowed, *, installed=(), rules=ImprovementRules()):
    """Retain one strong candidate from each affected lateral where possible."""
    mapping = lateral_map(network)
    ranked = [r for r in ranking if r['bus'] in set(allowed)]
    occupied = {mapping[c.bus_id] for c in installed}
    def healthy(row):
        return row['voltage_deficit_pu_hours'] < 1e-9 and row['local_baseline_shedding_kwh'] < 1e-9
    if rules.exclude_installed_laterals:
        alternatives = [r for r in ranked if mapping[r['bus']] not in occupied and not healthy(r)]
        if alternatives:
            ranked = [r for r in ranked if mapping[r['bus']] not in occupied]
    if any(not healthy(r) for r in ranked):
        ranked = [r for r in ranked if not healthy(r)]
    if not ranked:
        ranked = [r for r in ranking if r['bus'] in set(allowed)]
    count = max(ceil(len(allowed) / 3), min(4, len(set(mapping[r['bus']] for r in ranked))))
    count = min(len(ranked), count)
    group_peak = {}
    for row in ranked:
        label = mapping[row['bus']]
        # Use the group's strongest severity, not numerical distance from slack.
        score = (row['local_baseline_shedding_kwh'] +
                 row['voltage_deficit_pu_hours'] * 1000.0)
        group_peak[label] = max(group_peak.get(label, 0.0), score)
    group_order = sorted(group_peak, key=lambda label: (-group_peak[label], label))
    selected = []
    for label in group_order[:count]:
        representative = next((row for row in ranked if mapping[row['bus']] == label), None)
        if representative is not None:
            selected.append(representative['bus'])
    for row in ranked:
        if len(selected) >= count:
            break
        if row['bus'] not in selected:
            selected.append(row['bus'])
    for row in ranking:
        row['lateral'] = mapping.get(row['bus'], 'unknown')
        row['retained'] = row['bus'] in selected
        row['installed_lateral'] = row['lateral'] in occupied
    return tuple(selected)


def representative_lateral_windows(network, baseline, profiles, count=2, voltage_min_pu=.95):
    """Annual-aware 48-hour windows, rather than two potentially biased weeks.

    Preserve the existing budget of count * 168 hours. Select severe events on
    distinct *electrical* laterals, recurring shedding, annual system stress,
    and seasonally typical periods. Selection is deterministic and non-overlapping.
    Every window is consecutive; SOC is integrated chronologically inside it.
    Independent windows remain screening ONLY; annual verification is mandatory.
    """
    hours = len(profiles.timestamps)
    if len(baseline.steps) != hours:
        raise ValueError('Representative periods require a complete annual baseline')
    target_hours = count * 168
    # A seven-window / 336-hour budget by default; always use full-day boundaries.
    block = 48 if target_hours >= 48 else 24
    n_windows = target_hours // block
    if n_windows < 1 or hours < n_windows * block:
        raise ValueError('Insufficient hours for representative windows')
    mapping = lateral_map(network)
    labels = tuple(sorted(set(mapping.values()) - {'slack'}))
    bus_groups = {label: tuple(bus for bus, group in mapping.items() if group == label)
                  for label in labels}
    # Hourly measurements come from the CURRENT full-year installed-fleet run,
    # not a stale No-BESS simulation after a battery is installed.
    import numpy as np
    shed = {label: np.zeros(hours) for label in labels}
    deficit = {label: np.zeros(hours) for label in labels}
    system_load = np.zeros(hours)
    system_pv = np.zeros(hours)
    for hour, step in enumerate(baseline.steps):
        if step.pre_control_voltage_pu is None or step.shedding_by_bus_kw is None:
            raise ValueError('Representative sampling requires pre-shedding voltage and bus shedding')
        for label, buses in bus_groups.items():
            shed[label][hour] = sum(max(0., step.shedding_by_bus_kw.get(bus, 0.)) for bus in buses)
            deficit[label][hour] = sum(max(0., voltage_min_pu - step.pre_control_voltage_pu[bus]) for bus in buses)
        system_load[hour] = sum(max(0., values[hour]) for values in profiles.load_p_kw.values())
        system_pv[hour] = sum(max(0., values[hour]) for values in profiles.pv_p_kw.values())
    starts = list(range(0, hours - block + 1, 24))
    def rolling(values):
        cumulative = np.r_[0., np.cumsum(values)]
        return np.array([cumulative[i + block] - cumulative[i] for i in starts])
    shed_window = {label: rolling(v) for label, v in shed.items()}
    voltage_window = {label: rolling(v) for label, v in deficit.items()}
    system_shed = sum(shed_window.values(), np.zeros(len(starts)))
    system_voltage = sum(voltage_window.values(), np.zeros(len(starts)))
    load_window = rolling(system_load)
    pv_window = rolling(system_pv)
    annual_priority = sorted(labels, key=lambda label: (
        -float(shed[label].sum()), -float(deficit[label].sum()), label))
    selected = []
    selection_reasons = []
    def pick(ranking, reason):
        for ix in ranking:
            begin = starts[int(ix)]
            if all(begin + block <= old or old + block <= begin for old in selected):
                selected.append(begin)
                selection_reasons.append(reason)
                return True
        return False
    # A two-week budget normally gives seven 48h windows: three critical
    # lateral events plus one typical window in EACH of four seasons.
    season_slots = min(4, max(1, n_windows - 1))
    critical_slots = n_windows - season_slots
    for label in annual_priority[:min(len(annual_priority), critical_slots)]:
        score = shed_window[label] + 1000. * voltage_window[label]
        if not np.any(score):
            continue
        pick(np.argsort(-score, kind='stable'), f'critical lateral {label}')
    # Preserve seasonality regardless of the concentration of worst events.
    from pandas import Timestamp
    months = np.array([Timestamp(profiles.timestamps[begin]).month for begin in starts])
    for season in (0, 1, 2, 3):
        if len(selected) >= critical_slots + season_slots:
            break
        indices = np.flatnonzero((months - 1) // 3 == season)
        if not len(indices):
            continue
        ref_load = np.median(load_window[indices]); ref_pv = np.median(pv_window[indices])
        distances = (abs(load_window[indices]-ref_load) / max(1.,ref_load)
                     + abs(pv_window[indices]-ref_pv) / max(1.,ref_pv))
        order = indices[np.argsort(distances, kind='stable')]
        pick(order, f'typical season {season + 1}')
    if len(selected) < n_windows:
        stress_score = (system_shed / max(1., float(system_shed.max()))
                        + system_voltage / max(1.,float(system_voltage.max())))
        pick(np.argsort(-stress_score,kind='stable'), 'system-wide extreme')
    # Fill any remaining budget with separated stressed/typical candidates.
    if len(selected) < n_windows:
        score = system_shed / max(1., float(system_shed.max())) + system_voltage / max(1.,float(system_voltage.max()))
        pick_order = np.argsort(-score, kind='stable')
        while len(selected) < n_windows and pick(pick_order, 'additional stress diversity'):
            pass
    if len(selected) < n_windows:
        for begin in range(0, hours-block+1, block):
            if len(selected) == n_windows: break
            if all(begin + block <= old or old + block <= begin for old in selected):
                selected.append(begin); selection_reasons.append('chronological coverage')
    if len(selected) != n_windows:
        raise RuntimeError('Could not produce nonoverlapping representative windows')
    # Return index lists, keeping prior API and dated profile slicing intact.
    # Stage diagnostics can report the selected dates; method documented in v10.
    return [list(range(begin, begin + block)) for begin in sorted(selected)]
