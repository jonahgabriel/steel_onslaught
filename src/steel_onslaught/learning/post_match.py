"""Pure projection of a canonical match stream into learning evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from pydantic import BaseModel

from steel_onslaught.contracts.mode import ModelSOModeTransitionCompletedPayload
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

    scored: list[tuple[ModelSOEventEnvelope, ModelSOMatchScoredPayload]] = []
    decisions: list[ModelSOPilotDecisionPayload] = []
    for event in stream:
        payload_model = _PROJECTED_PAYLOAD_MODELS.get(event.event_type)
        if payload_model is None:
            raise ValueError(f"no payload contract registered for {event.event_type.value!r}")
        payload = payload_model.model_validate(event.payload)
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
        correlation_id=scored_event.correlation_id,
        duration_ticks=score.duration_ticks,
        winner_player_id=score.winner_player_id,
        is_draw=score.is_draw,
        scores=score.scores,
        event_counts=dict(sorted(event_counts.items())),
        decision_action_counts=dict(sorted(action_counts.items())),
        decision_reason_counts=dict(sorted(reason_counts.items())),
    )


__all__ = ["project_match_learning_evidence"]
