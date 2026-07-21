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
from typing import Annotated, Final, Literal, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints, model_validator

from steel_onslaught.contracts.player_selection import (
    HumanIdentityId,
    LoadoutId,
    ModelIdentityId,
    ModelSOHumanPlayerOptionBinding,
    ModelSOModelIdentityBinding,
    ModelSOModelPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    ModelSOSeatLaunchPolicy,
    ModelSOSeatOptionLoadoutBinding,
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
# A programmer source is the provider binding behind a model option or the
# human identity behind a human option.  Both already share this shape, so one
# constrained alias keeps the seat-identity pair closed without widening either
# side to a free string.
ProgrammerSourceId = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]*$")]

HUMAN_ROLE_ID: Final = "human"


class CatalogSeatIdentity(NamedTuple):
    """The two facts that make one catalog option its own decision-maker.

    This mirrors ``match.composition.SeatProgrammerIdentity`` — the runtime
    check that actually fails a live mirror closed — so the catalog and the
    runtime cannot disagree about what a mirror is.  Persona alone is *not*
    the identity: the same persona driven by two different models is the
    cleanest model-vs-model contest there is.  The same persona on the same
    provider, on both seats, is a mirror.
    """

    programmer_source_id: str
    role_id: str


class CatalogSeatIdentityError(ValueError):
    """Both seats resolved to one decision-maker, so the pairing is a mirror.

    Kept as its own type — and carrying the same ``error_code`` the browser
    transport reports for the runtime seat-identity failure — so a rejected
    pairing is never surfaced to an operator as an authorization or provider
    error.  ``ValueError`` remains the base so existing closed-contract
    callers keep their fail-closed behaviour.
    """

    error_code: Final = "seat_identity_conflict"

    def __init__(
        self, message: str, *, red: CatalogSeatIdentity, blue: CatalogSeatIdentity
    ) -> None:
        super().__init__(message)
        self.red = red
        self.blue = blue


def describe_seat_identity_conflict(*, red: CatalogSeatIdentity, blue: CatalogSeatIdentity) -> str:
    """Render the mirror rejection in words an operator can act on."""

    if red.role_id == HUMAN_ROLE_ID and blue.role_id == HUMAN_ROLE_ID:
        return (
            "Both seats are the same human operator "
            f"({red.programmer_source_id}). Pick a model for one seat."
        )
    return (
        f"Both seats would be the same pilot: {red.role_id} on {red.programmer_source_id}. "
        "Change the model or the persona on one seat — the same persona on two "
        "different models is allowed."
    )


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
    red_loadout_id: LoadoutId | None = None
    blue_loadout_id: LoadoutId | None = None


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
    red_loadout_id: LoadoutId | None = None
    blue_loadout_id: LoadoutId | None = None


CatalogOptionBinding = Annotated[
    ModelSOModelCatalogHumanOption | ModelSOModelCatalogModelOption,
    Field(discriminator="kind"),
]


