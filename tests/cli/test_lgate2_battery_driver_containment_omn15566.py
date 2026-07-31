"""Per-seed containment for the L-GATE-2 battery driver (OMN-15566).

The 2026-07-30 OMN-15488 battery crashed at baseline seed 4028 after 27 clean
rows: a delegation-node quality-gate rejection propagated out of
``_measure_match`` with no per-seed containment anywhere in this driver's
``_run_phase`` (battery mode) or ``_one`` (live-fire mode) loops, killing the
whole process instead of recording a loud casualty and continuing -- the
exact contamination-safety contract every other battery driver in this
program already carries (``run_ogate_objectives_battery.py``'s 2026-07-24
R2/2026-07-25 SO-COMP-CA fix, ``run_display_salience_battery.py``'s OMN-15171
port of the same contract).

RED-first: ``test_dead_seed_in_baseline_phase_crashes_the_whole_process_pre_fix``
proves the pre-fix shape (an unhandled exception propagates out of ``main()``)
would fail on this repo's own current ``main`` -- the fix converts that crash
into a contained, loudly-reported casualty (the remaining tests below).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.run_lgate2_adaptation_battery import main

pytestmark = pytest.mark.unit

_PRE_PROMOTION_PROVENANCE: dict[str, Any] = {
    "policy_id": "policy.genesis",
    "generation": 0,
    "spec_hash": "genesis_hash",
    "source_lineage_digest": "genesis_digest",
}
_PROMOTED_PROVENANCE: dict[str, Any] = {
    "policy_id": "policy.promoted",
    "generation": 1,
    "spec_hash": "promoted_hash",
    "source_lineage_digest": "promoted_digest",
}
_PROMOTION_EVENT: dict[str, Any] = {**_PROMOTED_PROVENANCE, "archetype": "aggressive"}


def _fake_row(seed: int, *, phase: str, promoted: dict[str, Any] | None = None) -> dict[str, Any]:
    """A minimal, always-passing row shaped exactly like ``_measure_match``'s return."""
    provenance = _PROMOTED_PROVENANCE if phase == "post" else _PRE_PROMOTION_PROVENANCE
    return {
        "phase": phase,
        "seed": seed,
        "match_id": f"match.fixture.{seed}",
        "policy_provenance": provenance,
        "winner_player_id": "player.red",
        "is_draw": False,
        "end_reason": "last_mech_standing",
        "duration_ticks": 10,
        "replay_validity": {"player.red": 1, "player.blue": 1},
        "learning_seat": {
            "seat": "red",
            "dealt": {},
            "planned": {},
            "keep_rates": {},
            "planned_share": {},
        },
        "failed_completions": 0,
        "empty_content_completions": {},
        "policy_promoted": promoted,
    }


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dead_seed: int | None = None,
    dead_seed_exc: Exception | None = None,
    promote_on_seed: int | None = 4101,
) -> None:
    def _fake_measure_match(
        overlay: object,
        *,
        red_loadout_path: Path,
        blue_loadout_path: Path,
        seed: int,
        phase: str,
        learning_player: str,
        learning_seat: str,
        learning_mech: str,
    ) -> dict[str, Any]:
        if seed == dead_seed:
            raise dead_seed_exc or RuntimeError(
                "simulated MALFORMED quality-gate rejection: response is not valid JSON"
            )
        promoted = _PROMOTION_EVENT if seed == promote_on_seed else None
        return _fake_row(seed, phase=phase, promoted=promoted)

    monkeypatch.setattr("scripts.run_lgate2_adaptation_battery._measure_match", _fake_measure_match)
    monkeypatch.setattr(
        "scripts.run_lgate2_adaptation_battery._lane_overlay",
        lambda state_root, *, overlay_path, max_value, learning_player, step, genesis=1.0: object(),
    )
    monkeypatch.setattr(
        "scripts.run_lgate2_adaptation_battery._live_fire_overlay",
        lambda state_root, *, learning_player, args: object(),
    )


