"""Shared single-duel invocation helper.

Extracted from ``cli/balance.py::_run_duel`` (tunable-pilots Task 6) in
learning Phase 2 Task 2, per Architectural Decision #1: the balance harness's
match-invocation machinery landed CLI-private, so it is EXTRACTED here —
never duplicated — and both the ``so balance`` round-robin sweep and the
learning loop's ``DuelEvaluator`` invoke this one helper.

Determinism: a duel's outcome is a pure function of
``(seed, loadouts, max_ticks, geometry)`` (MatchRunner contract). The
``match_id`` is attribution metadata only — it names ledger rows but never
feeds the RNG.
"""

from __future__ import annotations

from pathlib import Path

import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import ARENA_SIZE_CELLS, MatchRunner
from steel_onslaught.match.state import ModelSOMatchState
from steel_onslaught.pilots.schemas import ModelSOPosition

# Standard duel geometry — identical to the Task 34 ``run_match`` entrypoint.
DUEL_SPAWN_A = ModelSOPosition(x=5, y=5)
DUEL_SPAWN_B = ModelSOPosition(x=35, y=35)  # Chebyshev 30 apart on a 40x40 grid


def run_duel(
    *,
    loadout_a: ModelSOLoadout,
    loadout_b: ModelSOLoadout,
    seed: int,
    max_ticks: int,
    catalog: MatchContractCatalog,
    registry: PilotSpecRegistry,
    ledger_path: Path,
    match_id: str | None = None,
    loadout_dir_a: Path | None = None,
    loadout_dir_b: Path | None = None,
    side_a: str = "a",
    side_b: str = "b",
) -> ModelSOMatchState:
    """Run one deterministic seeded duel against the ledger at *ledger_path*.

    Every event lands in the SQLite ledger at *ledger_path* (appended; the
    file is shared across duels safely because each duel's ``match_id`` is
    unique). *loadout_dir_a*/*loadout_dir_b* are required whenever the
    corresponding loadout carries a relative ``pilot_spec_path`` (registry
    resolution step 1). Returns the final match state; ``winner_id`` is
    ``player.<side>`` for a decisive ending and ``None`` on a draw.
    """
    bus = InProcessEventBus()
    ledger = SQLiteLedger(ledger_path)
    bus.subscribe(ledger.append)
    runner = MatchRunner(
        match_id=match_id if match_id is not None else f"match.{ulid.new().str}",
        seed=seed,
        loadout_a=loadout_a,
        loadout_b=loadout_b,
        bus=bus,
        max_ticks=max_ticks,
        catalog=catalog,
        pilot_registry=registry,
        loadout_dir_a=loadout_dir_a,
        loadout_dir_b=loadout_dir_b,
        side_a=side_a,
        side_b=side_b,
        spawn_a=DUEL_SPAWN_A,
        spawn_b=DUEL_SPAWN_B,
        arena_size=ARENA_SIZE_CELLS,
    )
    return runner.run()
