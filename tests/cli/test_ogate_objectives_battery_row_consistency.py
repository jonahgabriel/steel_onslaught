"""Battery row winner/draw self-consistency.

2026-07-24 R2 abort-forensics follow-up: an aborted, zero-plan, tick-1 match
(seed 5028, ``match.01KYAT1XPK61H653M0YBKR2B88``, pair_p4_dmg8 ledger) wrote a
``battery_raw.jsonl`` row with ``is_draw: true`` AND ``winner_player_id:
"player.blue"`` simultaneously -- a silent wrong-number generator, since any
consumer that tallies ``winner_player_id`` across rows the obvious way
(without filtering to ``terminal_class == "elimination"`` first) counts a
draw/abort as a decisive win.

Root cause, verified against the raw ledger events for that match:

- ``MATCH_ENDED`` correctly carries ``winner_id=null``.
- ``MATCH_SCORED``'s flattened ``winner_player_id`` is a required non-null
  ``str`` field by contract (``ModelSOMatchScoredPayload``) and is NOT "who
  won" on its own -- the scoring reducer's documented Task 30 draw convention
  (``reducers/scoring.py::_score``) stamps the alphabetically-first player
  into it even on a draw, because the leaderboard's SQL schema declares the
  column ``NOT NULL`` for its own bucketing purposes. ``is_draw`` (and the
  nested ``winner`` block, which the payload's own validator requires
  ``None`` exactly when ``is_draw``) is the required disambiguator.

The engine is not bugged: the reducer's convention is documented and the
payload's own validator already enforces ``winner=None`` + zero victory
points on a draw. The bug was the battery driver forwarding the reducer's
leaderboard-internal placeholder into its own evidence row uncritically.
``_row_winner_player_id`` fixes that at the row-construction boundary; this
fix applies to rows written from now on and does NOT rewrite any existing
``battery_raw.jsonl`` (those are append-only evidence for merged results).
"""

from __future__ import annotations

import pytest

from scripts.run_ogate_objectives_battery import _row_winner_player_id
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOPlayerScore,
    ModelSOScoredWinner,
)

pytestmark = pytest.mark.unit


def _scored(
    *,
    is_draw: bool,
    winner_player_id: str = "player.blue",
    loser_player_id: str = "player.red",
) -> ModelSOMatchScoredPayload:
    """A minimal MATCH_SCORED payload, seed-5028-shaped when ``is_draw=True``:
    a real winner_player_id/winner_loadout_id/winner_score alongside is_draw
    and a null winner block -- exactly what the reducer's own convention (and
    its validator) allows."""
    return ModelSOMatchScoredPayload(
        match_id="match.fixture",
        winner=None
        if is_draw
        else ModelSOScoredWinner(player_id=winner_player_id, mech_id=f"mech.{winner_player_id}"),
        scores={
            winner_player_id: ModelSOPlayerScore(
                victory=0 if is_draw else 1,
                damage_dealt=0,
                damage_efficiency=0.0,
                pressure_efficiency=1.0,
                overload_penalty=0,
                replay_validity=1,
                final_score=150,
            ),
            loser_player_id: ModelSOPlayerScore(
                victory=0,
                damage_dealt=0,
                damage_efficiency=0.0,
                pressure_efficiency=1.0,
                overload_penalty=0,
                replay_validity=1,
                final_score=150,
            ),
        },
        winner_player_id=winner_player_id,
        winner_loadout_id="loadout.fixture",
        winner_score=150,
        loser_player_id=loser_player_id,
        loser_score=150,
        duration_ticks=1,
        scored_at="2026-07-24T19:36:25.183453+00:00",
        is_draw=is_draw,
    )


def test_draw_row_winner_is_nulled_despite_the_reducers_leaderboard_placeholder() -> None:
    """Reproduces the exact seed-5028 shape: is_draw=True with a real,
    non-null winner_player_id already sitting on the MATCH_SCORED payload."""
    scored = _scored(is_draw=True, winner_player_id="player.blue")
    assert scored.winner_player_id == "player.blue"  # the reducer's placeholder is real
    assert _row_winner_player_id(scored) is None  # the row must not repeat it


def test_decisive_row_keeps_the_real_winner() -> None:
    scored = _scored(is_draw=False, winner_player_id="player.blue")
    assert _row_winner_player_id(scored) == "player.blue"


@pytest.mark.parametrize("is_draw", [True, False])
def test_row_never_carries_both_a_winner_and_a_draw_flag(is_draw: bool) -> None:
    """The actual invariant the battery row must satisfy: is_draw and a
    non-null winner_player_id are mutually exclusive, regardless of what the
    underlying MATCH_SCORED payload's own winner_player_id field says."""
    scored = _scored(is_draw=is_draw)
    row = {"is_draw": scored.is_draw, "winner_player_id": _row_winner_player_id(scored)}

    assert not (row["is_draw"] and row["winner_player_id"] is not None)
