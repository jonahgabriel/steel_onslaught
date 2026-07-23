"""Active battlefield-effect state and the pure consult functions (Phase 2).

A deployed utility card folds one ``ModelSOUtilityEffect`` into match state.
The three counterplay effects are consulted by the weapon-fire resolver
through the pure functions below — the SAME functions the runner calls, so a
unit test that drives them drives the actual seam:

  * ``smoke``  — its area cells join the LOS obstacle set (blocks aimed fire
    through the cloud) for its duration;
  * ``chaff``  — a targeting debuff aura on the deploying mech, folded
    multiplicatively into the attacker's hit probability against that mech;
  * ``flares`` — spoils a sensor lock on the deploying mech (zeros
    ``lock_confidence``) for its duration.

Every function is identity when no matching effect is active: an empty effect
set yields an empty smoke-cell frozenset, a ``0.0`` chaff debuff, and a
``False`` flare-lock-break — so existing ledgers replay byte-identically and no
existing number moves until a utility card is actually deployed.

Expiry is deterministic (``tick >= expiry_tick``), derived purely from folded
``MATCH_TICK`` + ``expiry_tick``, so live and replay agree by construction (R9).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from steel_onslaught.contracts.card import SOUtilityKind

Cell = tuple[int, int]


class ModelSOUtilityEffect(BaseModel):
    """One deployed, still-active battlefield effect (frozen, closed)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: SOUtilityKind
    card_id: StrictStr = Field(min_length=1)
    origin_x: StrictInt
    origin_y: StrictInt
    radius: StrictInt = Field(ge=0)
    expiry_tick: StrictInt = Field(ge=1)
    owner_mech_id: StrictStr = Field(min_length=1)
    owner_player_id: StrictStr = Field(min_length=1)

    def is_active_at(self, tick: int) -> bool:
        """Whether this effect still bites at ``tick`` (expires at ``expiry_tick``)."""

        return tick < self.expiry_tick

    def covered_cells(self) -> frozenset[Cell]:
        """Every cell within the Chebyshev radius of this effect's origin."""

        return frozenset(
            (self.origin_x + dx, self.origin_y + dy)
            for dx in range(-self.radius, self.radius + 1)
            for dy in range(-self.radius, self.radius + 1)
        )


def expire_effects(
    effects: tuple[ModelSOUtilityEffect, ...], tick: int
) -> tuple[ModelSOUtilityEffect, ...]:
    """Return only the effects still active at ``tick`` (expiry pruning)."""

    return tuple(effect for effect in effects if effect.is_active_at(tick))


def smoke_obstacle_cells(effects: tuple[ModelSOUtilityEffect, ...], tick: int) -> frozenset[Cell]:
    """Union of all active smoke areas as LOS obstacle cells at ``tick``.

    Empty (identity) when no smoke is active, so ``obstacles | smoke_cells``
    equals the static obstacle set and no previously-clear shot changes.
    """

    cells: set[Cell] = set()
    for effect in effects:
        if effect.kind == "smoke" and effect.is_active_at(tick):
            cells |= effect.covered_cells()
    return frozenset(cells)


def chaff_targeting_debuff(
    effects: tuple[ModelSOUtilityEffect, ...],
    target_mech_id: str,
    tick: int,
) -> float:
    """Targeting debuff in [0, 1] against ``target_mech_id`` from active chaff.

    Chaff is a mech-scoped aura on the deploying mech: it degrades aimed fire
    *at* that mech.  ``0.0`` (identity) when the target carries no active chaff.
    Multiple stacks do not exceed a full debuff.
    """

    debuff = 0.0
    for effect in effects:
        if (
            effect.kind == "chaff"
            and effect.owner_mech_id == target_mech_id
            and effect.is_active_at(tick)
        ):
            # Chaff radius scales the aura strength deterministically; a
            # radius-0 chaff is a token aura, larger radii bite harder, capped.
            debuff = max(debuff, min(1.0, 0.25 + 0.15 * effect.radius))
    return debuff


def flare_lock_broken(
    effects: tuple[ModelSOUtilityEffect, ...],
    target_mech_id: str,
    tick: int,
) -> bool:
    """Whether an active flare on ``target_mech_id`` spoils a lock at ``tick``.

    ``False`` (identity) when the locked mech carries no active flare, so
    ``lock_confidence`` and every downstream number are unchanged.
    """

    return any(
        effect.kind == "flares"
        and effect.owner_mech_id == target_mech_id
        and effect.is_active_at(tick)
        for effect in effects
    )


__all__ = [
    "Cell",
    "ModelSOUtilityEffect",
    "chaff_targeting_debuff",
    "expire_effects",
    "flare_lock_broken",
    "smoke_obstacle_cells",
]
