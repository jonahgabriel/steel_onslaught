"""Structural in-register incentives — typed, replay-durable reward contracts.

Background (why this exists at all).  Across four model lineages the program
has measured the same negative result: pilots program *utility* cards far
below the 0.50 chance floor, and the L-GATE-2 batteries showed that
prompt-level steering does not move that behaviour.  Every lever tried so far
has been prompt- or balance-shaped.  This module carries the first lever of a
different class: a reward the pilot reads as **game state** rather than as
instruction text.

The one incentive defined here (``utility_deploy_vp_bounty``) pays victory
points — the currency that already decides the match — to the deploying
player each time a utility card actually resolves into ``UTILITY_DEPLOYED``.
Three properties are load-bearing:

- **Structural, not advisory.**  The payout is folded from the canonical event
  stream by ``MatchStateFold``, exactly like objective scoring, and counts
  toward the arena's ``vp_threshold``.  It changes what winning *is*, not what
  the pilot is *told*.
- **In-register, not in-prompt.**  The rate is surfaced as a numeric field on
  the card rows the pilot already reads (``legal_hand[].deploy_vp_bounty``,
  beside ``available_copies``/``heat_cost``) plus a top-level ``incentives``
  block.  No imperative sentence is added anywhere — see
  ``llm.programming._serialize_programming_observation``.  The code-owned
  instruction block and every persona prompt stay byte-identical.
- **Default OFF and replay-durable.**  Absent an overlay binding the value is
  ``None`` everywhere: the serialized prompt, the ``MATCH_STARTED`` payload,
  and the fold's VP derivation are all byte-identical to the pre-incentive
  tree.  When present it is stamped into ``MATCH_STARTED`` so a replay
  re-derives the same payouts from the ledger alone, never from live config.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ModelSOUtilityIncentive(BaseModel):
    """A per-deploy victory-point bounty on utility-card resolution.

    Used in three places with one identical shape: the application overlay
    binding (``contracts.utility_incentive``), the ``MATCH_STARTED`` payload
    (replay durability), and the programming observation (what the pilot
    reads).  One model, so the configured value, the recorded value, and the
    rendered value can never drift apart.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    # ``kind`` is the operator-facing discriminator written in overlay YAML,
    # mirroring the sibling handler-pack bindings.  Only one incentive kind
    # exists today; a second one gets its own literal and its own fold branch
    # rather than a mutable "type" string.
    kind: Literal["utility_deploy_vp_bounty"] = "utility_deploy_vp_bounty"
    vp_per_deploy: StrictInt = Field(
        gt=0,
        le=1000,
        description=(
            "Victory points awarded to the deploying player for each resolved "
            "UTILITY_DEPLOYED event. Must be positive: an incentive of zero is "
            "spelled by omitting the binding entirely, so 'configured' and "
            "'off' are never the same state."
        ),
    )


__all__ = ["ModelSOUtilityIncentive"]
