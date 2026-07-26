"""Closed arena contracts and the strict MATCH_STARTED arena snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.pilots.schemas import ModelSOPosition

_ARENA_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_OBJECTIVE_ID_PATTERN = re.compile(r"^objective\.[a-z][a-z0-9_]*$")

# Whether the arena's declared objectives actually PAY (SO-OBJ-DECOY).
#
#   "scoring" — the shipped behaviour and the default: control of an objective
#               cell awards ``vp_per_round`` and can cross ``vp_threshold``
#               into a VP victory.  Every arena authored before this field
#               existed is exactly this, and the field is omitted from
#               serialization at this value (see ``_objective_scoring_field``),
#               so their ``arena_contract_hash`` digests and their
#               ``MATCH_STARTED`` bytes are unchanged.
#   "decoy"   — the objectives are still DECLARED, still rendered into the
#               pilot observation and the programming prompt (cells,
#               ``vp_per_round``, control, distance, the VP scoreboard and the
#               ``vp_threshold`` rule line), but control NEVER awards VP, no
#               ``OBJECTIVE_SCORED`` is emitted, and no VP victory can be
#               declared.  This isolates the *stated goal in the decision
#               context* from *realized capture reward*, which the SO-SCEN-OBJ
#               battery could not separate (`docs/evidence/
#               2026-07-25-scenobj-asym-noobj-battery.md` §6a).
SOObjectiveScoring = Literal["scoring", "decoy"]


def _objective_scoring_field() -> Any:
    """The ``objective_scoring`` field, byte-invisible at its default.

    ``exclude_if`` is what makes this additive rather than breaking: at
    ``"scoring"`` the key is dropped from ``model_dump``, so the canonical JSON
    that ``arena_contract_hash`` digests — and the ``MATCH_STARTED`` payload
    that embeds the snapshot — are byte-identical to the pre-change tree for
    every existing arena and every historical ledger.  Same technique the
    ``MATCH_STARTED`` optional provenance fields use.
    """

    return Field(default="scoring", exclude_if=lambda value: value == "scoring")


# Whether the arena's declared objectives are shown to the pilot (SO-OBJ-MASK).
#
# This is the complementary axis to ``objective_scoring`` above, and the two
# are DELIBERATELY independent: ``objective_scoring`` is read only by
# ``MatchStateFold._score_objectives`` (does the engine pay?); this field is
# read only by ``MatchRunner`` where it decides what to pass into
# ``build_pilot_observation``/``ReducerPilotTick`` (does the pilot see it?).
# Crossing them completes the 2x2 the SO-OBJ-DECOY arm named but could not
# build alone:
#
#   scoring + visible  — the shipped, pre-existing behaviour (every arena
#                         authored before this field existed).
#   decoy   + visible  — SO-OBJ-DECOY (PR #210): objectives shown, never paid.
#   scoring + masked   — SO-OBJ-MASK (this field): objectives genuinely paid
#                         VP exactly as the shipped behaviour, but the
#                         ``objectives``/``victory_points`` view is withheld
#                         from every observation, so no VP total, objective
#                         cell, or ``vp_threshold`` reaches the model's
#                         prompt.  ``MatchStateFold`` is untouched: VP
#                         accrues, ``OBJECTIVE_SCORED``/``VICTORY_DECLARED``
#                         fire, and a VP victory is fully reachable — the
#                         match is played exactly as an ordinary objective
#                         match, just never narrated to the pilot.
#   decoy   + masked   — a legal but degenerate combination (no payout, no
#                         display); not built or scored by any arm here.
#
#   "visible" — the shipped behaviour and the default: identical to every
#               arena authored before this field existed, and omitted from
#               serialization at this value (see ``_objective_display_field``)
#               so digests and ``MATCH_STARTED`` bytes are unchanged.
#   "masked"  — the objectives/vp_threshold view is withheld from the pilot
#               observation the runner builds (``ModelSOPilotObservation.
#               objectives`` stays ``()``, ``victory_points`` stays ``None``,
#               regardless of how many objectives the arena declares or how
#               many the match has scored), so the serialized prompt is
#               byte-identical to an objective-free arena's prompt at the
#               same match state.  The fold's scoring is NOT read or altered
#               by this field.
SOObjectiveDisplay = Literal["visible", "masked"]


def _objective_display_field() -> Any:
    """The ``objective_display`` field, byte-invisible at its default.

    Same ``exclude_if`` technique as ``_objective_scoring_field`` and for the
    same reason: at ``"visible"`` the key is dropped from ``model_dump``, so
    every existing arena's ``arena_contract_hash`` and every historical
    ``MATCH_STARTED`` payload are unaffected by this field's addition.
    """

    return Field(default="visible", exclude_if=lambda value: value == "visible")


class _ClosedArenaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSOArenaRect(_ClosedArenaModel):
    """Inclusive obstacle rectangle used only in authored arena contracts."""

    x0: StrictInt = Field(ge=0)
    y0: StrictInt = Field(ge=0)
    x1: StrictInt = Field(ge=0)
    y1: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("arena rectangle corners must satisfy x0 <= x1 and y0 <= y1")
        return self

    def cells(self) -> frozenset[tuple[int, int]]:
        return frozenset(
            (x, y) for x in range(self.x0, self.x1 + 1) for y in range(self.y0, self.y1 + 1)
        )


class ModelSOArenaObjective(_ClosedArenaModel):
    """One contested scoring cell authored by a versioned arena contract.

    Objectives and cover are ONE layout problem (design §3.6): the cell must be
    standable (never an obstacle), reachable, and co-designed with sightlines.
    ``vp_per_round`` is awarded to the sole controlling player each scored
    round; the match-level ``vp_threshold`` lives on the arena, not here.
    """

    objective_id: StrictStr = Field(pattern=r"^objective\.[a-z][a-z0-9_]*$")
    cell: ModelSOPosition = Field(...)
    vp_per_round: StrictInt = Field(ge=1)


def _validate_objectives(
    *,
    arena_id: str,
    size: int,
    spawn_a: ModelSOPosition,
    spawn_b: ModelSOPosition,
    obstacles: frozenset[tuple[int, int]],
    objectives: tuple[ModelSOArenaObjective, ...],
    vp_threshold: int | None,
    objective_scoring: SOObjectiveScoring = "scoring",
    objective_display: SOObjectiveDisplay = "visible",
) -> None:
    """Objective layout invariants shared by the spec and the live snapshot.

    Presence is paired: an arena either has objectives AND a VP threshold, or
    neither.  A threshold without scoring cells (or cells without a finish
    line) would be a silently unreachable victory contract.

    ``objective_scoring="decoy"`` is only meaningful on an arena that HAS
    objectives to decoy: on an objective-free arena the mode would be a
    configured no-op, which is exactly the "configured but inert" class this
    codebase fails closed on.  ``objective_display="masked"`` (SO-OBJ-MASK)
    fails closed the same way, for the same reason: masking the view of
    objectives that were never declared is a no-op, not a mode.
    """

    if bool(objectives) != (vp_threshold is not None):
        raise ValueError(
            f"arena {arena_id!r} must declare objectives and vp_threshold together "
            f"(objectives={len(objectives)}, vp_threshold={vp_threshold!r})"
        )
    if objective_scoring == "decoy" and not objectives:
        raise ValueError(
            f"arena {arena_id!r} declares objective_scoring='decoy' but no objectives; "
            "decoy mode suppresses scoring for objectives that are still SHOWN to the "
            "pilot, so an objective-free decoy arena is a no-op (spell it 'scoring' and "
            "omit the objectives instead)"
        )
    if objective_display == "masked" and not objectives:
        raise ValueError(
            f"arena {arena_id!r} declares objective_display='masked' but no objectives; "
            "masked mode withholds a pilot view that would already be empty on an "
            "objective-free arena, so this is a no-op (spell it 'visible' and omit the "
            "objectives instead)"
        )
    ids = [objective.objective_id for objective in objectives]
    duplicate_ids = sorted({oid for oid in ids if ids.count(oid) > 1})
    if duplicate_ids:
        raise ValueError(f"arena {arena_id!r} has duplicate objective ids: {duplicate_ids}")
    cells = [(objective.cell.x, objective.cell.y) for objective in objectives]
    duplicate_cells = sorted({cell for cell in cells if cells.count(cell) > 1})
    if duplicate_cells:
        raise ValueError(f"arena {arena_id!r} has duplicate objective cells: {duplicate_cells}")
    for objective in objectives:
        cell = (objective.cell.x, objective.cell.y)
        if not (0 <= objective.cell.x < size and 0 <= objective.cell.y < size):
            raise ValueError(
                f"arena {arena_id!r} objective {objective.objective_id!r} {cell} "
                "is outside its grid"
            )
        if cell in obstacles:
            raise ValueError(
                f"arena {arena_id!r} objective {objective.objective_id!r} {cell} "
                "occupies an obstacle"
            )
        if cell in {(spawn_a.x, spawn_a.y), (spawn_b.x, spawn_b.y)}:
            raise ValueError(
                f"arena {arena_id!r} objective {objective.objective_id!r} {cell} "
                "occupies a spawn point"
            )


def _validate_layout(
    *,
    arena_id: str,
    size: int,
    spawn_a: ModelSOPosition,
    spawn_b: ModelSOPosition,
    obstacles: frozenset[tuple[int, int]],
) -> None:
    if not _ARENA_ID_PATTERN.fullmatch(arena_id):
        raise ValueError(f"arena_id {arena_id!r} does not match ^[a-z][a-z0-9_]*$")
    outside = sorted(
        cell for cell in obstacles if not (0 <= cell[0] < size and 0 <= cell[1] < size)
    )
    if outside:
        raise ValueError(f"arena {arena_id!r} has cells outside its {size}x{size} grid: {outside}")
    for label, spawn in (("spawn_a", spawn_a), ("spawn_b", spawn_b)):
        cell = (spawn.x, spawn.y)
        if not (0 <= spawn.x < size and 0 <= spawn.y < size):
            raise ValueError(f"arena {arena_id!r} {label} {cell} is outside its grid")
        if cell in obstacles:
            raise ValueError(f"arena {arena_id!r} {label} {cell} occupies an obstacle")
    if spawn_a == spawn_b:
        raise ValueError(f"arena {arena_id!r} spawn points must be distinct")


class ModelSOCurrentLiveArenaSnapshot(_ClosedArenaModel):
    """Required, self-contained arena truth on every current live match."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.arena_snapshot"] = Field(...)
    arena_id: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]*$")
    size: StrictInt = Field(gt=0)
    spawn_a: ModelSOPosition = Field(...)
    spawn_b: ModelSOPosition = Field(...)
    obstacles: tuple[ModelSOPosition, ...] = Field(...)
    sudden_death_start_tick: StrictInt | None = Field(..., gt=0)
    sudden_death_damage_base: StrictInt = Field(..., gt=0)
    # Objective-victory contract (Phase 4).  Defaults keep every historical
    # MATCH_STARTED payload valid: pre-objective ledgers carry neither field
    # and parse to the no-objectives arena they were recorded on.  Both fields
    # are paired-presence-validated below, so "optional" never means "silently
    # half-configured".
    objectives: tuple[ModelSOArenaObjective, ...] = ()
    vp_threshold: StrictInt | None = Field(default=None, gt=0)
    # Recorded, never configured (SO-OBJ-DECOY): the fold suppresses scoring
    # from THIS field on the embedded snapshot, so a replay of a decoy match
    # re-derives the same (empty) VP history from the ledger alone.
    objective_scoring: SOObjectiveScoring = _objective_scoring_field()
    # Recorded, never configured (SO-OBJ-MASK): the RUNNER withholds the
    # objectives/victory_points observation view from THIS field on the
    # embedded snapshot, never the fold — a masked match's VP history is real
    # and replays identically to a visible one; only what the LIVE pilot saw
    # differs, and that is not something replay reconstructs from state.
    objective_display: SOObjectiveDisplay = _objective_display_field()

    @property
    def obstacle_cells(self) -> frozenset[tuple[int, int]]:
        return frozenset((cell.x, cell.y) for cell in self.obstacles)

    @model_validator(mode="after")
    def _valid_layout(self) -> Self:
        cells = [(cell.x, cell.y) for cell in self.obstacles]
        if len(cells) != len(set(cells)):
            raise ValueError(f"arena {self.arena_id!r} contains duplicate obstacle cells")
        _validate_layout(
            arena_id=self.arena_id,
            size=self.size,
            spawn_a=self.spawn_a,
            spawn_b=self.spawn_b,
            obstacles=frozenset(cells),
        )
        _validate_objectives(
            arena_id=self.arena_id,
            size=self.size,
            spawn_a=self.spawn_a,
            spawn_b=self.spawn_b,
            obstacles=frozenset(cells),
            objectives=self.objectives,
            vp_threshold=self.vp_threshold,
            objective_scoring=self.objective_scoring,
            objective_display=self.objective_display,
        )
        return self


