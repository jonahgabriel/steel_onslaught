"""OMN-15489 — the card-mode duel gate must be causally driven by the specs.

This is the regression that fails RED against pre-fix ``main``.

The duel evaluator materializes a candidate and a parent ``ModelSOPilotSpec``
and hands the derived loadouts to the real duel executor. Before the fix, a
card-mode duel branched to ``MatchRunner._run_card_round``, which never
referenced the resolved seat pilots at all — registers were programmed purely
from the overlay's ``contracts.card_catalog.programmers`` bindings. Both duel
sides were therefore the SAME system, and the L-GATE-2 ``selection_outcome_v1``
gate was comparing provider variance against itself: ``docs/evidence/
2026-07-22-lgate2-significance-battery.md`` RUN B's promotion of
``vent_at_heat_margin`` 5 -> 4 was a structural zero, not a swamped signal.

The proof holds the entire match constant — same overlay, same seed, same
``match_id`` (so the dealer's per-seat scope deals the identical hands), same
opponent, same deterministic priority programmer with NO provider bound
anywhere — and varies ONLY the red seat's materialized pilot spec. Any
observable difference in the red seat's committed rounds can therefore only
have come through the spec.

Stated limits of THIS test, so nobody over-reads it:

- The duel is capped at 6 ticks. Past tick ~9 this seed ends decisively, and a
  decisive card-mode match currently fails card-round replay validation (the
  final partial round emits no ``CARDS_DISCARDED``) — a separate pre-existing
  defect, reproducible on unmodified ``main``, not introduced here.
- Within those 6 ticks the mech's heat never approaches the rupture band, so
  the heat-threshold parameters (``vent_at_heat_margin``,
  ``idle_vent_heat_threshold``, ``mode_switch_heat_ceiling``) do not change a
  decision *in this particular duel*. Their causality is pinned exactly, at the
  threshold boundary, by ``tests/cards/test_pilot_policy_rule.py``. Wiring is
  what this module proves; per-parameter discrimination in any specific battery
  remains an empirical question about that battery's trajectories.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.events.envelope import SOEventType
from steel_onslaught.learning.artifacts import MaterializedLoadout
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.learning.spec_adapter import params_from_spec, spec_from_params
from steel_onslaught.match.composition import load_loadout, load_pilot_spec
from steel_onslaught.match.duel import DuelResult, ModelSOEvaluationStorageKey
from tests.overlay import complete_test_overlay

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_CONTRACTS_DATA = Path("contracts_data").resolve()
_BASE_LOADOUT = _CONTRACTS_DATA / "loadouts/example_aggressive_light.yaml"
_TEMPLATE_PILOT = _CONTRACTS_DATA / "pilots/template_aggressive.yaml"

# One match_id shared by both arms: the dealer scope is
# (match_id, match_seed, tick, seat), so a differing match_id would change the
# dealt hands and destroy the single-variable comparison.
_MATCH_ID = "match.omn15489.causality"
_SEED = 4242
_MAX_TICKS = 6


def _card_mode_overlay(workdir: Path) -> ModelSOApplicationOverlay:
    """A hermetic card-mode overlay with NO card programmer bindings.

    An absent programmer binding keeps the deterministic priority planner, so
    this proof runs with no LLM anywhere — the differential cannot be provider
    variance by construction.
    """

    workdir.mkdir(parents=True, exist_ok=True)
    return ModelSOApplicationOverlay.model_validate(
        complete_test_overlay(
            {
                "schema_version": "1",
                "bus": {"kind": "in_process"},
                "event_ledger": {
                    "kind": "sqlite",
                    "path": workdir / "unused.sqlite3",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "event_schema": "canonical_event_v1",
                },
                "leaderboard": {
                    "kind": "sqlite",
                    "path": workdir / "leaderboard.sqlite3",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "storage_schema": "leaderboard_v1",
                },
                "learning_artifacts": {
                    "kind": "filesystem_yaml",
                    "evaluation_root": workdir,
                    "lineage_root": workdir / "lineage",
                },
                "evaluation_storage": {
                    "kind": "sqlite",
                    "root": workdir,
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "event_schema": "canonical_event_v1",
                    "leaderboard_schema": "leaderboard_v1",
                },
                "contracts": {
                    "catalog_dir": _CONTRACTS_DATA,
                    "pilot_registry_dir": _CONTRACTS_DATA / "pilots",
                    "card_catalog": {
                        "kind": "filesystem_yaml",
                        "cards_dir": _CONTRACTS_DATA / "cards",
                        "decks_dir": _CONTRACTS_DATA / "decks",
                        "card_mode_enabled": True,
                        "deck_id": "deck.standard.v1",
                    },
                },
                "clock": {"kind": "system_utc"},
                "identity": {"kind": "system"},
            },
            workdir,
        )
    )


def _template_params() -> ParamDict:
    return params_from_spec(load_pilot_spec(_TEMPLATE_PILOT))


def _materialize(
    store: YamlFilesystemLearningArtifactStore,
    *,
    evaluation_index: int,
    params: ParamDict,
    role: str,
) -> MaterializedLoadout:
    """Materialize a spec + derived loadout exactly as ``DuelEvaluator`` does."""

    workspace = store.prepare_evaluation(evaluation_index)
    digest = spec_hash("aggressive", params)
    spec = spec_from_params(
        archetype="aggressive",
        params=params,
        spec_id=f"pilot.learn.{role}_{digest[:12]}",
        parent_id="pilot.template.aggressive",
        display_name=f"Learn {role} {digest[:12]}",
    )
    return store.materialize_loadout(
        workspace, base=load_loadout(_BASE_LOADOUT), spec=spec, role=role
    )


def _red_rounds(result: DuelResult) -> tuple[tuple[str, ...], ...]:
    """The red seat's committed register sequences, round by round."""

    rounds: list[tuple[str, ...]] = []
    for event in result.events:
        if event.event_type is not SOEventType.PLAN_COMMITTED:
            continue
        if event.payload.get("seat") != "red":
            continue
        registers = event.payload.get("registers") or []
        rounds.append(tuple(str(register["card_id"]) for register in registers))
    return tuple(rounds)


