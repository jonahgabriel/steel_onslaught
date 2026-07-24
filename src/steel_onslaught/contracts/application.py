"""Closed application overlay for the current Slice-1 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.deck import DeckId
from steel_onslaught.contracts.model_catalog import ModelSOModelCatalogProjection
from steel_onslaught.contracts.pilot import PilotId
from steel_onslaught.contracts.player_selection import (
    ModelSOModelIdentityBinding,
    ModelSOPlayerRosterProjection,
    Side,
)
from steel_onslaught.contracts.split_deck import ModelSOCardDeckPolicy
from steel_onslaught.pilots.persona_prompts import (
    ModelSOMatchPromptProvenance,
    ModelSOPersonaPromptOverride,
)
from steel_onslaught.pilots.programming import ModelSOCardRuleCatalogProjection


class _ClosedBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ModelSOInProcessBusBinding(_ClosedBinding):
    kind: Literal["in_process"]


class ModelSOSQLiteEventLedgerBinding(_ClosedBinding):
    kind: Literal["sqlite"]
    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    event_schema: Literal["canonical_event_v1"]


class ModelSOSQLiteLeaderboardBinding(_ClosedBinding):
    kind: Literal["sqlite"]
    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    storage_schema: Literal["leaderboard_v1"]


class ModelSOFilesystemLearningArtifactsBinding(_ClosedBinding):
    kind: Literal["filesystem_yaml"]
    evaluation_root: Path
    lineage_root: Path
    experiment_root: Path


class ModelSOSelectionOutcomeThresholds(_ClosedBinding):
    """Scalar promotion-threshold overrides for the ``selection_outcome_v1`` lane.

    Field-for-field mirror of ``learning.promotion.ModelSOPromotionThresholds``
    (same names, same defaults, same ranges) — the overlay contract layer does
    not import the learning package, so the mirror is asserted by a parity
    test instead of a shared import.
    """

    p_value_max: StrictFloat = Field(default=0.05, gt=0.0, le=1.0)
    min_decisive_n: StrictInt = Field(default=10, ge=1)
    max_overload_rate_increase: StrictFloat = Field(default=0.05, ge=0.0)
    max_draw_rate: StrictFloat = Field(default=0.5, ge=0.0, le=1.0)
    min_param_distance: StrictFloat = Field(default=0.05, ge=0.0, le=1.0)


class ModelSOLiveLearningBinding(_ClosedBinding):
    """Opt-in live learning lane for one archetype's policy chain.

    ``genesis_parameters`` seed generation 0; once promotions exist in the
    event ledger, composition rehydrates the current policy from the durable
    ``POLICY_PROMOTED`` chain + lineage store instead (the event stream is
    the source of truth — changing genesis after promotions exist fails
    closed at composition).

    Two evaluator kinds select the live judgment behind the same coordinator:

    - ``win_damage_differential_v1`` — the deterministic single-match
      judgment (``parameter``/``step``/``max_value`` govern the perturbation).
    - ``selection_outcome_v1`` — evidence-driven proposal gated through the
      offline duel machinery; requires ``base_loadout_path`` (the loadout
      both duel sides field) and consumes ``duel_max_ticks`` /
      ``n_search_seeds`` / ``n_holdout_seeds`` / ``step_multiplier`` /
      ``thresholds`` (``parameter`` names the perturbed parameter; ``step``
      and ``max_value`` are ignored — the archetype bounds lattice governs).
    """

    kind: Literal["win_damage_differential_v1", "selection_outcome_v1"]
    archetype: StrictStr = Field(min_length=1)
    learning_player_id: StrictStr = Field(min_length=1)
    genesis_parameters: dict[str, StrictInt | StrictFloat | StrictStr] = Field(min_length=1)
    parameter: StrictStr = Field(min_length=1, default="aggression")
    step: StrictFloat = Field(gt=0, default=0.25)
    max_value: StrictFloat = Field(default=3.0)
    # selection_outcome_v1 lane only:
    base_loadout_path: Path | None = None
    duel_max_ticks: StrictInt = Field(gt=0, default=200)
    n_search_seeds: StrictInt = Field(ge=1, default=3)
    n_holdout_seeds: StrictInt = Field(ge=1, default=2)
    step_multiplier: StrictInt = Field(ge=1, default=1)
    thresholds: ModelSOSelectionOutcomeThresholds | None = None

    @model_validator(mode="after")
    def _kind_matches_lane_fields(self) -> Self:
        if self.kind == "selection_outcome_v1":
            if self.base_loadout_path is None:
                raise ValueError("selection_outcome_v1 requires base_loadout_path for its duels")
        else:
            if self.base_loadout_path is not None:
                raise ValueError(
                    "base_loadout_path is only consumed by selection_outcome_v1; "
                    "remove it from a win_damage_differential_v1 binding"
                )
            if self.thresholds is not None:
                raise ValueError(
                    "thresholds are only consumed by selection_outcome_v1; "
                    "remove them from a win_damage_differential_v1 binding"
                )
        return self


class ModelSOSQLiteEvaluationStorageBinding(_ClosedBinding):
    """Evaluation-local event and projection storage selected by the operator."""

    kind: Literal["sqlite"]
    root: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    event_schema: Literal["canonical_event_v1"]
    leaderboard_schema: Literal["leaderboard_v1"]


class ModelSOCardProgrammerBinding(_ClosedBinding):
    """Explicit seat-to-pilot-spec binding for card-mode programming."""

    side: Side
    pilot_spec_id: PilotId
    # Card-mode live experiments may explicitly record typed recovery instead
    # of aborting the match on a malformed provider plan.  The strict default
    # preserves fail-closed production behavior.
    failure_policy: Literal["raise", "fallback"] = "raise"


class ModelSOCardCatalogBinding(_ClosedBinding):
    """Explicit card/deck content roots selected by an application overlay."""

    kind: Literal["filesystem_yaml"]
    cards_dir: Path
    decks_dir: Path
    # A binding can describe content without activating card gameplay.  If a
    # caller opts into card mode, it must name the deck explicitly; no loader
    # may infer the first or a package-default deck.
    card_mode_enabled: StrictBool = False
    deck_id: DeckId | None = None
    # Optional split-deck composition.  Absence preserves the original
    # selected-single-deck card runtime; activation is explicit and cannot be
    # combined with the legacy ``deck_id`` selector.
    deck_policy: ModelSOCardDeckPolicy | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    # Card rounds are atomic by default.  ``paced`` is an explicit opt-in
    # because it changes the lifecycle timeline (one register per tick).
    card_cadence: Literal["atomic", "paced"] = "atomic"
    # Optional whole-round programmer bindings.  These are contract references
    # only; composition resolves the exact pilot spec, provider client, and
    # persona after all roots are validated.  An absent binding intentionally
    # preserves the deterministic priority programmer.
    programmers: tuple[ModelSOCardProgrammerBinding, ...] = ()

    @model_validator(mode="after")
    def _card_mode_requires_explicit_deck(self) -> Self:
        if self.card_mode_enabled and self.deck_id is None and self.deck_policy is None:
            raise ValueError("card_mode_enabled requires an explicit deck_id")
        if not self.card_mode_enabled and (
            self.deck_id is not None or self.deck_policy is not None
        ):
            raise ValueError("deck_id requires card_mode_enabled")
        if self.deck_policy is not None and self.deck_id is not None:
            raise ValueError("deck_policy cannot be combined with the selected deck_id")
        if not self.card_mode_enabled and self.programmers:
            raise ValueError("card programmer bindings require card_mode_enabled")
        if not self.card_mode_enabled and self.card_cadence != "atomic":
            raise ValueError("paced card cadence requires card_mode_enabled")
        sides = tuple(programmer.side for programmer in self.programmers)
        if len(sides) != len(set(sides)):
            raise ValueError("card programmer bindings must declare each seat at most once")
        return self


class ModelSOBalanceRulePackBinding(_ClosedBinding):
    """Explicit allowlisted card-programming rule pack selection."""

    kind: Literal["card_programming_rules"]
    pack_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    # Order is semantic: handlers are applied in this declared sequence.
    handler_ids: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def _handler_ids_are_unique(self) -> Self:
        if len(self.handler_ids) != len(set(self.handler_ids)):
            raise ValueError("balance rule handler_ids must be unique")
        return self


class ModelSOUtilityHandlerPackBinding(_ClosedBinding):
    """Explicit allowlisted utility-resolution handler pack selection (Phase 2).

    Mirrors ``ModelSOBalanceRulePackBinding`` but for the *resolution* phase:
    which smoke/chaff/flares handlers a match may use.  ``handler_ids`` selects
    a fail-closed subset of the canonical pack; an empty tuple is rejected so
    an overlay that opts in must name at least one handler.  Overlays that omit
    this binding keep the full default pack.
    """

    kind: Literal["utility_resolution_handlers"]
    pack_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    handler_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _handler_ids_are_unique(self) -> Self:
        if len(self.handler_ids) != len(set(self.handler_ids)):
            raise ValueError("utility handler_ids must be unique")
        return self


class ModelSOContractBindings(_ClosedBinding):
    """Filesystem contract roots owned by the application overlay.

    ``card_catalog`` is intentionally an opt-in binding while card runtime
    activation remains a later slice.  When present, both roots are resolved
    relative to the overlay and injected as configuration; no implicit
    package-path or default-deck lookup is permitted.
    """

    catalog_dir: Path
    pilot_registry_dir: Path
    arena_id: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]*$")
    card_catalog: ModelSOCardCatalogBinding | None = None
    balance_rule_pack: ModelSOBalanceRulePackBinding | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    utility_handler_pack: ModelSOUtilityHandlerPackBinding | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class ModelSOSystemClockBinding(_ClosedBinding):
    kind: Literal["system_utc"]


class ModelSOSystemIdentityBinding(_ClosedBinding):
    kind: Literal["system"]


class ModelSOFrontendTransportBinding(_ClosedBinding):
    """Public receive-only browser transport selected by the operator."""

    kind: Literal["websocket"]
    contract: Literal["steel_onslaught.frontend_transport.v1"]
    websocket_url: StrictStr = Field(min_length=1)
    event_schema: Literal["canonical_event_v1"]
    milliseconds_per_tick: StrictInt = Field(gt=0, le=60_000)

    @field_validator("websocket_url")
    @classmethod
    def _complete_websocket_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            raise ValueError("websocket_url must be a complete ws(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("websocket_url must not contain user information")
        if parsed.query or parsed.fragment:
            raise ValueError("websocket_url must not contain a query or fragment")
        if parsed.path in {"", "/"}:
            raise ValueError("websocket_url must declare an explicit stream path")
        if parsed.port is None:
            raise ValueError("websocket_url must declare an explicit port")
        return value


class ModelSOFrontendCommandGatewayBinding(_ClosedBinding):
    """Public local-browser command ingress selected by the server root.

    The binding exposes only a loopback WebSocket endpoint and the exact
    process-local authority contract. Principal/session identities and all
    provider capabilities remain server-held.
    """

    kind: Literal["websocket"]
    contract: Literal["steel_onslaught.browser_command_gateway.v1"]
    websocket_url: StrictStr = Field(min_length=1)
    authority_scope: Literal["injected_process_session"]

    @field_validator("websocket_url")
    @classmethod
    def _complete_loopback_websocket_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            raise ValueError("websocket_url must be a complete ws(s) URL")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("websocket_url must use a loopback host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("websocket_url must not contain user information")
        if parsed.query or parsed.fragment:
            raise ValueError("websocket_url must not contain a query or fragment")
        if parsed.path in {"", "/"}:
            raise ValueError("websocket_url must declare an explicit command path")
        if parsed.port is None:
            raise ValueError("websocket_url must declare an explicit port")
        return value


class ModelSOSecretRef(_ClosedBinding):
    """Opaque reference resolved by an injected capability, never secret material."""

    kind: Literal["opaque"]
    ref: StrictStr = Field(
        min_length=12,
        max_length=140,
        pattern=r"^secret://[a-z][a-z0-9_.-]{0,63}/[a-z][a-z0-9_.-]{0,63}$",
    )


class ModelSONoSecretResolverBinding(_ClosedBinding):
    kind: Literal["none"]


class ModelSOInjectedSecretResolverBinding(_ClosedBinding):
    kind: Literal["injected"]


class ModelSOLlmRetryBinding(_ClosedBinding):
    """Explicit deterministic retry policy for one HTTP provider."""

    max_attempts: StrictInt = Field(ge=1, le=5)
    initial_backoff_seconds: StrictFloat = Field(ge=0.0, le=60.0, allow_inf_nan=False)
    backoff_multiplier: StrictFloat = Field(ge=1.0, le=4.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _bounded_schedule(self) -> Self:
        final_backoff = self.initial_backoff_seconds * (
            self.backoff_multiplier ** (self.max_attempts - 1)
        )
        if final_backoff > 300.0:
            raise ValueError("retry schedule exceeds the 300 second backoff bound")
        return self


class ModelSOStubLlmProviderBinding(_ClosedBinding):
    kind: Literal["stub"]
    provider_id: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)


class ModelSOThinkingBinding(_ClosedBinding):
    """Optional provider ``thinking`` control forwarded verbatim into the chat body.

    Some OpenAI-compatible providers (e.g. Zhipu/GLM over z.ai) narrate their
    chain-of-thought into ``content`` unless the request explicitly disables the
    thinking span. This closed binding is serialized as a top-level
    ``thinking`` object on the request body only when declared; keyless and
    OpenRouter overlays that omit it produce a byte-identical request.
    """

    type: Literal["enabled", "disabled"]


class ModelSOLlmImageAttachmentBinding(_ClosedBinding):
    """Declares a config-time, deterministic per-tick arena render for this seat.

    ``arena_size`` is a static, config-declared value -- the overlay is
    authored for one specific arena, so the render call needs no dynamic
    threading of the live ``ModelSOArenaSpec`` through the pilot-factory
    graph. ``render_output_dir`` is the state-root-relative directory PNGs
    are persisted under, keyed by match id and tick, so the render evidence
    is durable and auditable alongside the sha256 recorded in the event
    ledger. Present only on the V-IMG arm's provider binding; the V-TEXT arm
    omits it entirely (``None``), which is what keeps V-TEXT byte-identical
    to the pre-existing text-only wire body.
    """

    enabled: Literal[True]
    arena_size: StrictInt = Field(gt=0, le=200)
    render_output_dir: Path


class ModelSOOpenAICompatibleProviderBinding(_ClosedBinding):
    kind: Literal["openai_compatible"]
    provider_id: StrictStr = Field(min_length=1)
    endpoint_url: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)
    secret_ref: ModelSOSecretRef | None
    timeout_seconds: StrictFloat = Field(gt=0.0, le=600.0, allow_inf_nan=False)
    max_tokens: StrictInt | None = Field(gt=0, le=32768)
    retry: ModelSOLlmRetryBinding
    # Optional provider-specific request extension. Present only for providers
    # that require ``thinking`` control; ``None`` (the default for every existing
    # overlay) forwards nothing, so the wire body stays byte-identical.
    thinking: ModelSOThinkingBinding | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    # Optional per-seat image-representation arm (2026-07-24 vision pilot
    # experiment). ``None`` on every existing overlay and on the V-TEXT arm of
    # the vision experiment itself; only the V-IMG arm's provider binding sets
    # this. This binding never reaches the wire request directly -- it only
    # configures the pilot-factory render call -- so it carries no
    # ``exclude_if`` significance for ``ModelSOOpenAIChatRequest`` byte
    # identity (that identity is guarded by ``ModelSOLlmCompletionRequest
    # .image_attachment`` staying ``None`` on every non-V-IMG request).
    image_attachment: ModelSOLlmImageAttachmentBinding | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("endpoint_url")
    @classmethod
    def _complete_http_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint_url must be a complete http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("endpoint_url must not contain user information")
        if parsed.query or parsed.fragment:
            raise ValueError("endpoint_url must not contain a query or fragment")
        return value


LlmProviderBinding = Annotated[
    ModelSOStubLlmProviderBinding | ModelSOOpenAICompatibleProviderBinding,
    Field(discriminator="kind"),
]
SecretResolverBinding = Annotated[
    ModelSONoSecretResolverBinding | ModelSOInjectedSecretResolverBinding,
    Field(discriminator="kind"),
]


class ModelSOLlmBindings(_ClosedBinding):
    """Complete provider, persona, and secret-capability selection."""

    providers: tuple[LlmProviderBinding, ...] = Field(min_length=1)
    model_identities: tuple[ModelSOModelIdentityBinding, ...]
    personas_dir: Path
    secret_resolver: SecretResolverBinding
    # Human-editable prompt surface.  An override replaces one persona's
    # authored doctrine (and optionally its temperature) without editing the
    # persona contract file or any code.  The effective prompt is recorded in
    # MATCH_STARTED provenance, so an edit here cannot escape the evidence.
    persona_overrides: tuple[ModelSOPersonaPromptOverride, ...] = Field(
        default=(),
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def _persona_overrides_are_unique(self) -> Self:
        persona_ids = [override.persona_id for override in self.persona_overrides]
        if len(persona_ids) != len(set(persona_ids)):
            raise ValueError("persona_overrides must declare each persona_id at most once")
        return self

    @model_validator(mode="after")
    def _valid_provider_and_model_identity_ids(self) -> Self:
        provider_ids = [provider.provider_id for provider in self.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("providers must declare unique provider_id values")
        identity_ids = [identity.model_identity_id for identity in self.model_identities]
        if len(identity_ids) != len(set(identity_ids)):
            raise ValueError("model_identities must declare unique model_identity_id values")
        unknown_providers = sorted(
            {
                identity.provider_binding_id
                for identity in self.model_identities
                if identity.provider_binding_id not in provider_ids
            }
        )
        if unknown_providers:
            raise ValueError(
                f"model_identities reference unknown provider bindings: {unknown_providers}"
            )
        if self.secret_resolver.kind == "none" and any(
            isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
            and provider.secret_ref is not None
            for provider in self.providers
        ):
            raise ValueError(
                "secret_resolver kind 'none' cannot be used with secret-bearing providers"
            )
        return self


BusBinding = Annotated[ModelSOInProcessBusBinding, Field(discriminator="kind")]
EventLedgerBinding = Annotated[ModelSOSQLiteEventLedgerBinding, Field(discriminator="kind")]
LeaderboardBinding = Annotated[ModelSOSQLiteLeaderboardBinding, Field(discriminator="kind")]
LearningArtifactsBinding = Annotated[
    ModelSOFilesystemLearningArtifactsBinding, Field(discriminator="kind")
]
EvaluationStorageBinding = Annotated[
    ModelSOSQLiteEvaluationStorageBinding, Field(discriminator="kind")
]
ClockBinding = Annotated[ModelSOSystemClockBinding, Field(discriminator="kind")]
IdentityBinding = Annotated[ModelSOSystemIdentityBinding, Field(discriminator="kind")]
FrontendTransportBinding = Annotated[ModelSOFrontendTransportBinding, Field(discriminator="kind")]


class ModelSOApplicationOverlay(_ClosedBinding):
    """Complete adapter and contract selection for one process."""

    schema_version: Literal["1"]
    bus: BusBinding
    event_ledger: EventLedgerBinding
    leaderboard: LeaderboardBinding
    learning_artifacts: LearningArtifactsBinding
    evaluation_storage: EvaluationStorageBinding
    contracts: ModelSOContractBindings
    llm: ModelSOLlmBindings
    clock: ClockBinding
    identity: IdentityBinding
    frontend_transport: FrontendTransportBinding
    # Opt-in: absent means the live learning lane stays cold (no coordinator,
    # no admission, no promotion events).  Explicitly stripped on the offline
    # duel executors so evaluation duels never feed the live chain.
    live_learning: ModelSOLiveLearningBinding | None = None


class ModelSOFrontendBootstrap(_ClosedBinding):
    """Strict public projection for receive-only browser composition.

    ``player_roster`` is explicitly null until a validated server-owned roster
    is supplied to the export boundary.  Null is safe unavailability, never a
    signal for the browser to infer or discover player options.
    """

    schema_version: Literal["1"]
    kind: Literal["steel_onslaught.frontend_bootstrap"]
    overlay_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    frontend_transport: ModelSOFrontendTransportBinding
    player_roster: ModelSOPlayerRosterProjection | None = None
    command_gateway: ModelSOFrontendCommandGatewayBinding | None = None
    # Optional richer metadata for model/provider pickers.  The existing
    # player_roster remains the launch authority and is intentionally kept
    # compatible with older browser bundles.
    model_catalog: ModelSOModelCatalogProjection | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    # Read-only operator inspection surfaces for the browser prompt/rule
    # workbench.  Both are the SAME typed projections ``so prompts show --json``
    # and ``so rules list --json`` emit, so a browser edit derives the identical
    # overlay fragment the CLI would, and the effective-prompt digest shown here
    # equals the one the runner records in MATCH_STARTED.  Null keeps older
    # browser bundles (and replay-only decks) working unchanged.
    prompt_provenance: ModelSOMatchPromptProvenance | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    rule_catalog: ModelSOCardRuleCatalogProjection | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


__all__ = [
    "ModelSOApplicationOverlay",
    "ModelSOBalanceRulePackBinding",
    "ModelSOCardCatalogBinding",
    "ModelSOCardDeckPolicy",
    "ModelSOCardProgrammerBinding",
    "ModelSOContractBindings",
    "ModelSOFilesystemLearningArtifactsBinding",
    "ModelSOFrontendBootstrap",
    "ModelSOFrontendCommandGatewayBinding",
    "ModelSOFrontendTransportBinding",
    "ModelSOInProcessBusBinding",
    "ModelSOInjectedSecretResolverBinding",
    "ModelSOLiveLearningBinding",
    "ModelSOLlmBindings",
    "ModelSOLlmImageAttachmentBinding",
    "ModelSOLlmRetryBinding",
    "ModelSOModelCatalogProjection",
    "ModelSOModelIdentityBinding",
    "ModelSONoSecretResolverBinding",
    "ModelSOOpenAICompatibleProviderBinding",
    "ModelSOPersonaPromptOverride",
    "ModelSOSQLiteEvaluationStorageBinding",
    "ModelSOSQLiteEventLedgerBinding",
    "ModelSOSQLiteLeaderboardBinding",
    "ModelSOSecretRef",
    "ModelSOSelectionOutcomeThresholds",
    "ModelSOStubLlmProviderBinding",
    "ModelSOSystemClockBinding",
    "ModelSOSystemIdentityBinding",
    "ModelSOThinkingBinding",
]
