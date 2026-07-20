"""Canonical multi-provider model catalog contracts.

The player roster remains the launch authority consumed by the command
gateway.  This module adds a richer, server-owned catalog that can be built
from several explicitly configured overlays and then projected back to that
existing roster contract for the browser.  It deliberately contains no
provider clients, filesystem discovery, fallback policy, or match state.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints, model_validator

from steel_onslaught.contracts.player_selection import (
    ModelIdentityId,
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelIdentityBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
    PersonaId,
    PlayerOptionBinding,
    PlayerOptionId,
    ProviderBindingId,
    RosterId,
    Sha256Digest,
    Side,
)


class _ClosedCatalogModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


CatalogId = Annotated[StrictStr, StringConstraints(pattern=r"^catalog\.[a-z0-9][a-z0-9_.-]*$")]
OverlayId = Annotated[StrictStr, StringConstraints(pattern=r"^overlay\.[a-z0-9][a-z0-9_.-]*$")]
CatalogSourceId = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^catalog_source\.[a-z0-9][a-z0-9_.-]*$"),
]


class ModelSOModelCatalogHumanOption(_ClosedCatalogModel):
    """Human option with the source contract identity retained for provenance."""

    kind: Literal["human"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    human_identity_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^human_identity\.[a-z0-9][a-z0-9_.-]*$",
    )
    pilot_spec_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^pilot\.[a-z0-9][a-z0-9_.-]*$",
    )
    input_source: Literal["browser_command"]
    source_overlay_id: OverlayId
    source_overlay_sha256: Sha256Digest
    source_roster_id: RosterId
    source_roster_sha256: Sha256Digest


class ModelSOModelCatalogModelOption(_ClosedCatalogModel):
    """Model option with provider, model, pilot, and source-overlay provenance."""

    kind: Literal["model"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    model_identity_id: ModelIdentityId
    provider_binding_id: ProviderBindingId
    provider_model: StrictStr = Field(min_length=1, max_length=160)
    pilot_spec_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^pilot\.[a-z0-9][a-z0-9_.-]*$",
    )
    persona_id: PersonaId
    input_source: Literal["llm_completion"]
    source_overlay_id: OverlayId
    source_overlay_sha256: Sha256Digest
    source_roster_id: RosterId
    source_roster_sha256: Sha256Digest


CatalogOptionBinding = Annotated[
    ModelSOModelCatalogHumanOption | ModelSOModelCatalogModelOption,
    Field(discriminator="kind"),
]


class ModelSOPublicModelCatalogHumanOption(_ClosedCatalogModel):
    kind: Literal["human"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)


class ModelSOPublicModelCatalogModelOption(_ClosedCatalogModel):
    kind: Literal["model"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    model_identity_id: ModelIdentityId
    provider_binding_id: ProviderBindingId
    provider_model: StrictStr = Field(min_length=1, max_length=160)


PublicModelCatalogOption = Annotated[
    ModelSOPublicModelCatalogHumanOption | ModelSOPublicModelCatalogModelOption,
    Field(discriminator="kind"),
]


class ModelSOModelCatalogProjection(_ClosedCatalogModel):
    """Secret-free catalog metadata that is safe to expose to the browser."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_catalog_projection"]
    catalog_id: CatalogId
    catalog_sha256: Sha256Digest
    options: tuple[PublicModelCatalogOption, ...] = Field(min_length=1)
    default_option_ids: tuple[PlayerOptionId | None, PlayerOptionId | None]
    mirror_match_mode: bool = False

    @model_validator(mode="after")
    def _unique_options(self) -> Self:
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("catalog projection options must have unique option_id values")
        return self