class ModelSOArenaSpec(_ClosedArenaModel):
    """Typed arena contract loaded only by the application composition root."""

    schema_version: Literal["0.1.0"] = Field(...)
    kind: Literal["steel_onslaught.arena"] = Field(...)
    arena_id: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: StrictStr = Field(min_length=1)
    size: StrictInt = Field(gt=0)
    spawn_a: ModelSOPosition = Field(...)
    spawn_b: ModelSOPosition = Field(...)
    obstacles: tuple[ModelSOPosition, ...] = Field(...)
    rects: tuple[ModelSOArenaRect, ...] = Field(...)
    sudden_death_start_tick: StrictInt | None = Field(default=None, gt=0)
    sudden_death_damage_base: StrictInt = Field(default=8, gt=0)
    objectives: tuple[ModelSOArenaObjective, ...] = ()
    vp_threshold: StrictInt | None = Field(default=None, gt=0)
    objective_scoring: SOObjectiveScoring = _objective_scoring_field()
    objective_display: SOObjectiveDisplay = _objective_display_field()

    @property
    def obstacle_cells(self) -> frozenset[tuple[int, int]]:
        cells = {(cell.x, cell.y) for cell in self.obstacles}
        for rect in self.rects:
            cells.update(rect.cells())
        return frozenset(cells)

    @model_validator(mode="after")
    def _valid_layout(self) -> Self:
        explicit = [(cell.x, cell.y) for cell in self.obstacles]
        if len(explicit) != len(set(explicit)):
            raise ValueError(f"arena {self.arena_id!r} contains duplicate explicit obstacles")
        _validate_layout(
            arena_id=self.arena_id,
            size=self.size,
            spawn_a=self.spawn_a,
            spawn_b=self.spawn_b,
            obstacles=self.obstacle_cells,
        )
        _validate_objectives(
            arena_id=self.arena_id,
            size=self.size,
            spawn_a=self.spawn_a,
            spawn_b=self.spawn_b,
            obstacles=self.obstacle_cells,
            objectives=self.objectives,
            vp_threshold=self.vp_threshold,
            objective_scoring=self.objective_scoring,
            objective_display=self.objective_display,
        )
        return self

    def to_snapshot(self) -> ModelSOCurrentLiveArenaSnapshot:
        return ModelSOCurrentLiveArenaSnapshot(
            schema_version="0.1.0",
            kind="steel_onslaught.arena_snapshot",
            arena_id=self.arena_id,
            size=self.size,
            spawn_a=self.spawn_a,
            spawn_b=self.spawn_b,
            obstacles=tuple(ModelSOPosition(x=x, y=y) for x, y in sorted(self.obstacle_cells)),
            sudden_death_start_tick=self.sudden_death_start_tick,
            sudden_death_damage_base=self.sudden_death_damage_base,
            objectives=self.objectives,
            vp_threshold=self.vp_threshold,
            objective_scoring=self.objective_scoring,
            objective_display=self.objective_display,
        )


