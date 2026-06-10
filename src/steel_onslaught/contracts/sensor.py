"""Sensor contract model — Task 10."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelSOSensorSpec(BaseModel):
    """Contract model for a sensor module specification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1.0"] = "0.1.0"
    kind: Literal["steel_onslaught.sensor"] = "steel_onslaught.sensor"

    id: str = Field(pattern=r"^sensor\.[a-z0-9_]+$")
    display_name: str

    # Detection geometry
    range: int = Field(gt=0, description="Maximum detection range in grid units")
    precision: float = Field(
        gt=0.0,
        le=1.0,
        description="Observation accuracy [0 exclusive, 1 inclusive]",
    )
    latency_ticks: int = Field(
        ge=0,
        description="Ticks between acquisition and first observation delivery",
    )

    # Resource costs (per tick while active)
    pressure_draw_per_tick: float = Field(ge=0.0, description="Boiler pressure consumed per tick")
    heat_per_tick: float = Field(ge=0.0, description="Heat generated per tick")

    # Signature contribution
    signature_impact: float = Field(
        ge=0.0,
        description="Additive contribution to this mech's detectable signature",
    )

    # Countermeasure vulnerability — float in [0, 1]
    jamming_vulnerability_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Susceptibility to jamming gizmos; 0 = immune, 1 = fully vulnerable",
    )
