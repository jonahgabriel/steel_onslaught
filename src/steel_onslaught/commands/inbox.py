"""Thread-safe process-local inbox for authenticated human decisions.

Prompts and accepted actions are retained in memory only.  There is no wait,
timeout, disconnect policy, fallback, pause/forfeit behavior, journal, or
restart/crash recovery in this module.
"""

from __future__ import annotations

import hashlib
import json
from threading import Lock
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from steel_onslaught.commands.authority import (
    AuthenticatedSessionCapability,
    CommandConflictError,
    CommandOwnershipError,
    PrincipalId,
    SessionId,
    SessionPermission,
    require_session_permission,
)
from steel_onslaught.contracts.commands import (
    ModelSOHumanTurnPrompt,
    ModelSOPlayerActionCommand,
    canonical_command_sha256,
)
from steel_onslaught.contracts.player_selection import Sha256Digest, Side
from steel_onslaught.pilots.schemas import ModelSOPilotObservation


class HumanDecisionInboxError(ValueError):
    """Base error for fail-closed prompt/action handling."""


class StaleHumanTurnError(HumanDecisionInboxError):
    """A prompt/action/observation does not match the active turn."""


class ActionNotAvailableError(HumanDecisionInboxError):
    """The submitted action is absent from the authoritative prompt choices."""


class HumanTurnDecisionConflictError(HumanDecisionInboxError):
    """A different command has already decided the active prompt."""


class HumanDecisionNotReadyError(HumanDecisionInboxError):
    """No authenticated action has been admitted for the requested observation."""


class _ClosedInboxModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ModelSOHumanPromptAdmission(_ClosedInboxModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.human_prompt_admission"] = (
        "steel_onslaught.human_prompt_admission"
    )
    authority_scope: Literal["process_lifetime"] = "process_lifetime"
    outcome: Literal["accepted"] = "accepted"
    prompt_sha256: Sha256Digest
    principal_id: PrincipalId
    session_id: SessionId
    side: Side


class ModelSOHumanActionAdmission(_ClosedInboxModel):
    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.human_action_admission"] = (
        "steel_onslaught.human_action_admission"
    )
    authority_scope: Literal["process_lifetime"] = "process_lifetime"
    outcome: Literal["accepted"] = "accepted"
    command_id: UUID
    command_sha256: Sha256Digest
    principal_id: PrincipalId
    session_id: SessionId
    side: Side
    prompt_sha256: Sha256Digest


class _PromptState:
    def __init__(
        self,
        *,
        prompt: ModelSOHumanTurnPrompt,
        prompt_sha256: Sha256Digest,
        admission: ModelSOHumanPromptAdmission,
    ) -> None:
        self.prompt = prompt
        self.prompt_sha256 = prompt_sha256
        self.admission = admission


class _ActionState:
    def __init__(
        self,
        *,
        command: ModelSOPlayerActionCommand,
        command_sha256: Sha256Digest,
        owner_key: tuple[PrincipalId, SessionId, Side],
        prompt_sha256: Sha256Digest,
        admission: ModelSOHumanActionAdmission,
    ) -> None:
        self.command = command
        self.command_sha256 = command_sha256
        self.owner_key = owner_key
        self.prompt_sha256 = prompt_sha256
        self.admission = admission


def _canonical_model_sha256(model: BaseModel) -> Sha256Digest:
    canonical = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_observation_sha256(observation: ModelSOPilotObservation) -> Sha256Digest:
    """Hash the closed pilot observation used to bind a human prompt."""

    return _canonical_model_sha256(observation)


def canonical_prompt_sha256(prompt: ModelSOHumanTurnPrompt) -> Sha256Digest:
    """Hash a closed prompt for process-lifetime equality."""

    return _canonical_model_sha256(prompt)


