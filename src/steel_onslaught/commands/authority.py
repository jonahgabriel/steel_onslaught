"""Process-lifetime authentication and admission for match commands.

This module is deliberately transport-free.  Callers inject an authenticated
session capability and pass its opaque principal/session references alongside
the wire command.  Accepted command ids live only in this Python process: they
are not durable receipts, a journal, or restart/crash recovery.
"""

from __future__ import annotations

import hashlib
import json
from threading import Lock
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.commands import ModelSOStartMatchCommand, canonical_command_sha256
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.contracts.player_selection import (
    HumanIdentityId,
    ModelSOHumanPlayerOptionBinding,
    ModelSOPlayerRosterBinding,
    Sha256Digest,
    Side,
    validate_player_roster_against_overlay,
)

PrincipalId = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^principal\.[a-z0-9][a-z0-9_.-]*$"),
]
SessionId = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^session\.[a-z0-9][a-z0-9_.-]*$"),
]
SessionPermission = Literal["match:create", "seat:red", "seat:blue"]


class CommandAuthorityError(ValueError):
    """Base error for fail-closed command admission."""


class SessionAuthenticationError(CommandAuthorityError):
    """The injected capability did not authenticate the requested session."""


class PermissionDeniedError(CommandAuthorityError):
    """The authenticated session lacks an exact required permission."""


class CommandContractStaleError(CommandAuthorityError):
    """A command names a stale overlay or roster digest."""


class SelectionAuthorityError(CommandAuthorityError):
    """A selected option is unknown, unavailable, or lacks seat authority."""


class CommandConflictError(CommandAuthorityError):
    """A command id was already admitted with different canonical content."""


class CommandOwnershipError(CommandAuthorityError):
    """An admitted command id was retried under a different authority context."""


