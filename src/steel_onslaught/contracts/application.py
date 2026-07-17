"""Closed application overlay for the current Slice-1 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.player_selection import (
    ModelSOModelIdentityBinding,
    ModelSOPlayerRosterProjection,
)


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


class ModelSOSQLiteEvaluationStorageBinding(_ClosedBinding):
    """Evaluation-local event and projection storage selected by the operator."""

    kind: Literal["sqlite"]
    root: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    event_schema: Literal["canonical_event_v1"]
    leaderboard_schema: Literal["leaderboard_v1"]


class ModelSOContractBindings(_ClosedBinding):
    catalog_dir: Path
    pilot_registry_dir: Path
    arena_id: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]*$")


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


class ModelSOOpenAICompatibleProviderBinding(_ClosedBinding):
    kind: Literal["openai_compatible"]
    provider_id: StrictStr = Field(min_length=1)
    endpoint_url: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)
    secret_ref: ModelSOSecretRef | None
    timeout_seconds: StrictFloat = Field(gt=0.0, le=300.0, allow_inf_nan=False)
    max_tokens: StrictInt | None = Field(gt=0, le=32768)
    retry: ModelSOLlmRetryBinding

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


__all__ = [
    "ModelSOApplicationOverlay",
    "ModelSOContractBindings",
    "ModelSOFilesystemLearningArtifactsBinding",
    "ModelSOFrontendBootstrap",
    "ModelSOFrontendTransportBinding",
    "ModelSOInProcessBusBinding",
    "ModelSOInjectedSecretResolverBinding",
    "ModelSOLlmBindings",
    "ModelSOLlmRetryBinding",
    "ModelSOModelIdentityBinding",
    "ModelSONoSecretResolverBinding",
    "ModelSOOpenAICompatibleProviderBinding",
    "ModelSOSQLiteEvaluationStorageBinding",
    "ModelSOSQLiteEventLedgerBinding",
    "ModelSOSQLiteLeaderboardBinding",
    "ModelSOSecretRef",
    "ModelSOStubLlmProviderBinding",
    "ModelSOSystemClockBinding",
    "ModelSOSystemIdentityBinding",
]
