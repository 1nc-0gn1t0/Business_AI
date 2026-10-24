import pytest

from app.geo.walk_graph import (
    Edge,
    Snap,
    directions,
    permitted,
    reachable_intervals,
    route_distance,
    traverse,
)


def edge(
    i: int, u: int, v: int, length: float = 100, forward: bool = True, backward: bool = True
) -> Edge:
    return Edge(i, u, v, length, forward, backward, ((49.0, 55.0), (49.001, 55.0)))


@pytest.mark.parametrize(
    "tags,allowed",
    [
        ({"highway": "footway"}, True),
        ({"highway": "steps"}, True),
        ({"highway": "residential", "oneway": "yes"}, True),
        ({"highway": "motorway"}, False),
        ({"highway": "motorway", "foot": "yes"}, True),
        ({"highway": "path", "access": "private"}, False),
        ({"highway": "path", "access": "no", "foot": "yes"}, True),
        ({"highway": "footway", "foot": "no"}, False),
        ({"highway": "construction"}, False),
        ({"highway": "path", "foot:conditional": "yes @ (Mo-Fr)"}, False),
        ({"highway": "residential", "sidewalk": "separate"}, False),
    ],
)
def test_access_policy(tags: dict[str, str], allowed: bool) -> None:
    assert permitted(tags) == allowed


def test_barriers_and_foot_direction() -> None:
    assert not permitted({"barrier": "fence"}, node=True)
    assert not permitted({"barrier": "gate"}, node=True)
    assert permitted({"barrier": "gate", "foot": "yes"}, node=True)
    assert not permitted({"barrier": "gate", "foot": "yes", "locked": "yes"}, node=True)
    assert directions({"oneway": "yes"}) == (True, True)
    assert directions({"oneway:foot": "yes"}) == (True, False)
    assert directions({"oneway:foot": "-1"}) == (False, True)
    assert directions({"foot:backward": "no"}) == (True, False)


def test_shortest_routes_disconnected_crossings_and_partial_edges() -> None:
    a, b, c, bridge = edge(1, 1, 2), edge(2, 2, 3), edge(3, 1, 3, 300), edge(4, 4, 5)
    start = Snap(a, 0.0, 0.0)
    distances = traverse([a, b, c, bridge], start, 150)
    assert distances == {1: 0.0, 2: 100.0}
    assert route_distance(start, Snap(b, 0.4, 10), distances) == pytest.approx(150)
    assert route_distance(start, Snap(bridge, 0.5, 0), distances) is None
    assert reachable_intervals(b, start, distances, 150) == [(0.0, 0.5)]
    assert traverse([a, b, c], start, 250)[3] == 200
    assert traverse([bridge, c, b, a], start, 250) == traverse([a, b, c, bridge], start, 250)


def test_virtual_mid_edge_oneway_and_connectors() -> None:
    e = edge(1, 1, 2, 100, True, False)
    start = Snap(e, 0.5, 10)
    distances = traverse([e], start, 30)
    assert distances == {}
    assert route_distance(start, Snap(e, 0.65, 5), distances) == pytest.approx(30)
    assert route_distance(start, Snap(e, 0.4, 0), distances) is None
    assert reachable_intervals(e, start, distances, 30) == [(0.5, 0.7)]
    assert traverse([e], Snap(e, 0, 0), 100) == {1: 0.0, 2: 100.0}


def test_bounded_large_chain_and_reverse_foot_direction() -> None:
    chain = [edge(i, i, i + 1, 1) for i in range(1, 10001)]
    start = Snap(chain[0], 0.0, 0.0)
    distances = traverse(chain, start, 500)
    assert len(distances) == 501 and distances[501] == 500
    reverse = edge(1, 1, 2, 100, False, True)
    assert traverse([reverse], Snap(reverse, 1.0, 0.0), 100) == {2: 0.0, 1: 100.0}