def _argv(*, n: int, promote_attempts: int, state_root: Path) -> list[str]:
    return [
        "run_lgate2_adaptation_battery.py",
        "--seat",
        "red",
        "--n",
        str(n),
        "--promote-attempts",
        str(promote_attempts),
        "--state-root",
        str(state_root),
        "--fresh",
    ]


def test_dead_seed_in_baseline_phase_is_contained_not_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RED on pre-fix main (raises RuntimeError, uncaught); GREEN post-fix:
    the battery completes, the dead seed is recorded as a casualty (never a
    row), the remaining baseline seeds still run, and later phases proceed
    normally through to a real promotion and post-phase confirmation."""
    dead_seed = 4002
    _install_fakes(monkeypatch, dead_seed=dead_seed)
    monkeypatch.setattr(sys, "argv", _argv(n=3, promote_attempts=2, state_root=tmp_path))

    exit_code = main()

    # A casualty occurred -- the process must force-fail even though every
    # phase that DID run completed and promoted cleanly.
    assert exit_code != 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    # 2 of 3 requested baseline seeds produced a row; the dead seed did not.
    assert summary["baseline"]["matches"] == 2
    assert summary["baseline"]["skipped_seeds"] == [
        {
            "phase": "baseline",
            "seed": dead_seed,
            "error": "RuntimeError: simulated MALFORMED quality-gate rejection: response is "
            "not valid JSON",
        }
    ]
    # Promote/post phases are unaffected -- the run-wide list names exactly
    # the one casualty, scoped to its own phase.
    assert summary["promote"]["skipped_seeds"] == []
    assert summary["post"]["skipped_seeds"] == []
    assert summary["skipped_seeds"] == summary["baseline"]["skipped_seeds"]
    # The promotion chain still completed -- containment must not weaken the
    # phase/provenance assertions, which stay hard failures untouched by this
    # fix (baseline-must-never-promote, post-must-fly-the-promoted-policy).
    assert summary["promotion"]["policy_id"] == "policy.promoted"
    assert summary["post"]["matches"] == 3

    raw_lines = (tmp_path / "battery_raw.jsonl").read_text(encoding="utf-8").splitlines()
    recorded_seeds = {json.loads(line)["seed"] for line in raw_lines}
    assert dead_seed not in recorded_seeds

    skipped_sibling = json.loads(
        (tmp_path / "skipped_seeds.jsonl").read_text(encoding="utf-8").strip()
    )
    assert skipped_sibling["seed"] == dead_seed


def test_dead_seed_carries_structured_transport_fields_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A casualty raised as ``LlmTransportError`` (argv/exit_code/stderr/stdout,
    OMN-15240/OMN-15535) must surface those structured fields verbatim in the
    persisted record -- not just the flattened message."""
    from steel_onslaught.llm.schemas import LlmTransportError

    dead_seed = 4002
    argv = ("uv", "run", "--project", "/fake/omnibase_infra", "onex", "node", "fake")
    stdout = json.dumps(
        {"result": {"terminal_payload": {"quality_gates_failed": ["MALFORMED: bad json"]}}}
    )
    dead_seed_exc = LlmTransportError(
        "onex delegation CLI exited 1: (quality gate rejection)",
        retryable=False,
        argv=argv,
        exit_code=1,
        stderr="uv warning preamble",
        stdout=stdout,
    )
    _install_fakes(monkeypatch, dead_seed=dead_seed, dead_seed_exc=dead_seed_exc)
    monkeypatch.setattr(sys, "argv", _argv(n=3, promote_attempts=2, state_root=tmp_path))

    main()

    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    (record,) = summary["skipped_seeds"]
    assert record["argv"] == list(argv)
    assert record["exit_code"] == 1
    assert record["stderr"] == "uv warning preamble"
    assert "MALFORMED" in record["stdout"]