class _ClosedAuthorityModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ModelSOAuthenticatedSession(_ClosedAuthorityModel):
    """Result returned by the injected authentication capability."""

    principal_id: PrincipalId
    session_id: SessionId
    human_identity_id: HumanIdentityId | None
    permissions: tuple[SessionPermission, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _permissions_are_closed_and_unique(self) -> ModelSOAuthenticatedSession:
        if len(self.permissions) != len(set(self.permissions)):
            raise ValueError("permissions must be unique")
        if any(permission.startswith("seat:") for permission in self.permissions):
            if self.human_identity_id is None:
                raise ValueError("seat permissions require a human_identity_id")
        return self


class AuthenticatedSessionCapability(Protocol):
    """Injected authentication boundary; no network or auth adapter is supplied here."""

    def resolve(
        self,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOAuthenticatedSession | None: ...


class ModelSOHumanSeatAuthorityClaim(_ClosedAuthorityModel):
    side: Side
    principal_id: PrincipalId
    session_id: SessionId


class ModelSOStartMatchAuthorityContext(_ClosedAuthorityModel):
    """Non-wire authenticated context for one start-match admission."""

    creator_principal_id: PrincipalId
    creator_session_id: SessionId
    human_seats: tuple[ModelSOHumanSeatAuthorityClaim, ...] = ()

    @field_validator("human_seats")
    @classmethod
    def _canonical_human_seat_order(
        cls,
        claims: tuple[ModelSOHumanSeatAuthorityClaim, ...],
    ) -> tuple[ModelSOHumanSeatAuthorityClaim, ...]:
        """Canonicalize semantic seat authority independently of tuple input order."""

        order: dict[Side, int] = {"red": 0, "blue": 1}
        return tuple(sorted(claims, key=lambda claim: order[claim.side]))

    @model_validator(mode="after")
    def _human_seat_claims_are_unique(self) -> ModelSOStartMatchAuthorityContext:
        sides = [claim.side for claim in self.human_seats]
        if len(sides) != len(set(sides)):
            raise ValueError("human_seats must contain at most one claim per side")
        return self


class ModelSOCommandAdmissionResult(_ClosedAuthorityModel):
    """Deterministic accepted result retained for this process lifetime only."""

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.command_admission"] = "steel_onslaught.command_admission"
    authority_scope: Literal["process_lifetime"] = "process_lifetime"
    outcome: Literal["accepted"] = "accepted"
    command_id: UUID
    command_sha256: Sha256Digest
    principal_id: PrincipalId
    session_id: SessionId


class _AdmissionRecord:
    def __init__(
        self,
        *,
        command_sha256: Sha256Digest,
        context_sha256: Sha256Digest,
        result: ModelSOCommandAdmissionResult,
    ) -> None:
        self.command_sha256 = command_sha256
        self.context_sha256 = context_sha256
        self.result = result


def _canonical_model_sha256(model: BaseModel) -> Sha256Digest:
    canonical = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_overlay_sha256(overlay: ModelSOApplicationOverlay) -> Sha256Digest:
    """Return the canonical overlay digest used by the Phase 51 start command."""

    return _canonical_model_sha256(overlay)


def _canonical_authority_context_sha256(
    context: ModelSOStartMatchAuthorityContext,
) -> Sha256Digest:
    order: dict[Side, int] = {"red": 0, "blue": 1}
    canonical = context.model_copy(
        update={
            "human_seats": tuple(sorted(context.human_seats, key=lambda claim: order[claim.side]))
        }
    )
    return _canonical_model_sha256(canonical)


def require_session_permission(
    capability: AuthenticatedSessionCapability,
    *,
    principal_id: PrincipalId,
    session_id: SessionId,
    permission: SessionPermission,
) -> ModelSOAuthenticatedSession:
    """Authenticate a session reference and require one exact closed permission."""

    session = capability.resolve(principal_id=principal_id, session_id=session_id)
    if session is None:
        raise SessionAuthenticationError(
            f"session {session_id!r} did not authenticate for principal {principal_id!r}"
        )
    if session.principal_id != principal_id or session.session_id != session_id:
        raise SessionAuthenticationError("session capability returned mismatched authority")
    if permission not in session.permissions:
        raise PermissionDeniedError(
            f"session {session_id!r} lacks required permission {permission!r}"
        )
    return session


class ProcessLocalCommandAuthority:
    """Thread-safe start-match authority with process-lifetime idempotency only."""

    def __init__(
        self,
        *,
        overlay: ModelSOApplicationOverlay,
        roster: ModelSOPlayerRosterBinding,
        sessions: AuthenticatedSessionCapability,
        pilot_registry: PilotSpecRegistry,
        canonical_overlay: ModelSOApplicationOverlay | None = None,
    ) -> None:
        validate_player_roster_against_overlay(
            roster=roster,
            overlay=overlay,
            pilot_registry=pilot_registry,
        )
        self._overlay = overlay
        self._roster = roster
        self._sessions = sessions
        # A selected catalog overlay may be a runtime projection of the
        # browser's canonical launch overlay (for example, it can rebind card
        # programmers to the selected pilot).  Authority must compare the
        # browser's expected hash with that canonical launch contract rather
        # than a derived runtime projection.
        self._overlay_sha256 = canonical_overlay_sha256(canonical_overlay or overlay)
        self._roster_sha256 = roster.canonical_sha256()
        self._records: dict[UUID, _AdmissionRecord] = {}
        self._lock = Lock()

    @property
    def admission_count(self) -> int:
        """Number of distinct accepted ids retained in this process."""

        with self._lock:
            return len(self._records)

    def admit_start_match(
        self,
        command: ModelSOStartMatchCommand,
        *,
        context: ModelSOStartMatchAuthorityContext,
    ) -> ModelSOCommandAdmissionResult:
        """Validate authority/contracts and admit one start command idempotently."""

        if command.expected_overlay_sha256 != self._overlay_sha256:
            raise CommandContractStaleError("start command expected_overlay_sha256 is stale")
        if command.expected_roster_sha256 != self._roster_sha256:
            raise CommandContractStaleError("start command expected_roster_sha256 is stale")

        require_session_permission(
            self._sessions,
            principal_id=context.creator_principal_id,
            session_id=context.creator_session_id,
            permission="match:create",
        )
        self._validate_selections_and_seat_authority(command=command, context=context)

        command_sha256 = canonical_command_sha256(command)
        context_sha256 = _canonical_authority_context_sha256(context)
        with self._lock:
            existing = self._records.get(command.command_id)
            if existing is not None:
                if existing.command_sha256 != command_sha256:
                    raise CommandConflictError(
                        f"command id {command.command_id} already has different canonical content"
                    )
                if existing.context_sha256 != context_sha256:
                    raise CommandOwnershipError(
                        f"command id {command.command_id} belongs to another authority context"
                    )
                return existing.result

            result = ModelSOCommandAdmissionResult(
                command_id=command.command_id,
                command_sha256=command_sha256,
                principal_id=context.creator_principal_id,
                session_id=context.creator_session_id,
            )
            self._records[command.command_id] = _AdmissionRecord(
                command_sha256=command_sha256,
                context_sha256=context_sha256,
                result=result,
            )
            return result

    def _validate_selections_and_seat_authority(
        self,
        *,
        command: ModelSOStartMatchCommand,
        context: ModelSOStartMatchAuthorityContext,
    ) -> None:
        options = {option.option_id: option for option in self._roster.options}
        seat_policies = {seat.side: seat for seat in self._roster.seats}
        selections = {selection.side: selection for selection in command.selections}
        claims = {claim.side: claim for claim in context.human_seats}

        expected_human_sides: set[Side] = set()
        for side in ("red", "blue"):
            selection = selections[side]
            option = options.get(selection.option_id)
            if option is None:
                raise SelectionAuthorityError(
                    f"{side} selection references unknown option {selection.option_id!r}"
                )
            if selection.option_id not in seat_policies[side].allowed_option_ids:
                raise SelectionAuthorityError(
                    f"option {selection.option_id!r} is not allowed for {side} seat"
                )
            if not isinstance(option, ModelSOHumanPlayerOptionBinding):
                continue

            expected_human_sides.add(side)
            claim = claims.get(side)
            if claim is None:
                raise SelectionAuthorityError(f"human {side} selection requires a seat claim")
            permission: SessionPermission = "seat:red" if side == "red" else "seat:blue"
            session = require_session_permission(
                self._sessions,
                principal_id=claim.principal_id,
                session_id=claim.session_id,
                permission=permission,
            )
            if session.human_identity_id != option.human_identity_id:
                raise SelectionAuthorityError(
                    f"authenticated {side} seat does not own selected human identity"
                )

        if set(claims) != expected_human_sides:
            extra = sorted(set(claims) - expected_human_sides)
            raise SelectionAuthorityError(f"seat claims do not match human selections: {extra}")


__all__ = [
    "AuthenticatedSessionCapability",
    "CommandAuthorityError",
    "CommandConflictError",
    "CommandContractStaleError",
    "CommandOwnershipError",
    "ModelSOAuthenticatedSession",
    "ModelSOCommandAdmissionResult",
    "ModelSOHumanSeatAuthorityClaim",
    "ModelSOStartMatchAuthorityContext",
    "PermissionDeniedError",
    "PrincipalId",
    "ProcessLocalCommandAuthority",
    "SelectionAuthorityError",
    "SessionAuthenticationError",
    "SessionId",
    "SessionPermission",
    "canonical_overlay_sha256",
    "require_session_permission",
]
