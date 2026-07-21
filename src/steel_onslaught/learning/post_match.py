"""Pure projection of a canonical match stream into learning evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel

from steel_onslaught.contracts.card_learning import ModelSOCardLearningMetric
from steel_onslaught.contracts.mode import ModelSOModeTransitionCompletedPayload
from steel_onslaught.events.card_payloads import (
    ModelSOHandDealtPayload,
    ModelSOPlanCommittedPayload,
    ModelSORegisterResolvedPayload,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    CURRENT_CONSUMED_PAYLOAD_MODELS,
    ModelSOMatchScoredPayload,
    ModelSOPilotDecisionPayload,
)
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence

# ``MODE_TRANSITION_COMPLETED`` is an emitted, closed payload that is
# intentionally outside the current-consumed census (35/33 protocol).  The
# after-match projector still validates it because real match ledgers contain
# it; no event schema or registry census change is needed.
_PROJECTED_PAYLOAD_MODELS: Mapping[SOEventType, type[BaseModel]] = {
    **CURRENT_CONSUMED_PAYLOAD_MODELS,
    SOEventType.MODE_TRANSITION_COMPLETED: ModelSOModeTransitionCompletedPayload,
}


def project_match_learning_evidence(
    events: Iterable[ModelSOEventEnvelope],
) -> ModelSOAfterMatchLearningEvidence:
    """Fold one complete canonical ledger stream into terminal evidence.

    The projector validates every payload through the event payload authority,
    so an unknown field or an unrecognized payload fails closed before any
    evidence is persisted.  Exactly one score event is required; duplicate
    terminal events indicate a ledger/replay violation rather than a new
    learning sample.
    """

    stream = tuple(events)
    if not stream:
        raise ValueError("cannot project learning evidence from an empty match stream")
    match_id = stream[0].match_id
    if any(event.match_id != match_id for event in stream):
        raise ValueError("match stream contains events for more than one match")
    correlation_id = stream[0].correlation_id
    if any(event.correlation_id != correlation_id for event in stream):
        raise ValueError("match stream contains more than one workflow correlation_id")

    scored: list[tuple[ModelSOEventEnvelope, ModelSOMatchScoredPayload]] = []
    decisions: list[ModelSOPilotDecisionPayload] = []
    rule_pack_provenance = None
    prompt_provenance = None
    for event in stream:
        payload_model = _PROJECTED_PAYLOAD_MODELS.get(event.event_type)
        if payload_model is None:
            raise ValueError(f"no payload contract registered for {event.event_type.value!r}")
        payload = payload_model.model_validate(event.payload)
        if event.event_type is SOEventType.MATCH_STARTED:
            rule_pack_provenance = payload.card_rule_pack_provenance  # type: ignore[attr-defined]
            prompt_provenance = payload.prompt_provenance  # type: ignore[attr-defined]
        if event.event_type is SOEventType.MATCH_SCORED:
            if not isinstance(payload, ModelSOMatchScoredPayload):
                raise TypeError("MATCH_SCORED payload authority returned the wrong model")
            scored.append((event, payload))
        elif event.event_type is SOEventType.PILOT_DECISION_MADE:
            if not isinstance(payload, ModelSOPilotDecisionPayload):
                raise TypeError("PILOT_DECISION_MADE payload authority returned the wrong model")
            decisions.append(payload)

    if len(scored) != 1:
        raise ValueError(f"expected exactly one MATCH_SCORED event, found {len(scored)}")
    scored_event, score = scored[0]
    if score.match_id != match_id:
        raise ValueError("MATCH_SCORED payload match_id differs from its envelope")

    event_counts = Counter(event.event_type.value for event in stream)
    action_counts = Counter(decision.action.value for decision in decisions)
    reason_counts = Counter(decision.reason_code.value for decision in decisions)
    return ModelSOAfterMatchLearningEvidence(
        match_id=match_id,
        scored_event_id=scored_event.event_id,
        correlation_id=correlation_id,
        duration_ticks=score.duration_ticks,
        winner_player_id=score.winner_player_id,
        is_draw=score.is_draw,
        scores=score.scores,
        event_counts=dict(sorted(event_counts.items())),
        decision_action_counts=dict(sorted(action_counts.items())),
        decision_reason_counts=dict(sorted(reason_counts.items())),
        card_rule_pack_provenance=rule_pack_provenance,
        prompt_provenance=prompt_provenance,
        card_learning_metrics=project_card_learning_metrics(stream),
    )


def project_card_learning_metrics(
    events: Iterable[ModelSOEventEnvelope],
    *,
    mech_id: str | None = None,
) -> tuple[ModelSOCardLearningMetric, ...]:
    """Project card lifecycle events, optionally for one canonical mech.

    This helper intentionally validates every supplied card payload through
    the consumed-event authority.  ``mech_id`` is only a side-selection filter
    for paired evaluator telemetry; it does not alter the event truth.
    """

    state: dict[str, _MutableCardMetric] = {}
    for event in events:
        if event.event_type not in {
            SOEventType.HAND_DEALT,
            SOEventType.PLAN_COMMITTED,
            SOEventType.REGISTER_RESOLVED,
        }:
            continue
        if mech_id is not None and event.subject.mech_id != mech_id:
            continue
        payload_model = _PROJECTED_PAYLOAD_MODELS[event.event_type]
        payload = payload_model.model_validate(event.payload)
        if event.event_type is SOEventType.HAND_DEALT:
            if not isinstance(payload, ModelSOHandDealtPayload):
                raise TypeError("HAND_DEALT payload authority returned the wrong model")
            for card_id in payload.card_ids:
                state.setdefault(str(card_id), _MutableCardMetric()).dealt_count += 1
        elif event.event_type is SOEventType.PLAN_COMMITTED:
            if not isinstance(payload, ModelSOPlanCommittedPayload):
                raise TypeError("PLAN_COMMITTED payload authority returned the wrong model")
            for register in payload.registers:
                state.setdefault(str(register.card_id), _MutableCardMetric()).planned_count += 1
        elif isinstance(payload, ModelSORegisterResolvedPayload) and payload.card_id is not None:
            item = state.setdefault(str(payload.card_id), _MutableCardMetric())
            item.resolved_count += 1
            item.outcome_counts[payload.outcome.value] += 1
            item.action_counts[payload.action] += 1
    return tuple(
        ModelSOCardLearningMetric(
            card_id=card_id,
            dealt_count=item.dealt_count,
            planned_count=item.planned_count,
            resolved_count=item.resolved_count,
            outcome_counts=dict(sorted(item.outcome_counts.items())),
            action_counts=dict(sorted(item.action_counts.items())),
        )
        for card_id, item in sorted(state.items())
    )


@dataclass
class _MutableCardMetric:
    dealt_count: int = 0
    planned_count: int = 0
    resolved_count: int = 0
    outcome_counts: Counter[str] = field(default_factory=Counter)
    action_counts: Counter[str] = field(default_factory=Counter)


__all__ = ["project_card_learning_metrics", "project_match_learning_evidence"]
