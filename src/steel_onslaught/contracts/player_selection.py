"""Closed player-roster and future match-provenance contracts.

These models describe authority only.  They do not discover providers, open a
command transport, create a match, or alter the current event payloads.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints, model_validator

from steel_onslaught.contracts.pilot import PilotId

if TYPE_CHECKING:
    from steel_onslaught.contracts.application import ModelSOApplicationOverlay


class _ClosedStrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


ModelIdentityId = Annotated[
    StrictStr, StringConstraints(pattern=r"^model_identity\.[a-z0-9][a-z0-9_.-]*$")
]
PlayerOptionId = Annotated[
    StrictStr, StringConstraints(pattern=r"^player_option\.[a-z0-9][a-z0-9_.-]*$")
]
HumanIdentityId = Annotated[
    StrictStr, StringConstraints(pattern=r"^human_identity\.[a-z0-9][a-z0-9_.-]*$")
]
RosterId = Annotated[StrictStr, StringConstraints(pattern=r"^roster\.[a-z0-9][a-z0-9_.-]*$")]
LoadoutId = Annotated[StrictStr, StringConstraints(pattern=r"^loadout\.[a-z0-9][a-z0-9_.-]*$")]
MatchId = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^match\.[0-7][0-9A-HJKMNP-TV-Z]{25}$"),
]
MechId = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^mech\.[a-z][a-z0-9_-]*\.01$"),
]
PlayerId = Annotated[StrictStr, StringConstraints(pattern=r"^player\.[a-z0-9][a-z0-9_.-]*$")]
TurnId = Annotated[StrictStr, StringConstraints(pattern=r"^turn\.[a-z0-9][a-z0-9_.-]*$")]
ProviderBindingId = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]*$")]
PersonaId = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]*$")]
Sha256Digest = Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Side = Literal["red", "blue"]


class ModelSOModelIdentityBinding(_ClosedStrictModel):
    """Stable public model identity pointing at one internal provider binding."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_identity"]
    model_identity_id: ModelIdentityId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    provider_binding_id: ProviderBindingId


