"""Battery driver must exit non-zero when any requested seed lands no row.

2026-07-25 SO-COMP-CA / SO-COMP-R1 finding (independently hit by both arms):
before this change, ``main()`` unconditionally ``return 0``, even when the
per-seed try/except in the battery loop (`run_ogate_objectives_battery.py`)
swallowed an exception and recorded the seed in ``skipped_seeds`` instead of
writing a row to ``battery_raw.jsonl``. The summary correctly force-fails
``o_gate_pass`` in that case, but nothing about the *process exit code*
reflected the shortfall -- a retry loop keyed on exit code (the obvious
pattern; used by SO-COMP-CA's first, discarded run per
``docs/evidence/2026-07-25-composition-ca-only-dmg16-battery.md`` §9) cannot
see the loss and silently proceeds with a shrunken battery. That run landed
26 of 30 rows (4 short) with zero error signal on ``$?``.

This test drives the real ``main()`` entrypoint (not a surrogate) through a
skipped-seed path exactly like the sibling ``test_ogate_objectives_battery_
skip_seeds.py`` fixtures, and asserts the fix: a battery with any skipped
seed exits non-zero. It also pins that a clean battery (no skips) is
untouched -- exit code 0, identical summary shape -- so the fix cannot be
satisfied by breaking the successful-run contract every other consumer
(``o-gate`` scorecards, replay/evidence tooling) depends on.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.run_ogate_objectives_battery import _BLUE, _RED, main

pytestmark = pytest.mark.unit


def _fake_row(seed: int) -> dict[str, Any]:
    return {
        "seed": seed,
        "match_id": f"match.fixture.{seed}",
        "end_reason": "last_mech_standing",
        "victory_kind": "last_mech_standing",
        "terminal_class": "elimination",
        "winner_player_id": _RED,
        "is_draw": False,
        "duration_ticks": 10,
        "vp_totals": {},
        "vp_margin": 0,
        "first_award_tick": None,
        "objectives": {},
        "total_awards": 0,
        "total_control_changes": 0,
        "failed_completions": 0,
        "replay_validity": {_RED: 1, _BLUE: 1},
    }


def _argv(*, n: int, seed_base: int, state_root: Path) -> list[str]:
    return [
        "run_ogate_objectives_battery.py",
        "--n",
        str(n),
        "--seed-base",
        str(seed_base),
        "--state-root",
        str(state_root),
        "--fresh",
    ]


def test_skipped_seed_causes_nonzero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The exact failure mode from the SO-COMP-CA discarded run: one seed
    dies with a transport-adjacent error (``LlmTransportError`` in the real
    fleet, simulated here as any exception the per-seed try/except catches)
    and lands no row -- the process must not report success."""
    seed_base = 5000
    dead_seed = seed_base + 2

    def _fake(
        overlay: object,
        *,
        seed: int,
        max_ticks: int,
        expected_arena_hash: str,
        expected_arena_id: str,
        red_loadout_path: Path,
        blue_loadout_path: Path,
    ) -> dict[str, Any]:
        if seed == dead_seed:
            raise RuntimeError("simulated LlmTransportError: connection reset")
        return _fake_row(seed)

    monkeypatch.setattr("scripts.run_ogate_objectives_battery._run_match", _fake)
    monkeypatch.setattr(sys, "argv", _argv(n=3, seed_base=seed_base, state_root=tmp_path))

    exit_code = main()

    assert exit_code != 0, (
        "a battery that skipped a requested seed must not exit 0 -- a retry "
        "loop keyed on exit code would silently lose the seed, exactly as "
        "happened in the SO-COMP-CA discarded run (docs/evidence/"
        "2026-07-25-composition-ca-only-dmg16-battery.md §9)"
    )


def test_multiple_skipped_seeds_still_causes_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed_base = 5000
    dead_seeds = {seed_base + 1, seed_base + 3}

    def _fake(
        overlay: object,
        *,
        seed: int,
        max_ticks: int,
        expected_arena_hash: str,
        expected_arena_id: str,
        red_loadout_path: Path,
        blue_loadout_path: Path,
    ) -> dict[str, Any]:
        if seed in dead_seeds:
            raise RuntimeError("simulated provider 5xx")
        return _fake_row(seed)

    monkeypatch.setattr("scripts.run_ogate_objectives_battery._run_match", _fake)
    monkeypatch.setattr(sys, "argv", _argv(n=3, seed_base=seed_base, state_root=tmp_path))

    exit_code = main()

    assert exit_code != 0


def test_clean_battery_with_no_skips_still_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression guard: the fix must not make every battery exit non-zero --
    only ones that actually skipped a requested seed."""
    seed_base = 5000

    def _fake(
        overlay: object,
        *,
        seed: int,
        max_ticks: int,
        expected_arena_hash: str,
        expected_arena_id: str,
        red_loadout_path: Path,
        blue_loadout_path: Path,
    ) -> dict[str, Any]:
        return _fake_row(seed)

    monkeypatch.setattr("scripts.run_ogate_objectives_battery._run_match", _fake)
    monkeypatch.setattr(sys, "argv", _argv(n=2, seed_base=seed_base, state_root=tmp_path))

    exit_code = main()

    assert exit_code == 0
