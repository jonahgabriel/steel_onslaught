"""Tests for ``learning/duel_evaluator.py`` — Phase 2 Task 2 invariants.

Invariants under test (plan Task 2):

1. ``aggregate_pair`` full 9-case table: exactly (CANDIDATE, CANDIDATE) ->
   CANDIDATE and (PARENT, PARENT) -> PARENT; the other 7 combinations -> DRAW.
2. ``DuelEvaluator`` structurally satisfies ``EvaluatorProtocol``
   (mypy-enforced assignment).
3. Determinism: two ``evaluate`` calls with the same 2-seed battery return
   equal ``ModelSOSeedOutcome`` lists — identical winners AND overload counts.
4. Self-pairing bias check: ``evaluate(p, p, seeds)`` aggregates every seed to
   DRAW (side-swap cancellation proven, not assumed).
5. Side swap actually happens: the two duel ledgers of one seed show the
   candidate's materialized pilot_id on the red side in one duel and the blue
   side in the other (PILOT_DECISION_MADE subjects attribute the mech).
6. Outcomes return in the given seed order; duplicate seeds raise ValueError.
7. No writes outside ``workdir``: contracts_data/ snapshot unchanged, no
   implicit ledger directory created in the working directory.
8. An invalid base loadout (budget violation) propagates run_match's
   validation error — no silent catch.
9. Off-template parent params produce a valid materialized spec chaining to
   the archetype template id.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.contracts.pilot_registry import load_pilot_spec
from steel_onslaught.learning.duel_evaluator import DuelEvaluator, aggregate_pair
from steel_onslaught.learning.protocols import EvaluatorProtocol, SOSeedWinner
from steel_onslaught.learning.spec_adapter import params_from_spec

_BASE_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml").resolve()
_TEMPLATE_PILOT = Path("contracts_data/pilots/template_aggressive.yaml").resolve()
_CONTRACTS_DATA = Path("contracts_data").resolve()

# Small max_ticks + <=2 seeds keep the slow integration tests bounded (plan
# Task 2 Step 1) while still producing decisive outcomes on most seeds.
_MAX_TICKS = 80


def _template_params() -> ParamDict:
    return params_from_spec(load_pilot_spec(_TEMPLATE_PILOT))


def _perturbed(params: ParamDict, field: str = "vent_at_heat_margin", delta: int = 1) -> ParamDict:
    out: ParamDict = dict(params)
    out[field] = int(out[field]) + delta
    return out


def _snapshot(root: Path) -> dict[str, str]:
    """File list + content hashes under *root* (the §4.5 no-mutation probe)."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _make_evaluator(workdir: Path, *, base_loadout: Path = _BASE_LOADOUT) -> DuelEvaluator:
    return DuelEvaluator(
        archetype="aggressive",
        base_loadout=base_loadout,
        workdir=workdir,
        max_ticks=_MAX_TICKS,
    )


# ---------------------------------------------------------------------------
# 1. aggregate_pair — exhaustive 9-case table (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_pair_full_nine_case_table() -> None:
    """Only the two unanimous combinations are decisive; the other 7 are DRAW."""
    decisive = {
        (SOSeedWinner.CANDIDATE, SOSeedWinner.CANDIDATE): SOSeedWinner.CANDIDATE,
        (SOSeedWinner.PARENT, SOSeedWinner.PARENT): SOSeedWinner.PARENT,
    }
    combos = list(itertools.product(SOSeedWinner, SOSeedWinner))
    assert len(combos) == 9
    for first, second in combos:
        expected = decisive.get((first, second), SOSeedWinner.DRAW)
        assert aggregate_pair(first, second) is expected
    draw_count = sum(
        1 for first, second in combos if aggregate_pair(first, second) is SOSeedWinner.DRAW
    )
    assert draw_count == 7


# ---------------------------------------------------------------------------
# 2. EvaluatorProtocol conformance (mypy-enforced assignment)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_duel_evaluator_satisfies_evaluator_protocol(tmp_path: Path) -> None:
    evaluator = _make_evaluator(tmp_path / "work")
    # Runtime structural check (mypy --strict enforces statically).
    protocol_var: EvaluatorProtocol = evaluator
    assert protocol_var is evaluator


# ---------------------------------------------------------------------------
# 6b. Duplicate seeds raise ValueError
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_duplicate_seeds_raise_value_error(tmp_path: Path) -> None:
    evaluator = _make_evaluator(tmp_path / "work")
    parent = _template_params()
    with pytest.raises(ValueError, match="duplicate"):
        evaluator.evaluate(_perturbed(parent), parent, [7, 7])


# ---------------------------------------------------------------------------
# 8. Invalid base loadout (budget violation) propagates — no silent catch
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_invalid_base_loadout_propagates_budget_violation(tmp_path: Path) -> None:
    """A 5th module on the 4-slot scout chassis trips run_match's budget gate."""
    raw = yaml.safe_load(_BASE_LOADOUT.read_text(encoding="utf-8"))
    raw["modules"]["weapons"].append("weapon.medium.steam_cannon")
    bad_path = tmp_path / "bad_loadout.yaml"
    bad_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    parent = _template_params()
    with pytest.raises(ValueError, match="violates budgets"):
        evaluator = _make_evaluator(tmp_path / "work", base_loadout=bad_path)
        evaluator.evaluate(_perturbed(parent), parent, [1])


