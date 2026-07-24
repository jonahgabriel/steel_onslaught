"""Spatial-representation DTOs -- show-dont-tell arms R1/R2 (2026-07-24).

Hypothesis under test: the whole-round card-programming pilot can reason
spatially but has never been SHOWN the space in a usable form -- the ordinary
prompt (``llm.programming._serialize_programming_observation``) surfaces raw
own-position coordinates, a single-bit ``has_line_of_sight_to_enemy``, and a
flat ``cover_cells`` obstacle list, with no rendered map and no per-card
consequence preview. These models are the closed, typed wire shapes for the
additive fix: a rendered viewport map, a per-dealt-movement-card consequence
preview (resulting cell / enemy-LOS-after / distance-after), and per-dealt
weapon-card in-range flags.

Every field here is populated ONLY when a seat's ``ModelSOLlmPilotParams.
spatial_representation`` opts in (``"grid"``/``"grid_scaffold"``); the
``ModelSOProgrammingObservation``/``ModelSOCardSeatRequest`` fields that carry
these models default to ``None``/``()``, so an unopted seat's observation and
serialized prompt are byte-identical to the pre-arm shape. No strategy is told
here -- only the same-resolver-computed facts a pilot with eyes would already
see.

Zero fold/reducer/runner authority lives in this module: it is DTOs only. The
values are computed by ``match.spatial_preview`` (which calls the SAME
resolver/LOS functions the live match uses) and attached by
``match.card_adapter.CardRunnerAdapter.produce``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from steel_onslaught.contracts.card import CardId
from steel_onslaught.pilots.schemas import ModelSOPosition

# One fixed legend for every rendered grid -- not a per-instance field, so it
# cannot drift between renders and never needs a mutable dict on a frozen
# model. Precedence when a cell qualifies for more than one marker (e.g. an
# objective cell that also sits behind an enemy-LOS shadow) is top-to-bottom:
# own mech > enemy mech > objective > obstacle > enemy-LOS-blocked > open.
SPATIAL_GRID_LEGEND: dict[str, str] = {
    "S": "your mech (self)",
    "E": "enemy mech",
    "#": "obstacle / cover (impassable terrain)",
    "O": "objective cell",
    "x": "open cell where the enemy's line of sight is BLOCKED (safe from enemy fire here)",
    ".": "open cell, clear enemy line of sight",
    "~": "outside the arena bounds",
}


class ModelSOSpatialGridView(BaseModel):
    """A fixed-radius ASCII viewport centered on the observing mech.

    A full 60x60 arena render is prohibitively token-expensive for a local
    model (thousands of tokens of symbol-dense text); the viewport is capped
    at ``radius`` cells in every direction (default 12, i.e. a 25x25 render)
    -- enough to cover what is reachable/shootable in one round for a
    brawler-range loadout without inflating the prompt 3-5x. Objective/cover
    facts outside the viewport stay in their existing structured list fields
    (``own_observation.cover_cells``, ``objectives.cells``); the grid is the
    LOCAL legibility channel, not a replacement for those global facts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    radius: StrictInt = Field(ge=1)
    # Absolute arena coordinate of the grid's top-left (row 0, col 0) cell, so
    # the model can translate a rendered position back to an absolute cell if
    # it needs to compare against ``cover_cells``/``objectives`` coordinates.
    origin: ModelSOPosition
    # One string per row, top (min y) to bottom (max y); each character is one
    # cell, left (min x) to right (max x). Deterministic: pure function of
    # position/obstacles/objectives, never provider- or clock-dependent.
    rows: tuple[StrictStr, ...]


class ModelSOMovementPreview(BaseModel):
    """The resolver-computed consequence of playing one dealt movement card.

    ``resulting_cell``/``enemy_los_after``/``distance_to_enemy_after`` are
    computed by calling ``match.move_resolution.resolve_move_destination`` --
    the exact function ``MatchRunner._resolve_move`` calls to resolve a live
    MOVE_INTENT -- and ``match.geometry.line_of_sight_clear``, never a
    reimplementation. A property test
    (``tests/match/test_move_resolution.py``) asserts the preview and the live
    resolver can never diverge for the same inputs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    card_id: CardId
    direction: StrictStr = Field(min_length=1)
    resulting_cell: ModelSOPosition
    enemy_los_after: Literal["blocked", "clear", "no_living_enemy"]
    distance_to_enemy_after: StrictInt | None = Field(default=None, ge=0)


class ModelSOWeaponRangeFlag(BaseModel):
    """Whether a dealt weapon card is in range of the enemy right now.

    2026-07-24 prompt-content audit: 85/107 red fire attempts in the qwen35
    baseline battery were out of range. ``range``/``distance_current`` are the
    exact fields the engine's own fire-intent validator compares
    (``validate_weapon_fire_intent``); this flag never invents a different
    range/distance computation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    card_id: CardId
    weapon_id: StrictStr = Field(min_length=1)
    range: StrictInt = Field(ge=0)
    distance_current: StrictInt | None = Field(default=None, ge=0)
    in_range: bool


__all__ = [
    "SPATIAL_GRID_LEGEND",
    "ModelSOMovementPreview",
    "ModelSOSpatialGridView",
    "ModelSOWeaponRangeFlag",
]
