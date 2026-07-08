"""fanet.mobility — node placement + movement over time.

MobilityModel is an ABC. Default implementation: StaticMobility (fixed positions,
placed once on a grid/random-seeded layout). Later: GaussMarkov3D, RandomWaypoint
behind the same interface; moving nodes change topology adjacency over time.
"""
from __future__ import annotations
import abc
import math
import random
from typing import List, Tuple
from .nodes import Node, NodeType


class MobilityModel(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def place(self, nodes: List[Node], area: Tuple[float, float, float], seed: int) -> None:
        """Assign initial positions in-place."""
        ...

    def step(self, nodes: List[Node], dt: float) -> None:
        """Advance positions by dt seconds. Static = no-op."""
        return None


class StaticMobility(MobilityModel):
    """Fixed, CONNECTIVITY-AWARE layout: GCS at area centre; drones clustered
    within ~0.45*comm_range of centre (so the swarm is mesh-connected and all
    reach the GCS); the attacker sits at ~0.85*comm_range from centre — just
    inside range of the cluster edge, modelling an infiltration entry point that
    then multi-hops inward. Positions never change.

    (Connectivity depends on comm_range vs spread; this layout guarantees a
    usable network for small tests. Sparser layouts -> disconnected, by design.)"""
    name = "static"

    def place(self, nodes: List[Node], area: Tuple[float, float, float], seed: int) -> None:
        rng = random.Random(seed)
        ax, ay, az = area
        cx, cy, cz = ax / 2, ay / 2, az / 2
        rng_drones = [n for n in nodes if n.is_drone]
        r_swarm = min(n.comm_range for n in nodes) * 0.45 if nodes else 50.0
        for n in nodes:
            if n.ntype == NodeType.GCS:
                n.pos = (cx, cy, cz)
            elif n.ntype == NodeType.ATTACKER:
                # entry point just inside range of the cluster edge
                d = (min(n.comm_range for n in nodes)) * 0.85
                n.pos = (cx - d, cy, cz)
            else:  # drones clustered around centre
                ang = rng.uniform(0, 6.2832); rad = rng.uniform(0, r_swarm)
                n.pos = (cx + rad * math.cos(ang), cy + rad * math.sin(ang),
                         cz + rng.uniform(-r_swarm * 0.3, r_swarm * 0.3))


MOBILITIES = {"static": StaticMobility}


def make_mobility(name: str) -> MobilityModel:
    if name not in MOBILITIES:
        raise ValueError(f"unknown mobility '{name}'; have {list(MOBILITIES)}")
    return MOBILITIES[name]()
