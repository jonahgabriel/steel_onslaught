"""ONEX-style live composition for one Steel Onslaught match.

``assemble_match_live()`` is the single wiring function that composes the
match stack — mirroring omnimarket's ``assemble_live_orchestrator()`` pattern:
construct the in-process bus, then inject it as the protocol-typed dependency
to the runner (which subscribes the canonical fold), the ledger effect, the
scoring reducer, and the leaderboard projection.

The composition makes the subscriber order and the effect/projection seams
explicit and ONEX-faithful, rather than an inline procedural sequence:

  1. Ledger effect (``SQLiteLedger.append``) — every event lands first.
  2. Canonical fold (``MatchStateFold``) — subscribed in ``MatchRunner.__init__``.
  3. Scoring reducer (``ReducerScoring``) — the replay-validity hard gate.
  4. Leaderboard projection (``LeaderboardHandler``) — materializes MATCH_SCORED.

``run_match()`` (the Proof-of-Life entrypoint) delegates to this composition
and drives the runner to termination.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.bus.protocol import EventBus
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.ledger.protocol import EventLedger
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import ARENA_SIZE_CELLS, MatchRunner
from steel_onslaught.pilots.schemas import ModelSOPosition
from steel_onslaught.projections.leaderboard.handler import LeaderboardHandler
from steel_onslaught.reducers.scoring import ReducerScoring, verify_replay_validity


@dataclass(frozen=True)
class LiveMatchStack:
    """The wired match stack returned by ``assemble_match_live``.

    Holds the composition's named parts so callers (the CLI, tests, the
    learning loop) can drive the runner and inspect the ledger/fold without
    re-deriving the wiring.
    """

    match_id: str
    bus: EventBus
    runner: MatchRunner
    ledger: EventLedger
    scoring: ReducerScoring
    leaderboard: LeaderboardHandler


def assemble_match_live(
    *,
    red: ModelSOLoadout,
    blue: ModelSOLoadout,
    red_loadout_dir: Path,
    blue_loadout_dir: Path,
    seed: int,
    max_ticks: int,
    ledger_path: Path,
    leaderboard_path: Path,
    catalog: MatchContractCatalog | None = None,
    pilot_registry: Any = None,
) -> LiveMatchStack:
    """Wire the full match stack and return the named composition parts.

    Subscriber order is fixed and load-bearing:
      ledger (canonical record) → fold (state authority) → scoring (gate) →
      leaderboard (projection). See the module docstring for the rationale.
    """
    # 0. Resolve contracts + registry (load once; the fold and runner share).
    if catalog is None:
        catalog = MatchContractCatalog.load(None)
    if pilot_registry is None:
        from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry

        pilot_registry = PilotSpecRegistry.load(None)

    bus: EventBus = InProcessEventBus()
    # 1. Ledger effect — every event lands in the append-only record first.
    ledger = SQLiteLedger(
        ModelSOSQLiteLedgerConfig(
            path=ledger_path,
            journal_mode="WAL",
            check_same_thread=True,
            transaction_mode="autocommit",
            event_schema="canonical_event_v1",
        )
    )
    bus.subscribe(ledger.append)

    # 2. Canonical fold — MatchRunner subscribes MatchStateFold in __init__.
    match_id = f"match.{ulid.new().str}"
    runner = MatchRunner(
        match_id=match_id,
        seed=seed,
        loadout_a=red,
        loadout_b=blue,
        bus=bus,
        max_ticks=max_ticks,
        catalog=catalog,
        pilot_registry=pilot_registry,
        loadout_dir_a=red_loadout_dir,
        loadout_dir_b=blue_loadout_dir,
        side_a="red",
        side_b="blue",
        spawn_a=ModelSOPosition(x=5, y=5),
        spawn_b=ModelSOPosition(x=35, y=35),  # Chebyshev 30 apart on a 40x40 grid
        arena_size=ARENA_SIZE_CELLS,
    )

    # 3. Scoring reducer — the replay-validity hard gate on the terminal event.
    scoring = ReducerScoring(
        match_id,
        runner._correlation_id,
        emit=bus.publish,
        replay_validity_check=lambda: verify_replay_validity(
            ledger, match_id, runner.fold.state, catalog=catalog
        ),
    )
    bus.subscribe(scoring.handle)

    # 4. Leaderboard projection — materializes the full MATCH_SCORED payload.
    leaderboard = LeaderboardHandler(leaderboard_path)

    def _on_match_scored(event: ModelSOEventEnvelope) -> None:
        # The lifecycle reducer emits a skinny draw-backstop MATCH_SCORED;
        # only the scoring reducer's full payload feeds the leaderboard.
        if event.payload.get("kind") == "steel_onslaught.match_scored":
            leaderboard.on_match_scored(event.payload)

    bus.subscribe(_on_match_scored, event_types=[SOEventType.MATCH_SCORED])

    return LiveMatchStack(
        match_id=match_id,
        bus=bus,
        runner=runner,
        ledger=ledger,
        scoring=scoring,
        leaderboard=leaderboard,
    )
