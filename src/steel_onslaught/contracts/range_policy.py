"""Typed preferred-range policy contracts for tactical rule plugins.

The policy is deliberately independent of providers, card dealing, and the
canonical reducers.  A composition root can inject one policy into a pure
card-programming handler while the event ledger remains the authority for the
resulting movement and weapon effects.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

RangeArchetype = Literal["berserker", "sniper", "opportunist"]
RangeMoveDirection = Literal["toward_enemy", "away_from_enemy", "left", "right"]


class ModelSOPreferredRangePolicy(BaseModel):
    """Closed policy describing a pilot's preferred combat distance.

    ``preferred_max`` is the upper edge of the band.  A Berserker policy must
    opt into ``forbid_away_outside_range``; when outside that band the range
    handler will not allow an ``away_from_enemy``/Reposition card to remain in
    the proposed plan.  Sniper and opportunist policies may choose a different
    outside-range direction, but the policy itself never mutates match state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.preferred_range_policy"] = (
        "steel_onslaught.preferred_range_policy"
    )
    policy_id: StrictStr = Field(
        min_length=1,
        max_length=96,
        pattern=r"^range_policy\.[a-z][a-z0-9_.-]*$",
    )
    archetype: RangeArchetype
    preferred_min: StrictInt = Field(ge=0)
    preferred_max: StrictInt = Field(gt=0)
    outside_range_direction: RangeMoveDirection
    forbid_away_outside_range: StrictBool = True

    @model_validator(mode="after")
    def _validate_range_band(self) -> Self:
        if self.preferred_min > self.preferred_max:
            raise ValueError("preferred_min must be less than or equal to preferred_max")
        if self.archetype == "berserker" and not self.forbid_away_outside_range:
            raise ValueError("berserker policies must forbid away movement outside range")
        if self.forbid_away_outside_range and self.outside_range_direction == "away_from_enemy":
            raise ValueError(
                "a policy that forbids away movement must choose an approach direction"
            )
        if self.archetype == "berserker" and self.outside_range_direction != "toward_enemy":
            raise ValueError("berserker policies must approach the enemy outside range")
        return self


__all__ = ["ModelSOPreferredRangePolicy", "RangeArchetype", "RangeMoveDirection"]
