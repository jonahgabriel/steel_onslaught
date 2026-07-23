"""Closed arena contracts and the strict MATCH_STARTED arena snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.pilots.schemas import ModelSOPosition

_ARENA_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_OBJECTIVE_ID_PATTERN = re.compile(r"^objective\.[a-z][a-z0-9_]*$")


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
) -> None:
    """Objective layout invariants shared by the spec and the live snapshot.

    Presence is paired: an arena either has objectives AND a VP threshold, or
    neither.  A threshold without scoring cells (or cells without a finish
    line) would be a silently unreachable victory contract.
    """

    if bool(objectives) != (vp_threshold is not None):
        raise ValueError(
            f"arena {arena_id!r} must declare objectives and vp_threshold together "
            f"(objectives={len(objectives)}, vp_threshold={vp_threshold!r})"
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
    "arena_contract_hash",
    "neutral_historical_arena_snapshot",
]