def _duels(tmp_path: Path, *, candidate_params: ParamDict) -> Iterator[DuelResult]:
    """Run the parent-vs-parent and candidate-vs-parent arms of one comparison.

    Imported lazily so the module still collects when the composition root is
    unavailable for an unrelated reason.
    """

    from steel_onslaught.match.composition import build_duel_executor

    workdir = tmp_path / "work"
    overlay = _card_mode_overlay(workdir)
    store = YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=workdir,
            lineage_root=workdir / "lineage",
            experiment_root=workdir / "experiments",
        )
    )
    parent = _materialize(store, evaluation_index=1, params=_template_params(), role="par")
    candidate = _materialize(store, evaluation_index=2, params=candidate_params, role="cand")

    executor = build_duel_executor(overlay)
    try:
        for index, red in enumerate((parent, candidate)):
            yield executor(
                loadout_a=red.loadout,
                loadout_b=parent.loadout,
                seed=_SEED,
                max_ticks=_MAX_TICKS,
                storage=ModelSOEvaluationStorageKey(namespace="omn15489", duel=f"arm_{index}"),
                match_id=_MATCH_ID,
                loadout_path_a=red.path,
                loadout_path_b=parent.path,
                side_a="red",
                side_b="blue",
            )
    finally:
        executor.close()


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        # A numeric lattice knob: at floor 60 the mode-switch rule can no longer
        # fire on this chassis' pressure, so the round leads with a different
        # card than the parent's floor-12 policy commits.
        ("mode_switch_pressure_floor", 60),
        # A categorical knob: both policies fire, but at different weapon
        # slots, which the ATTACK card's ``weapon_slot`` effect distinguishes.
        ("weapon_preference", "lowest_heat"),
    ],
)
def test_candidate_spec_changes_a_card_mode_duel_decision(
    tmp_path: Path, parameter: str, value: object
) -> None:
    """A single-parameter spec delta must move at least one committed round.

    RED against pre-fix code: card mode never consulted the seat pilot, so both
    arms produced byte-identical PLAN_COMMITTED sequences and this assertion
    failed — which is precisely why the RUN B promotion was vacuous.
    """

    candidate_params: ParamDict = dict(_template_params())
    candidate_params[parameter] = value  # type: ignore[assignment]
    parent_result, candidate_result = _duels(tmp_path, candidate_params=candidate_params)

    parent_rounds = _red_rounds(parent_result)
    candidate_rounds = _red_rounds(candidate_result)

    assert parent_rounds, "card mode produced no red-seat PLAN_COMMITTED rounds"
    assert len(parent_rounds) == len(candidate_rounds) or parent_rounds != candidate_rounds
    assert parent_rounds != candidate_rounds, (
        f"{parameter} is causally inert in card mode: both arms committed "
        f"identical rounds ({len(parent_rounds)} rounds)"
    )


def test_identical_specs_produce_identical_card_rounds(tmp_path: Path) -> None:
    """The differential is the SPEC, not run-to-run nondeterminism.

    Without this control the test above could be satisfied by any source of
    variance; here the candidate params equal the parent params and the two
    arms must be byte-identical.
    """

    parent_result, candidate_result = _duels(tmp_path, candidate_params=_template_params())
    assert _red_rounds(parent_result) == _red_rounds(candidate_result)
