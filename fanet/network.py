"""fanet.network — assembles nodes + topology + routing + mobility into one FANET.

This is the object the episode runner drives: the attacker reaches drones through
`reachable_from` / `route`, so which honeydrone it hits is decided by the network,
not hard-coded rotation.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Set
from .nodes import Node, NodeType, build_swarm
from .topology import Topology, make_topology
from .routing import RoutingProtocol, make_routing
from .mobility import MobilityModel, make_mobility


class Fanet:
    def __init__(self, nodes: List[Node], topology: Topology,
                 routing: RoutingProtocol, mobility: MobilityModel):
        self.nodes = nodes
        self.by_id = {n.node_id: n for n in nodes}
        self.topology = topology
        self.routing = routing
        self.mobility = mobility
        self._adj: Dict[str, Set[str]] = {}

    # ── construction ────────────────────────────────────────────────
    @classmethod
    def from_config(cls, scenario: dict, seed: int) -> "Fanet":
        nc = scenario["nodes"]; fc = scenario["fanet"]
        nodes = build_swarm(nc.get("n_gcs", 1), nc.get("n_normal", 1),
                            nc.get("n_honey", 1), nc.get("n_attacker", 1),
                            comm_range=fc.get("comm_range", 150.0))
        mob = make_mobility(fc.get("mobility", "static"))
        mob.place(nodes, tuple(fc.get("area", [500.0, 500.0, 100.0])), seed)
        net = cls(nodes, make_topology(fc.get("topology", "star")),
                  make_routing(fc.get("routing", "shortest_path")), mob)
        net.rebuild()
        return net

    # ── topology / routing queries ──────────────────────────────────
    def rebuild(self) -> None:
        """Recompute adjacency (call after mobility step)."""
        self._adj = self.topology.adjacency(self.nodes)

    def adjacency(self) -> Dict[str, Set[str]]:
        return self._adj

    def neighbors(self, node_id: str) -> Set[str]:
        return self._adj.get(node_id, set())

    def route(self, src: str, dst: str) -> Optional[List[str]]:
        return self.routing.route(src, dst, self._adj)

    def reachable_from(self, node_id: str) -> Set[str]:
        return self.routing.reachable(node_id, self._adj)

    def step(self, dt: float = 1.0) -> None:
        self.mobility.step(self.nodes, dt)
        self.rebuild()

    # ── role helpers ────────────────────────────────────────────────
    def attackers(self) -> List[Node]:
        return [n for n in self.nodes if n.ntype == NodeType.ATTACKER]

    def drones(self) -> List[Node]:
        return [n for n in self.nodes if n.is_drone]

    def reachable_drones(self, attacker_id: str) -> List[Node]:
        """Drones the attacker can reach (multi-hop) — its actual attack surface."""
        ids = self.reachable_from(attacker_id)
        return [self.by_id[i] for i in ids if self.by_id[i].is_drone]
