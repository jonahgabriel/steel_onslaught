"""Leaderboard projection handler — Task 30.

Subscribes to ``MATCH_SCORED`` events and upserts a row into the
``leaderboard_entries`` SQLite table (``ledger/leaderboard.sqlite``).

The ``created_at`` column records the first-write timestamp and is
intentionally NOT updated on subsequent upserts — it records when the
match was first scored, not when it was re-scored.

``is_draw`` disambiguates draw entries from decisive wins: draws are stored
but excluded from ``top_n`` rankings.

The injected repository owns both materialization and query methods.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from steel_onslaught.events.factory import Clock
from steel_onslaught.events.payloads import ModelSOMatchScoredPayload
from steel_onslaught.projections.leaderboard.protocol import ModelSOLeaderboardEntry


class ModelSOSQLiteLeaderboardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path
    journal_mode: Literal["WAL"]
    check_same_thread: bool
    transaction_mode: Literal["autocommit"]
    storage_schema: Literal["leaderboard_v1"]


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS leaderboard_entries (
    match_id          TEXT PRIMARY KEY,
    winner_player_id  TEXT NOT NULL,
    winner_loadout_id TEXT NOT NULL,
    winner_score      INTEGER NOT NULL,
    loser_player_id   TEXT NOT NULL,
    loser_score       INTEGER NOT NULL,
    duration_ticks    INTEGER NOT NULL,
    scored_at         TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    is_draw           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leaderboard_winner
    ON leaderboard_entries(winner_player_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_score
    ON leaderboard_entries(winner_score DESC);
"""

_UPSERT_SQL = """
INSERT INTO leaderboard_entries
  (match_id, winner_player_id, winner_loadout_id, winner_score,
   loser_player_id, loser_score, duration_ticks, scored_at, created_at,
   is_draw)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(match_id) DO UPDATE SET
  winner_player_id  = excluded.winner_player_id,
  winner_loadout_id = excluded.winner_loadout_id,
  winner_score      = excluded.winner_score,
  loser_player_id   = excluded.loser_player_id,
  loser_score       = excluded.loser_score,
  duration_ticks    = excluded.duration_ticks,
  scored_at         = excluded.scored_at,
  is_draw           = excluded.is_draw
  -- created_at intentionally NOT updated
"""

_TOP_N_SQL = """
SELECT match_id, winner_player_id, winner_loadout_id, winner_score,
       loser_player_id, loser_score, duration_ticks, scored_at,
       created_at, is_draw
  FROM leaderboard_entries
 WHERE is_draw = 0
 ORDER BY winner_score DESC
 LIMIT ?
"""

_PLAYER_WINS_SQL = """
SELECT COALESCE(SUM(winner_score), 0)
  FROM leaderboard_entries
 WHERE winner_player_id = ?
   AND is_draw = 0
"""

_PLAYER_LOSSES_SQL = """
SELECT COALESCE(SUM(loser_score), 0)
  FROM leaderboard_entries
 WHERE loser_player_id = ?
   AND is_draw = 0
"""

_PLAYER_WIN_COUNT_SQL = """
SELECT COUNT(*)
  FROM leaderboard_entries
 WHERE winner_player_id = ?
   AND is_draw = 0
"""

_PLAYER_LOSS_COUNT_SQL = """
SELECT COUNT(*)
  FROM leaderboard_entries
 WHERE loser_player_id = ?
   AND is_draw = 0
"""

_DRAW_COUNT_SQL = """
SELECT COUNT(*)
  FROM leaderboard_entries
 WHERE is_draw = 1
"""


# ---------------------------------------------------------------------------
# Handler (write path)
# ---------------------------------------------------------------------------


class LeaderboardHandler:
    """Subscribes to MATCH_SCORED payloads and upserts leaderboard rows.

    Pass this instance's ``on_match_scored`` to the EventBus subscriber,
    filtering on ``SOEventType.MATCH_SCORED``.
    """

    def __init__(self, config: ModelSOSQLiteLeaderboardConfig, *, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._conn = sqlite3.connect(
            config.path,
            check_same_thread=config.check_same_thread,
            isolation_level={"autocommit": None}[config.transaction_mode],
        )
        try:
            if self._conn.isolation_level is not None:
                raise RuntimeError("leaderboard SQLite connection did not apply autocommit policy")
            row = self._conn.execute(f"PRAGMA journal_mode={config.journal_mode}").fetchone()
            if row is None or str(row[0]).upper() != config.journal_mode:
                raise RuntimeError(
                    f"SQLite refused required journal mode {config.journal_mode!r}: {row!r}"
                )
            schema_sql = {"leaderboard_v1": _CREATE_SQL}[config.storage_schema]
            self._conn.executescript(schema_sql)
        except BaseException:
            self._conn.close()
            raise

    @property
    def db_path(self) -> Path:
        return self._config.path

    def on_match_scored(self, payload: ModelSOMatchScoredPayload) -> None:
        """Upsert one already-validated canonical MATCH_SCORED payload."""
        created_at = self._clock.now().isoformat()

        self._conn.execute(
            _UPSERT_SQL,
            (
                payload.match_id,
                payload.winner_player_id,
                payload.winner_loadout_id,
                payload.winner_score,
                payload.loser_player_id,
                payload.loser_score,
                payload.duration_ticks,
                payload.scored_at,
                created_at,
                1 if payload.is_draw else 0,
            ),
        )

    def top_n(self, n: int) -> list[ModelSOLeaderboardEntry]:
        cursor = self._conn.execute(_TOP_N_SQL, (n,))
        return [_row_to_entry(row) for row in cursor]

    def player_record(self, player_id: str) -> dict[str, int]:
        """Return ``{wins, losses, total_score}`` for *player_id*.

        Draws are excluded from win/loss counts; scores from losses are
        included in total_score (they represent meaningful damage dealt).
        """
        win_count = int(self._conn.execute(_PLAYER_WIN_COUNT_SQL, (player_id,)).fetchone()[0])
        loss_count = int(self._conn.execute(_PLAYER_LOSS_COUNT_SQL, (player_id,)).fetchone()[0])
        win_score = int(self._conn.execute(_PLAYER_WINS_SQL, (player_id,)).fetchone()[0])
        loss_score = int(self._conn.execute(_PLAYER_LOSSES_SQL, (player_id,)).fetchone()[0])
        return {
            "wins": win_count,
            "losses": loss_count,
            "total_score": win_score + loss_score,
        }

    def draw_count(self) -> int:
        """Return the number of draw entries in the leaderboard."""
        return int(self._conn.execute(_DRAW_COUNT_SQL).fetchone()[0])


# ---------------------------------------------------------------------------
# Row deserializer
# ---------------------------------------------------------------------------


def _row_to_entry(row: tuple[object, ...]) -> ModelSOLeaderboardEntry:
    (
        match_id,
        winner_player_id,
        winner_loadout_id,
        winner_score,
        loser_player_id,
        loser_score,
        duration_ticks,
        scored_at,
        created_at,
        is_draw,
    ) = row
    return ModelSOLeaderboardEntry(
        match_id=str(match_id),
        winner_player_id=str(winner_player_id),
        winner_loadout_id=str(winner_loadout_id),
        winner_score=int(str(winner_score)),
        loser_player_id=str(loser_player_id),
        loser_score=int(str(loser_score)),
        duration_ticks=int(str(duration_ticks)),
        scored_at=str(scored_at),
        created_at=str(created_at),
        is_draw=bool(is_draw),
    )
