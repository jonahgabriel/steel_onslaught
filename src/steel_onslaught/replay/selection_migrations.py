"""Explicit caller-owned inputs for future historical selection migration.

This module deliberately does not mutate or up-convert current events.  A
future offline migration may consume this complete input, but it may not infer
player kind, identity, hashes, or decision sources from historical pilot ids.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from steel_onslaught.contracts.pilot import PilotId
from steel_onslaught.contracts.player_selection import (
    LoadoutId,
    MatchId,
    ModelSOHumanDecisionSource,
    ModelSOHumanSeatAssignment,
    ModelSOModelDecisionSource,
    ModelSOModelSeatAssignment,
    PlayerId,
    RosterId,
    Sha256Digest,
    Side,
)


class _ClosedStrictMigrationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


LegacyHeuristicArchetype = Literal["aggressive", "defensive", "predictive"]


class ModelSOLegacyHeuristicSeatAssignment(_ClosedStrictMigrationInput):
    """Explicit historical automated seat; never a roster player option."""

    kind: Literal["legacy_heuristic"]
    side: Side
    player_id: PlayerId
    loadout_id: LoadoutId
    pilot_spec_id: PilotId
    pilot_spec_sha256: Sha256Digest
    pilot_archetype: LegacyHeuristicArchetype
    input_source: Literal["automated"]


HistoricalSeatAssignment = Annotated[
    ModelSOHumanSeatAssignment | ModelSOModelSeatAssignment | ModelSOLegacyHeuristicSeatAssignment,
    Field(discriminator="kind"),
]


class ModelSOHistoricalMatchLaunchProvenanceInput(_ClosedStrictMigrationInput):
    """Caller-supplied launch evidence that can name pre-roster heuristic pilots."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.historical_match_launch_provenance_input"]
    match_id: MatchId
    launch_command_id: UUID
    launch_command_sha256: Sha256Digest
    overlay_sha256: Sha256Digest
    roster_id: RosterId
    roster_sha256: Sha256Digest
    seat_assignments: tuple[HistoricalSeatAssignment, HistoricalSeatAssignment]

    @model_validator(mode="after")
    def _assignments_are_exact(self) -> Self:
        sides = [assignment.side for assignment in self.seat_assignments]
        if set(sides) != {"red", "blue"} or len(sides) != len(set(sides)):
            raise ValueError(
                "seat_assignments must contain exactly one red and one blue assignment"
            )
        player_ids = [assignment.player_id for assignment in self.seat_assignments]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("seat assignments must use distinct player_id values")
        return self


class ModelSOLegacyHeuristicDecisionSource(_ClosedStrictMigrationInput):
    """Explicit source evidence for one historical automated decision."""

    kind: Literal["legacy_heuristic"]
    input_source: Literal["automated"]
    pilot_spec_id: PilotId
    pilot_spec_sha256: Sha256Digest
    pilot_archetype: LegacyHeuristicArchetype


HistoricalDecisionSource = Annotated[
    ModelSOHumanDecisionSource | ModelSOModelDecisionSource | ModelSOLegacyHeuristicDecisionSource,
    Field(discriminator="kind"),
]


class ModelSOHistoricalDecisionSourceInput(_ClosedStrictMigrationInput):
    event_id: StrictStr = Field(min_length=26, max_length=26)
    source: HistoricalDecisionSource


class ModelSOHistoricalSelectionMigrationInput(_ClosedStrictMigrationInput):
    """Complete evidence required to migrate one immutable historical match."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.historical_selection_migration_input"]
    match_id: MatchId
    launch: ModelSOHistoricalMatchLaunchProvenanceInput
    decision_sources: tuple[ModelSOHistoricalDecisionSourceInput, ...]

    @model_validator(mode="after")
    def _validate_explicit_evidence(self) -> Self:
        if self.match_id != self.launch.match_id:
            raise ValueError("match_id must equal launch.match_id")
        event_ids = [item.event_id for item in self.decision_sources]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("decision_sources must use unique event_id values")
        return self


__all__ = [
    "HistoricalDecisionSource",
    "HistoricalSeatAssignment",
    "ModelSOHistoricalDecisionSourceInput",
    "ModelSOHistoricalMatchLaunchProvenanceInput",
    "ModelSOHistoricalSelectionMigrationInput",
    "ModelSOLegacyHeuristicDecisionSource",
    "ModelSOLegacyHeuristicSeatAssignment",
]
