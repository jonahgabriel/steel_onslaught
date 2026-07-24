"""Battery driver survives a dead seed instead of dying with the whole run.

2026-07-24 R2 abort-forensics fix: before this change, one unhandled
``_run_match`` exception (a provider 429/5xx, a transport drop, ...) propagated
out of ``main``'s loop and killed the entire battery process -- the V-IMG
vision arm lost 29 of 30 seeds to a single first-call 429. ``main`` now catches
per-seed and continues, but a shrunken-but-silently-"clean" battery would be
worse than the crash it replaces, so three properties are guarded here:

- a dead seed is skipped, not fatal: the remaining seeds still run and are
  scored;
- the skip is never silent: ``battery_summary.json`` records ``requested_n``
  (what was asked for) distinct from ``n`` (what actually ran), the offending
  seed + error in ``skipped_seeds``, and force-fails ``o_gate_pass`` even when
  the matches that DID run would otherwise have passed the gate;
- ``battery_raw.jsonl`` -- the evidence ledger of matches that actually ran --
  never gets a synthetic row for a seed that never produced one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.run_ogate_objectives_battery import _BLUE, _RED, main

pytestmark = pytest.mark.unit

_DEAD_SEED_OFFSET = 2  # base+2 -> the second seed in the battery


def _fake_row(seed: int) -> dict[str, Any]:
    """A minimal, always-passing row shaped exactly like ``_run_match``'s return."""
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


def _install_fake_run_match(monkeypatch: pytest.MonkeyPatch, *, dead_seed: int) -> None:
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
            raise RuntimeError("simulated provider 429: rate limited")
        return _fake_row(seed)

    monkeypatch.setattr("scripts.run_ogate_objectives_battery._run_match", _fake)


def test_dead_seed_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seed_base = 5000
    dead_seed = seed_base + _DEAD_SEED_OFFSET
    _install_fake_run_match(monkeypatch, dead_seed=dead_seed)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ogate_objectives_battery.py",
            "--n",
            "3",
            "--seed-base",
            str(seed_base),
            "--state-root",
            str(tmp_path),
            "--fresh",
        ],
    )

    exit_code = main()

    assert exit_code == 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    # The two live seeds still ran and scored; only the dead seed is absent.
    assert summary["n"] == 2
    assert summary["requested_n"] == 3


def test_skip_is_recorded_loudly_and_force_fails_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed_base = 5000
    dead_seed = seed_base + _DEAD_SEED_OFFSET
    _install_fake_run_match(monkeypatch, dead_seed=dead_seed)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ogate_objectives_battery.py",
            "--n",
            "3",
            "--seed-base",
            str(seed_base),
            "--state-root",
            str(tmp_path),
            "--fresh",
        ],
    )

    main()

    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    # The two matches that ran are both clean eliminations, so the fraction
    # alone would read 1.0 -- o_gate_pass must still be forced False.
    assert summary["play_terminal_fraction"] == 1.0
    assert summary["o_gate_pass"] is False
    assert summary["skipped_seeds"] == [
        {"seed": str(dead_seed), "error": "RuntimeError: simulated provider 429: rate limited"}
    ]


def test_skipped_seed_never_reaches_the_raw_evidence_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed_base = 5000
    dead_seed = seed_base + _DEAD_SEED_OFFSET
    _install_fake_run_match(monkeypatch, dead_seed=dead_seed)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ogate_objectives_battery.py",
            "--n",
            "3",
            "--seed-base",
            str(seed_base),
            "--state-root",
            str(tmp_path),
            "--fresh",
        ],
    )

    main()

    raw_lines = (tmp_path / "battery_raw.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2
    recorded_seeds = {json.loads(line)["seed"] for line in raw_lines}
    assert dead_seed not in recorded_seeds
    assert recorded_seeds == {seed_base + 1, seed_base + 3}


def test_no_skips_leaves_summary_shape_byte_identical_to_pre_fix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A clean battery (no skips) still gets the two new keys, but o_gate_pass
    is decided purely by the play-terminal fraction, never force-failed."""
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
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ogate_objectives_battery.py",
            "--n",
            "2",
            "--seed-base",
            str(seed_base),
            "--state-root",
            str(tmp_path),
            "--fresh",
        ],
    )

    main()

    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    assert summary["n"] == 2
    assert summary["requested_n"] == 2
    assert summary["skipped_seeds"] == []
    assert summary["o_gate_pass"] is True
