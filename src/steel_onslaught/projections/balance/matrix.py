"""Round-robin win matrix projection — tunable-pilots Task 6.

``ModelSOBalanceMatrix`` records the outcome tally of every unordered
combatant-config pairing in a balance sweep: per pairing ``wins_a`` /
``wins_b`` / ``draws`` over the swept seed set, plus the overall draw rate.

The model enforces the Task 6 row invariant structurally: every pairing must
account for exactly ``seeds`` matches (``wins_a + wins_b + draws == seeds``),
so an under- or over-counted sweep cannot be represented at all.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelSOBalancePairing(BaseModel):
    """Outcome tally for one unordered combatant-config pairing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_a: str = Field(min_length=1)
    config_b: str = Field(min_length=1)
    wins_a: int = Field(ge=0)
    wins_b: int = Field(ge=0)
    draws: int = Field(ge=0)

    @property
    def matches(self) -> int:
        """Total matches recorded for this pairing."""
        return self.wins_a + self.wins_b + self.draws

    @model_validator(mode="after")
    def _distinct_configs(self) -> ModelSOBalancePairing:
        if self.config_a == self.config_b:
            raise ValueError(f"a pairing needs two distinct configs, got {self.config_a!r} twice")
        return self


class ModelSOBalanceMatrix(BaseModel):
    """Ordered pairing tallies for one deterministic round-robin sweep."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seeds: int = Field(ge=1, description="Seed count N; seeds 1..N were swept per pairing")
    pairings: tuple[ModelSOBalancePairing, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _every_pairing_accounts_for_every_seed(self) -> ModelSOBalanceMatrix:
        for pairing in self.pairings:
            if pairing.matches != self.seeds:
                raise ValueError(
                    f"pairing {pairing.config_a!r} vs {pairing.config_b!r}: "
                    f"wins_a + wins_b + draws == {pairing.matches}, expected seeds == {self.seeds}"
                )
        return self

    @property
    def total_matches(self) -> int:
        """Total matches across all pairings (pairings * seeds)."""
        return len(self.pairings) * self.seeds

    @property
    def total_draws(self) -> int:
        """Total draws across all pairings."""
        return sum(pairing.draws for pairing in self.pairings)

    @property
    def draw_rate(self) -> float:
        """Overall draw rate: total draws over total matches."""
        return self.total_draws / self.total_matches

    def to_csv(self) -> str:
        """Render the matrix as deterministic CSV (header + one row per pairing)."""
        lines = ["config_a,config_b,wins_a,wins_b,draws"]
        lines.extend(
            f"{p.config_a},{p.config_b},{p.wins_a},{p.wins_b},{p.draws}" for p in self.pairings
        )
        return "\n".join(lines) + "\n"
