"""Pure deterministic arena-geometry proof."""

import pytest

from steel_onslaught.match.geometry import (
    blocked_directions,
    bresenham_line,
    chebyshev_line,
    greedy_sidestep,
    line_of_sight_clear,
)
from steel_onslaught.pilots.schemas import ModelSOPosition, SOCompassDirection


@pytest.mark.unit
def test_integer_lines_are_deterministic_and_endpoint_exact() -> None:
    origin = ModelSOPosition(x=1, y=1)
    target = ModelSOPosition(x=5, y=3)

    assert chebyshev_line(origin, target) == ((2, 2), (3, 3), (4, 3), (5, 3))
    assert bresenham_line(origin, target) == ((1, 1), (2, 1), (3, 2), (4, 2), (5, 3))
    assert chebyshev_line(origin, target) == chebyshev_line(origin, target)
    assert bresenham_line(origin, target) == bresenham_line(origin, target)


@pytest.mark.unit
def test_line_of_sight_ignores_endpoints_but_rejects_interior_cover() -> None:
    origin = ModelSOPosition(x=0, y=0)
    target = ModelSOPosition(x=4, y=4)

    assert line_of_sight_clear(origin, target, frozenset())
    assert line_of_sight_clear(origin, target, frozenset({(0, 0), (4, 4)}))
    assert not line_of_sight_clear(origin, target, frozenset({(2, 2)}))


@pytest.mark.unit
def test_blocked_directions_and_sidestep_use_fixed_priority() -> None:
    origin = ModelSOPosition(x=1, y=1)
    target = ModelSOPosition(x=4, y=1)
    obstacles = frozenset({(2, 1)})

    assert blocked_directions(origin, size=5, obstacles=obstacles) == (SOCompassDirection.E,)
    first = greedy_sidestep(
        origin,
        target,
        obstacles=obstacles,
        size=5,
        toward=True,
        forbidden=frozenset(),
    )
    assert first == ModelSOPosition(x=2, y=0)
    assert (
        greedy_sidestep(
            origin,
            target,
            obstacles=obstacles,
            size=5,
            toward=True,
            forbidden=frozenset(),
        )
        == first
    )


@pytest.mark.unit
def test_blocked_directions_accepts_foundry_scale_without_grid_assumptions() -> None:
    """Geometry remains parameterized for the 60x60 Foundry contract."""
    assert blocked_directions(ModelSOPosition(x=59, y=59), size=60, obstacles=frozenset()) == (
        SOCompassDirection.NE,
        SOCompassDirection.E,
        SOCompassDirection.SE,
        SOCompassDirection.S,
        SOCompassDirection.SW,
    )
