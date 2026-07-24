"""O-GATE battery driver: ``--expected-arena`` selection + zero-objective scorecard.

The scenario-axis re-measure (design 2026-07-22) reruns the surfaced-fixed qwen35
utility battery on the SYMMETRIC ``foundry_60`` arena, which has no objectives and
no ``vp_threshold``. Two driver properties make that possible without touching any
overlay/arena/balance:

- ``--expected-arena`` defaults to ``foundry_60_asym_v1`` so every pre-existing run
  is byte-identical, and passing ``--expected-arena foundry_60`` selects the
  symmetric arena for the MATCH_STARTED assert and the arena_contract_hash seam;
- the objective/VP scorecard aggregation tolerates an arena with ZERO objectives:
  objective counts collapse to 0 while keep(play-terminal)/terminal-class/winner/
  brawler statistics still compute, because every objective path is guarded by
  empty-collection defaults and no objective count is ever a divisor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_ogate_objectives_battery import (
    _ARENA_ID,
    _BLUE,
    _RED,
    _build_parser,
    _objective_metrics,
    _summarize,
    _terminal_class,
)
from steel_onslaught.contracts.arena import arena_contract_hash
from steel_onslaught.match.composition import load_match_contract_catalog

pytestmark = pytest.mark.unit

_CONTRACTS_DATA = Path(__file__).resolve().parents[2] / "contracts_data"


# ---------------------------------------------------------------------------
# --expected-arena CLI selection
# ---------------------------------------------------------------------------


def test_expected_arena_defaults_to_the_asym_arena() -> None:
    """Byte-identical default: no --expected-arena keeps the asym objective arena."""
    args = _build_parser().parse_args([])
    assert args.expected_arena == _ARENA_ID
    assert _ARENA_ID == "foundry_60_asym_v1"


def test_expected_arena_arg_selects_the_symmetric_arena() -> None:
    args = _build_parser().parse_args(["--expected-arena", "foundry_60"])
    assert args.expected_arena == "foundry_60"


def test_symmetric_arena_hash_is_computable_and_distinct() -> None:
    """The --expected-arena hash seam resolves for the objective-less arena too.

    Proves the arena_contract_hash the driver asserts on MATCH_STARTED can be
    computed for ``foundry_60`` (the symmetric arena has no objectives) and is a
    different digest than the asym arena's, so the seam is arena-specific.
    """
    catalog = load_match_contract_catalog(_CONTRACTS_DATA)
    sym_hash = arena_contract_hash(catalog.arenas["foundry_60"].to_snapshot())
    asym_hash = arena_contract_hash(catalog.arenas["foundry_60_asym_v1"].to_snapshot())
    assert sym_hash and asym_hash
    assert sym_hash != asym_hash
    # The symmetric arena genuinely carries zero objectives.
    assert list(catalog.arenas["foundry_60"].objectives) == []


# ---------------------------------------------------------------------------
# Zero-objective scorecard tolerance
# ---------------------------------------------------------------------------


def _row(**over: object) -> dict[str, object]:
    """A minimal battery row with ZERO objectives (symmetric-arena shape)."""
    base: dict[str, object] = {
        "terminal_class": "elimination",
        "end_reason": "last_mech_standing",
        "victory_kind": "last_mech_standing",
        "is_draw": False,
        "winner_player_id": _RED,
        "duration_ticks": 42,
        "vp_totals": {},  # symmetric arena has no VP
        "vp_margin": 0,
        "objectives": {},  # ZERO objectives
        "total_control_changes": 0,
        "failed_completions": 0,
        "replay_validity": {_RED: 1, _BLUE: 1},
    }
    base.update(over)
    return base


def test_objective_metrics_on_no_awards_is_empty_not_crashing() -> None:
    assert _objective_metrics([]) == {}


def test_summarize_tolerates_zero_objectives_and_still_computes_core_stats() -> None:
    """No objectives => objective aggregation is empty, but keep/terminal/winner hold."""
    rows = [
        _row(winner_player_id=_RED),
        _row(winner_player_id=_BLUE, terminal_class="elimination"),
        _row(
            is_draw=True,
            winner_player_id=None,
            terminal_class="tick_cap",
            end_reason="draw_max_ticks",
            victory_kind=None,
        ),
    ]
    summary = _summarize(rows, gate_threshold=0.95)

    # Objective/VP scorecard collapsed to zero, no crash.
    assert summary["objectives"] == {}
    assert summary["matches_with_control_change"] == 0
    assert summary["vp_threshold_margins"] == []

    # Keep-rate (play-terminal fraction) + terminal classes still compute.
    assert summary["n"] == 3
    assert summary["terminal_classes"] == {"elimination": 2, "tick_cap": 1}
    assert summary["play_terminal_fraction"] == round(2 / 3, 4)
    assert summary["o_gate_pass"] is False

    # Winner + brawler stats still compute.
    assert summary["winners"] == {_RED: 1, _BLUE: 1, "draw": 1}
    assert summary["brawler"]["wins"] == 1
    assert summary["brawler"]["win_rate_all"] == round(1 / 3, 4)
    assert summary["duration_ticks"]["max"] == 42


def test_terminal_class_still_classifies_without_objectives() -> None:
    # Symmetric arena never emits vp_threshold; elimination + clock still classify.
    assert _terminal_class("last_mech_standing", "last_mech_standing") == "elimination"
    assert _terminal_class("draw_max_ticks", None) == "tick_cap"
    assert _terminal_class(None, "tick_cap_failsafe") == "tick_cap"
