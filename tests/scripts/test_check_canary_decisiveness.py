"""OMN-15488 leg (a) §6.3 — the canary decisiveness gate must actually decide.

§6.3 exists because leg (a) flies a pairing nobody has ever flown: a
sniper-vs-sniper mirror of two long-range ironclads, under an evaluator that
promotes ONLY on a decisive learning-seat win. If that regime is
stalemate-dominated, the promote budget is exhausted and the §6.1 NO-PROMOTION
escape lands after ~5.5 hours of exclusive endpoint occupancy. A two-match
canary bounds that discovery to about twenty minutes -- but only if something
CHECKS it, and clause 3 (at least one decisive termination) had no checker
anywhere in the tree.

Every test below names the launch this gate must forbid.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.check_canary_decisiveness import (
    DECISIVE_END_REASONS,
    evaluate,
    main,
)

_OVERLAY = (
    Path(__file__).resolve().parents[2]
    / "contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml"
)


def _row(
    *,
    seed: int,
    end_reason: str = "last_mech_standing",
    replay_validity: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "phase": "baseline",
        "seed": seed,
        "match_id": f"match-{seed}",
        "end_reason": end_reason,
        "is_draw": end_reason.startswith("draw_"),
        "winner_player_id": None if end_reason.startswith("draw_") else "player.blue",
        "replay_validity": replay_validity or {"player.blue": 1, "player.red": 1},
    }


def _write_lane(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    providers: tuple[str, ...] = ("qwen35", "qwen35_sniper_mirror_red"),
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "battery_raw.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    connection = sqlite3.connect(root / "events.sqlite3")
    try:
        connection.execute(
            "CREATE TABLE events (match_id TEXT, event_type TEXT, payload_json TEXT, "
            "emitted_at TEXT)"
        )
        for index, provider_id in enumerate(providers):
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (
                    f"match-{index}",
                    "llm_completion_resolved",
                    json.dumps({"provider_id": provider_id}),
                    "2026-07-31T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return root


def _verdicts(root: Path) -> dict[str, bool]:
    return {result.name: result.passed for result in evaluate(root, _OVERLAY, expected_rows=2)}


@pytest.mark.unit
def test_a_clean_canary_passes_every_clause(tmp_path: Path) -> None:
    root = _write_lane(
        tmp_path / "canary",
        [_row(seed=9101), _row(seed=9102, end_reason="draw_max_ticks")],
    )
    assert all(_verdicts(root).values())
    assert main(["--state-root", str(root), "--overlay", str(_OVERLAY)]) == 0


@pytest.mark.unit
def test_a_stalemate_only_canary_blocks_the_launch(tmp_path: Path) -> None:
    """THE clause this gate was built for. Both matches at the tick bound means
    the sniper mirror is stalemate-dominated at this arena/loadout: the battery
    is NOT launched, and the outcome is an execution-infrastructure finding,
    not a hypothesis result."""
    root = _write_lane(
        tmp_path / "canary",
        [
            _row(seed=9101, end_reason="draw_max_ticks"),
            _row(seed=9102, end_reason="draw_max_ticks"),
        ],
    )
    verdicts = _verdicts(root)
    assert verdicts["clause-3-decisiveness"] is False
    assert verdicts["clause-1-replay-validity"] is True
    assert main(["--state-root", str(root), "--overlay", str(_OVERLAY)]) == 1


@pytest.mark.unit
def test_a_mutual_destruction_draw_is_not_decisive(tmp_path: Path) -> None:
    """A tick-bound draw and a mutual-destruction draw are both draws; neither
    is a learning-seat win, so neither can promote."""
    root = _write_lane(
        tmp_path / "canary",
        [
            _row(seed=9101, end_reason="draw_mutual_destruction"),
            _row(seed=9102, end_reason="draw_max_ticks"),
        ],
    )
    assert _verdicts(root)["clause-3-decisiveness"] is False


@pytest.mark.unit
@pytest.mark.parametrize("end_reason", sorted(DECISIVE_END_REASONS))
def test_each_decisive_terminal_satisfies_clause_three(tmp_path: Path, end_reason: str) -> None:
    root = _write_lane(
        tmp_path / f"canary-{end_reason}",
        [_row(seed=9101, end_reason=end_reason), _row(seed=9102, end_reason="draw_max_ticks")],
    )
    assert _verdicts(root)["clause-3-decisiveness"] is True


@pytest.mark.unit
def test_an_aborted_run_is_not_counted_as_decisive(tmp_path: Path) -> None:
    """``aborted`` / ``provider_semantic_failure`` are infrastructure
    terminals, never gameplay outcomes -- counting them would let a broken
    provider look like a healthy mirror."""
    for reason in ("aborted", "aborted_runaway", "provider_semantic_failure"):
        root = _write_lane(
            tmp_path / f"canary-{reason}",
            [_row(seed=9101, end_reason=reason), _row(seed=9102, end_reason=reason)],
        )
        assert _verdicts(root)["clause-3-decisiveness"] is False, reason


@pytest.mark.unit
def test_an_invalid_replay_blocks_the_launch(tmp_path: Path) -> None:
    root = _write_lane(
        tmp_path / "canary",
        [
            _row(seed=9101, replay_validity={"player.blue": 1, "player.red": 0}),
            _row(seed=9102),
        ],
    )
    assert _verdicts(root)["clause-1-replay-validity"] is False


@pytest.mark.unit
def test_a_short_canary_blocks_the_launch(tmp_path: Path) -> None:
    root = _write_lane(tmp_path / "canary", [_row(seed=9101)])
    assert _verdicts(root)["clause-1-replay-validity"] is False


@pytest.mark.unit
def test_an_undeclared_provider_blocks_the_launch(tmp_path: Path) -> None:
    """Clause 2: the canary must have run on the overlay it claims to have run
    on. A stray provider means the lane is not the pre-registered one."""
    root = _write_lane(
        tmp_path / "canary",
        [_row(seed=9101), _row(seed=9102)],
        providers=("qwen35", "some-other-backend"),
    )
    assert _verdicts(root)["clause-2-providers"] is False


@pytest.mark.unit
def test_missing_evidence_fails_closed_rather_than_passing(tmp_path: Path) -> None:
    """No raw file at all: the gate must never report OK on absent evidence."""
    empty = tmp_path / "nothing"
    empty.mkdir()
    results = evaluate(empty, _OVERLAY, expected_rows=2)
    assert results and not any(result.passed for result in results)
    assert main(["--state-root", str(empty), "--overlay", str(_OVERLAY)]) == 1


@pytest.mark.unit
def test_a_missing_ledger_fails_only_the_provider_clause_and_still_blocks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "canary"
    root.mkdir()
    (root / "battery_raw.jsonl").write_text(
        json.dumps(_row(seed=9101)) + "\n" + json.dumps(_row(seed=9102)) + "\n",
        encoding="utf-8",
    )
    verdicts = _verdicts(root)
    assert verdicts["clause-2-providers"] is False
    assert verdicts["clause-3-decisiveness"] is True
    assert main(["--state-root", str(root), "--overlay", str(_OVERLAY)]) == 1
