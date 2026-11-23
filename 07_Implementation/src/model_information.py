"""Run snapshots and a shared, offline model reference for Qt and HTML."""
from dataclasses import asdict
from html import escape

from .metrics import annual_capital_recovery_factor
from .planning_policy import effective_joint_search
from .saved_schema import upgrade_saved_fields


MISSING = "Not recorded"
DAILY_MODE = "daily_milp_dispatch"


def study_information(study, *, static=False):
    if study is None:
        return {}
    network = study.network
    slack = next(bus for bus in network.buses if bus.is_slack)
    system = {
        "buses": len(network.buses), "branches": len(network.lines),
        "base_power_kva": network.base_power_kva, "base_voltage_kv": slack.base_kv,
        "frequency_hz": network.frequency_hz, "slack_bus": slack.bus_id, "slack_voltage_pu": slack.v_set_pu,
        "rated_branches": sum(line.ampacity_a is not None for line in network.lines),
        "installed_pv_kw": sum(unit.p_rated_kw for unit in network.pv_units),
    }
    data = {"Network": study.context.get("Network"), "Network settings": system,
            "Active input source": "Static workbook operating point" if static else study.input_mode,
            "Simulation interval": {} if static else dict(study.simulation_window),
            "Clock": study.context.get("Clock"),
            "Time step hours": None if static else study.profiles.dt_hours}
    if study.request is not None:
        request = study.request
        for key in ("Workbook provenance", "Network SHA256", "Distributor network SHA256"):
            data[key] = study.context.get(key)
        data["Source files"] = {"network": str(request.network_path)}
        if not static:
            data["Source files"].update(
                load=str(request.dataset_folder or request.load_path or request.load_source),
                solar=str(study.context.get("PV source provenance") or request.pv_path or
                          study.context.get("PV source") or request.pv_source))
            data["Forecast model"] = study.forecast_info if study.input_mode == "forecast" else None
            data["PV conversion (W/m2)"] = study.context.get("PV conversion (W/m2)")
    return data


def dispatch_information(simulation):
    if simulation.fleet_dispatch_mode != DAILY_MODE:
        return {}
    from .daily_milp_dispatch import DailyMILPSettings
    return {"Daily MILP settings": asdict(DailyMILPSettings.from_simulation(simulation)),
            "Effective inverter sizing (kVA/kW)": simulation.effective_bess_inverter_kva_per_kw}


def settings_information(study, settings, kind=None):
    """Use the configuration passed to the worker, or a separately labeled preview."""
    context = study_information(study, static=kind == "base case")
    if kind == "base case":
        context["FBS settings"] = asdict(settings.simulation.fbs_config)
    else:
        context.update({
            "Simulation settings": asdict(settings.simulation),
            "Economic inputs": asdict(settings.economics),
            "Annual capital recovery factor": annual_capital_recovery_factor(settings.economics),
            "Settings controls": dict(settings.values),
        })
        context.update(dispatch_information(settings.simulation))
        if settings.manual_bess:
            context["Manual BESS"] = dict(vars(settings.manual_bess))
        if kind == "simulation" and settings.manual_bess is None:
            context["Fleet count"] = 0
        if kind in (None, "optimization") and settings.managed_search:
            from .fleet_ga_optimizer import FleetGAConfig
            context["Optimizer algorithm"] = "Joint GA"
            context["Effective Joint GA settings"] = asdict(effective_joint_search(settings.values))
            context["Effective Joint GA settings"]["elite_count"] = FleetGAConfig().elite_count
    context["Model reference"] = model_reference(context, kind=kind)
    return context


