"""Storage-neutral leaderboard ports."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


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
    def on_match_scored(self, payload: dict[str, Any]) -> None:
        """Materialize one canonical MATCH_SCORED payload."""
        ...

    def top_n(self, n: int) -> list[ModelSOLeaderboardEntry]:
        """Return the top decisive entries."""
        ...


__all__ = ["LeaderboardRepository", "ModelSOLeaderboardEntry"]
