"""Task 10 orchestration skeleton; no duplicate FBS/BESS equations."""
from .fbs import FBSConfig
from .bess import BESSConfig, BESSState
from .network_model import NetworkModel
from .data_loader import ProfileSlice, ProfileData


def simulate_step(network: NetworkModel, profile_slice: ProfileSlice,
                  fbs_config: FBSConfig, bess_config: BESSConfig | None = None,
                  bess_state: BESSState | None = None, bess_request_kw: float = 0.0):
    raise NotImplementedError("Later integration task: assemble OperatingPoint and call public solvers")


def simulate_timeseries(network: NetworkModel, profiles: ProfileData,
                        simulation_config, bess_config=None, dispatch_policy=None):
    raise NotImplementedError("Task 17: implement time-series orchestration")
