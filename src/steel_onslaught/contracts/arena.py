"""Closed arena contracts and the strict MATCH_STARTED arena snapshot."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from steel_onslaught.pilots.schemas import ModelSOPosition

_ARENA_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


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
    )


__all__ = [
    "ModelSOArenaRect",
    "ModelSOArenaSpec",
    "ModelSOCurrentLiveArenaSnapshot",
    "neutral_historical_arena_snapshot",
]
