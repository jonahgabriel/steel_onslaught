"""Process-local match-launch admission and canonical provenance construction.

This coordinator composes the existing authenticated command authority with
the server-owned roster and application overlay.  It does not construct pilot
clients, open transports, or provide durable admission across process restarts.
"""

from __future__ import annotations

import hashlib
import json
from threading import Condition, Lock
from uuid import UUID

from pydantic import BaseModel

from steel_onslaught.commands.authority import (
    AuthenticatedSessionCapability,
    ModelSOStartMatchAuthorityContext,
    PrincipalId,
    ProcessLocalCommandAuthority,
    SessionId,
    SessionPermission,
    canonical_overlay_sha256,
    require_session_permission,
)
from steel_onslaught.commands.inbox import (
    HumanDecisionCancelledError,
    ModelSOHumanActionAdmission,
    ProcessLocalHumanDecisionInbox,
    canonical_observation_sha256,
)
from steel_onslaught.commands.live_provider import ProcessLocalOneShotLiveProviderCapability
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.commands import (
    ModelSODisengagePlayerAction,
    ModelSOFireWeaponPlayerAction,
    ModelSOHumanTurnPrompt,
    ModelSOMovePlayerAction,
    ModelSOPlayerActionCommand,
    ModelSORemainPlayerAction,
    ModelSOStartMatchCommand,
    ModelSOSwitchModePlayerAction,
    ModelSOVentPlayerAction,
    PlayerAction,
)
from steel_onslaught.contracts.mode import ModeId
from steel_onslaught.contracts.player_selection import (
    MatchId,
    ModelSOHumanPlayerOptionBinding,
    ModelSOHumanSeatAssignment,
    ModelSOMatchLaunchProvenance,
    ModelSOModelPlayerOptionBinding,
    ModelSOModelSeatAssignment,
    ModelSOPlayerRosterBinding,
    PlayerOptionBinding,
    SeatAssignment,
    Sha256Digest,
    Side,
)
from steel_onslaught.pilots.schemas import (
    ModelSOPilotObservation,
    SOPilotAction,
    available_actions,
)


class MatchLaunchCoordinatorError(ValueError):
    """Base error for process-local launch coordination."""


class NonStubModelProviderError(MatchLaunchCoordinatorError):
    """A selected model would require a provider outside the local stub gate."""


class MatchLaunchConflictError(MatchLaunchCoordinatorError):
    """An admitted start command was rebound to different launch provenance."""


def _prompt_actions(observation: ModelSOPilotObservation) -> tuple[PlayerAction, ...]:
    """Translate schema-level availability into deterministic wire choices."""

    available = available_actions(observation)
    actions: list[PlayerAction] = [ModelSORemainPlayerAction(kind="remain")]
    if SOPilotAction.MOVE in available:
        actions.append(ModelSOMovePlayerAction(kind="move", direction="toward_enemy", speed="full"))
    if SOPilotAction.FIRE_WEAPON in available:
        target = (
            observation.enemy_observations[-1].enemy_mech_id
            if observation.enemy_observations
            else None
        )
        actions.extend(
            ModelSOFireWeaponPlayerAction(
                kind="fire_weapon",
                weapon_id=weapon.weapon_id,
                target_mech_id=target,
            )
            for weapon in sorted(observation.weapons, key=lambda candidate: candidate.weapon_id)
            if weapon.cooldown_remaining_ticks == 0
            and observation.boiler.pressure_current >= weapon.pressure_cost
        )
    if SOPilotAction.VENT in available:
        actions.append(ModelSOVentPlayerAction(kind="vent"))
    if SOPilotAction.SWITCH_MODE in available:
        actions.extend(
            ModelSOSwitchModePlayerAction(kind="switch_mode", target_mode=mode)
            for mode in sorted(ModeId, key=lambda candidate: candidate.value)
            if mode is not observation.current_mode
        )
    if SOPilotAction.DISENGAGE in available:
        actions.append(
            ModelSODisengagePlayerAction(
                kind="disengage",
                direction="defensive",
                speed="full",
            )
        )
    return tuple(actions)


