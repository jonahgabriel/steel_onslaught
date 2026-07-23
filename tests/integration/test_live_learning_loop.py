"""End-to-end proof of the live learning loop (learning-adaptation-01/02/03).

The three blockers this file locks shut:

- **01 (dead code):** with the overlay's ``live_learning`` binding present,
  composition instantiates one ``LiveLearningCoordinator`` with a concrete
  deterministic evaluator and ADMITS every live match on it — proven here by
  the duplicate-admission guard firing for a composed match id.
- **02 (no event):** a promotion appends a payload-validated
  ``POLICY_PROMOTED`` event to the promoting match's stream, caused by its
  ``MATCH_SCORED``; folding the stream (twice, plus from a freshly composed
  dependency graph) reconstructs the identical promotion state, and the
  post-terminal appendix leaves reprojection AND replay validity green.
- **03 (seam raises):** a scored match with learning enabled completes
  without raising (the cross-boundary seam regression — this exact shape
  crashed with "must be admitted before terminal evidence" on the pre-fix
  tree), while an UN-admitted terminal still fails closed by design.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.lineage import spec_hash
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import ModelSOPolicyPromotedPayload
from steel_onslaught.learning.after_match import AfterMatchLearningHandler
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.learning.live import LiveLearningCoordinator
from steel_onslaught.learning.live_evaluator import WinDamageDifferentialEvaluator
from steel_onslaught.learning.post_match import project_match_learning_evidence
from steel_onslaught.learning.promotion_fold import (
    fold_policy_promotions,
    resolve_promotion_chain,
)
from steel_onslaught.match.composition import (
    LiveMatchStack,
    RuntimeDependencies,
    assemble_match_with_dependencies,
    build_runtime_dependencies,
    load_loadout,
)
from steel_onslaught.match.runner import MatchIdentity
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.reducers.scoring import verify_replay_validity
from tests.overlay import complete_test_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RED = _REPO_ROOT / "contracts_data/loadouts/proof_red_predictive_ironclad.yaml"
_BLUE = _REPO_ROOT / "contracts_data/loadouts/proof_blue_aggressive_hunter.yaml"
_ARCHETYPE = "aggressive"
_GENESIS_PARAMETERS = {"aggression": 1.0}

# Deterministic proof-pilot duels (measured this session): seed 12345 → red
# wins 103-42 on damage (promotes); seed 777 → red wins on points but is
# OUT-damaged 123-149 (evaluator must reject).
_PROMOTING_SEED = 12345
_NON_PROMOTING_WIN_SEED = 777


def _overlay(tmp_path: Path, *, live_learning: bool) -> ModelSOApplicationOverlay:
    raw: dict[str, Any] = {
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
    }
    if live_learning:
        raw["live_learning"] = {
            "kind": "win_damage_differential_v1",
            "archetype": _ARCHETYPE,
            "learning_player_id": "player.red",
            "genesis_parameters": dict(_GENESIS_PARAMETERS),
            "parameter": "aggression",
            "step": 0.25,
            "max_value": 3.0,
        }
    return ModelSOApplicationOverlay.model_validate(complete_test_overlay(raw, tmp_path))


def _run_match(
    dependencies: RuntimeDependencies, *, seed: int
) -> tuple[LiveMatchStack, ModelSOMatchState]:
    identity = MatchIdentity(
        match_id=dependencies.identities.new_match_id(),
        correlation_id=dependencies.identities.new_correlation_id(),
    )
    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=load_loadout(_RED),
        blue=load_loadout(_BLUE),
        red_loadout_path=_RED,
        blue_loadout_path=_BLUE,
        seed=seed,
        max_ticks=200,
        identity=identity,
    )
    try:
        final = stack.runner.run()
    finally:
        stack.close()
    return stack, final


def _flatten(exc: BaseException) -> list[BaseException]:
    nested = getattr(exc, "exceptions", None)
    if nested is None:
        return [exc]
    flat: list[BaseException] = []
    for child in nested:
        flat.extend(_flatten(child))
    return flat


@pytest.mark.integration
def test_scored_match_with_learning_enabled_completes_and_promotes(tmp_path: Path) -> None:
    """The cross-boundary seam regression (03) + the auditable promotion (01/02).

    This exact composition RAISED ``must be admitted before terminal
    evidence`` through the real bus on the pre-fix tree.
    """

    overlay = _overlay(tmp_path, live_learning=True)
    dependencies = build_runtime_dependencies(overlay)
    coordinator = dependencies.live_learning
    assert coordinator is not None, "live_learning binding must construct a coordinator"
    genesis_policy = coordinator.current_policy
    assert genesis_policy.generation == 0
    assert genesis_policy.spec_hash == spec_hash(_ARCHETYPE, _GENESIS_PARAMETERS)

    stack, final = _run_match(dependencies, seed=_PROMOTING_SEED)
    match_id = stack.identity.match_id

    # Blocker 01: composition admitted the match on the SAME coordinator —
    # a second admission for the same id must be refused.
    with pytest.raises(ValueError, match="already"):
        coordinator.begin_match(match_id)

    events = tuple(dependencies.ledger.read_all(match_id))
    promoted_events = [e for e in events if e.event_type is SOEventType.POLICY_PROMOTED]
    assert len(promoted_events) == 1
    promoted = promoted_events[0]
    scored = next(e for e in events if e.event_type is SOEventType.MATCH_SCORED)

    # Blocker 02: the promotion fact is on the promoting match's stream,
    # ordered after and caused by its MATCH_SCORED.
    assert events.index(promoted) > events.index(scored)
    assert promoted.envelope.causation_id == scored.envelope.message_id
    assert promoted.envelope.correlation_id == scored.envelope.correlation_id
    payload = ModelSOPolicyPromotedPayload.model_validate(promoted.payload)
    assert payload.match_id == match_id
    assert payload.archetype == _ARCHETYPE
    assert payload.generation == 1
    assert payload.parent_spec_hash == genesis_policy.spec_hash
    assert payload.evidence_scored_event_id == scored.event_id

    # The fielded in-memory policy is exactly the event-recorded one.
    fielded = coordinator.current_policy
    assert fielded.generation == 1
    assert fielded.spec_hash == payload.spec_hash
    assert fielded.policy_id == payload.policy_id
    assert fielded.source_lineage_digest == payload.source_lineage_digest
    assert fielded.parameters["aggression"] == 1.25

    # The event's digest resolves to a durable lineage record (parameter truth).
    lineage_path = (
        tmp_path
        / "lineage"
        / _ARCHETYPE
        / payload.spec_hash
        / f"{payload.source_lineage_digest}.yaml"
    )
    assert lineage_path.is_file()

    # §4.2 census trap: REPROJECTING the stream that now contains the
    # appendix must pass the fail-closed payload authority.
    reprojected = project_match_learning_evidence(events)
    assert reprojected.event_counts["policy_promoted"] == 1

    # Post-terminal append legality: replaying the full stream — appendix
    # included — still reproduces the live final state exactly.
    assert verify_replay_validity(
        dependencies.ledger,
        match_id,
        final,
        catalog=dependencies.catalog,
        event_factory=dependencies.event_factory,
    )

    # Folding the events twice yields the identical promotion state.
    first_fold = resolve_promotion_chain(fold_policy_promotions(events), archetype=_ARCHETYPE)
    second_fold = resolve_promotion_chain(
        fold_policy_promotions(tuple(dependencies.ledger.read_all(match_id))),
        archetype=_ARCHETYPE,
    )
    assert first_fold == second_fold == (payload,)


@pytest.mark.integration
def test_promotion_state_rehydrates_identically_in_a_fresh_composition(tmp_path: Path) -> None:
    """Replay-auditability: a fresh dependency graph over the same durable
    surfaces reconstructs the promoted policy from the event chain + lineage
    store, and a non-differential win does NOT extend the chain."""

    overlay = _overlay(tmp_path, live_learning=True)
    first = build_runtime_dependencies(overlay)
    assert first.live_learning is not None
    _run_match(first, seed=_PROMOTING_SEED)
    promoted_policy: ModelSOLiveLearningPolicy = first.live_learning.current_policy
    assert promoted_policy.generation == 1

    # Fresh composition (a new process in production): the coordinator's
    # policy is rebuilt from the POLICY_PROMOTED chain, not process memory.
    second = build_runtime_dependencies(overlay)
    assert second.live_learning is not None
    assert second.live_learning.current_policy == promoted_policy

    # Seed 777: red wins on points but is out-damaged — the evaluator must
    # reject, the chain must not grow, and the match must still complete.
    stack, _ = _run_match(second, seed=_NON_PROMOTING_WIN_SEED)
    assert second.live_learning.current_policy == promoted_policy
    second_stream = tuple(second.ledger.read_all(stack.identity.match_id))
    assert not any(e.event_type is SOEventType.POLICY_PROMOTED for e in second_stream)

    # The cross-match fold over the whole catalog still resolves to exactly
    # the one generation-1 tip.
    promotions: list[ModelSOEventEnvelope] = []
    for match_id in second.ledger.read_match_ids():
        promotions.extend(second.ledger.read_all(match_id))
    chain = resolve_promotion_chain(fold_policy_promotions(promotions), archetype=_ARCHETYPE)
    assert len(chain) == 1
    assert chain[0].generation == 1
    assert chain[0].spec_hash == promoted_policy.spec_hash


@pytest.mark.integration
def test_unadmitted_terminal_still_fails_closed_through_the_real_seam(tmp_path: Path) -> None:
    """The coordinator's admission guard (the pre-fix crash) is retained as a
    fail-closed seam-regression tripwire: an un-admitted terminal delivered
    through the REAL bus raises instead of silently promoting."""

    overlay = _overlay(tmp_path, live_learning=False)
    dependencies = build_runtime_dependencies(overlay)
    identity = MatchIdentity(
        match_id=dependencies.identities.new_match_id(),
        correlation_id=dependencies.identities.new_correlation_id(),
    )
    stack = assemble_match_with_dependencies(
        dependencies=dependencies,
        red=load_loadout(_RED),
        blue=load_loadout(_BLUE),
        red_loadout_path=_RED,
        blue_loadout_path=_BLUE,
        seed=_PROMOTING_SEED,
        max_ticks=200,
        identity=identity,
    )
    genesis = ModelSOLiveLearningPolicy(
        policy_id=f"policy.{_ARCHETYPE}.genesis",
        archetype=_ARCHETYPE,
        parameters=dict(_GENESIS_PARAMETERS),
        spec_hash=spec_hash(_ARCHETYPE, _GENESIS_PARAMETERS),
        generation=0,
    )
    unadmitted = LiveLearningCoordinator(
        current_policy=genesis,
        evaluator=WinDamageDifferentialEvaluator(learning_player_id="player.red"),
    )
    handler = AfterMatchLearningHandler(
        ledger=stack.ledger,
        artifacts=YamlFilesystemLearningArtifactStore(
            ModelSOFilesystemLearningArtifactsConfig(
                evaluation_root=tmp_path / "evaluations",
                lineage_root=tmp_path / "lineage",
                experiment_root=tmp_path / "experiments",
            )
        ),
        promotion=unadmitted,
        emit=stack.bus.publish,
        event_factory=stack.event_factory,
    )
    stack.bus.subscribe(handler.handle, event_types=[SOEventType.MATCH_SCORED])
    try:
        with pytest.raises(ExceptionGroup) as excinfo:
            stack.runner.run()
    finally:
        stack.close()
    messages = [str(e) for e in _flatten(excinfo.value)]
    assert any("must be admitted before terminal evidence" in m for m in messages)


@pytest.mark.integration
def test_promotion_port_without_emission_capability_is_a_composition_error(
    tmp_path: Path,
) -> None:
    """Optional-input trap (fail closed): promotion without event emission
    would silently un-event-source promotions — construction must refuse."""

    overlay = _overlay(tmp_path, live_learning=True)
    dependencies = build_runtime_dependencies(overlay)
    assert dependencies.live_learning is not None
    with pytest.raises(ValueError, match="event-sourced"):
        AfterMatchLearningHandler(
            ledger=dependencies.ledger,
            artifacts=YamlFilesystemLearningArtifactStore(
                ModelSOFilesystemLearningArtifactsConfig(
                    evaluation_root=tmp_path / "evaluations2",
                    lineage_root=tmp_path / "lineage2",
                    experiment_root=tmp_path / "experiments2",
                )
            ),
            promotion=dependencies.live_learning,
        )
