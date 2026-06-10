"""Gizmo contract model for Steel Onslaught.

Gizmos are small-footprint modifiers that fit in a single slot and apply
conditional effects keyed by trigger names (e.g. ``on_redline``). They are
constrained by mass, slot count, and chassis compatibility.

Design reference: §14 and §14.3 of docs/plans/2026-04-30-steel-onslaught-design.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GizmoCategory(StrEnum):
    """Valid gizmo categories from design §14."""

    EFFICIENCY = "efficiency"
    AMPLIFIER = "amplifier"
    CONTROL = "control"
    DISRUPTION = "disruption"
    SAFETY = "safety"


class ModelSOGizmoConstraints(BaseModel):
    """Physical and chassis-fit constraints for a gizmo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mass: int = Field(gt=0, description="Mass units consumed in the loadout budget.")
    slots: int = Field(gt=0, description="Module slot count consumed.")
    compatible_chassis: list[str] = Field(
        min_length=1,
        description="List of chassis class strings this gizmo may be installed on.",
    )


class ModelSOGizmoSpec(BaseModel):
    """Validated gizmo specification — loaded from YAML contract files.

    Effects and tradeoffs are free-form dicts keyed by trigger name so that
    future gizmos can introduce new trigger kinds without schema changes.
    The forbidden_stacking list prevents players from double-slotting
    overlapping safety gizmos; it must NOT contain the gizmo's own id.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="0.1.0")
    kind: str = Field(default="steel_onslaught.gizmo")
    id: str = Field(
        min_length=1, description="Canonical gizmo id, e.g. gizmo.cooling.emergency_condenser"
    )
    display_name: str = Field(min_length=1)
    category: GizmoCategory
    constraints: dict[str, Any] = Field(
        description="Mass, slots, compatible_chassis — parsed from the constraints block."
    )
    effects: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form effects keyed by trigger (e.g. on_redline).",
    )
    tradeoffs: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form tradeoff penalties applied passively.",
    )
    forbidden_stacking: list[str] = Field(
        default_factory=list,
        description="Gizmo ids that cannot be installed alongside this gizmo.",
    )

    @model_validator(mode="after")
    def _no_self_reference_in_stacking(self) -> ModelSOGizmoSpec:
        """Reject specs where the gizmo forbids stacking with itself."""
        if self.id in self.forbidden_stacking:
            raise ValueError(
                f"forbidden_stacking must not contain the gizmo's own id ({self.id!r})."
            )
        return self
