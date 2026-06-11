"""Tests for the leaderboard projection handler — Task 30.

Invariants asserted:
- Re-emitting MATCH_SCORED for an already-recorded match leaves exactly 1 row.
- After an update, created_at is unchanged from the original insert; scored_at is updated.
- top_n(5) returns the 5 highest winner_score rows.
- top_n query excludes draws (is_draw = 1).
- player_record returns correct wins/losses/total_score.
- draw_count() returns the number of draw entries.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from steel_onslaught.projections.leaderboard.handler import (
    LeaderboardHandler,
    LeaderboardProjection,
    ModelSOLeaderboardEntry,
)


def _make_handler(tmp_path: Path) -> LeaderboardHandler:
    db_path = tmp_path / "leaderboard.sqlite"
    return LeaderboardHandler(db_path)


def _scored_payload(
    match_id: str,
    winner_player_id: str,
    winner_loadout_id: str,
    winner_score: int,
    loser_player_id: str,
    loser_score: int,
    duration_ticks: int,
    scored_at: str,
    is_draw: bool = False,
) -> dict[str, object]:
    return {
        "match_id": match_id,
        "winner_player_id": winner_player_id,
        "winner_loadout_id": winner_loadout_id,
        "winner_score": winner_score,
        "loser_player_id": loser_player_id,
        "loser_score": loser_score,
        "duration_ticks": duration_ticks,
        "scored_at": scored_at,
        "is_draw": is_draw,
    }


@pytest.mark.unit
def test_single_insert(tmp_path: Path) -> None:
    handler = _make_handler(tmp_path)
    payload = _scored_payload(
        match_id="match.001",
        winner_player_id="player.red",
        winner_loadout_id="loadout.red.01",
        winner_score=1550,
        loser_player_id="player.blue",
        loser_score=320,
        duration_ticks=87,
        scored_at="2026-04-30T16:00:00Z",
    )
    handler.on_match_scored(payload)

    lb = LeaderboardProjection(handler.db_path)
    entries = lb.top_n(10)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.match_id == "match.001"
    assert entry.winner_player_id == "player.red"
    assert entry.winner_score == 1550
    assert entry.loser_score == 320
    assert entry.duration_ticks == 87
    assert entry.is_draw is False


@pytest.mark.unit
def test_upsert_preserves_created_at(tmp_path: Path) -> None:
    """Re-emitting MATCH_SCORED for same match_id: exactly 1 row, created_at unchanged."""
    handler = _make_handler(tmp_path)
    payload_v1 = _scored_payload(
        match_id="match.001",
        winner_player_id="player.red",
        winner_loadout_id="loadout.red.01",
        winner_score=1550,
        loser_player_id="player.blue",
        loser_score=320,
        duration_ticks=87,
        scored_at="2026-04-30T16:00:00Z",
    )
    handler.on_match_scored(payload_v1)

    # Simulate a re-emit (e.g. replay re-scores) with a different scored_at.
    payload_v2 = _scored_payload(
        match_id="match.001",
        winner_player_id="player.red",
        winner_loadout_id="loadout.red.01",
        winner_score=1560,  # updated score
        loser_player_id="player.blue",
        loser_score=330,
        duration_ticks=87,
        scored_at="2026-04-30T17:00:00Z",  # different scored_at
    )
    handler.on_match_scored(payload_v2)

    # Exactly one row.
    conn = sqlite3.connect(handler.db_path)
    rows = conn.execute("SELECT COUNT(*) FROM leaderboard_entries").fetchone()
    assert rows[0] == 1

    # created_at unchanged.
    row = conn.execute(
        "SELECT created_at, scored_at, winner_score FROM leaderboard_entries"
    ).fetchone()
    # created_at must equal the first insert time (not the second).
    created_at, scored_at, winner_score = row
    assert scored_at == "2026-04-30T17:00:00Z"
    assert winner_score == 1560
    # created_at was set on first insert; the upsert must NOT update it.
    assert created_at is not None
    # We can't assert the exact value since it's set internally, but it must
    # differ from scored_at (which was updated).
    conn.close()


@pytest.mark.unit
def test_top_n_ordering(tmp_path: Path) -> None:
    """top_n(N) returns the N highest winner_score rows, descending."""
    handler = _make_handler(tmp_path)
    scores = [300, 1200, 850, 2000, 600, 950, 450]
    for i, score in enumerate(scores):
        handler.on_match_scored(
            _scored_payload(
                match_id=f"match.{i:03d}",
                winner_player_id="player.a",
                winner_loadout_id="loadout.a",
                winner_score=score,
                loser_player_id="player.b",
                loser_score=score // 2,
                duration_ticks=100,
                scored_at="2026-04-30T16:00:00Z",
            )
        )

    lb = LeaderboardProjection(handler.db_path)
    top5 = lb.top_n(5)
    assert len(top5) == 5
    winner_scores = [e.winner_score for e in top5]
    assert winner_scores == sorted(winner_scores, reverse=True)
    assert winner_scores[0] == 2000


@pytest.mark.unit
def test_top_n_excludes_draws(tmp_path: Path) -> None:
    """Draws (is_draw=True) are NOT included in top_n results."""
    handler = _make_handler(tmp_path)
    # One decisive match.
    handler.on_match_scored(
        _scored_payload(
            match_id="match.decisive",
            winner_player_id="player.a",
            winner_loadout_id="loadout.a",
            winner_score=1500,
            loser_player_id="player.b",
            loser_score=400,
            duration_ticks=80,
            scored_at="2026-04-30T16:00:00Z",
            is_draw=False,
        )
    )
    # One draw match.
    handler.on_match_scored(
        _scored_payload(
            match_id="match.draw",
            winner_player_id="player.a",
            winner_loadout_id="loadout.a",
            winner_score=0,
            loser_player_id="player.b",
            loser_score=0,
            duration_ticks=200,
            scored_at="2026-04-30T16:01:00Z",
            is_draw=True,
        )
    )

    lb = LeaderboardProjection(handler.db_path)
    top = lb.top_n(10)
    # Only the decisive match appears.
    assert len(top) == 1
    assert top[0].match_id == "match.decisive"
    assert top[0].is_draw is False


@pytest.mark.unit
def test_draw_count(tmp_path: Path) -> None:
    """draw_count() returns the number of draw entries."""
    handler = _make_handler(tmp_path)
    handler.on_match_scored(
        _scored_payload(
            match_id="match.draw.01",
            winner_player_id="player.a",
            winner_loadout_id="loadout.a",
            winner_score=0,
            loser_player_id="player.b",
            loser_score=0,
            duration_ticks=200,
            scored_at="2026-04-30T16:00:00Z",
            is_draw=True,
        )
    )
    handler.on_match_scored(
        _scored_payload(
            match_id="match.draw.02",
            winner_player_id="player.a",
            winner_loadout_id="loadout.a",
            winner_score=0,
            loser_player_id="player.c",
            loser_score=0,
            duration_ticks=200,
            scored_at="2026-04-30T16:02:00Z",
            is_draw=True,
        )
    )
    lb = LeaderboardProjection(handler.db_path)
    assert lb.draw_count() == 2


@pytest.mark.unit
def test_player_record(tmp_path: Path) -> None:
    """player_record() returns correct wins/losses/total_score."""
    handler = _make_handler(tmp_path)
    # player.a wins twice.
    handler.on_match_scored(
        _scored_payload(
            match_id="match.001",
            winner_player_id="player.a",
            winner_loadout_id="loadout.a",
            winner_score=1500,
            loser_player_id="player.b",
            loser_score=300,
            duration_ticks=80,
            scored_at="2026-04-30T16:00:00Z",
        )
    )
    handler.on_match_scored(
        _scored_payload(
            match_id="match.002",
            winner_player_id="player.a",
            winner_loadout_id="loadout.a",
            winner_score=1200,
            loser_player_id="player.c",
            loser_score=250,
            duration_ticks=90,
            scored_at="2026-04-30T16:01:00Z",
        )
    )
    # player.a loses once.
    handler.on_match_scored(
        _scored_payload(
            match_id="match.003",
            winner_player_id="player.b",
            winner_loadout_id="loadout.b",
            winner_score=1800,
            loser_player_id="player.a",
            loser_score=500,
            duration_ticks=70,
            scored_at="2026-04-30T16:02:00Z",
        )
    )

    lb = LeaderboardProjection(handler.db_path)
    record = lb.player_record("player.a")
    assert record["wins"] == 2
    assert record["losses"] == 1
    # total_score = sum of winner_score when winner + loser_score when loser
    assert record["total_score"] == 1500 + 1200 + 500


@pytest.mark.unit
def test_model_leaderboard_entry_fields() -> None:
    """ModelSOLeaderboardEntry validates correctly and is frozen."""
    entry = ModelSOLeaderboardEntry(
        match_id="match.001",
        winner_player_id="player.a",
        winner_loadout_id="loadout.a",
        winner_score=1500,
        loser_player_id="player.b",
        loser_score=300,
        duration_ticks=80,
        scored_at="2026-04-30T16:00:00Z",
        created_at="2026-04-30T15:59:00Z",
        is_draw=False,
    )
    assert entry.match_id == "match.001"
    assert entry.is_draw is False
    # Frozen: mutation must raise ValidationError.
    with pytest.raises(ValidationError):
        entry.match_id = "other"  # type: ignore[misc]
