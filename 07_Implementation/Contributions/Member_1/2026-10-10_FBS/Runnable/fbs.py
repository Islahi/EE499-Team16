"""
fbs.py
------
Task #13: Forward/Backward Sweep (FBS) power-flow solver for a radial
distribution network, for a single time step.

Input : a NetworkModel built by network_model.py
Output: FBSResult containing per-bus voltages, per-branch currents/power
        flows, total system losses, and convergence status.

Algorithm (standard distribution FBS, e.g. Kersting "Distribution System
Modeling and Analysis"):

  0. Build the radial tree (parent/children) from the slack bus and order
     buses by BFS "depth" level.
  1. Flat-start all non-slack bus voltages at the slack voltage.
  2. BACKWARD SWEEP (leaves -> root):
        For every bus b, compute its own load current
            I_load(b) = conj( S_b / V_b )
        where S_b is the net PQ demand at b (loads minus PV injection).
        The current flowing INTO b on its upstream branch equals I_load(b)
        plus the sum of all downstream branch currents already computed for
        b's children (KCL at the bus).
  3. FORWARD SWEEP (root -> leaves):
        For every bus b (excluding the slack), update its voltage from its
        parent's voltage and the branch current/impedance:
            V_b = V_parent - I_branch(parent->b) * Z(parent->b)
  4. Convergence check: max bus-voltage change between sweeps < tolerance.
     Repeat steps 2-3 until converged or max_iter is reached.
  5. Once converged, compute branch (sending-end) power flows and I^2*R / I^2*X
     losses per branch, and sum them for total system loss.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import cmath

from network_model import NetworkModel, Line


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #

@dataclass
class BusResult:
    bus_id: int
    v_pu: complex

    @property
    def v_mag_pu(self) -> float:
        return abs(self.v_pu)

    @property
    def v_ang_deg(self) -> float:
        return cmath.phase(self.v_pu) * 180.0 / cmath.pi


@dataclass
class BranchResult:
    from_bus: int
    to_bus: int
    i_pu: complex                 # branch current, p.u.
    s_sending_pu: complex         # power flowing INTO the branch at from_bus
    p_loss_pu: float
    q_loss_pu: float

    @property
    def i_mag_pu(self) -> float:
        return abs(self.i_pu)


@dataclass
class FBSResult:
    converged: bool
    iterations: int
    bus_results: Dict[int, BusResult]
    branch_results: List[BranchResult]
    total_p_loss_pu: float
    total_q_loss_pu: float
    base_mva: float
    base_kv: float

    def summary(self) -> str:
        lines = []
        lines.append(f"Converged: {self.converged}  (iterations = {self.iterations})")
        lines.append(f"Total losses: {self.total_p_loss_pu*self.base_mva*1000:.3f} kW, "
                      f"{self.total_q_loss_pu*self.base_mva*1000:.3f} kVAr")
        lines.append("")
        lines.append("Bus voltages:")
        for bid in sorted(self.bus_results):
            br = self.bus_results[bid]
            kv = br.v_mag_pu * self.base_kv
            lines.append(f"  Bus {bid}: {br.v_mag_pu:.5f} pu  ({kv:.3f} kV)  "
                          f"angle {br.v_ang_deg:+.3f} deg")
        lines.append("")
        lines.append("Branch flows:")
        for b in self.branch_results:
            mva = abs(b.s_sending_pu) * self.base_mva
            lines.append(
                f"  {b.from_bus}->{b.to_bus}: I = {b.i_mag_pu:.5f} pu, "
                f"S_send = {b.s_sending_pu.real*self.base_mva*1000:+.2f} kW "
                f"{b.s_sending_pu.imag*self.base_mva*1000:+.2f} kVAr "
                f"({mva:.4f} MVA), loss = {b.p_loss_pu*self.base_mva*1000:.3f} kW"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Tree-building helpers
# --------------------------------------------------------------------------- #

def _bfs_order(network: NetworkModel) -> List[int]:
    """Returns bus ids ordered by BFS distance from the slack bus (slack first).
    Network must already be validated as radial (see NetworkModel.validate_radial).
    """
    slack = network.slack_bus_id
    order = [slack]
    frontier = [slack]
    while frontier:
        nxt = []
        for b in frontier:
            for ln in network.lines_from(b):
                order.append(ln.to_bus)
                nxt.append(ln.to_bus)
        frontier = nxt
    return order


# --------------------------------------------------------------------------- #
# Core FBS solver
# --------------------------------------------------------------------------- #

def run_fbs(
    network: NetworkModel,
    tol_pu: float = 1e-6,
    max_iter: int = 100,
) -> FBSResult:
    """Run Forward/Backward Sweep power flow for one time step.

    Parameters
    ----------
    network : NetworkModel
        Output of network_model.py (must be a validated radial network).
    tol_pu : float
        Convergence tolerance on the max bus-voltage magnitude change
        between successive forward sweeps, in per-unit.
    max_iter : int
        Maximum number of backward/forward sweep pairs before giving up.

    Returns
    -------
    FBSResult
    """
    network.validate_radial()

    bfs = _bfs_order(network)                      # slack first, leaves last
    children: Dict[int, List[Line]] = {b: network.lines_from(b) for b in network.buses}
    parent_line: Dict[int, Optional[Line]] = {b: network.line_to(b) for b in network.buses}

    slack_id = network.slack_bus_id
    slack_v = network.buses[slack_id].v_slack_pu or complex(1.0, 0.0)

    # 1. Flat start
    v: Dict[int, complex] = {slack_id: slack_v}
    for b in bfs[1:]:
        v[b] = complex(slack_v.real, slack_v.imag)   # flat start at slack voltage

    converged = False
    iterations = 0
    branch_current: Dict[int, complex] = {}  # keyed by "to_bus" id (its upstream branch)

    for it in range(1, max_iter + 1):
        iterations = it

        # ---------------- Backward sweep (leaves -> root) ----------------
        # process in reverse BFS order so every child is handled before its parent
        branch_current = {}
        for b in reversed(bfs):
            if b == slack_id:
                continue
            s_b = network.net_bus_injection_pu(b)       # load convention
            i_load = (s_b / v[b]).conjugate() if v[b] != 0 else complex(0, 0)

            i_children_sum = complex(0, 0)
            for ln in children[b]:
                i_children_sum += branch_current[ln.to_bus]

            branch_current[b] = i_load + i_children_sum  # current on branch feeding bus b

        # ---------------- Forward sweep (root -> leaves) -------------------
        v_old = dict(v)
        for b in bfs:
            if b == slack_id:
                v[b] = slack_v
                continue
            ln = parent_line[b]
            v[b] = v[ln.from_bus] - branch_current[b] * ln.z_pu

        # ---------------- Convergence check ---------------------------------
        max_dv = max(abs(v[b] - v_old[b]) for b in bfs)
        if max_dv < tol_pu:
            converged = True
            break

    # ---------------- Post-processing: branch flows & losses ----------------
    branch_results: List[BranchResult] = []
    total_p_loss = 0.0
    total_q_loss = 0.0
    for b in bfs:
        if b == slack_id:
            continue
        ln = parent_line[b]
        i_branch = branch_current[b]
        s_sending = v[ln.from_bus] * i_branch.conjugate()
        s_loss = (abs(i_branch) ** 2) * ln.z_pu  # I^2 * Z -> complex loss (P + jQ)
        total_p_loss += s_loss.real
        total_q_loss += s_loss.imag
        branch_results.append(BranchResult(
            from_bus=ln.from_bus,
            to_bus=ln.to_bus,
            i_pu=i_branch,
            s_sending_pu=s_sending,
            p_loss_pu=s_loss.real,
            q_loss_pu=s_loss.imag,
        ))

    bus_results = {b: BusResult(bus_id=b, v_pu=v[b]) for b in bfs}

    return FBSResult(
        converged=converged,
        iterations=iterations,
        bus_results=bus_results,
        branch_results=branch_results,
        total_p_loss_pu=total_p_loss,
        total_q_loss_pu=total_q_loss,
        base_mva=network.base_mva,
        base_kv=network.base_kv,
    )


if __name__ == "__main__":
    from network_model import build_default_5bus_network

    net = build_default_5bus_network()
    result = run_fbs(net, tol_pu=1e-6, max_iter=100)
    print(result.summary())