class ProcessLocalHumanLoopbackCoordinator:
    """Public process-local prompt/action surface over the authenticated inbox."""

    def __init__(
        self,
        *,
        sessions: AuthenticatedSessionCapability,
    ) -> None:
        self._sessions = sessions
        self._inbox = ProcessLocalHumanDecisionInbox(sessions=sessions)
        self._prompts: dict[tuple[PrincipalId, SessionId, Side, str], ModelSOHumanTurnPrompt] = {}
        self._condition = Condition(Lock())
        self._shutdown = False

    @property
    def action_admission_count(self) -> int:
        return self._inbox.action_admission_count

    def wait_for_prompt(
        self,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
        match_id: MatchId,
        after_tick: int,
    ) -> ModelSOHumanTurnPrompt:
        """Wait for the next authoritative prompt newer than ``after_tick``."""

        permission: SessionPermission = "seat:red" if side == "red" else "seat:blue"
        require_session_permission(
            self._sessions,
            principal_id=principal_id,
            session_id=session_id,
            permission=permission,
        )
        key = (principal_id, session_id, side, match_id)
        with self._condition:
            self._condition.wait_for(
                lambda: (
                    self._shutdown
                    or (key in self._prompts and self._prompts[key].expected_tick > after_tick)
                )
            )
            if self._shutdown:
                raise HumanDecisionCancelledError("human loopback coordinator is shut down")
            return self._prompts[key]

    def submit_action(
        self,
        command: ModelSOPlayerActionCommand,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> ModelSOHumanActionAdmission:
        return self._inbox.submit_action(
            command,
            principal_id=principal_id,
            session_id=session_id,
            side=side,
        )

    def consume_for_observation(
        self,
        observation: ModelSOPilotObservation,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> ModelSOPlayerActionCommand:
        return self._inbox.consume_for_observation(
            observation,
            principal_id=principal_id,
            session_id=session_id,
            side=side,
        )

    def wait_for_observation(
        self,
        observation: ModelSOPilotObservation,
        *,
        principal_id: PrincipalId,
        session_id: SessionId,
        side: Side,
    ) -> ModelSOPlayerActionCommand:
        """Publish one exact prompt, then wait for its authenticated action."""

        prompt = ModelSOHumanTurnPrompt(
            schema_version="1",
            kind="steel_onslaught.human_turn",
            match_id=observation.match_id,
            turn_id=f"turn.{side}.{observation.tick:06d}",
            side=side,
            expected_tick=observation.tick,
            observation_sha256=canonical_observation_sha256(observation),
            available_actions=_prompt_actions(observation),
        )
        self._inbox.publish_prompt(
            prompt,
            principal_id=principal_id,
            session_id=session_id,
        )
        key = (principal_id, session_id, side, observation.match_id)
        with self._condition:
            if self._shutdown:
                raise HumanDecisionCancelledError("human loopback coordinator is shut down")
            self._prompts[key] = prompt
            self._condition.notify_all()
        return self._inbox.wait_for_observation(
            observation,
            principal_id=principal_id,
            session_id=session_id,
            side=side,
        )

    def shutdown(self) -> None:
        """Cancel public prompt waits and all underlying decision waits."""

        with self._condition:
            self._shutdown = True
            self._condition.notify_all()
        self._inbox.shutdown()


def _canonical_model_sha256(model: BaseModel) -> Sha256Digest:
    canonical = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProcessLocalMatchLaunchCoordinator:
    """Authenticate a start command and return its secret-free launch provenance."""

    def __init__(
        self,
        *,
        overlay: ModelSOApplicationOverlay,
        roster: ModelSOPlayerRosterBinding,
        sessions: AuthenticatedSessionCapability,
        live_provider_capability: ProcessLocalOneShotLiveProviderCapability | None = None,
    ) -> None:
        self._overlay = overlay
        self._roster = roster
        self._live_provider_capability = live_provider_capability
        self._authority = ProcessLocalCommandAuthority(
            overlay=overlay,
            roster=roster,
            sessions=sessions,
        )
        self._options = {option.option_id: option for option in roster.options}
        self._seat_policies = {seat.side: seat for seat in roster.seats}
        self._model_identities = {
            identity.model_identity_id: identity for identity in overlay.llm.model_identities
        }
        self._providers = {provider.provider_id: provider for provider in overlay.llm.providers}
        self._records: dict[UUID, ModelSOMatchLaunchProvenance] = {}
        self._lock = Lock()

    @property
    def launch_admission_count(self) -> int:
        """Number of commands that passed the complete local launch gate."""

        with self._lock:
            return len(self._records)

    def admit_start_match(
        self,
        command: ModelSOStartMatchCommand,
        *,
        context: ModelSOStartMatchAuthorityContext,
        match_id: MatchId,
    ) -> ModelSOMatchLaunchProvenance:
        """Authenticate, validate, enforce local providers, and bind one launch."""

        admission = self._authority.admit_start_match(command, context=context)

        selections = {selection.side: selection for selection in command.selections}
        candidate = ModelSOMatchLaunchProvenance(
            schema_version="1",
            kind="steel_onslaught.match_launch_provenance",
            match_id=match_id,
            launch_command_id=command.command_id,
            launch_command_sha256=admission.command_sha256,
            overlay_sha256=canonical_overlay_sha256(self._overlay),
            roster_id=self._roster.roster_id,
            roster_sha256=self._roster.canonical_sha256(),
            seat_assignments=(
                self._assignment_for("red", selections["red"].option_id),
                self._assignment_for("blue", selections["blue"].option_id),
            ),
        )

        with self._lock:
            existing = self._records.get(command.command_id)
            if existing is not None:
                if existing != candidate:
                    raise MatchLaunchConflictError(
                        f"command id {command.command_id} is already bound to another match launch"
                    )
                return existing
            self._authorize_selected_model_providers(
                command,
                context=context,
                command_sha256=admission.command_sha256,
            )
            self._records[command.command_id] = candidate
            return candidate

    def _authorize_selected_model_providers(
        self,
        command: ModelSOStartMatchCommand,
        *,
        context: ModelSOStartMatchAuthorityContext,
        command_sha256: Sha256Digest,
    ) -> None:
        selected_live_bindings: list[tuple[str, str, str]] = []
        for selection in command.selections:
            option = self._options[selection.option_id]
            if not isinstance(option, ModelSOModelPlayerOptionBinding):
                continue
            identity = self._model_identities[option.model_identity_id]
            provider = self._providers[identity.provider_binding_id]
            if provider.kind != "stub":
                selected_live_bindings.append(
                    (option.option_id, identity.model_identity_id, provider.provider_id)
                )

        if not selected_live_bindings:
            return
        # Two seats may intentionally select the same model identity (the
        # default browser launch is GLM-vs-GLM).  Admit the shared provider
        # grant once; distinct live identities still require separate
        # injected grants and remain fail-closed.
        unique_live_bindings = list(
            dict.fromkeys(
                (model_identity_id, provider_id)
                for _option_id, model_identity_id, provider_id in selected_live_bindings
            )
        )
        if len(unique_live_bindings) > 1:
            raise NonStubModelProviderError(
                "the process-local live gate accepts one exact non-stub model identity per launch"
            )
        option_id, model_identity_id, provider_id = selected_live_bindings[0]
        if self._live_provider_capability is None:
            raise NonStubModelProviderError(
                f"selected model option {option_id!r} requires a non-stub provider; "
                "the process-local playable gate accepts only stub providers without "
                "an explicit one-shot capability"
            )
        self._live_provider_capability.consume(
            creator_principal_id=context.creator_principal_id,
            creator_session_id=context.creator_session_id,
            launch_command_id=command.command_id,
            launch_command_sha256=command_sha256,
            overlay_sha256=canonical_overlay_sha256(self._overlay),
            roster_sha256=self._roster.canonical_sha256(),
            model_identity_id=model_identity_id,
            provider_id=provider_id,
        )

    def _assignment_for(self, side: Side, option_id: str) -> SeatAssignment:
        option: PlayerOptionBinding = self._options[option_id]
        policy = self._seat_policies[side]
        option_sha256 = _canonical_model_sha256(option)
        if isinstance(option, ModelSOHumanPlayerOptionBinding):
            return ModelSOHumanSeatAssignment(
                kind="human",
                side=side,
                player_id=f"player.{side}",
                option_id=option.option_id,
                loadout_id=policy.loadout_id,
                pilot_spec_id=option.pilot_spec_id,
                option_sha256=option_sha256,
                human_identity_id=option.human_identity_id,
                input_source=option.input_source,
            )
        return ModelSOModelSeatAssignment(
            kind="model",
            side=side,
            player_id=f"player.{side}",
            option_id=option.option_id,
            loadout_id=policy.loadout_id,
            pilot_spec_id=option.pilot_spec_id,
            option_sha256=option_sha256,
            model_identity_id=option.model_identity_id,
            persona_id=option.persona_id,
            input_source=option.input_source,
        )


__all__ = [
    "MatchLaunchConflictError",
    "MatchLaunchCoordinatorError",
    "NonStubModelProviderError",
    "ProcessLocalHumanLoopbackCoordinator",
    "ProcessLocalMatchLaunchCoordinator",
]
