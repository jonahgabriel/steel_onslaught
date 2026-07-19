"""Tests for the strict post-match learning evidence projection."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.card_learning import ModelSOCardLearningMetric
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import CURRENT_CONSUMED_PAYLOAD_MODELS
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.learning.post_match import (
    project_card_learning_metrics,
    project_match_learning_evidence,
)
from steel_onslaught.match.composition import assemble_match_live
from tests.fixtures.event_samples import build_sample_envelopes
from tests.overlay import complete_test_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _complete_fixture_stream() -> list[ModelSOEventEnvelope]:
    samples = build_sample_envelopes()
    return [samples[event_type] for event_type in CURRENT_CONSUMED_PAYLOAD_MODELS]


@pytest.mark.unit
def test_projection_counts_canonical_events_and_pilot_decisions() -> None:
    evidence = project_match_learning_evidence(_complete_fixture_stream())

    assert evidence.kind == "steel_onslaught.match_learning_evidence"
    assert evidence.schema_version == "1"
    assert evidence.match_id == "match.fixture.0001"
    assert evidence.winner_player_id == "player.a"
    assert evidence.is_draw is False
    assert evidence.duration_ticks > 0
    assert evidence.event_counts[SOEventType.MATCH_SCORED.value] == 1
    assert sum(evidence.event_counts.values()) == len(_complete_fixture_stream())
    assert evidence.decision_action_counts["fire_weapon"] == 1
    assert evidence.decision_reason_counts["target_in_range"] == 1
    assert tuple(metric.card_id for metric in evidence.card_learning_metrics) == (
        "card.attack.fire_primary",
        "card.movement.advance",
        "card.vent.emergency_vent",
    )
    movement = evidence.card_learning_metrics[1]
    assert movement.dealt_count == 1
    assert movement.planned_count == 1
    assert movement.resolved_count == 1
    assert dict(movement.outcome_counts) == {"resolved": 1}
    assert dict(movement.action_counts) == {"move": 1}


@pytest.mark.unit
def test_card_metrics_only_use_canonical_card_lifecycle_events() -> None:
    stream = _complete_fixture_stream()

    metrics = project_card_learning_metrics(stream)

    assert {str(metric.card_id) for metric in metrics} == {
        "card.attack.fire_primary",
        "card.movement.advance",
        "card.vent.emergency_vent",
    }
    # CARDS_DISCARDED contains all three ids but is deliberately not a usage
    # event, and must not change any metric.
    without_discard = tuple(
        event for event in stream if event.event_type is not SOEventType.CARDS_DISCARDED
    )
    assert project_card_learning_metrics(without_discard) == metrics


@pytest.mark.unit
def test_card_metrics_reject_unknown_fields_in_canonical_payload() -> None:
    samples = build_sample_envelopes()
    hand = samples[SOEventType.HAND_DEALT]
    invalid = hand.model_copy(update={"payload": {**hand.payload, "untrusted": True}})
    stream = [
        invalid if event.event_type is SOEventType.HAND_DEALT else event
        for event in _complete_fixture_stream()
    ]

    with pytest.raises(ValidationError, match="untrusted"):
        project_match_learning_evidence(stream)


@pytest.mark.unit
def test_card_metrics_allow_heat_locked_reuse_without_new_plan_assignment() -> None:
    samples = build_sample_envelopes()
    resolved = samples[SOEventType.REGISTER_RESOLVED]
    heat_locked = resolved.model_copy(
        update={
            "payload": {
                **resolved.payload,
                "card_id": "card.attack.heat_locked_reuse",
                "action": "fire_primary",
                "outcome": "heat_locked",
                "fill_reason": None,
            }
        }
    )

    metrics = project_card_learning_metrics([heat_locked])

    assert metrics == (
        ModelSOCardLearningMetric(
            card_id="card.attack.heat_locked_reuse",
            dealt_count=0,
            planned_count=0,
            resolved_count=1,
            outcome_counts={"heat_locked": 1},
            action_counts={"fire_primary": 1},
        ),
    )


@pytest.mark.unit
def test_projection_rejects_unknown_payload_fields_before_persisting() -> None:
    samples = build_sample_envelopes()
    score = samples[SOEventType.MATCH_SCORED]
    invalid = score.model_copy(update={"payload": {**score.payload, "untrusted": True}})
    stream = [
        event
        for event in _complete_fixture_stream()
        if event.event_type is not SOEventType.MATCH_SCORED
    ]
    stream.append(invalid)

    with pytest.raises(ValidationError, match="untrusted"):
        project_match_learning_evidence(stream)


@pytest.mark.unit
def test_projection_rejects_duplicate_terminal_score_events() -> None:
    samples = build_sample_envelopes()
    stream = _complete_fixture_stream()
    stream.append(samples[SOEventType.MATCH_SCORED])

    with pytest.raises(ValueError, match="exactly one MATCH_SCORED"):
        project_match_learning_evidence(stream)


@pytest.mark.unit
def test_projection_rejects_mixed_workflow_correlation_ids() -> None:
    stream = _complete_fixture_stream()
    changed = stream[1]
    stream[1] = changed.model_copy(
        update={
            "envelope": changed.envelope.model_copy(
                update={"correlation_id": UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")}
            )
        }
    )

    with pytest.raises(ValueError, match="workflow correlation_id"):
        project_match_learning_evidence(stream)


@pytest.mark.unit
def test_projection_preserves_draw_convention_without_inventing_a_winner() -> None:
    samples = build_sample_envelopes()
    score = samples[SOEventType.MATCH_SCORED]
    raw_score = dict(score.payload)
    raw_score["winner"] = None
    raw_score["is_draw"] = True
    raw_score["scores"] = {
        player_id: {**player_score, "victory": 0}
        for player_id, player_score in score.payload["scores"].items()
    }
    draw = score.model_copy(update={"payload": raw_score})
    stream = [
        event
        for event in _complete_fixture_stream()
        if event.event_type is not SOEventType.MATCH_SCORED
    ]
    stream.append(draw)

    evidence = project_match_learning_evidence(stream)

    assert evidence.is_draw is True
    # MATCH_SCORED's canonical draw convention fills this field with the
    # alphabetically-first seat while ``is_draw`` remains authoritative.
    assert evidence.winner_player_id == "player.a"


@pytest.mark.unit
def test_match_evidence_store_is_content_addressed_and_first_write_wins(tmp_path: Path) -> None:
    evidence = project_match_learning_evidence(_complete_fixture_stream())
    store = YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=tmp_path / "evaluations",
            lineage_root=tmp_path / "lineage",
            experiment_root=tmp_path / "experiments",
        )
    )

    first = store.write_after_match_evidence(evidence)
    assert first == store.write_after_match_evidence(evidence)
    assert first.is_file()
    assert first.parent == tmp_path / "evaluations" / "matches"
    claims = tuple((tmp_path / "experiments" / "claims" / "matches").glob("*.sha256"))
    assert len(claims) == 1

    conflicting = evidence.model_copy(update={"duration_ticks": evidence.duration_ticks + 1})
    with pytest.raises(FileExistsError, match="refusing to replace non-identical"):
        store.write_after_match_evidence(conflicting)


@pytest.mark.integration
def test_composed_match_persists_after_match_evidence_from_ledger(tmp_path: Path) -> None:
    raw = complete_test_overlay(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": tmp_path / "events.sqlite",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": tmp_path / "leaderboard.sqlite",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "storage_schema": "leaderboard_v1",
            },
            "learning_artifacts": {
                "kind": "filesystem_yaml",
                "evaluation_root": tmp_path / "evaluations",
                "lineage_root": tmp_path / "lineage",
            },
            "evaluation_storage": {
                "kind": "sqlite",
                "root": tmp_path / "evaluations",
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
                "leaderboard_schema": "leaderboard_v1",
            },
            "contracts": {
                "catalog_dir": _REPO_ROOT / "contracts_data",
                "pilot_registry_dir": _REPO_ROOT / "contracts_data/pilots",
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
        },
        tmp_path,
    )
    overlay = ModelSOApplicationOverlay.model_validate(raw)
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=_REPO_ROOT / "contracts_data/loadouts/proof_red_predictive_ironclad.yaml",
        blue_loadout_path=_REPO_ROOT / "contracts_data/loadouts/proof_blue_aggressive_hunter.yaml",
        seed=12345,
        max_ticks=200,
    )
    try:
        final = stack.runner.run()
    finally:
        stack.close()

    evidence = tuple((tmp_path / "evaluations" / "matches").glob("*.yaml"))
    assert len(evidence) == 1
    persisted = yaml.safe_load(evidence[0].read_text(encoding="utf-8"))
    assert persisted["match_id"] == final.match_id
    assert persisted["event_counts"]["match_scored"] == 1