def test_clean_battery_has_no_casualties_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control case: no dead seed at all -- unchanged behavior, exit 0."""
    _install_fakes(monkeypatch)
    monkeypatch.setattr(sys, "argv", _argv(n=2, promote_attempts=1, state_root=tmp_path))

    exit_code = main()

    assert exit_code == 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    assert summary["skipped_seeds"] == []
    assert summary["baseline"]["skipped_seeds"] == []
    assert not (tmp_path / "skipped_seeds.jsonl").exists()


# --- OMN-15566 r5b: AssertionError is excluded from containment ---
#
# The r5 adversarial verifier's finding 3: the per-seed ``except Exception``
# in both ``_run_phase`` (battery mode) and ``_one`` (live-fire mode) also
# swallowed ``_measure_match``'s own in-match integrity asserts ("learning
# lane must record provenance", "match did not score") -- a broken
# instrumentation/harness bug silently relabeled as a routine "casualty"
# instead of aborting hard. ``except AssertionError: raise`` now runs BEFORE
# the generic containment arm at both call sites.


def _live_fire_argv(*, lf_matches: int, state_root: Path) -> list[str]:
    return [
        "run_lgate2_adaptation_battery.py",
        "--mode",
        "live-fire",
        "--seat",
        "red",
        "--lf-matches",
        str(lf_matches),
        "--state-root",
        str(state_root),
        "--fresh",
    ]


def test_assertion_error_in_battery_phase_is_fatal_not_contained(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RED on pre-fix main: an ``AssertionError`` from ``_measure_match``
    (e.g. "learning lane must record provenance") would previously be
    silently contained as a casualty and the battery would complete
    normally. Post-fix it must propagate out of ``main()`` uncaught -- an
    invariant violation is a hard failure, not a recoverable per-seed
    casualty."""
    dead_seed = 4002
    _install_fakes(
        monkeypatch,
        dead_seed=dead_seed,
        dead_seed_exc=AssertionError("learning lane must record provenance"),
    )
    monkeypatch.setattr(sys, "argv", _argv(n=3, promote_attempts=2, state_root=tmp_path))

    with pytest.raises(AssertionError, match="learning lane must record provenance"):
        main()

    # The process aborted before ever reaching the summary write -- no
    # casualty record, no completed run.
    assert not (tmp_path / "battery_summary.json").exists()
    assert not (tmp_path / "skipped_seeds.jsonl").exists()


def test_assertion_error_in_live_fire_is_fatal_not_contained(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live-fire mode's ``_one`` carries the identical exclusion -- an
    ``AssertionError`` from ``_measure_match`` must abort ``main()``
    uncaught, not be recorded as a contained casualty."""
    dead_seed = 4302  # second live-fire match (4300 + index, index=2)
    _install_fakes(
        monkeypatch,
        dead_seed=dead_seed,
        dead_seed_exc=AssertionError("match did not score"),
        promote_on_seed=None,
    )
    monkeypatch.setattr(sys, "argv", _live_fire_argv(lf_matches=4, state_root=tmp_path))

    with pytest.raises(AssertionError, match="match did not score"):
        main()

    assert not (tmp_path / "live_fire_summary.json").exists()
    assert not (tmp_path / "skipped_seeds.jsonl").exists()


def test_dead_seed_still_contained_alongside_the_assertion_error_exclusion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Negative control for the exclusion above: a NON-assertion casualty
    (``LlmTransportError``, the real OMN-15488 failure class) must still be
    contained exactly as before -- the exclusion narrows containment to one
    exception type, it does not remove containment."""
    from steel_onslaught.llm.schemas import LlmTransportError

    dead_seed = 4002
    dead_seed_exc = LlmTransportError(
        "onex delegation CLI exited 1: (quality gate rejection)",
        retryable=False,
        argv=("uv", "run", "onex", "node", "node_delegate_skill_orchestrator"),
        exit_code=1,
        stderr="",
        stdout="",
    )
    _install_fakes(monkeypatch, dead_seed=dead_seed, dead_seed_exc=dead_seed_exc)
    monkeypatch.setattr(sys, "argv", _argv(n=3, promote_attempts=2, state_root=tmp_path))

    exit_code = main()

    assert exit_code != 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    (record,) = summary["skipped_seeds"]
    assert record["seed"] == dead_seed
