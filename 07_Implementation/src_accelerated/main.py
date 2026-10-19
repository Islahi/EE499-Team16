"""Runnable one-step demo; profiles/BESS integration comes later."""
from .network_cases import build_guide_5_bus_case
from .fbs import OperatingPoint, FBSConfig, run_fbs


def base_operating_point(network):
    """Fixture using base loads and PV rated output, NOT a dispatch policy."""
    ids = [b.bus_id for b in network.buses]
    loads, pvs = network.loads_by_bus(), network.pv_by_bus()
    return OperatingPoint(
        {i: sum(l.p_base_kw for l in loads[i]) for i in ids},
        {i: sum(l.q_base_kvar for l in loads[i]) for i in ids},
        {i: sum(p.p_rated_kw for p in pvs[i]) for i in ids},
        {i: 0.0 for i in ids}, {i: 0.0 for i in ids}, {i: 0.0 for i in ids})


def main():
    network = build_guide_5_bus_case()
    result = run_fbs(network, base_operating_point(network), FBSConfig())
    print(f"Guide five-bus verification case: {result.message}, {result.iterations} sweeps")
    for bus, magnitude in sorted(result.voltage_mag_pu.items()):
        print(f"Bus {bus}: {magnitude:.8f} pu, {result.voltage_angle_deg[bus]:.6f} degrees")
    print(f"Slack: {result.slack_p_kw:.8f} kW, {result.slack_q_kvar:.8f} kvar")
    print(f"Losses: {result.total_loss_p_kw:.8f} kW, {result.total_loss_q_kvar:.8f} kvar")
    if not result.converged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
