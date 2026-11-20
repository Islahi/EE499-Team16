"""Independent nonlinear nodal-equation reference (SciPy), not an FBS copy.

Run from 07_Implementation: python -m Validation.verify_nodal_reference
"""
import numpy as np
from scipy.optimize import root
from src.network_cases import build_guide_3_bus_case, build_guide_5_bus_case, build_5_bus_case
from src.network_model import Load
from src.main import base_operating_point
from src.fbs import FBSConfig, run_fbs


def verify(network):
    network.validate()
    ids = [b.bus_id for b in network.buses]
    lookup = {bus: i for i, bus in enumerate(ids)}
    slack = lookup[network.slack_bus_id()]
    non_slack = [i for i in range(len(ids)) if i != slack]
    zbase = network.buses[0].base_kv**2 / (network.base_power_kva/1000)
    ybus = np.zeros((len(ids), len(ids)), dtype=complex)
    for line in network.lines:
        i, j = lookup[line.from_bus], lookup[line.to_bus]
        y = zbase / complex(line.r_ohm, line.x_ohm)
        ybus[i, i] += y
        ybus[j, j] += y
        ybus[i, j] -= y
        ybus[j, i] -= y
    op = base_operating_point(network)
    demand = np.array([complex(op.p_load_kw[i]-op.p_pv_kw[i], op.q_load_kvar[i])
                       / network.base_power_kva for i in ids])

    def residual(x):
        v = np.ones(len(ids), dtype=complex)
        v[non_slack] = x[:len(non_slack)] + 1j*x[len(non_slack):]
        mismatch = (v * np.conj(ybus @ v) + demand)[non_slack]
        return np.r_[mismatch.real, mismatch.imag]

    solved = root(residual, np.r_[np.ones(len(non_slack)), np.zeros(len(non_slack))], tol=1e-11)
    assert solved.success, solved.message
    assert np.max(np.abs(residual(solved.x))) < 1e-10
    reference = np.ones(len(ids), dtype=complex)
    reference[non_slack] = solved.x[:len(non_slack)] + 1j*solved.x[len(non_slack):]
    fbs = run_fbs(network, op, FBSConfig(voltage_tolerance_pu=1e-12))
    assert fbs.converged
    difference = max(abs(fbs.voltage_complex_pu[bus]-reference[i]) for i, bus in enumerate(ids))
    assert difference < 1e-10, difference
    print(f"{len(ids)} buses: max complex voltage difference {difference:.3e} pu; "
          f"FBS sweeps {fbs.iterations}; losses {fbs.total_loss_p_kw:.9f} kW")


if __name__ == "__main__":
    verify(build_guide_3_bus_case())
    verify(build_guide_5_bus_case())
    # Synthetic load fixture, explicitly not published bus demand.
    verify(build_5_bus_case([Load(f"test{i}", i, 100*i, 40*i) for i in range(2, 6)]))