class ModelSOHumanPlayerOptionBinding(_ClosedStrictModel):
    kind: Literal["human"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    human_identity_id: HumanIdentityId
    pilot_spec_id: PilotId
    input_source: Literal["browser_command"]


class ModelSOModelPlayerOptionBinding(_ClosedStrictModel):
    kind: Literal["model"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    model_identity_id: ModelIdentityId
    pilot_spec_id: PilotId
    persona_id: PersonaId
    input_source: Literal["llm_completion"]


PlayerOptionBinding = Annotated[
    ModelSOHumanPlayerOptionBinding | ModelSOModelPlayerOptionBinding,
    Field(discriminator="kind"),
]


class ModelSOSeatLaunchPolicy(_ClosedStrictModel):
    side: Side
    loadout_id: LoadoutId
    allowed_option_ids: tuple[PlayerOptionId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _allowed_options_are_unique(self) -> Self:
        if len(self.allowed_option_ids) != len(set(self.allowed_option_ids)):
            raise ValueError("allowed_option_ids must be unique")
        return self


class ModelSOPublicHumanPlayerOption(_ClosedStrictModel):
    kind: Literal["human"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)


class ModelSOPublicModelPlayerOption(_ClosedStrictModel):
    kind: Literal["model"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    model_identity_id: ModelIdentityId


PublicPlayerOption = Annotated[
    ModelSOPublicHumanPlayerOption | ModelSOPublicModelPlayerOption,
    Field(discriminator="kind"),
]


class ModelSOPublicSeatLaunchPolicy(_ClosedStrictModel):
    side: Side
    allowed_option_ids: tuple[PlayerOptionId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _allowed_options_are_unique(self) -> Self:
        if len(self.allowed_option_ids) != len(set(self.allowed_option_ids)):
            raise ValueError("allowed_option_ids must be unique")
        return self


class ModelSOPlayerRosterProjection(_ClosedStrictModel):
    """Secret-free browser projection; no provider, pilot, persona, or loadout refs."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.player_roster_projection"]
    roster_id: RosterId
    roster_sha256: Sha256Digest
    options: tuple[PublicPlayerOption, ...] = Field(min_length=1)
    seats: tuple[ModelSOPublicSeatLaunchPolicy, ModelSOPublicSeatLaunchPolicy]

    @model_validator(mode="after")
    def _validate_public_roster(self) -> Self:
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("options must declare unique option_id values")
        sides = [seat.side for seat in self.seats]
        if set(sides) != {"red", "blue"} or len(sides) != len(set(sides)):
            raise ValueError("seats must contain exactly one red and one blue policy")
        known = set(option_ids)
        allowed = {option_id for seat in self.seats for option_id in seat.allowed_option_ids}
        unknown = sorted(allowed - known)
        if unknown:
            raise ValueError(f"seat policies reference unknown option ids: {unknown}")
        unreachable = sorted(known - allowed)
        if unreachable:
            raise ValueError(f"roster options must be allowed by at least one seat: {unreachable}")
        return self


class ModelSOPlayerRosterBinding(_ClosedStrictModel):
    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.player_roster"]
    roster_id: RosterId
    options: tuple[PlayerOptionBinding, ...] = Field(min_length=1)
    seats: tuple[ModelSOSeatLaunchPolicy, ModelSOSeatLaunchPolicy]

    @model_validator(mode="after")
    def _validate_closed_roster(self) -> Self:
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("options must declare unique option_id values")
        sides = [seat.side for seat in self.seats]
        if set(sides) != {"red", "blue"} or len(sides) != len(set(sides)):
            raise ValueError("seats must contain exactly one red and one blue policy")
        known = set(option_ids)
        allowed = {option_id for seat in self.seats for option_id in seat.allowed_option_ids}
        unknown = sorted(allowed - known)
        if unknown:
            raise ValueError(f"seat policies reference unknown option ids: {unknown}")
        unreachable = sorted(known - allowed)
        if unreachable:
            raise ValueError(f"roster options must be allowed by at least one seat: {unreachable}")
        return self

    def canonical_sha256(self) -> Sha256Digest:
        """Return the digest of this complete server-owned roster contract."""

        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def public_projection(self) -> ModelSOPlayerRosterProjection:
        options: list[PublicPlayerOption] = []
        for option in self.options:
            if isinstance(option, ModelSOHumanPlayerOptionBinding):
                options.append(
                    ModelSOPublicHumanPlayerOption(
                        kind="human",
                        option_id=option.option_id,
                        display_name=option.display_name,
                    )
                )
            else:
                options.append(
                    ModelSOPublicModelPlayerOption(
                        kind="model",
                        option_id=option.option_id,
                        display_name=option.display_name,
                        model_identity_id=option.model_identity_id,
                    )
                )
        public_seats = (
            ModelSOPublicSeatLaunchPolicy(
                side=self.seats[0].side,
                allowed_option_ids=self.seats[0].allowed_option_ids,
            ),
            ModelSOPublicSeatLaunchPolicy(
                side=self.seats[1].side,
                allowed_option_ids=self.seats[1].allowed_option_ids,
            ),
        )
        return ModelSOPlayerRosterProjection(
            schema_version="1",
            kind="steel_onslaught.player_roster_projection",
            roster_id=self.roster_id,
            roster_sha256=self.canonical_sha256(),
            options=tuple(options),
            seats=public_seats,
        )


def validate_player_roster_against_overlay(
    *,
    roster: ModelSOPlayerRosterBinding,
    overlay: ModelSOApplicationOverlay,
) -> None:
    """Validate the explicit roster -> model identity -> provider reference chain."""

    provider_ids = {provider.provider_id for provider in overlay.llm.providers}
    identities = {identity.model_identity_id: identity for identity in overlay.llm.model_identities}
    dangling_providers = sorted(
        {
            identity.provider_binding_id
            for identity in identities.values()
            if identity.provider_binding_id not in provider_ids
        }
    )
    if dangling_providers:
        raise ValueError(
            f"model identities reference unknown provider bindings: {dangling_providers}"
        )
    unknown_identities = sorted(
        {
            option.model_identity_id
            for option in roster.options
            if isinstance(option, ModelSOModelPlayerOptionBinding)
            and option.model_identity_id not in identities
        }
    )
    if unknown_identities:
        raise ValueError(f"roster options reference unknown model identities: {unknown_identities}")


class _SeatAssignmentBase(_ClosedStrictModel):
    side: Side
    player_id: PlayerId
    option_id: PlayerOptionId
    loadout_id: LoadoutId
    pilot_spec_id: PilotId
    option_sha256: Sha256Digest


class ModelSOHumanSeatAssignment(_SeatAssignmentBase):
    kind: Literal["human"]
    human_identity_id: HumanIdentityId
    input_source: Literal["browser_command"]


class ModelSOModelSeatAssignment(_SeatAssignmentBase):
    kind: Literal["model"]
    model_identity_id: ModelIdentityId
    persona_id: PersonaId
    input_source: Literal["llm_completion"]


SeatAssignment = Annotated[
    ModelSOHumanSeatAssignment | ModelSOModelSeatAssignment,
    Field(discriminator="kind"),
]


class ModelSOMatchLaunchProvenance(_ClosedStrictModel):
    """Future MATCH_STARTED provenance; not wired into the current payload map."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.match_launch_provenance"]
    match_id: MatchId
    launch_command_id: UUID
    launch_command_sha256: Sha256Digest
    overlay_sha256: Sha256Digest
    roster_id: RosterId
    roster_sha256: Sha256Digest
    seat_assignments: tuple[SeatAssignment, SeatAssignment]

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


class ModelSOHumanDecisionSource(_ClosedStrictModel):
    kind: Literal["human"]
    input_source: Literal["browser_command"]
    command_id: UUID
    turn_id: TurnId
    observation_sha256: Sha256Digest


class ModelSOModelDecisionSource(_ClosedStrictModel):
    kind: Literal["model"]
    input_source: Literal["llm_completion"]
    model_identity_id: ModelIdentityId
    persona_id: PersonaId


DecisionSource = Annotated[
    ModelSOHumanDecisionSource | ModelSOModelDecisionSource,
    Field(discriminator="kind"),
]


__all__ = [
    "DecisionSource",
    "HumanIdentityId",
    "LoadoutId",
    "MatchId",
    "MechId",
    "ModelIdentityId",
    "ModelSOHumanDecisionSource",
    "ModelSOHumanPlayerOptionBinding",
    "ModelSOHumanSeatAssignment",
    "ModelSOMatchLaunchProvenance",
    "ModelSOModelDecisionSource",
    "ModelSOModelIdentityBinding",
    "ModelSOModelPlayerOptionBinding",
    "ModelSOModelSeatAssignment",
    "ModelSOPlayerRosterBinding",
    "ModelSOPlayerRosterProjection",
    "ModelSOSeatLaunchPolicy",
    "PersonaId",
    "PlayerId",
    "PlayerOptionBinding",
    "PlayerOptionId",
    "ProviderBindingId",
    "PublicPlayerOption",
    "RosterId",
    "SeatAssignment",
    "Sha256Digest",
    "Side",
    "TurnId",
    "validate_player_roster_against_overlay",
]
