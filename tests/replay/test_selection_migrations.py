"""Explicit-input-only contract tests for future selection migration."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.player_selection import (
    ModelSOModelDecisionSource,
    ModelSOModelSeatAssignment,
)
from steel_onslaught.replay.selection_migrations import (
    ModelSOHistoricalDecisionSourceInput,
    ModelSOHistoricalMatchLaunchProvenanceInput,
    ModelSOHistoricalSelectionMigrationInput,
    ModelSOLegacyHeuristicDecisionSource,
    ModelSOLegacyHeuristicSeatAssignment,
)

_COMMAND_ID = UUID("11111111-1111-4111-8111-111111111111")
_HASH = "c" * 64
_MATCH_ID = "match.01J00000000000000000000000"


def _launch() -> ModelSOHistoricalMatchLaunchProvenanceInput:
    common = {"option_sha256": _HASH}
    return ModelSOHistoricalMatchLaunchProvenanceInput(
        schema_version="1",
        kind="steel_onslaught.historical_match_launch_provenance_input",
        match_id=_MATCH_ID,
        launch_command_id=_COMMAND_ID,
        launch_command_sha256=_HASH,
        overlay_sha256=_HASH,
        roster_id="roster.historical_explicit",
        roster_sha256=_HASH,
        seat_assignments=(
            ModelSOLegacyHeuristicSeatAssignment(
                kind="legacy_heuristic",
                side="red",
                player_id="player.red",
                loadout_id="loadout.playable.heuristic_light",
                pilot_spec_id="pilot.template.aggressive",
                pilot_spec_sha256=_HASH,
                pilot_archetype="aggressive",
                input_source="automated",
            ),
            ModelSOModelSeatAssignment(
                kind="model",
                side="blue",
                player_id="player.blue",
                option_id="player_option.local_qwen",
                loadout_id="loadout.playable.model_light",
                pilot_spec_id="pilot.llm.qwen35",
                model_identity_id="model_identity.local_qwen",
                persona_id="berserker",
                input_source="llm_completion",
                **common,
            ),
        ),
    )


def _input() -> ModelSOHistoricalSelectionMigrationInput:
    return ModelSOHistoricalSelectionMigrationInput(
        schema_version="1",
        kind="steel_onslaught.historical_selection_migration_input",
        match_id=_MATCH_ID,
        launch=_launch(),
        decision_sources=(
            ModelSOHistoricalDecisionSourceInput(
                event_id="01J00000000000000000000000",
                source=ModelSOLegacyHeuristicDecisionSource(
                    kind="legacy_heuristic",
                    input_source="automated",
                    pilot_spec_id="pilot.template.aggressive",
                    pilot_spec_sha256=_HASH,
                    pilot_archetype="aggressive",
                ),
            ),
            ModelSOHistoricalDecisionSourceInput(
                event_id="01J00000000000000000000001",
                source=ModelSOModelDecisionSource(
                    kind="model",
                    input_source="llm_completion",
                    model_identity_id="model_identity.local_qwen",
                    persona_id="berserker",
                ),
            ),
        ),
    )


@pytest.mark.unit
def test_explicit_migration_input_round_trips_without_inference() -> None:
    migration = _input()
    assert (
        ModelSOHistoricalSelectionMigrationInput.model_validate_json(migration.model_dump_json())
        == migration
    )
    assert {item.source.kind for item in migration.decision_sources} == {
        "legacy_heuristic",
        "model",
    }
    legacy_assignment = migration.launch.seat_assignments[0]
    assert legacy_assignment.kind == "legacy_heuristic"
    assert "option_id" not in legacy_assignment.model_dump()
    assert migration.match_id == migration.launch.match_id == _MATCH_ID


@pytest.mark.unit
def test_migration_requires_complete_caller_supplied_identity_and_hash_evidence() -> None:
    raw = _input().model_dump(mode="python")
    launch = dict(raw["launch"])
    del launch["roster_sha256"]
    with pytest.raises(ValidationError):
        ModelSOHistoricalSelectionMigrationInput.model_validate({**raw, "launch": launch})
    with pytest.raises(ValidationError):
        ModelSOHistoricalSelectionMigrationInput.model_validate(
            {"match_id": _MATCH_ID, "pilot_id": "pilot.llm.qwen35"}
        )


@pytest.mark.unit
def test_migration_rejects_match_mismatch_and_duplicate_decision_evidence() -> None:
    migration = _input()
    with pytest.raises(ValidationError):
        ModelSOHistoricalSelectionMigrationInput(
            schema_version="1",
            kind="steel_onslaught.historical_selection_migration_input",
            match_id="match.01J00000000000000000000001",
            launch=migration.launch,
            decision_sources=migration.decision_sources,
        )
    with pytest.raises(ValidationError):
        ModelSOHistoricalSelectionMigrationInput(
            schema_version="1",
            kind="steel_onslaught.historical_selection_migration_input",
            match_id=migration.match_id,
            launch=migration.launch,
            decision_sources=(migration.decision_sources[0],) * 2,
        )


@pytest.mark.unit
def test_migration_legacy_heuristic_requires_explicit_automated_identity_evidence() -> None:
    raw = _input().model_dump(mode="python")
    launch = dict(raw["launch"])
    assignments = list(launch["seat_assignments"])
    legacy_assignment = dict(assignments[0])
    del legacy_assignment["pilot_spec_sha256"]
    assignments[0] = legacy_assignment
    launch["seat_assignments"] = tuple(assignments)
    with pytest.raises(ValidationError):
        ModelSOHistoricalSelectionMigrationInput.model_validate({**raw, "launch": launch})

    decision_sources = list(raw["decision_sources"])
    legacy_decision = dict(decision_sources[0])
    source = dict(legacy_decision["source"])
    source["kind"] = "model"
    legacy_decision["source"] = source
    decision_sources[0] = legacy_decision
    with pytest.raises(ValidationError):
        ModelSOHistoricalSelectionMigrationInput.model_validate(
            {**raw, "decision_sources": tuple(decision_sources)}
        )