# ---------------------------------------------------------------------------
# 3 + 6a. Determinism and seed-order preservation (integration, slow)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
def test_evaluate_is_deterministic_and_preserves_seed_order(tmp_path: Path) -> None:
    """Identical 2-seed battery twice => equal outcome lists (winners AND
    overload counts) — 'identical seeds => identical win matrix' at the
    single-pairing level. Seeds are deliberately unsorted to pin ordering."""
    evaluator = _make_evaluator(tmp_path / "work")
    parent = _template_params()
    candidate = _perturbed(parent)
    seeds = [4, 3]

    first = evaluator.evaluate(candidate, parent, seeds)
    second = evaluator.evaluate(candidate, parent, seeds)

    assert first == second  # frozen-model equality: winner + overload counts
    assert [outcome.seed for outcome in first] == seeds


# ---------------------------------------------------------------------------
# 4. Self-pairing bias check: candidate == parent => all DRAW (integration, slow)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
def test_self_pairing_aggregates_every_seed_to_draw(tmp_path: Path) -> None:
    """The two duels of a seed are the same match with labels swapped, so the
    aggregation must cancel to DRAW on every seed — proven, not assumed."""
    evaluator = _make_evaluator(tmp_path / "work")
    parent = _template_params()

    outcomes = evaluator.evaluate(dict(parent), parent, [1, 2])

    assert [outcome.winner for outcome in outcomes] == [SOSeedWinner.DRAW, SOSeedWinner.DRAW]
    for outcome in outcomes:
        # Label-swapped identical matches: per-side overloads must mirror too.
        assert outcome.candidate_overloads == outcome.parent_overloads


# ---------------------------------------------------------------------------
# 5 + 9. Side swap happens on disk; off-template parent spec materializes valid
# ---------------------------------------------------------------------------


def _read_rows(ledger_path: Path, sql: str) -> list[tuple[str, ...]]:
    with closing(sqlite3.connect(ledger_path)) as conn:
        return list(conn.execute(sql))


@pytest.mark.integration
@pytest.mark.slow
def test_side_swap_happens_and_off_template_parent_spec_is_valid(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    evaluator = _make_evaluator(workdir)
    parent = _perturbed(_template_params(), field="idle_vent_heat_threshold", delta=-1)
    candidate = _perturbed(parent)

    evaluator.evaluate(candidate, parent, [5])

    # --- 5. Side swap: candidate pilot on red in one duel, blue in the other.
    candidate_id = f"pilot.learn.cand_{spec_hash('aggressive', candidate)[:12]}"
    ledgers = sorted(workdir.rglob("*.sqlite3"))
    assert len(ledgers) == 2  # one seed => two side-swapped duels
    candidate_players: set[str] = set()
    for ledger_path in ledgers:
        started = _read_rows(
            ledger_path,
            "SELECT payload_json FROM events WHERE event_type = 'match_started'",
        )
        assert len(started) == 1
        mechs = json.loads(started[0][0])["mechs"]
        candidate_mechs = [m for m in mechs if m["pilot_id"] == candidate_id]
        assert len(candidate_mechs) == 1
        candidate_players.add(candidate_mechs[0]["player_id"])
        # PILOT_DECISION_MADE subjects attribute the candidate's mech.
        decision_subjects = _read_rows(
            ledger_path,
            "SELECT subject_json FROM events WHERE event_type = 'pilot_decision_made'",
        )
        assert any(
            json.loads(subject)["mech_id"] == candidate_mechs[0]["mech_id"]
            for (subject,) in decision_subjects
        )
    assert candidate_players == {"player.red", "player.blue"}

    # --- 9. Off-template parent spec materialized valid, chained to the template.
    parent_id = f"pilot.learn.par_{spec_hash('aggressive', parent)[:12]}"
    materialized_specs = [
        ModelSOPilotSpec.model_validate(loaded)
        for path in sorted(workdir.rglob("*.yaml"))
        if (loaded := yaml.safe_load(path.read_text(encoding="utf-8")))["kind"]
        == "steel_onslaught.pilot"
    ]
    parent_specs = [spec for spec in materialized_specs if spec.id == parent_id]
    assert len(parent_specs) == 1
    assert parent_specs[0].lineage.parent == "pilot.template.aggressive"
    assert params_from_spec(parent_specs[0]) == parent
    # The candidate spec chains to the materialized parent (non-null lineage).
    candidate_specs = [spec for spec in materialized_specs if spec.id == candidate_id]
    assert len(candidate_specs) == 1
    assert candidate_specs[0].lineage.parent == parent_id


# ---------------------------------------------------------------------------
# 7. No writes outside workdir (§4.5 / Decision #6)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
def test_no_writes_outside_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """contracts_data/ is byte-unchanged by an evaluate; nothing lands in the
    working directory (no implicit ledger dir — the MVP/Task-6 invariant)."""
    workdir = tmp_path / "work"
    evaluator = _make_evaluator(workdir)
    parent = _template_params()
    candidate = _perturbed(parent)

    before = _snapshot(_CONTRACTS_DATA)
    empty_cwd = tmp_path / "empty_cwd"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)

    evaluator.evaluate(candidate, parent, [1, 2])

    assert _snapshot(_CONTRACTS_DATA) == before
    assert list(empty_cwd.iterdir()) == []
    # Everything the evaluation materialized lives under workdir.
    created = [path for path in workdir.rglob("*") if path.is_file()]
    assert created
    assert all(path.is_relative_to(workdir) for path in created)
