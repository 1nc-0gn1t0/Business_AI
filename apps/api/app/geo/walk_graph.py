"""Pure bounded directed Dijkstra; no inferred geometric intersections."""

import heapq
import math
from dataclasses import dataclass

BUILD_VERSION = "osm-foot-node-topology-v2-components"
ALGORITHM_VERSION = "osm-foot-dijkstra-segments-v1"
WALK_HIGHWAYS = {
    "footway",
    "pedestrian",
    "path",
    "steps",
    "living_street",
    "residential",
    "service",
    "unclassified",
    "tertiary",
    "tertiary_link",
    "secondary",
    "secondary_link",
    "primary",
    "primary_link",
    "track",
    "road",
    "corridor",
    "crossing",
}
ALLOW = {"yes", "designated", "permissive", "official"}
PASSABLE_BARRIERS = {"no", "bollard", "cycle_barrier", "entrance", "sally_port", "kerb"}


def permitted(tags: dict[str, str], *, node: bool = False) -> bool:
    # Conservative public-access profile. Conditional rules require a temporal engine.
    if any(k.endswith(":conditional") for k in tags):
        return False
    foot = tags.get("foot")
    if foot is not None and foot not in ALLOW:
        return False
    if foot is None and tags.get("access", "yes") not in ALLOW:
        return False
    if tags.get("locked") == "yes" or tags.get("highway") in {"construction", "proposed"}:
        return False
    if node:
        return foot in ALLOW or tags.get("barrier", "no") in PASSABLE_BARRIERS
    if tags.get("area") == "yes" or tags.get("sidewalk") == "separate":
        return False
    return tags.get("highway") in WALK_HIGHWAYS or (
        tags.get("highway") in {"motorway", "motorway_link", "trunk", "trunk_link"}
        and foot in ALLOW
    )


def directions(tags: dict[str, str]) -> tuple[bool, bool]:
    # Motor-vehicle oneway and roundabout do not by themselves restrict pedestrians.
    direction = tags.get("oneway:foot", "no")
    if direction not in {"yes", "1", "true", "-1", "reverse", "no", "0", "false"}:
        return False, False
    forward = direction not in {"-1", "reverse"} and tags.get("foot:forward", "yes") in ALLOW
    backward = direction not in {"yes", "1", "true"} and tags.get("foot:backward", "yes") in ALLOW
    return forward, backward


@dataclass(frozen=True)
class Edge:
    id: int
    u: int
    v: int
    length: float
    forward: bool
    backward: bool
    coordinates: tuple[tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class Snap:
    edge: Edge
    fraction: float
    connector: float


def traverse(edges: list[Edge], start: Snap, budget: float) -> dict[int, float]:
    adjacency: dict[int, list[tuple[int, float]]] = {}
    for e in edges:
        if not math.isfinite(e.length) or e.length <= 0:
            raise ValueError("Invalid graph edge cost")
        if e.forward:
            adjacency.setdefault(e.u, []).append((e.v, e.length))
        if e.backward:
            adjacency.setdefault(e.v, []).append((e.u, e.length))
    seeds = []
    e = start.edge
    if e.forward:
        seeds.append((start.connector + (1 - start.fraction) * e.length, e.v))
    if e.backward:
        seeds.append((start.connector + start.fraction * e.length, e.u))
    # Endpoints need no movement against a one-way direction to occupy their vertex.
    if start.fraction <= 1e-9:
        seeds.append((start.connector, e.u))
    if start.fraction >= 1 - 1e-9:
        seeds.append((start.connector, e.v))
    heapq.heapify(seeds)
    distances: dict[int, float] = {}
    while seeds:
        cost, node = heapq.heappop(seeds)
        if cost > budget or node in distances:
            continue
        distances[node] = cost
        for other, length in adjacency.get(node, ()):
            if other not in distances and cost + length <= budget:
                heapq.heappush(seeds, (cost + length, other))
    return distances


def route_distance(start: Snap, target: Snap, distances: dict[int, float]) -> float | None:
    e, f = target.edge, target.fraction
    costs = []
    if e.forward and e.u in distances:
        costs.append(distances[e.u] + f * e.length)
    if e.backward and e.v in distances:
        costs.append(distances[e.v] + (1 - f) * e.length)
    if f <= 1e-9 and e.u in distances:
        costs.append(distances[e.u])
    if f >= 1 - 1e-9 and e.v in distances:
        costs.append(distances[e.v])
    delta = f - start.fraction
    if e.id == start.edge.id and (
        abs(delta) <= 1e-9 or (delta > 0 and e.forward) or (delta < 0 and e.backward)
    ):
        costs.append(start.connector + abs(delta) * e.length)
    return min(costs) + target.connector if costs else None


def reachable_intervals(
    edge: Edge, start: Snap, distances: dict[int, float], budget: float
) -> list[tuple[float, float]]:
    parts = []
    if edge.forward and edge.u in distances:
        parts.append((0.0, min(1.0, (budget - distances[edge.u]) / edge.length)))
    if edge.backward and edge.v in distances:
        parts.append((max(0.0, 1 - (budget - distances[edge.v]) / edge.length), 1.0))
    if edge.id == start.edge.id and start.connector <= budget:
        left = (budget - start.connector) / edge.length
        parts.append(
            (
                max(0.0, start.fraction - left) if edge.backward else start.fraction,
                min(1.0, start.fraction + left) if edge.forward else start.fraction,
            )
        )
    merged: list[tuple[float, float]] = []
    for low, high in sorted(parts):
        if high - low <= 1e-9:
            continue
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    return merged
