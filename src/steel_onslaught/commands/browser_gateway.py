"""Transport-independent browser command ingress for the live match.

The gateway is intentionally a controller, rather than a WebSocket server.  A
future HTTP/WebSocket adapter can translate frames into the closed request
models below and call this module without gaining access to authority
internals, providers, or secrets.  Events flow in the opposite direction:
the browser is a receive-only event consumer and this controller rejects all
event frames presented as inbound commands.
"""

from __future__ import annotations

from threading import Lock
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from steel_onslaught.commands.authority import (
    AuthenticatedSessionCapability,
    ModelSOHumanSeatAuthorityClaim,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    SessionId,
    SessionPermission,
    require_session_permission,
)
from steel_onslaught.commands.coordinator import (
    ProcessLocalHumanLoopbackCoordinator,
    ProcessLocalMatchLaunchCoordinator,
)
from steel_onslaught.commands.inbox import ModelSOHumanActionAdmission
from steel_onslaught.contracts.commands import (
    ModelSOPlayerActionCommand,
    ModelSOStartMatchCommand,
    canonical_command_sha256,
)
from steel_onslaught.contracts.player_selection import (
    MatchId,
    ModelSOHumanPlayerOptionBinding,
    ModelSOMatchLaunchProvenance,
    ModelSOPlayerRosterBinding,
    Sha256Digest,
    Side,
    TurnId,
)


class BrowserGatewayError(ValueError):
    """Base error for fail-closed browser ingress."""


class BrowserGatewayOriginError(BrowserGatewayError):
    """The adapter supplied a non-loopback or unapproved browser origin."""


class BrowserGatewayReceiveOnlyError(BrowserGatewayError):
    """A browser attempted to send an event/control frame to a receive port."""


class BrowserGatewayCommandConflictError(BrowserGatewayError):
    """An idempotency key was reused with different request content."""


