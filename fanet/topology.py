"""fanet.topology — connectivity (who can talk to whom).

Topology is an ABC returning an adjacency map {node_id -> set(node_id)}.
Three interchangeable implementations (chosen by scenario.yaml fanet.topology):
  - StarTopology     : every drone links to the GCS (UAV<->UAV via GCS).
  - MeshTopology     : range-based; nodes within comm_range are adjacent (multi-hop).
  - ClusterTopology  : gateway drones relay; members link to their cluster gateway.
The attacker is connected to whatever drones are within its comm range (it has
no privileged link to the GCS).
"""
from __future__ import annotations
import abc
import math
from typing import Dict, List, Set
from .nodes import Node, NodeType


def _dist(a: Node, b: Node) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a.pos, b.pos)))


class Topology(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def adjacency(self, nodes: List[Node]) -> Dict[str, Set[str]]:
        """Return symmetric adjacency map {id -> set(neighbor ids)}."""
        ...

    @staticmethod
    def _empty(nodes: List[Node]) -> Dict[str, Set[str]]:
        return {n.node_id: set() for n in nodes}

    @staticmethod
    def _link(adj: Dict[str, Set[str]], a: str, b: str) -> None:
        if a != b:
            adj[a].add(b); adj[b].add(a)


class StarTopology(Topology):
    """All drones link to GCS. Attacker links to in-range drones (range-based)."""
    name = "star"

    def adjacency(self, nodes: List[Node]) -> Dict[str, Set[str]]:
        adj = self._empty(nodes)
        gcs = [n for n in nodes if n.ntype == NodeType.GCS]
        drones = [n for n in nodes if n.is_drone]
        for g in gcs:
            for d in drones:
                self._link(adj, g.node_id, d.node_id)
        # attacker: range-based access to nearby drones (no GCS link)
        for atk in [n for n in nodes if n.ntype == NodeType.ATTACKER]:
            for d in drones:
                if _dist(atk, d) <= atk.comm_range:
                    self._link(adj, atk.node_id, d.node_id)
        return adj


class MeshTopology(Topology):
    """Range-based ad-hoc mesh: any two nodes within comm_range are adjacent."""
    name = "mesh"

    def adjacency(self, nodes: List[Node]) -> Dict[str, Set[str]]:
        adj = self._empty(nodes)
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                if _dist(a, b) <= min(a.comm_range, b.comm_range):
                    self._link(adj, a.node_id, b.node_id)
        return adj


class ClusterTopology(Topology):
    """Hierarchical: drones group into clusters around gateway drones that relay
    to the GCS. Heuristic: first honey/normal drone per K is a gateway;
    members link to nearest gateway, gateways link to GCS."""
    name = "cluster"

    def __init__(self, cluster_size: int = 3):
        self.cluster_size = cluster_size

    def adjacency(self, nodes: List[Node]) -> Dict[str, Set[str]]:
        adj = self._empty(nodes)
        gcs = [n for n in nodes if n.ntype == NodeType.GCS]
        drones = [n for n in nodes if n.is_drone]
        if not drones:
            return adj
        gateways = drones[::self.cluster_size]  # every k-th drone is a gateway
        for g in gcs:
            for gw in gateways:
                self._link(adj, g.node_id, gw.node_id)
        for d in drones:
            gw = min(gateways, key=lambda x: _dist(d, x))
            self._link(adj, d.node_id, gw.node_id)
        for atk in [n for n in nodes if n.ntype == NodeType.ATTACKER]:
            for d in drones:
                if _dist(atk, d) <= atk.comm_range:
                    self._link(adj, atk.node_id, d.node_id)
        return adj


TOPOLOGIES = {"star": StarTopology, "mesh": MeshTopology, "cluster": ClusterTopology}


def make_topology(name: str) -> Topology:
    if name not in TOPOLOGIES:
        raise ValueError(f"unknown topology '{name}'; have {list(TOPOLOGIES)}")
    return TOPOLOGIES[name]()