def model_reference(context, optimizer=None, *, kind=None):
    """Versioned equation text. Select the sections supported by the recorded model."""
    simulation = context.get("Simulation settings") or {}
    economics = context.get("Economic inputs") or {}
    timing = context.get("Dispatch timing") or {}
    mode = timing.get("fleet_dispatch_mode", simulation.get("fleet_dispatch_mode"))
    static = kind == "base case" or bool(context.get("Case definition"))
    daily = mode == DAILY_MODE and not static
    joint_ga = context.get("Optimizer algorithm") == "Joint GA" or bool(
        (optimizer or {}).get("fleet_ga_optimizer"))
    equations, assumptions, references = [], [], []
    if simulation.get("fbs_config") or context.get("FBS settings"):
        equations.append(("Radial Forward/Backward Sweep",
            "sᵢ = (P_load − P_PV − P_BESS + j(Q_load − Q_PV − Q_BESS)) / S_base\n"
            "iᵢ = conj(sᵢ / vᵢ)     Iᵢⱼ = iⱼ + Σₖ Iⱼₖ     vⱼ = vᵢ − zᵢⱼ Iᵢⱼ\n"
            "Convergence: maxᵢ |vᵢ,new − vᵢ,old| ≤ ε",
            "Use kW, kvar and kVA on a consistent three-phase base. Voltages, currents and impedances in the sweeps are in per unit. The backward sum is over children k of bus j. The slack voltage is fixed."))
        assumptions.append("Balanced radial feeder with fixed topology, one slack bus and one nominal voltage level.")
    if static:
        assumptions.append("Static FBS uses workbook base loads and installed PV ratings, with zero battery power. Hourly dispatch and annual economics do not apply.")
    if mode and not static:
        equations.append(("Battery energy and SOC",
            "P_BESS = P_dis − P_ch\nEₜ₊₁ = Eₜ + (η_ch P_ch − P_dis / η_dis) Δt\n"
            "SOCₜ = Eₜ / E_rated     SOC_min ≤ SOCₜ ≤ SOC_max",
            "P_ch and P_dis are nonnegative kW, E is kWh, Δt is hours, and efficiencies and SOC are fractions. Charge and discharge are bounded by nameplate, direction-specific and SOC limits."))
        equations.append(("Corrective actions and network limits",
            "P_served = P_requested − P_shed     0 ≤ P_shed ≤ P_requested\n"
            "Q_served = Q_requested × P_served / P_requested   (for P_requested > 0)\n"
            "P_PV,used = P_PV,available − P_curt     0 ≤ P_curt ≤ P_PV,available",
            "The controller evaluates voltage in pu, configured grid limits in kW, and enabled branch ampacity in A. Progressive shedding can assign greater weights to higher fractions of load shed. Reported energy uses the final verified hourly powers."))
    if daily:
        equations.extend([
            ("Daily restoration and operating mode",
             "0 ≤ P_ch ≤ z P_ch,max     0 ≤ P_dis ≤ (1 − z) P_dis,max     z ∈ {0, 1}\n"
             "E_end = E_start   (MILP)     |E_end − E_start| ≤ ε_E   (executed audit)",
             "Each scheduled 24-hour block, including a partial closing block, restores stored energy. The executed audit uses the recorded kWh tolerance. This applies when a battery is installed."),
            ("Battery P/Q and inverter capability",
             "PF = P_dis / √(P_dis² + Q_BESS²) ≥ PF_min    (when P_dis > 0)\n"
             "0 ≤ Q_BESS ≤ P_dis tan(arccos(PF_min))\n"
             "P_BESS² + Q_BESS² ≤ S_rated²     S_rated = P_rated × max(k_BESS, 1 / PF_min)",
             "P, Q and S use kW, kvar and kVA. Reactive injection is discharge-linked and zero while charging or idle. Hourly coordinated control uses a conservative inscribed capability polygon and verifies the network solution with FBS."),
        ])
        assumptions.extend([
            "The daily MILP uses first-order voltage sensitivities. Hourly power flow checks the implemented coordinated dispatch on the nonlinear feeder.",
            "The scheduler uses the supplied hourly input profile over its recorded horizon. Historical input can give perfect foresight within that window.",
        ])
        references.append("Ahmed, Sindi, Azzouz & Awad (2022). Optimal Sizing and Scheduling of Mobile Energy Storage Toward High Penetration Levels of Renewable Energy and Fast Charging Stations. DOI 10.1109/TEC.2021.3116234. Scheduling and operating constraints adapted for stationary batteries.")
    if joint_ga:
        equations.append(("Joint GA objective and fitness",
            "F_screen = C_CAPEX (CRF + f_O&M) + Σ_d w_d (C_energy,d + C_penalty,d + C_inventory,d)\n"
            "Fitness(rank r) = N − r + 1    (r starts at 1 among N feasible candidates)",
            "Representative-day weights w_d are numbers of represented days. The screening ledger charges depleted stored energy at the import tariff divided by charge efficiency, and credits surplus using discharge efficiency and the export tariff. Infeasible candidates receive infinite cost. The GA uses rank fitness as parent-selection weights and samples uniformly if every candidate in a generation is infeasible."))
        assumptions.append("Fleet placements are stationary. Representative days and independent stress days screen candidates. The chronological full-year check uses recorded hourly inputs and can retain the no-battery baseline. A GA search does not certify a global optimum.")
        references.append("Ahmed, Sindi, Azzouz & Awad (2023). Stochastic multi-benefit planning of mobile energy storage in reconfigurable active distribution systems. Sustainable Energy, Grids and Networks 36, 101190. Stationary comparison and scenario-planning background.")
    if economics and not static:
        if economics.get("power_cost_basis") == "kva":
            capex = "C_CAPEX = Σ_b (c_E E_rated + c_S S_rated)"
            capex_note = "Energy CAPEX is in USD/kWh and inverter CAPEX is in USD/kVA."
        elif economics.get("power_cost_basis") == "kw":
            capex = "C_CAPEX = Σ_b (c_E E_rated + c_P P_rated)"
            capex_note = "The recorded legacy basis prices energy in USD/kWh and power in USD/kW."
        else:
            capex, capex_note = MISSING, "CAPEX basis was not recorded."
        method = economics.get("annualization_method")
        crf = ("r = (1 + i_nominal) / (1 + inflation) − 1\nCRF = r(1 + r)ⁿ / [(1 + r)ⁿ − 1]\nCRF = 1/n when |r| < 10⁻¹²"
               if method == "real_crf" else "CRF = 1 / n" if method == "straight_line" else MISSING)
        equations.extend([
            ("Battery investment and annual ownership", capex + "\n" + crf +
             "\nC_capital = CRF × C_CAPEX     C_O&M = f_O&M × C_CAPEX",
             f"{capex_note} Lifetime n is in years and the annual ownership terms are in USD/year."),
            ("Chronological annual operating cost",
             "C_operating = Σₜ Δt (c_import P_import − c_export P_export + c_shed P_shed + c_curt P_curt) + C_inventory\n"
             "C_inventory = Σ_b c_import max(E_initial − E_final, 0) / η_ch\n"
             "C_annual = C_operating + C_capital + C_O&M",
             "Grid import and export are nonnegative directional kW. Tariffs and penalties are in USD/kWh. The chronological inventory ledger charges deficits only. An annual cost requires a complete hourly calendar year and the recorded tariff assumptions."),
        ])
        assumptions.append("Tariffs, penalties and investment assumptions are configured inputs. Changing them changes the estimated annual cost.")
    return {"version": 1, "equations": equations, "assumptions": assumptions, "references": references}