class _ClosedGatewayModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def _loopback_host(value: str, *, context: str) -> str:
    """Validate a Host header without DNS resolution or ambient trust."""

    if not value or any(char in value for char in "/?#@"):
        raise BrowserGatewayOriginError(f"{context} must be a loopback host")
    parsed = urlsplit(f"//{value}")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise BrowserGatewayOriginError(f"{context} must use a loopback host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise BrowserGatewayOriginError(f"{context} has an invalid port") from exc
    if port is not None and not 1 <= port <= 65_535:
        raise BrowserGatewayOriginError(f"{context} has an invalid port")
    return value.lower()


def _loopback_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrowserGatewayOriginError("origin must be a complete http(s) origin")
    if parsed.username is not None or parsed.password is not None:
        raise BrowserGatewayOriginError("origin must not contain user information")
    if parsed.path or parsed.query or parsed.fragment:
        raise BrowserGatewayOriginError("origin must not contain a path, query, or fragment")
    host = _loopback_host(parsed.netloc, context="origin")
    return f"{parsed.scheme.lower()}://{host}"


class ModelSOBrowserRequestContext(_ClosedGatewayModel):
    """Untrusted transport metadata supplied by an HTTP/WebSocket adapter."""

    origin: StrictStr = Field(min_length=1)
    host: StrictStr = Field(min_length=1)

    @field_validator("origin")
    @classmethod
    def _origin_is_loopback(cls, value: str) -> str:
        return _loopback_origin(value)

    @field_validator("host")
    @classmethod
    def _host_is_loopback(cls, value: str) -> str:
        return _loopback_host(value, context="host")


class ModelSOBrowserStartMatchRequest(_ClosedGatewayModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.browser_start_match"] = "steel_onslaught.browser_start_match"
    match_id: MatchId
    command: ModelSOStartMatchCommand


class ModelSOBrowserActionRequest(_ClosedGatewayModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.browser_player_action"] = "steel_onslaught.browser_player_action"
    side: Side
    command: ModelSOPlayerActionCommand


class ModelSOBrowserStartAccepted(_ClosedGatewayModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.browser_start_accepted"] = (
        "steel_onslaught.browser_start_accepted"
    )
    authority_scope: Literal["process_lifetime"] = "process_lifetime"
    outcome: Literal["accepted"] = "accepted"
    command_id: UUID
    command_sha256: Sha256Digest
    match_id: MatchId
    overlay_sha256: Sha256Digest
    roster_sha256: Sha256Digest


class ModelSOBrowserActionAccepted(_ClosedGatewayModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.browser_action_accepted"] = (
        "steel_onslaught.browser_action_accepted"
    )
    authority_scope: Literal["process_lifetime"] = "process_lifetime"
    outcome: Literal["accepted"] = "accepted"
    command_id: UUID
    command_sha256: Sha256Digest
    match_id: MatchId
    turn_id: TurnId
    expected_tick: int = Field(ge=0)
    side: Side
    prompt_sha256: Sha256Digest


class _StartPort(Protocol):
    def admit_start_match(
        self,
        command: ModelSOStartMatchCommand,
        *,
        context: ModelSOStartMatchAuthorityContext,
        match_id: MatchId,
    ) -> ModelSOMatchLaunchProvenance: ...


class _HumanPort(Protocol):
    def submit_action(
        self,
        command: ModelSOPlayerActionCommand,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> ModelSOHumanActionAdmission: ...


class BrowserCommandGateway:
    """Authenticate and admit browser commands over injected process ports.

    This class owns no socket and never resolves a secret.  The lock covers
    the complete admission call so two concurrent deliveries of one command
    cannot race into two coordinator calls.  Idempotency is deliberately
    process-lifetime only, matching the underlying command authority.
    """

    def __init__(
        self,
        *,
        sessions: AuthenticatedSessionCapability,
        roster: ModelSOPlayerRosterBinding,
        start_coordinator: _StartPort | ProcessLocalMatchLaunchCoordinator,
        human_coordinator: _HumanPort | ProcessLocalHumanLoopbackCoordinator,
        allowed_origins: tuple[str, ...],
    ) -> None:
        if not allowed_origins:
            raise BrowserGatewayOriginError("at least one allowed origin is required")
        self._allowed_origins = frozenset(_loopback_origin(origin) for origin in allowed_origins)
        self._sessions = sessions
        self._roster = roster
        self._start_coordinator = start_coordinator
        self._human_coordinator = human_coordinator
        self._lock = Lock()
        self._start_results: dict[UUID, ModelSOBrowserStartAccepted] = {}
        self._action_results: dict[UUID, ModelSOBrowserActionAccepted] = {}
        self._start_owners: dict[UUID, tuple[PrincipalId, SessionId]] = {}
        self._action_owners: dict[UUID, tuple[PrincipalId, SessionId]] = {}

    def _check_context(self, context: ModelSOBrowserRequestContext) -> None:
        if context.origin not in self._allowed_origins:
            raise BrowserGatewayOriginError("origin is not allowed for this gateway")

    @staticmethod
    def reject_inbound_event(frame: object) -> None:
        """Reject any event/control frame sent toward the command port."""

        del frame
        raise BrowserGatewayReceiveOnlyError(
            "event transport is receive-only; event frames cannot be submitted"
        )

    # Friendly alias for adapters/tests that express the guard as an assertion.
    assert_receive_only = reject_inbound_event

    def start_match(
        self,
        request: ModelSOBrowserStartMatchRequest,
        *,
        transport: ModelSOBrowserRequestContext,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOBrowserStartAccepted:
        self._check_context(transport)
        command = request.command
        command_sha256 = canonical_command_sha256(command)
        with self._lock:
            session = require_session_permission(
                self._sessions,
                principal_id=principal_id,
                session_id=session_id,
                permission="match:create",
            )
            existing = self._start_results.get(command.command_id)
            if existing is not None:
                if self._start_owners[command.command_id] != (principal_id, session_id) or (
                    existing.command_sha256 != command_sha256
                    or existing.match_id != request.match_id
                ):
                    raise BrowserGatewayCommandConflictError(
                        f"command id {command.command_id} was reused with different content"
                    )
                return existing

            options = {option.option_id: option for option in self._roster.options}
            claims: list[ModelSOHumanSeatAuthorityClaim] = []
            for selection in command.selections:
                option = options.get(selection.option_id)
                if isinstance(option, ModelSOHumanPlayerOptionBinding):
                    if session.human_identity_id != option.human_identity_id:
                        # Let the canonical coordinator report the same closed
                        # authority failure; this branch only avoids building a
                        # claim for an identity this session cannot represent.
                        continue
                    claims.append(
                        ModelSOHumanSeatAuthorityClaim(
                            side=selection.side,
                            principal_id=principal_id,
                            session_id=session_id,
                        )
                    )
            provenance = self._start_coordinator.admit_start_match(
                command,
                context=ModelSOStartMatchAuthorityContext(
                    creator_principal_id=principal_id,
                    creator_session_id=session_id,
                    human_seats=tuple(claims),
                ),
                match_id=request.match_id,
            )
            result = ModelSOBrowserStartAccepted(
                command_id=command.command_id,
                command_sha256=provenance.launch_command_sha256,
                match_id=provenance.match_id,
                overlay_sha256=provenance.overlay_sha256,
                roster_sha256=provenance.roster_sha256,
            )
            self._start_results[command.command_id] = result
            self._start_owners[command.command_id] = (principal_id, session_id)
            return result

    def submit_action(
        self,
        request: ModelSOBrowserActionRequest,
        *,
        transport: ModelSOBrowserRequestContext,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOBrowserActionAccepted:
        self._check_context(transport)
        command = request.command
        command_sha256 = canonical_command_sha256(command)
        with self._lock:
            permission: SessionPermission = "seat:red" if request.side == "red" else "seat:blue"
            require_session_permission(
                self._sessions,
                principal_id=principal_id,
                session_id=session_id,
                permission=permission,
            )
            existing = self._action_results.get(command.command_id)
            if existing is not None:
                if (
                    self._action_owners[command.command_id] != (principal_id, session_id)
                    or existing.command_sha256 != command_sha256
                    or existing.side != request.side
                ):
                    raise BrowserGatewayCommandConflictError(
                        f"command id {command.command_id} was reused with different content"
                    )
                return existing
            admission = self._human_coordinator.submit_action(
                command,
                principal_id=principal_id,
                session_id=session_id,
                side=request.side,
            )
            result = ModelSOBrowserActionAccepted(
                command_id=admission.command_id,
                command_sha256=admission.command_sha256,
                match_id=command.match_id,
                turn_id=command.turn_id,
                expected_tick=command.expected_tick,
                side=request.side,
                prompt_sha256=admission.prompt_sha256,
            )
            self._action_results[command.command_id] = result
            self._action_owners[command.command_id] = (principal_id, session_id)
            return result


__all__ = [
    "BrowserCommandGateway",
    "BrowserGatewayCommandConflictError",
    "BrowserGatewayError",
    "BrowserGatewayOriginError",
    "BrowserGatewayReceiveOnlyError",
    "ModelSOBrowserActionAccepted",
    "ModelSOBrowserActionRequest",
    "ModelSOBrowserRequestContext",
    "ModelSOBrowserStartAccepted",
    "ModelSOBrowserStartMatchRequest",
]
