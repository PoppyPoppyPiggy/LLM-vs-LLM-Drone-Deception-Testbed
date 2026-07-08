"""fanet.routing — path selection over the topology adjacency.

RoutingProtocol is an ABC. Default implementation: ShortestPathRouting (BFS,
unweighted hop count). Later: AODV / OLSR can be dropped in behind the same
interface.
"""
from __future__ import annotations
import abc
from collections import deque
from typing import Dict, List, Optional, Set


class RoutingProtocol(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def route(self, src: str, dst: str, adjacency: Dict[str, Set[str]]) -> Optional[List[str]]:
        """Return a path [src, ..., dst] (inclusive) or None if unreachable."""
        ...

    def reachable(self, src: str, adjacency: Dict[str, Set[str]]) -> Set[str]:
        """All nodes reachable from src (multi-hop)."""
        seen, q = {src}, deque([src])
        while q:
            cur = q.popleft()
            for nb in adjacency.get(cur, ()):
                if nb not in seen:
                    seen.add(nb); q.append(nb)
        seen.discard(src)
        return seen


class ShortestPathRouting(RoutingProtocol):
    name = "shortest_path"

    def route(self, src: str, dst: str, adjacency: Dict[str, Set[str]]) -> Optional[List[str]]:
        if src == dst:
            return [src]
        prev = {src: None}
        q = deque([src])
        while q:
            cur = q.popleft()
            for nb in sorted(adjacency.get(cur, ())):   # sorted = deterministic
                if nb not in prev:
                    prev[nb] = cur
                    if nb == dst:
                        path = [dst]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])
                        return list(reversed(path))
                    q.append(nb)
        return None


ROUTERS = {"shortest_path": ShortestPathRouting}


def make_routing(name: str) -> RoutingProtocol:
    if name not in ROUTERS:
        raise ValueError(f"unknown routing '{name}'; have {list(ROUTERS)}")
    return ROUTERS[name]()
