"""Tuned-duel end-to-end divergence proof — tunable-pilots Task 5.

Re-runs the Proof-of-Life decisive duel (seed 12345) twice: once with the PoL
blue loadout (archetype fallback -> template aggressive spec) and once with
the same loadout re-piloted by the tuned fork
``pilot.tuned.aggressive_hot_v1`` (``mode_switch_pressure_floor: 50`` vs
template 12 — the single tuned parameter).

Parameter selection (plan Task 5 Step 3, empirical trace of the template duel
at seed 12345, captured 2026-06-11):

- the primary candidate ``vent_at_heat_margin`` is NOT divergent for this
  seed: blue's heat peaks at 42 and never enters the ``[rupture-5,
  rupture-2)`` window (volatile boiler rupture 85), so the plan's designated
  fallback ``mode_switch_pressure_floor`` is tuned instead;
- the trace shows blue's rule-2 assault switch firing at tick 1 with
  pressure 43 and heat 0; a floor of 50 (> 43) provably suppresses it, and
  with no enemy in weapon range and heat 0 the tuned pilot falls through to
  rule 5 (MOVE toward enemy);
- pinned divergence: tick 1, blue's ``pilot_decision_made`` —
  template ``switch_mode``/``mode_advantage``/0.8 vs tuned
  ``move``/``closing_distance``/0.7.

The proof, per the plan's Task 5 invariants:

- the tuned duel's canonical event sequence diverges from the template
  duel's;
- the two ledgers are identical up to the first divergence (Decision #3
  canonical scoping: ``(tick, sequence_in_tick, event_type, producer_node,
  subject, payload)``, excluding ``event_id``/``emitted_at``);
- the first divergent event is a ``pilot_decision_made`` for the tuned
  (blue) mech;
- the decision pair is exactly the tuned parameter's doing: the template
  rule-2 switch fired (so pressure >= 12, heat <= 80, mode lock expired,
  not in assault) while the tuned rule-2 did not and every later rule kept
  the same inputs — which pins the observation pressure inside ``[12, 50)``.

Comparison scoping notes (both deliberate, both explainable):

- ``match_id`` is a fresh ULID per ``run_match`` call and leaks into payloads
  via the boiler state embedded in ``match_started``; it is normalized to a
  sentinel before comparison (it would differ even between two identical
  template runs).
- the ``match_started`` payload embeds each mech's *declared identity*
  (``loadout_id``, ``pilot_id``).  The tuned loadout declares a different
  pilot by construction, so the tick-0 ``match_started`` rows are asserted
  to differ in exactly those blue-mech identity fields and nothing else;
  the behavioral divergence search runs over every subsequent row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from steel_onslaught.contracts.budget import validate_loadout_budgets
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import _module_budgets, load_loadout, run_match
from steel_onslaught.match.state import ModelSOMatchState, SOMatchStatus

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts"

POL_RED = _LOADOUTS / "proof_red_predictive_ironclad.yaml"
POL_BLUE_TEMPLATE = _LOADOUTS / "proof_blue_aggressive_hunter.yaml"
POL_BLUE_TUNED = _LOADOUTS / "tuned_aggressive_hunter.yaml"

BLUE_MECH_ID = "mech.blue.01"
SEED = 12345  # the canonical PoL decisive-victory seed
MAX_TICKS = 200

_TEMPLATE_PRESSURE_FLOOR = 12
_TUNED_PRESSURE_FLOOR = 50

# (tick, sequence_in_tick, event_type, producer_node, subject_json, payload_json)
CanonicalRow = tuple[int, int, str, str, str, str]


def _canonical_rows(ledger_path: Path, match_id: str) -> list[CanonicalRow]:
    """Decision #3 canonical rows: drop event_id/emitted_at, normalize match_id."""
    rows: list[CanonicalRow] = []
    for event in SQLiteLedger(ledger_path).read_all(match_id):
        payload_json = json.dumps(event.payload, sort_keys=True, separators=(",", ":")).replace(
            match_id, "<match>"
        )
        subject_json = json.dumps(
            {"mech_id": event.subject.mech_id, "player_id": event.subject.player_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        rows.append(
            (
                event.tick,
                event.sequence_in_tick,
                event.event_type.value,
                event.producer_node,
                subject_json,
                payload_json,
            )
        )
    return rows


def _run(blue_loadout: Path, out_dir: Path) -> tuple[ModelSOMatchState, list[CanonicalRow]]:
    ledger_path = out_dir / "match.sqlite"
    state = run_match(
        red_loadout=POL_RED,
        blue_loadout=blue_loadout,
        seed=SEED,
        max_ticks=MAX_TICKS,
        ledger_path=ledger_path,
        leaderboard_path=out_dir / "leaderboard.sqlite",
    )
    return state, _canonical_rows(ledger_path, state.match_id)


def _strip_blue_identity(match_started_payload_json: str) -> str:
    """Replace the blue mech's declared identity fields with sentinels."""
    payload: dict[str, Any] = json.loads(match_started_payload_json)
    for mech in payload["mechs"]:
        if mech["mech_id"] == BLUE_MECH_ID:
            mech["loadout_id"] = "<loadout>"
            mech["pilot_id"] = "<pilot>"
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _first_divergence(t_rows: list[CanonicalRow], u_rows: list[CanonicalRow]) -> int | None:
    for index, (t_row, u_row) in enumerate(zip(t_rows, u_rows, strict=False)):
        if t_row != u_row:
            return index
    if len(t_rows) != len(u_rows):
        return min(len(t_rows), len(u_rows))
    return None


@pytest.mark.integration
@pytest.mark.slow
def test_tuned_pilot_diverges_explainably(tmp_path: Path) -> None:
    template_dir = tmp_path / "template"
    tuned_dir = tmp_path / "tuned"
    template_dir.mkdir()
    tuned_dir.mkdir()

    template_state, t_rows = _run(POL_BLUE_TEMPLATE, template_dir)
    tuned_state, u_rows = _run(POL_BLUE_TUNED, tuned_dir)
    assert template_state.status is SOMatchStatus.ENDED
    assert tuned_state.status is SOMatchStatus.ENDED

    # --- tick-0 match_started: differs ONLY in blue's declared identity ----
    t_started, u_started = t_rows[0], u_rows[0]
    assert t_started[2] == "match_started"
    assert u_started[2] == "match_started"
    assert t_started[5] != u_started[5], "tuned loadout must declare a different pilot"
    assert t_started[:5] == u_started[:5]
    assert _strip_blue_identity(t_started[5]) == _strip_blue_identity(u_started[5])

    # --- behavioral divergence over every subsequent canonical row ---------
    t_events = t_rows[1:]
    u_events = u_rows[1:]
    div = _first_divergence(t_events, u_events)
    assert div is not None, "tuned parameters must change the duel"
    assert t_events[:div] == u_events[:div], "ledgers must be identical up to the divergence"

    t_div, u_div = t_events[div], u_events[div]
    # Pinned by the Step 3 trace (seed 12345): divergence at tick 1, blue's
    # decision slot — template pressure 43 satisfies the template floor (12)
    # but not the tuned floor (50).
    assert t_div[2] == "pilot_decision_made"
    assert u_div[2] == "pilot_decision_made"
    assert t_div[:5] == u_div[:5], "divergence must be the same decision slot, decided differently"
    assert t_div[0] == 1  # divergence tick pinned by the trace
    subject = json.loads(t_div[4])
    assert subject["mech_id"] == BLUE_MECH_ID

    # --- the flip is exactly mode_switch_pressure_floor's doing ------------
    t_decision = json.loads(t_div[5])
    u_decision = json.loads(u_div[5])
    # Template: rule 2 assault switch (the only switch_mode the aggressive
    # tree emits) => pressure >= 12, heat <= mode_switch_heat_ceiling, mode
    # lock expired, not already in assault.
    assert t_decision["action"] == "switch_mode"
    assert t_decision["action_params"] == {"target_mode": "assault"}
    assert t_decision["reason_code"] == "mode_advantage"
    assert t_decision["confidence"] == 0.8
    # Tuned: rule 2 suppressed (pressure < 50) with every other rule input
    # identical => the pilot falls through to rule 5 MOVE.  Together the pair
    # pins the observation pressure inside [12, 50).
    assert u_decision["action"] == "move"
    assert u_decision["reason_code"] == "closing_distance"
    assert _TEMPLATE_PRESSURE_FLOOR < _TUNED_PRESSURE_FLOOR  # window non-empty


@pytest.mark.integration
def test_tuned_pilot_costs_nothing_on_any_budget_axis() -> None:
    """Addendum §7: budget validation output is identical with a tuned pilot."""
    catalog = MatchContractCatalog.load()
    template_loadout = load_loadout(POL_BLUE_TEMPLATE)
    tuned_loadout = load_loadout(POL_BLUE_TUNED)

    template_entries = _module_budgets(template_loadout, catalog)
    tuned_entries = _module_budgets(tuned_loadout, catalog)
    assert template_entries == tuned_entries, "pilot specs must contribute zero on every axis"

    chassis = catalog.chassis[template_loadout.chassis_id]
    boiler = catalog.boilers[template_loadout.boiler_id]
    template_violations = validate_loadout_budgets(
        template_loadout, chassis, boiler, template_entries
    )
    tuned_violations = validate_loadout_budgets(tuned_loadout, chassis, boiler, tuned_entries)
    assert template_violations == tuned_violations == []