class ModelSOPublicModelCatalogHumanOption(_ClosedCatalogModel):
    """Secret-free human option.

    ``human_identity_id`` is published because it is half of this option's seat
    identity: without it a browser cannot tell that two differently-named human
    options are the same operator, and it would offer a mirror the server will
    reject.  It is a local contract id, never a credential.
    """

    kind: Literal["human"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    human_identity_id: HumanIdentityId


class ModelSOPublicModelCatalogModelOption(_ClosedCatalogModel):
    """Secret-free model option carrying the full identity an operator picks by.

    ``persona_id`` is published for the same reason as ``human_identity_id``
    above: model identity alone cannot distinguish "Qwen35 / sniper" from
    "Qwen35 / berserker", and it is the other half of the seat-identity pair.
    """

    kind: Literal["model"]
    option_id: PlayerOptionId
    display_name: StrictStr = Field(min_length=1, max_length=80)
    model_identity_id: ModelIdentityId
    provider_binding_id: ProviderBindingId
    provider_model: StrictStr = Field(min_length=1, max_length=160)
    persona_id: PersonaId


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
    red_programmer_source_id: ProgrammerSourceId
    blue_programmer_source_id: ProgrammerSourceId
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

    @property
    def red_seat_identity(self) -> CatalogSeatIdentity:
        return CatalogSeatIdentity(self.red_programmer_source_id, self.red_role_id)

    @property
    def blue_seat_identity(self) -> CatalogSeatIdentity:
        return CatalogSeatIdentity(self.blue_programmer_source_id, self.blue_role_id)

    @model_validator(mode="after")
    def _pairing_is_distinct_without_mirror_mode(self) -> Self:
        """Reject only a true mirror: one option, or one seat identity, twice.

        Role alone is deliberately NOT the rejection key.  Sniper-vs-sniper
        across two different providers is a legal — and the most informative —
        model-vs-model contest, so it is admitted here exactly as the runtime
        seat-identity check admits it.

        Loadout and chassis symmetry are also deliberately *not* mirror
        conditions any more.  They were, while the catalog shipped one curated
        pairing; with every configured option offered to both seats they reject
        legitimate pairings (a human option and the model option that shares its
        source loadout), and two identical mechs flown by two different models
        is a controlled comparison rather than a mirror.  The declaration that
        a catalog's two chassis differ is still enforced on the catalog itself.
        """

        if self.mirror_match_mode:
            return self
        if self.red_option_id == self.blue_option_id:
            raise ValueError("duplicate default option requires mirror_match_mode")
        if self.red_seat_identity == self.blue_seat_identity:
            raise ValueError("duplicate default seat identity requires mirror_match_mode")
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
    loadout_paths: tuple[StrictStr, StrictStr] | None = None
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


class ModelSOCatalogSeatPolicy(_ClosedCatalogModel):
    """Index-level seat policy whose allow-list defaults to every option.

    ``allowed_option_ids`` is still a real, enforced mechanism — the command
    authority rejects any selection outside the materialized list, and a
    deployment that must fence a seat can still name a subset.  What changed is
    the default: omitting it declares "this seat may pick any configured
    option", which is the shipped posture.  Curating the list by hand was the
    reason a newly configured model silently failed to appear in a seat's
    dropdown (or made the whole catalog invalid as an unreachable option).
    """

    side: Side
    loadout_id: LoadoutId
    allowed_option_ids: tuple[PlayerOptionId, ...] | None = None
    default_option_id: PlayerOptionId | None = None
    option_loadouts: tuple[ModelSOSeatOptionLoadoutBinding, ...] = ()

    @model_validator(mode="after")
    def _declared_allow_list_is_usable(self) -> Self:
        if self.allowed_option_ids is None:
            return self
        if not self.allowed_option_ids:
            raise ValueError("an explicit allowed_option_ids must name at least one option")
        if len(self.allowed_option_ids) != len(set(self.allowed_option_ids)):
            raise ValueError("allowed_option_ids must be unique")
        return self

    def materialize(self, catalog_option_ids: Sequence[PlayerOptionId]) -> ModelSOSeatLaunchPolicy:
        """Expand into the fully explicit runtime seat policy.

        The runtime contract stays closed and explicit: the merged catalog and
        its projected roster always carry a literal option list, so nothing
        downstream has to interpret ``None``.
        """

        allowed = (
            tuple(catalog_option_ids)
            if self.allowed_option_ids is None
            else self.allowed_option_ids
        )
        return ModelSOSeatLaunchPolicy(
            side=self.side,
            loadout_id=self.loadout_id,
            allowed_option_ids=allowed,
            default_option_id=self.default_option_id,
            option_loadouts=self.option_loadouts,
        )


CatalogSeatPolicySpec = ModelSOSeatLaunchPolicy | ModelSOCatalogSeatPolicy


class ModelSOModelCatalogIndex(_ClosedCatalogModel):
    """Declarative index of the exact overlay/roster sources to merge."""

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.model_catalog_sources"]
    catalog_id: CatalogId
    roster_id: RosterId
    sources: tuple[ModelSOModelCatalogSourceBinding, ...] = Field(min_length=1)
    seats: tuple[ModelSOCatalogSeatPolicy, ModelSOCatalogSeatPolicy]
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
        overlay_ids = [source.source_overlay_id for source in self.sources]
        if len(overlay_ids) != len(set(overlay_ids)):
            raise ValueError("catalog sources must declare unique source_overlay_id values")
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
            red_default, blue_default = defaults[0], defaults[1]
            identities = (
                self._seat_identity_for_option(self._option_for_id(red_default)),
                self._seat_identity_for_option(self._option_for_id(blue_default)),
            )
            if identities[0] == identities[1]:
                raise ValueError("duplicate default seat identity requires mirror_match_mode")
            # Both defaults must resolve to a declared loadout; a catalog that
            # cannot seat its own defaults is invalid regardless of symmetry.
            self.seats[0].loadout_for_option(defaults[0])
            self.seats[1].loadout_for_option(defaults[1])
            if self.default_chassis_ids[0] == self.default_chassis_ids[1]:
                raise ValueError("duplicate default chassis requires mirror_match_mode")
        return self

    @staticmethod
    def _role_for_option(option: CatalogOptionBinding) -> str:
        return (
            HUMAN_ROLE_ID
            if isinstance(option, ModelSOModelCatalogHumanOption)
            else option.persona_id
        )

    @staticmethod
    def _seat_identity_for_option(option: CatalogOptionBinding) -> CatalogSeatIdentity:
        """Return the ``(programmer source, role)`` identity of one option.

        A human option's decision-maker is the human identity behind it, so two
        differently-named options for the same operator are one identity.  A
        model option's decision-maker is its provider binding plus its persona.
        """

        if isinstance(option, ModelSOModelCatalogHumanOption):
            return CatalogSeatIdentity(option.human_identity_id, HUMAN_ROLE_ID)
        return CatalogSeatIdentity(option.provider_binding_id, option.persona_id)

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
        red_identity = self._seat_identity_for_option(self._option_for_id(red_option_id))
        blue_identity = self._seat_identity_for_option(self._option_for_id(blue_option_id))
        red_role = red_identity.role_id
        blue_role = blue_identity.role_id
        red_loadout_id = red_seat.loadout_for_option(red_option_id)
        blue_loadout_id = blue_seat.loadout_for_option(blue_option_id)
        pairing_fields = {
            "schema_version": "1",
            "kind": "steel_onslaught.model_catalog_pairing",
            "catalog_id": self.catalog_id,
            "catalog_sha256": self.canonical_sha256(),
            "red_option_id": red_option_id,
            "blue_option_id": blue_option_id,
            "red_role_id": red_role,
            "blue_role_id": blue_role,
            "red_programmer_source_id": red_identity.programmer_source_id,
            "blue_programmer_source_id": blue_identity.programmer_source_id,
            "red_loadout_id": red_loadout_id,
            "blue_loadout_id": blue_loadout_id,
            "red_chassis_id": self.default_chassis_ids[0],
            "blue_chassis_id": self.default_chassis_ids[1],
            "mirror_match_mode": self.mirror_match_mode,
        }
        if not self.mirror_match_mode and red_identity == blue_identity:
            # One typed failure covers both "the same option twice" and "two
            # different options that are the same decision-maker", because the
            # operator-visible fact is identical in both cases.
            raise CatalogSeatIdentityError(
                describe_seat_identity_conflict(red=red_identity, blue=blue_identity),
                red=red_identity,
                blue=blue_identity,
            )
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
            red_programmer_source_id=red_identity.programmer_source_id,
            blue_programmer_source_id=blue_identity.programmer_source_id,
            red_loadout_id=red_loadout_id,
            blue_loadout_id=blue_loadout_id,
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
        policies: list[ModelSOSeatLaunchPolicy] = []
        for seat in self.seats:
            option_loadouts: list[ModelSOSeatOptionLoadoutBinding] = []
            for option_id in seat.allowed_option_ids:
                option = self._option_for_id(option_id)
                loadout_id = option.red_loadout_id if seat.side == "red" else option.blue_loadout_id
                if loadout_id is not None:
                    option_loadouts.append(
                        ModelSOSeatOptionLoadoutBinding(
                            option_id=option_id,
                            loadout_id=loadout_id,
                        )
                    )
            policies.append(seat.model_copy(update={"option_loadouts": tuple(option_loadouts)}))
        return ModelSOPlayerRosterBinding(
            schema_version="1",
            kind="steel_onslaught.player_roster",
            roster_id=self.roster_id,
            options=tuple(options),
            seats=(policies[0], policies[1]),
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
                        human_identity_id=option.human_identity_id,
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
                        persona_id=option.persona_id,
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
        loadout_id = seat.loadout_for_option(option_id)
        if isinstance(option, ModelSOModelCatalogHumanOption):
            return ModelSOModelCatalogSelectionProvenance(
                schema_version="1",
                kind="steel_onslaught.model_catalog_selection",
                selection_kind="human",
                catalog_id=self.catalog_id,
                catalog_sha256=self.canonical_sha256(),
                side=side,
                option_id=option.option_id,
                loadout_id=loadout_id,
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
            loadout_id=loadout_id,
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
    # Preserve seat-specific option loadout mappings when a source roster
    # differentiates the two roles.  Falling back through ``loadout_for_option``
    # keeps legacy one-loadout rosters compatible while ensuring the catalog
    # cannot silently collapse distinct source options onto one loadout.
    seat_loadouts = {
        seat.side: {
            option_id: seat.loadout_for_option(option_id) for option_id in seat.allowed_option_ids
        }
        for seat in roster.seats
    }

    def declared_loadouts(option_id: PlayerOptionId) -> tuple[LoadoutId | None, LoadoutId | None]:
        """Return this option's ``(red, blue)`` loadouts from its source roster.

        A source roster that binds an option to only one of its seats still
        declares that option's loadout exactly once.  The catalog offers every
        configured option to both seats, so that single declared loadout is the
        one used by whichever seat selects it.  Nothing is inferred from a name
        and no loadout is invented: if the source roster declared none for
        either seat, both stay ``None`` and the seat's own loadout applies.
        """

        red = seat_loadouts["red"].get(option_id)
        blue = seat_loadouts["blue"].get(option_id)
        return (red if red is not None else blue, blue if blue is not None else red)

    for option in roster.options:
        red_loadout_id, blue_loadout_id = declared_loadouts(option.option_id)
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
                    red_loadout_id=red_loadout_id,
                    blue_loadout_id=blue_loadout_id,
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
                red_loadout_id=red_loadout_id,
                blue_loadout_id=blue_loadout_id,
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
    seats: tuple[CatalogSeatPolicySpec, CatalogSeatPolicySpec],
    default_chassis_ids: tuple[str, str],
    mirror_match_mode: bool = False,
    resolve_option_loadouts: bool = False,
) -> ModelSOModelCatalog:
    """Merge explicitly declared sources into one canonical catalog.

    An index seat that omits ``allowed_option_ids`` is materialized here into
    the explicit list of every merged catalog option, in source declaration
    order, so the built catalog is always fully explicit.
    """

    if not sources:
        raise ValueError("model catalog requires at least one explicit source")
    options = tuple(option for source in sources for option in source.options)
    option_by_id = {option.option_id: option for option in options}
    catalog_option_ids = tuple(option.option_id for option in options)
    declared_seats = tuple(
        seat if isinstance(seat, ModelSOSeatLaunchPolicy) else seat.materialize(catalog_option_ids)
        for seat in seats
    )
    resolved_seats: list[ModelSOSeatLaunchPolicy] = []
    for seat in declared_seats:
        # An index that spells its own per-option loadouts out stays
        # authoritative; resolution only fills a seat that declared none.
        if not resolve_option_loadouts or seat.option_loadouts:
            resolved_seats.append(seat)
            continue
        option_loadouts: list[ModelSOSeatOptionLoadoutBinding] = []
        for option_id in seat.allowed_option_ids:
            option = option_by_id[option_id]
            loadout_id = option.red_loadout_id if seat.side == "red" else option.blue_loadout_id
            if loadout_id is None:
                break
            option_loadouts.append(
                ModelSOSeatOptionLoadoutBinding(
                    option_id=option_id,
                    loadout_id=loadout_id,
                )
            )
        if len(option_loadouts) == len(seat.allowed_option_ids):
            resolved_seats.append(
                seat.model_copy(update={"option_loadouts": tuple(option_loadouts)})
            )
        else:
            resolved_seats.append(seat)
    return ModelSOModelCatalog(
        schema_version="1",
        kind="steel_onslaught.model_catalog",
        catalog_id=catalog_id,
        roster_id=roster_id,
        options=options,
        seats=(resolved_seats[0], resolved_seats[1]),
        default_chassis_ids=default_chassis_ids,
        mirror_match_mode=mirror_match_mode,
    )


__all__ = [
    "HUMAN_ROLE_ID",
    "CatalogId",
    "CatalogOptionBinding",
    "CatalogSeatIdentity",
    "CatalogSeatIdentityError",
    "CatalogSeatPolicySpec",
    "CatalogSourceId",
    "ModelSOCatalogSeatPolicy",
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
    "ProgrammerSourceId",
    "PublicModelCatalogOption",
    "build_model_catalog",
    "describe_seat_identity_conflict",
    "model_catalog_source_from_roster",
]
