"""Storage-neutral leaderboard ports."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.events.payloads import ModelSOMatchScoredPayload


class ModelSOLeaderboardEntry(BaseModel):
    """Storage-neutral leaderboard row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    match_id: str
    winner_player_id: str
    winner_loadout_id: str
    winner_score: int = Field(ge=0)
    loser_player_id: str
    loser_score: int = Field(ge=0)
    duration_ticks: int = Field(gt=0)
    scored_at: str
    created_at: str
    is_draw: bool


class LeaderboardRepository(Protocol):
    def on_match_scored(self, payload: ModelSOMatchScoredPayload) -> None:
        """Materialize one canonical MATCH_SCORED payload."""
        ...

    def top_n(self, n: int) -> list[ModelSOLeaderboardEntry]:
        """Return the top decisive entries."""
        ...

    def player_record(self, player_id: str) -> dict[str, int]: ...

    def draw_count(self) -> int: ...


__all__ = ["LeaderboardRepository", "ModelSOLeaderboardEntry"]