def neutral_historical_arena_snapshot(
    *,
    size: int,
    spawn_a: ModelSOPosition,
    spawn_b: ModelSOPosition,
) -> ModelSOCurrentLiveArenaSnapshot:
    """Build an explicit open-field value for an offline historical migration."""

    return ModelSOCurrentLiveArenaSnapshot(
        schema_version="0.1.0",
        kind="steel_onslaught.arena_snapshot",
        arena_id="historical_open_field",
        size=size,
        spawn_a=spawn_a,
        spawn_b=spawn_b,
        obstacles=(),
        sudden_death_start_tick=None,
        sudden_death_damage_base=8,
    )


def arena_contract_hash(snapshot: ModelSOCurrentLiveArenaSnapshot) -> str:
    """Canonical sha256 of one live arena snapshot (objectives included).

    ``MATCH_STARTED`` carries this digest so every ledger names the EXACT
    arena/objective contract the match flew on (Phase 4 seam / finish-line
    requirement).  Canonical form: compact JSON with sorted keys over the
    snapshot's ``model_dump(mode="json")`` — the same serialization the
    payload embeds, so the hash is recomputable from any recorded event.
    """

    canonical = json.dumps(
        snapshot.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "ModelSOArenaObjective",
    "ModelSOArenaRect",
    "ModelSOArenaSpec",
    "ModelSOCurrentLiveArenaSnapshot",
    "SOObjectiveDisplay",
    "SOObjectiveScoring",
    "arena_contract_hash",
    "neutral_historical_arena_snapshot",
]