def _value(value):
    if value is None or value == "":
        return MISSING
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value)) if value else "None"
    return str(value)


def _table(title, rows):
    content = "".join(f"<tr><th scope='row'>{escape(name)}</th><td>{escape(_value(value))}</td></tr>"
                      for name, value in rows)
    return f"<h3>{escape(title)}</h3><table class='model-values' cellspacing='0' cellpadding='5'>{content}</table>"


def model_information(metadata, input_snapshot=None):
    """Render only saved values or explicitly supplied preview values."""
    metadata = upgrade_saved_fields(metadata)
    if metadata.get("legacy"):
        return {section: f"<p>{MISSING}</p>" for section in
                ("Current parameters", "Mathematical equations", "Model assumptions")}
    context = metadata.get("context") or {}
    snapshot = input_snapshot or {}
    optimizer = metadata.get("optimizer") or {}
    static = metadata.get("kind") == "base case" or bool(context.get("Case definition"))
    recorded_simulation = context.get("Simulation settings") or metadata.get("simulation") or {}
    simulation = {} if static else recorded_simulation
    solver = context.get("FBS settings") or recorded_simulation.get("fbs_config") or (metadata.get("solver") or {}).get("config") or {}
    controls = context.get("Settings controls") or {}
    economics = context.get("Economic inputs") or optimizer.get("economic_configuration") or {}
    source = context.get("Source files") or {}
    window = context.get("Simulation interval") or snapshot.get("window") or {}
    system = context.get("Network settings") or {}
    topology = metadata.get("topology") or {}
    slack = next((bus for bus in topology.get("buses", []) if bus.get("is_slack")), {})
    representative = optimizer.get("representative_days") or {}
    scheduling = context.get("Daily MILP settings") or {}
    ga = context.get("Effective Joint GA settings") or {}
    actual_ga = (optimizer.get("fleet_ga_optimizer") or {}).get("config") or {}
    handled = dict(ga)
    for current, recorded in (("population", "population_size"), ("generations", "max_generations"),
                             ("workers", "workers"), ("seed", "seed"), ("crossover", "crossover_rate"),
                             ("mutation", "mutation_rate"), ("stall_generations", "stall_generation_limit"),
                             ("relative_tolerance", "relative_tolerance"), ("elite_count", "elite_count")):
        if recorded in actual_ga:
            handled[current] = actual_ga[recorded]
    currency = economics.get("currency")
    basis = economics.get("power_cost_basis")
    unit = {"kw": "kW", "kva": "kVA"}.get(basis)

    def optional_limit(key):
        if key in simulation and simulation[key] is None:
            return "Uncapped"
        return simulation.get(key)

    def bounds(prefix):
        minimum, maximum, step = (controls.get(f"{prefix}_{name}_{'kw' if prefix.endswith('power') else 'kwh'}")
                                  for name in ("min", "max", "step"))
        return f"{minimum}–{maximum}, step {step}" if None not in (minimum, maximum, step) else None

    def scale(value):
        return f"{value} {currency}" if value is not None and currency else value

    parameters = _table("Study and data", [
        ("Run ID", metadata.get("run_id", context.get("Run ID"))), ("Study type", metadata.get("kind")),
        ("Network", context.get("Network")), ("Input mode", context.get("Active input source")),
        ("Network workbook", source.get("network")), ("Demand source", source.get("load") or context.get("Demand")),
        ("PV source", source.get("solar") or context.get("PV source")),
        ("Study start", window.get("start")), ("Study end (exclusive)", window.get("end_exclusive")),
        ("Hours", window.get("hours")), ("Time step (h)", context.get("Time step hours", snapshot.get("dt_hours"))),
        ("Clock", context.get("Clock", snapshot.get("clock"))),
        ("PV conversion (W/m²)", context.get("PV conversion (W/m2)")),
        ("Forecast method", (context.get("Forecast model") or {}).get("method")
         if isinstance(context.get("Forecast model"), dict) else context.get("Forecast model")),
    ]) + _table("Solver and network", [
        ("FBS backend", solver.get("backend") or (metadata.get("solver") or {}).get("name")),
        ("Maximum FBS iterations", solver.get("max_iterations")), ("FBS tolerance (pu)", solver.get("voltage_tolerance_pu")),
        ("Buses", system.get("buses", len(topology["buses"]) if "buses" in topology else None)),
        ("Branches", system.get("branches", len(topology["lines"]) if "lines" in topology else None)),
        ("Workbook provenance", context.get("Workbook provenance")),
        ("Selected workbook SHA256", context.get("Network SHA256")),
        ("Distributor workbook SHA256", context.get("Distributor network SHA256")),
        ("Slack bus", system.get("slack_bus", slack.get("bus_id"))),
        ("Slack voltage (pu)", system.get("slack_voltage_pu", slack.get("v_set_pu"))),
        ("Voltage bounds (pu)", f"{simulation['voltage_min_pu']}–{simulation['voltage_max_pu']}"
         if "voltage_min_pu" in simulation and "voltage_max_pu" in simulation else None),
        ("Base power (kVA)", system.get("base_power_kva", topology.get("base_power_kva"))),
        ("Base voltage (kV)", system.get("base_voltage_kv", slack.get("base_kv"))),
        ("Frequency (Hz)", system.get("frequency_hz", topology.get("frequency_hz"))),
        ("Installed PV (kW)", system.get("installed_pv_kw")),
        ("Enforce line ampacity", simulation.get("enforce_line_ampacity")), ("Branches with ampacity ratings", system.get("rated_branches")),
        ("Grid import limit (kW)", optional_limit("grid_import_limit_kw")),
        ("Grid export limit (kW)", optional_limit("grid_export_limit_kw")),
        ("Allow load shedding", simulation.get("allow_load_shedding")),
        ("Shedding policy", simulation.get("shedding_policy")),
        ("Shedding tiers (load fraction)", simulation.get("shedding_tier_edges")),
        ("Shedding tier weights", simulation.get("shedding_tier_weights")),
        ("Allow PV curtailment", simulation.get("allow_pv_curtailment")),
    ])
    if not static and metadata.get("kind") != "simulation":
        parameters += _table("Optimizer", [
            ("Method", context.get("Optimizer algorithm") or optimizer.get("algorithm")),
            ("Population", handled.get("population")), ("Maximum generations", handled.get("generations")),
            ("Configured GA workers", handled.get("workers")),
            ("GA worker limit used", min(handled["workers"], handled["population"])
             if None not in (handled.get("workers"), handled.get("population")) else None),
            ("Annual verification workers", optimizer.get("parallel_annual_workers", handled.get("annual_workers"))),
            ("Seed", handled.get("seed")),
            ("Mutation probability", handled.get("mutation")), ("Crossover probability", handled.get("crossover")),
            ("Elites", handled.get("elite_count")), ("Stall generations", handled.get("stall_generations")),
            ("Relative improvement tolerance", handled.get("relative_tolerance")),
            ("Annual finalist budget", optimizer.get("annual_verification_fallback_budget", handled.get("annual_fallbacks"))),
            ("Representative-day method", representative.get("method")),
            ("Representative days", representative.get("cluster_count")),
            ("Independent stress days", optimizer.get("independent_stress_days")),
            ("Maximum fleet size", optimizer.get("maximum_bess_units", controls.get("spin_bess_units"))),
            ("Eligible buses", optimizer.get("eligible_bus_ids", controls.get("allowed_buses"))),
            ("Candidate power (kW)", bounds("spin_opt_power")), ("Candidate energy (kWh)", bounds("spin_opt_energy")),
            ("Minimum duration (h)", (optimizer.get("bess_duration_constraint") or {}).get("minimum_hours", controls.get("spin_opt_duration_min_hours"))),
            ("Maximum duration (h)", (optimizer.get("bess_duration_constraint") or {}).get("maximum_hours", controls.get("spin_opt_duration_max_hours"))),
        ])
    manual = context.get("Manual BESS")
    fleet = optimizer.get("fleet", context.get("Selected BESS fleet"))
    units = [manual] if manual else fleet or []
    battery_params = context.get("Fleet battery parameters") or manual or {}

    def control_soc(key):
        value = controls.get(f"spin_soc_{key}_percent")
        return value / 100 if value is not None else None
    if not static:
        parameters += _table("Battery and dispatch", [
            ("Installed units", len(units) if manual or fleet is not None else context.get("Fleet count")),
            ("Dispatch", context.get("Dispatch") or simulation.get("fleet_dispatch_mode")),
            ("Look-ahead (h)", simulation.get("dispatch_horizon_hours")),
            ("Minimum discharge PF", simulation.get("minimum_discharge_pf")),
            ("Daily SOC tolerance (kWh)", simulation.get("daily_soc_tolerance_kwh")),
            ("SOC min / max / initial (fraction)", " / ".join(_value(battery_params.get(f"soc_{key}", control_soc(key)))
                                                              for key in ("min", "max", "initial"))),
            ("Charge efficiency (fraction)", battery_params.get("eta_charge", controls.get("charge_efficiency"))),
            ("Discharge efficiency (fraction)", battery_params.get("eta_discharge", controls.get("discharge_efficiency"))),
            ("PV inverter rating (kVA/kW)", simulation.get("opf_pv_kva_multiplier")),
            ("Daily MILP monitored bus limit", scheduling.get("monitored_buses")),
            ("Daily MILP cycling cost (USD/kWh)", scheduling.get("cycling_cost_usd_per_kwh")),
            ("Daily MILP reactive cost (USD/kvarh)", scheduling.get("reactive_cost_usd_per_kvarh")),
            ("Daily MILP voltage shortfall cost (USD/pu-hour)", scheduling.get("voltage_shortfall_cost_per_pu_hour")),
            ("Daily MILP voltage excess cost (USD/pu-hour)", scheduling.get("voltage_excess_cost_per_pu_hour")),
            ("Daily MILP time limit (s)", scheduling.get("milp_time_limit_s")),
        ])
    if units:
        ratio = context.get("Effective inverter sizing (kVA/kW)", optimizer.get("inverter_kva_per_kw"))
        if ratio is None and basis == "kva":
            ratio = economics.get("inverter_kva_per_kw")
        for item in units:
            power = item.get("power_rating_kw")
            rated = item.get("inverter_rating_kva")
            if rated is None and power is not None and ratio is not None:
                rated = power * ratio
            parameters += _table(f"Battery at bus {_value(item.get('bus_id'))}", [
                ("Rated power (kW)", power), ("Rated energy (kWh)", item.get("energy_capacity_kwh")),
                ("Inverter nameplate (kVA)", rated),
                ("Maximum charge (kW)", item.get("max_charge_kw")), ("Maximum discharge (kW)", item.get("max_discharge_kw")),
            ])
    if not static:
        parameters += _table("Economics", [
            ("Currency", currency), ("Energy CAPEX (per kWh)", scale(economics.get("cost_per_kwh"))),
            (f"Inverter CAPEX (per {unit})" if basis == "kva" else "Power CAPEX (per kW)" if unit else "Power CAPEX basis",
             scale(economics.get("cost_per_kw")) if unit else None),
            ("Inverter sizing ratio (kVA/kW)", economics.get("inverter_kva_per_kw") if basis == "kva" else None),
            ("Import tariff (per kWh)", scale(economics.get("grid_import_tariff_per_kwh"))),
            ("Export tariff (per kWh)", scale(economics.get("grid_export_tariff_per_kwh"))),
            ("Load-shedding penalty (per kWh)", scale(economics.get("shedding_penalty_per_kwh"))),
            ("PV curtailment penalty (per kWh)", scale(economics.get("curtailment_penalty_per_kwh"))),
            ("Lifetime (years)", economics.get("lifetime_years")),
            ("Annual O&M (fraction of CAPEX)", economics.get("annual_om_fraction")),
            ("Annualization method", economics.get("annualization_method")),
            ("Nominal interest (fraction)", economics.get("nominal_interest_rate")),
            ("Inflation (fraction)", economics.get("annual_inflation_rate")),
            ("Capital recovery factor", context.get("Annual capital recovery factor")),
        ])
    if "Proposed tariffs" in context:
        proposed_import, proposed_export = context["Proposed tariffs"]
        parameters += _table("Pending tariff edits (awaiting confirmation)", [
            ("Proposed import tariff (per kWh)", scale(proposed_import)),
            ("Proposed export tariff (per kWh)", scale(proposed_export)),
        ])
    if context.get("Preview note"):
        inputs = _table("Entered values", context["Unvalidated inputs"].items())
        parameters = f"<p>{escape(context['Preview note'])}</p>" + inputs + parameters

    reference = context.get("Model reference") or model_reference(
        {**context, "Simulation settings": simulation, "FBS settings": solver, "Economic inputs": economics},
        optimizer, kind=metadata.get("kind"))
    equations = "".join(f"<h3>{escape(title)}</h3><p class='model-equation'>{escape(formula).replace(chr(10), '<br>')}</p>"
                        f"<p>{escape(note)}</p>" for title, formula, note in reference.get("equations", ()))
    assumptions = list(reference.get("assumptions", ()))
    assumptions.extend(context[key] for key in ("PV history validation", "Classification disclaimer", "Historical irradiance override")
                       if isinstance(context.get(key), str) and context[key])
    notes = "".join(f"<li>{escape(item)}</li>" for item in assumptions)
    references = "".join(f"<li>{escape(item)}</li>" for item in reference.get("references", ()))
    return {
        "Current parameters": parameters,
        "Mathematical equations": equations or f"<p>{MISSING}</p>",
        "Model assumptions": (f"<ul>{notes}</ul>" if notes else f"<p>{MISSING}</p>") +
                             "<h3>Scientific references</h3>" +
                             (f"<ul>{references}</ul>" if references else f"<p>{MISSING}</p>"),
    }