class ProcessLocalHumanDecisionInbox:
    """Authenticated human prompt/action inbox with no blocking behavior."""

    def __init__(self, *, sessions: AuthenticatedSessionCapability) -> None:
        self._sessions = sessions
        self._prompts: dict[tuple[PrincipalId, SessionId, Side, str], _PromptState] = {}
        self._commands: dict[UUID, _ActionState] = {}
        self._decisions: dict[
            tuple[PrincipalId, SessionId, Side, str, str, int, Sha256Digest], _ActionState
        ] = {}
        self._lock = Lock()

    @property
    def action_admission_count(self) -> int:
        """Number of distinct accepted action command ids in this process."""

        with self._lock:
            return len(self._commands)

    def publish_prompt(
        self,
        prompt: ModelSOHumanTurnPrompt,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
    ) -> ModelSOHumanPromptAdmission:
        """Register the newest authoritative prompt for one session-owned seat/match."""

        permission: SessionPermission = "seat:red" if prompt.side == "red" else "seat:blue"
        require_session_permission(
            self._sessions,
            principal_id=principal_id,
            session_id=session_id,
            permission=permission,
        )
        prompt_sha256 = canonical_prompt_sha256(prompt)
        prompt_key = (principal_id, session_id, prompt.side, prompt.match_id)
        with self._lock:
            existing = self._prompts.get(prompt_key)
            if existing is not None:
                if existing.prompt_sha256 == prompt_sha256:
                    return existing.admission
                if prompt.expected_tick <= existing.prompt.expected_tick:
                    raise StaleHumanTurnError(
                        "prompt must advance expected_tick for the same session seat and match"
                    )

            admission = ModelSOHumanPromptAdmission(
                prompt_sha256=prompt_sha256,
                principal_id=principal_id,
                session_id=session_id,
                side=prompt.side,
            )
            self._prompts[prompt_key] = _PromptState(
                prompt=prompt,
                prompt_sha256=prompt_sha256,
                admission=admission,
            )
            return admission

    def submit_action(
        self,
        command: ModelSOPlayerActionCommand,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> ModelSOHumanActionAdmission:
        """Admit an authenticated action iff it exactly matches the active prompt."""

        permission: SessionPermission = "seat:red" if side == "red" else "seat:blue"
        require_session_permission(
            self._sessions,
            principal_id=principal_id,
            session_id=session_id,
            permission=permission,
        )
        command_sha256 = canonical_command_sha256(command)
        owner_key = (principal_id, session_id, side)
        prompt_key = (*owner_key, command.match_id)

        with self._lock:
            existing_command = self._commands.get(command.command_id)
            if existing_command is not None:
                if existing_command.command_sha256 != command_sha256:
                    raise CommandConflictError(
                        f"command id {command.command_id} already has different canonical content"
                    )
                if existing_command.owner_key != owner_key:
                    raise CommandOwnershipError(
                        f"command id {command.command_id} belongs to another authority context"
                    )
                return existing_command.admission

            prompt_state = self._prompts.get(prompt_key)
            if prompt_state is None:
                raise StaleHumanTurnError("no active prompt for session seat and match")
            prompt = prompt_state.prompt
            if (
                command.turn_id != prompt.turn_id
                or command.expected_tick != prompt.expected_tick
                or command.observation_sha256 != prompt.observation_sha256
            ):
                raise StaleHumanTurnError(
                    "action turn/tick/observation does not match the active prompt"
                )
            if not any(command.action == available for available in prompt.available_actions):
                raise ActionNotAvailableError("action is absent from prompt.available_actions")

            decision_key = (
                *owner_key,
                command.match_id,
                command.turn_id,
                command.expected_tick,
                command.observation_sha256,
            )
            existing_decision = self._decisions.get(decision_key)
            if existing_decision is not None:
                raise HumanTurnDecisionConflictError(
                    f"prompt was already decided by command {existing_decision.command.command_id}"
                )

            admission = ModelSOHumanActionAdmission(
                command_id=command.command_id,
                command_sha256=command_sha256,
                principal_id=principal_id,
                session_id=session_id,
                side=side,
                prompt_sha256=prompt_state.prompt_sha256,
            )
            state = _ActionState(
                command=command,
                command_sha256=command_sha256,
                owner_key=owner_key,
                prompt_sha256=prompt_state.prompt_sha256,
                admission=admission,
            )
            self._commands[command.command_id] = state
            self._decisions[decision_key] = state
            return admission

    def consume_for_observation(
        self,
        observation: ModelSOPilotObservation,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> ModelSOPlayerActionCommand:
        """Return the already-admitted action; never wait and never synthesize a fallback."""

        permission: SessionPermission = "seat:red" if side == "red" else "seat:blue"
        require_session_permission(
            self._sessions,
            principal_id=principal_id,
            session_id=session_id,
            permission=permission,
        )
        observation_sha256 = canonical_observation_sha256(observation)
        owner_key = (principal_id, session_id, side)
        prompt_key = (*owner_key, observation.match_id)

        with self._lock:
            prompt_state = self._prompts.get(prompt_key)
            if prompt_state is None:
                raise StaleHumanTurnError("no active prompt for observation match")
            prompt = prompt_state.prompt
            if (
                prompt.expected_tick != observation.tick
                or prompt.observation_sha256 != observation_sha256
            ):
                raise StaleHumanTurnError(
                    "observation tick/hash does not match the active human prompt"
                )
            decision_key = (
                *owner_key,
                prompt.match_id,
                prompt.turn_id,
                prompt.expected_tick,
                prompt.observation_sha256,
            )
            decision = self._decisions.get(decision_key)
            if decision is None:
                raise HumanDecisionNotReadyError(
                    "no admitted human action is ready for this observation"
                )
            return decision.command


__all__ = [
    "ActionNotAvailableError",
    "HumanDecisionInboxError",
    "HumanDecisionNotReadyError",
    "HumanTurnDecisionConflictError",
    "ModelSOHumanActionAdmission",
    "ModelSOHumanPromptAdmission",
    "ProcessLocalHumanDecisionInbox",
    "StaleHumanTurnError",
    "canonical_observation_sha256",
    "canonical_prompt_sha256",
]