class ModelSOModelCatalogPairingProvenance(_ClosedCatalogModel):
    """The explicit red/blue composition admitted for a launch."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_catalog_pairing"]
    catalog_id: CatalogId
    catalog_sha256: Sha256Digest
    red_option_id: PlayerOptionId
    blue_option_id: PlayerOptionId
    red_role_id: StrictStr = Field(min_length=1, max_length=96)
    blue_role_id: StrictStr = Field(min_length=1, max_length=96)
    red_loadout_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^loadout\.[a-z0-9][a-z0-9_.-]*$",
    )
    blue_loadout_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^loadout\.[a-z0-9][a-z0-9_.-]*$",
    )
    red_chassis_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^chassis\.[a-z0-9][a-z0-9_.-]*$",
    )
    blue_chassis_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^chassis\.[a-z0-9][a-z0-9_.-]*$",
    )
    mirror_match_mode: bool = False
    pairing_sha256: Sha256Digest

    @model_validator(mode="after")
    def _pairing_is_distinct_without_mirror_mode(self) -> Self:
        if self.mirror_match_mode:
            return self
        if self.red_option_id == self.blue_option_id:
            raise ValueError("duplicate default option requires mirror_match_mode")
        if self.red_role_id == self.blue_role_id:
            raise ValueError("duplicate default role requires mirror_match_mode")
        if self.red_loadout_id == self.blue_loadout_id:
            raise ValueError("duplicate default loadout requires mirror_match_mode")
        if self.red_chassis_id == self.blue_chassis_id:
            raise ValueError("duplicate default chassis requires mirror_match_mode")
        return self


class ModelSOModelCatalogSelectionProvenance(_ClosedCatalogModel):
    """Exact source chain for one selected catalog option and seat."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_catalog_selection"]
    selection_kind: Literal["human", "model"]
    catalog_id: CatalogId
    catalog_sha256: Sha256Digest
    side: Side
    option_id: PlayerOptionId
    loadout_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^loadout\.[a-z0-9][a-z0-9_.-]*$",
    )
    display_name: StrictStr = Field(min_length=1, max_length=80)
    source_overlay_id: OverlayId
    source_overlay_sha256: Sha256Digest
    source_roster_id: RosterId
    source_roster_sha256: Sha256Digest
    pilot_spec_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^pilot\.[a-z0-9][a-z0-9_.-]*$",
    )
    paired_option_id: PlayerOptionId
    pairing: ModelSOModelCatalogPairingProvenance
    human_identity_id: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=96,
        pattern=r"^human_identity\.[a-z0-9][a-z0-9_.-]*$",
    )
    model_identity_id: ModelIdentityId | None = None
    provider_binding_id: ProviderBindingId | None = None
    provider_model: StrictStr | None = Field(default=None, min_length=1, max_length=160)
    persona_id: PersonaId | None = None

    @model_validator(mode="after")
    def _kind_matches_fields(self) -> Self:
        if self.selection_kind == "human":
            if self.human_identity_id is None:
                raise ValueError("human catalog selections require human_identity_id")
            if any(
                value is not None
                for value in (
                    self.model_identity_id,
                    self.provider_binding_id,
                    self.provider_model,
                    self.persona_id,
                )
            ):
                raise ValueError("human catalog selections cannot carry model/provider fields")
        else:
            if self.human_identity_id is not None:
                raise ValueError("model catalog selections cannot carry human_identity_id")
            if any(
                value is None
                for value in (
                    self.model_identity_id,
                    self.provider_binding_id,
                    self.provider_model,
                    self.persona_id,
                )
            ):
                raise ValueError("model catalog selections require model/provider fields")
        return self


