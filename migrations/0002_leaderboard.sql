-- Migration 0002: leaderboard materialized view
-- Created by Task 30 (2026-04-30 plan)
-- Lives in ledger/leaderboard.sqlite (separate from per-match event ledgers).
CREATE TABLE IF NOT EXISTS leaderboard_entries (
    match_id          TEXT PRIMARY KEY,
    winner_player_id  TEXT NOT NULL,
    winner_loadout_id TEXT NOT NULL,
    winner_score      INTEGER NOT NULL,
    loser_player_id   TEXT NOT NULL,
    loser_score       INTEGER NOT NULL,
    duration_ticks    INTEGER NOT NULL,
    scored_at         TEXT NOT NULL,
    created_at        TEXT NOT NULL,  -- preserved across upserts
    is_draw           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leaderboard_winner ON leaderboard_entries(winner_player_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_score ON leaderboard_entries(winner_score DESC);