class ModelSOModelCatalogSource(_ClosedCatalogModel):
    """One explicitly configured overlay/roster contribution to a catalog."""

    source_overlay_id: OverlayId
    source_overlay_sha256: Sha256Digest
    source_roster_id: RosterId
    source_roster_sha256: Sha256Digest
    options: tuple[CatalogOptionBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _source_provenance_is_consistent(self) -> Self:
        for option in self.options:
            if option.source_overlay_id != self.source_overlay_id:
                raise ValueError("catalog option source_overlay_id disagrees with its source")
            if option.source_overlay_sha256 != self.source_overlay_sha256:
                raise ValueError("catalog option source_overlay_sha256 disagrees with its source")
            if option.source_roster_id != self.source_roster_id:
                raise ValueError("catalog option source_roster_id disagrees with its source")
            if option.source_roster_sha256 != self.source_roster_sha256:
                raise ValueError("catalog option source_roster_sha256 disagrees with its source")
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("catalog source options must have unique option_id values")
        return self


class ModelSOModelCatalogOptionAlias(_ClosedCatalogModel):
    """Explicit source-to-global option mapping; no implicit namespacing."""

    source_option_id: PlayerOptionId
    catalog_option_id: PlayerOptionId


class ModelSOModelCatalogSourceBinding(_ClosedCatalogModel):
    """Filesystem source references for an operator-declared catalog index."""

    source_id: CatalogSourceId
    source_overlay_id: OverlayId
    overlay_path: StrictStr = Field(min_length=1, max_length=512)
    roster_path: StrictStr = Field(min_length=1, max_length=512)
    option_id_map: tuple[ModelSOModelCatalogOptionAlias, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _aliases_are_unique(self) -> Self:
        source_ids = [alias.source_option_id for alias in self.option_id_map]
        catalog_ids = [alias.catalog_option_id for alias in self.option_id_map]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("catalog source option_id_map has duplicate source_option_id values")
        if len(catalog_ids) != len(set(catalog_ids)):
            raise ValueError("catalog source option_id_map has duplicate catalog_option_id values")
        return self


class ModelSOModelCatalogIndex(_ClosedCatalogModel):
    """Declarative index of the exact overlay/roster sources to merge."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_catalog_sources"]
    catalog_id: CatalogId
    roster_id: RosterId
    sources: tuple[ModelSOModelCatalogSourceBinding, ...] = Field(min_length=1)
    seats: tuple[ModelSOSeatLaunchPolicy, ModelSOSeatLaunchPolicy]
    default_chassis_ids: tuple[
        Annotated[StrictStr, StringConstraints(pattern=r"^chassis\.[a-z0-9][a-z0-9_.-]*$")],
        Annotated[StrictStr, StringConstraints(pattern=r"^chassis\.[a-z0-9][a-z0-9_.-]*$")],
    ]
    mirror_match_mode: bool = False

    @model_validator(mode="after")
    def _sources_are_unique_and_global_aliases_are_unique(self) -> Self:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("catalog sources must declare unique source_id values")
        catalog_option_ids = [
            alias.catalog_option_id for source in self.sources for alias in source.option_id_map
        ]
        if len(catalog_option_ids) != len(set(catalog_option_ids)):
            raise ValueError("catalog sources must declare globally unique catalog option ids")
        return self


class ModelSOModelCatalog(_ClosedCatalogModel):
    """Server-owned multi-provider catalog and its explicit seat policy."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_catalog"]
    catalog_id: CatalogId
    roster_id: RosterId
    options: tuple[CatalogOptionBinding, ...] = Field(min_length=1)
    seats: tuple[ModelSOSeatLaunchPolicy, ModelSOSeatLaunchPolicy]
    default_chassis_ids: tuple[
        Annotated[StrictStr, StringConstraints(pattern=r"^chassis\.[a-z0-9][a-z0-9_.-]*$")],
        Annotated[StrictStr, StringConstraints(pattern=r"^chassis\.[a-z0-9][a-z0-9_.-]*$")],
    ]
    mirror_match_mode: bool = False

    @model_validator(mode="after")
    def _validate_catalog(self) -> Self:
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("catalog options must declare unique option_id values")
        sides = [seat.side for seat in self.seats]
        if set(sides) != {"red", "blue"} or len(sides) != len(set(sides)):
            raise ValueError("catalog seats must contain exactly one red and one blue policy")
        if sides != ["red", "blue"]:
            raise ValueError("catalog seats must be ordered red then blue")
        known = set(option_ids)
        allowed = {option_id for seat in self.seats for option_id in seat.allowed_option_ids}
        unknown = sorted(allowed - known)
        if unknown:
            raise ValueError(f"catalog seats reference unknown option ids: {unknown}")
        unreachable = sorted(known - allowed)
        if unreachable:
            raise ValueError(
                f"catalog options must be reachable by at least one seat: {unreachable}"
            )
        if not self.mirror_match_mode:
            defaults = tuple(seat.default_option_id for seat in self.seats)
            if any(default is None for default in defaults):
                raise ValueError("non-mirror catalogs require explicit defaults for both seats")
            assert defaults[0] is not None and defaults[1] is not None
            if defaults[0] == defaults[1]:
                raise ValueError("duplicate default option requires mirror_match_mode")
            roles = tuple(
                self._role_for_option(
                    next(option for option in self.options if option.option_id == default)
                )
                for default in defaults
            )
            if roles[0] == roles[1]:
                raise ValueError("duplicate default role requires mirror_match_mode")
            if self.seats[0].loadout_id == self.seats[1].loadout_id:
                raise ValueError("duplicate default loadout requires mirror_match_mode")
            if self.default_chassis_ids[0] == self.default_chassis_ids[1]:
                raise ValueError("duplicate default chassis requires mirror_match_mode")
        return self

    @staticmethod
    def _role_for_option(option: CatalogOptionBinding) -> str:
        return "human" if isinstance(option, ModelSOModelCatalogHumanOption) else option.persona_id

    def _option_for_id(self, option_id: PlayerOptionId) -> CatalogOptionBinding:
        option = next((option for option in self.options if option.option_id == option_id), None)
        if option is None:
            raise ValueError(f"catalog has no option {option_id!r}")
        return option

    def pairing_provenance(
        self,
        *,
        red_option_id: PlayerOptionId,
        blue_option_id: PlayerOptionId,
    ) -> ModelSOModelCatalogPairingProvenance:
        """Validate and hash one explicit red/blue composition."""

        red_seat, blue_seat = self.seats
        if red_option_id not in red_seat.allowed_option_ids:
            raise ValueError(f"option {red_option_id!r} is not allowed for red seat")
        if blue_option_id not in blue_seat.allowed_option_ids:
            raise ValueError(f"option {blue_option_id!r} is not allowed for blue seat")
        red_role = self._role_for_option(self._option_for_id(red_option_id))
        blue_role = self._role_for_option(self._option_for_id(blue_option_id))
        pairing_fields = {
            "schema_version": "1",
            "kind": "steel_onslaught.model_catalog_pairing",
            "catalog_id": self.catalog_id,
            "catalog_sha256": self.canonical_sha256(),
            "red_option_id": red_option_id,
            "blue_option_id": blue_option_id,
            "red_role_id": red_role,
            "blue_role_id": blue_role,
            "red_loadout_id": red_seat.loadout_id,
            "blue_loadout_id": blue_seat.loadout_id,
            "red_chassis_id": self.default_chassis_ids[0],
            "blue_chassis_id": self.default_chassis_ids[1],
            "mirror_match_mode": self.mirror_match_mode,
        }
        if not self.mirror_match_mode:
            if red_option_id == blue_option_id:
                raise ValueError("duplicate selected option requires mirror_match_mode")
            if red_role == blue_role:
                raise ValueError("duplicate selected role requires mirror_match_mode")
            if red_seat.loadout_id == blue_seat.loadout_id:
                raise ValueError("duplicate selected loadout requires mirror_match_mode")
            if self.default_chassis_ids[0] == self.default_chassis_ids[1]:
                raise ValueError("duplicate selected chassis requires mirror_match_mode")
        pairing_sha256 = hashlib.sha256(
            json.dumps(pairing_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ModelSOModelCatalogPairingProvenance(
            schema_version="1",
            kind="steel_onslaught.model_catalog_pairing",
            catalog_id=self.catalog_id,
            catalog_sha256=self.canonical_sha256(),
            red_option_id=red_option_id,
            blue_option_id=blue_option_id,
            red_role_id=red_role,
            blue_role_id=blue_role,
            red_loadout_id=red_seat.loadout_id,
            blue_loadout_id=blue_seat.loadout_id,
            red_chassis_id=self.default_chassis_ids[0],
            blue_chassis_id=self.default_chassis_ids[1],
            mirror_match_mode=self.mirror_match_mode,
            pairing_sha256=pairing_sha256,
        )

    def canonical_sha256(self) -> Sha256Digest:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_roster_binding(self) -> ModelSOPlayerRosterBinding:
        """Project to the existing launch-authority roster without discovery."""

        options: list[PlayerOptionBinding] = []
        for option in self.options:
            if isinstance(option, ModelSOModelCatalogHumanOption):
                options.append(
                    ModelSOHumanPlayerOptionBinding(
                        kind="human",
                        option_id=option.option_id,
                        display_name=option.display_name,
                        human_identity_id=option.human_identity_id,
                        pilot_spec_id=option.pilot_spec_id,
                        input_source=option.input_source,
                    )
                )
            else:
                options.append(
                    ModelSOModelPlayerOptionBinding(
                        kind="model",
                        option_id=option.option_id,
                        display_name=option.display_name,
                        model_identity_id=option.model_identity_id,
                        pilot_spec_id=option.pilot_spec_id,
                        persona_id=option.persona_id,
                        input_source=option.input_source,
                    )
                )
        return ModelSOPlayerRosterBinding(
            schema_version="1",
            kind="steel_onslaught.player_roster",
            roster_id=self.roster_id,
            options=tuple(options),
            seats=self.seats,
        )

    def public_projection(self) -> ModelSOModelCatalogProjection:
        options: list[PublicModelCatalogOption] = []
        for option in self.options:
            if isinstance(option, ModelSOModelCatalogHumanOption):
                options.append(
                    ModelSOPublicModelCatalogHumanOption(
                        kind="human",
                        option_id=option.option_id,
                        display_name=option.display_name,
                    )
                )
            else:
                options.append(
                    ModelSOPublicModelCatalogModelOption(
                        kind="model",
                        option_id=option.option_id,
                        display_name=option.display_name,
                        model_identity_id=option.model_identity_id,
                        provider_binding_id=option.provider_binding_id,
                        provider_model=option.provider_model,
                    )
                )
        return ModelSOModelCatalogProjection(
            schema_version="1",
            kind="steel_onslaught.model_catalog_projection",
            catalog_id=self.catalog_id,
            catalog_sha256=self.canonical_sha256(),
            options=tuple(options),
            default_option_ids=(
                self.seats[0].default_option_id,
                self.seats[1].default_option_id,
            ),
            mirror_match_mode=self.mirror_match_mode,
        )

    def selection_provenance(
        self,
        *,
        side: Side,
        option_id: PlayerOptionId,
        opponent_option_id: PlayerOptionId | None = None,
    ) -> ModelSOModelCatalogSelectionProvenance:
        """Return complete source provenance for one explicit seat selection."""

        seat = next((seat for seat in self.seats if seat.side == side), None)
        if seat is None:
            raise ValueError(f"catalog has no {side} seat policy")
        if option_id not in seat.allowed_option_ids:
            raise ValueError(f"option {option_id!r} is not allowed for {side} seat")
        option = self._option_for_id(option_id)
        if opponent_option_id is None:
            opposite = self.seats[1] if side == "red" else self.seats[0]
            if opposite.default_option_id is None:
                raise ValueError("selection provenance requires an explicit paired option")
            opponent_option_id = opposite.default_option_id
        pairing = (
            self.pairing_provenance(
                red_option_id=option_id,
                blue_option_id=opponent_option_id,
            )
            if side == "red"
            else self.pairing_provenance(
                red_option_id=opponent_option_id,
                blue_option_id=option_id,
            )
        )
        if isinstance(option, ModelSOModelCatalogHumanOption):
            return ModelSOModelCatalogSelectionProvenance(
                schema_version="1",
                kind="steel_onslaught.model_catalog_selection",
                selection_kind="human",
                catalog_id=self.catalog_id,
                catalog_sha256=self.canonical_sha256(),
                side=side,
                option_id=option.option_id,
                loadout_id=seat.loadout_id,
                display_name=option.display_name,
                source_overlay_id=option.source_overlay_id,
                source_overlay_sha256=option.source_overlay_sha256,
                source_roster_id=option.source_roster_id,
                source_roster_sha256=option.source_roster_sha256,
                pilot_spec_id=option.pilot_spec_id,
                paired_option_id=opponent_option_id,
                pairing=pairing,
                human_identity_id=option.human_identity_id,
            )
        return ModelSOModelCatalogSelectionProvenance(
            schema_version="1",
            kind="steel_onslaught.model_catalog_selection",
            selection_kind="model",
            catalog_id=self.catalog_id,
            catalog_sha256=self.canonical_sha256(),
            side=side,
            option_id=option.option_id,
            loadout_id=seat.loadout_id,
            display_name=option.display_name,
            source_overlay_id=option.source_overlay_id,
            source_overlay_sha256=option.source_overlay_sha256,
            source_roster_id=option.source_roster_id,
            source_roster_sha256=option.source_roster_sha256,
            pilot_spec_id=option.pilot_spec_id,
            paired_option_id=opponent_option_id,
            pairing=pairing,
            model_identity_id=option.model_identity_id,
            provider_binding_id=option.provider_binding_id,
            provider_model=option.provider_model,
            persona_id=option.persona_id,
        )


def model_catalog_source_from_roster(
    *,
    overlay_id: OverlayId,
    overlay_sha256: Sha256Digest,
    roster: ModelSOPlayerRosterBinding,
    model_identities: Sequence[ModelSOModelIdentityBinding],
    provider_models: Mapping[ProviderBindingId, str],
    option_id_map: Mapping[PlayerOptionId, PlayerOptionId] | None = None,
) -> ModelSOModelCatalogSource:
    """Create one catalog source from already validated overlay dependencies.

    ``option_id_map`` is explicit when source rosters are combined.  If it is
    supplied, it must map every source option exactly once; no namespace or
    provider fallback is inferred.
    """

    identities = {identity.model_identity_id: identity for identity in model_identities}
    source_ids = {option.option_id for option in roster.options}
    mapping = dict(option_id_map or {option_id: option_id for option_id in source_ids})
    if set(mapping) != source_ids:
        missing = sorted(source_ids - set(mapping))
        extra = sorted(set(mapping) - source_ids)
        raise ValueError(
            "catalog option_id_map must cover source options exactly "
            f"(missing={missing}, extra={extra})"
        )
    if len(mapping.values()) != len(set(mapping.values())):
        raise ValueError("catalog option_id_map must produce unique catalog option ids")

    catalog_options: list[CatalogOptionBinding] = []
    roster_sha256 = roster.canonical_sha256()
    for option in roster.options:
        catalog_option_id = mapping[option.option_id]
        if isinstance(option, ModelSOHumanPlayerOptionBinding):
            catalog_options.append(
                ModelSOModelCatalogHumanOption(
                    kind="human",
                    option_id=catalog_option_id,
                    display_name=option.display_name,
                    human_identity_id=option.human_identity_id,
                    pilot_spec_id=option.pilot_spec_id,
                    input_source=option.input_source,
                    source_overlay_id=overlay_id,
                    source_overlay_sha256=overlay_sha256,
                    source_roster_id=roster.roster_id,
                    source_roster_sha256=roster_sha256,
                )
            )
            continue
        identity = identities.get(option.model_identity_id)
        if identity is None:
            raise ValueError(
                f"catalog source references unknown model identity {option.model_identity_id!r}"
            )
        provider_model = provider_models.get(identity.provider_binding_id)
        if provider_model is None:
            raise ValueError(
                "catalog source has no configured model for provider "
                f"{identity.provider_binding_id!r}"
            )
        catalog_options.append(
            ModelSOModelCatalogModelOption(
                kind="model",
                option_id=catalog_option_id,
                display_name=option.display_name,
                model_identity_id=option.model_identity_id,
                provider_binding_id=identity.provider_binding_id,
                provider_model=provider_model,
                pilot_spec_id=option.pilot_spec_id,
                persona_id=option.persona_id,
                input_source=option.input_source,
                source_overlay_id=overlay_id,
                source_overlay_sha256=overlay_sha256,
                source_roster_id=roster.roster_id,
                source_roster_sha256=roster_sha256,
            )
        )
    return ModelSOModelCatalogSource(
        source_overlay_id=overlay_id,
        source_overlay_sha256=overlay_sha256,
        source_roster_id=roster.roster_id,
        source_roster_sha256=roster_sha256,
        options=tuple(catalog_options),
    )


def build_model_catalog(
    *,
    catalog_id: CatalogId,
    roster_id: RosterId,
    sources: Sequence[ModelSOModelCatalogSource],
    seats: tuple[ModelSOSeatLaunchPolicy, ModelSOSeatLaunchPolicy],
    default_chassis_ids: tuple[str, str],
    mirror_match_mode: bool = False,
) -> ModelSOModelCatalog:
    """Merge explicitly declared sources into one canonical catalog."""

    if not sources:
        raise ValueError("model catalog requires at least one explicit source")
    options = tuple(option for source in sources for option in source.options)
    return ModelSOModelCatalog(
        schema_version="1",
        kind="steel_onslaught.model_catalog",
        catalog_id=catalog_id,
        roster_id=roster_id,
        options=options,
        seats=seats,
        default_chassis_ids=default_chassis_ids,
        mirror_match_mode=mirror_match_mode,
    )


__all__ = [
    "CatalogId",
    "CatalogOptionBinding",
    "CatalogSourceId",
    "ModelSOModelCatalog",
    "ModelSOModelCatalogHumanOption",
    "ModelSOModelCatalogIndex",
    "ModelSOModelCatalogModelOption",
    "ModelSOModelCatalogOptionAlias",
    "ModelSOModelCatalogPairingProvenance",
    "ModelSOModelCatalogProjection",
    "ModelSOModelCatalogSelectionProvenance",
    "ModelSOModelCatalogSource",
    "ModelSOModelCatalogSourceBinding",
    "ModelSOPublicModelCatalogHumanOption",
    "ModelSOPublicModelCatalogModelOption",
    "OverlayId",
    "PublicModelCatalogOption",
    "build_model_catalog",
    "model_catalog_source_from_roster",
]
