"""SpecLike adapter over ModelSOPilotSpec — Task 1 of Phase 2.

Architectural Decision #3 (2026-06-11-learning-loop-phase2-plan.md):
- Float parameters step 0.05 (declared exactly once in FLOAT_STEPS).
- Int parameters always step 1 (no entry needed).
- Bounds are derived from ModelSO*PilotParams model_fields metadata (ge/le and StrEnum
  choices) — NEVER retyped from the addendum tables.

NOTE: deliberately no ``from __future__ import annotations`` — we call
``typing.get_type_hints()`` to resolve the string-form annotations that the
pilot.py module emits (it uses the future import). Direct ``__annotations__``
access would give bare strings under Python 3.12+ deferred evaluation.
"""

import typing
from enum import EnumMeta

from steel_onslaught.contracts.lineage import ParamDict
from steel_onslaught.contracts.pilot import (
    ModelSOAggressivePilotParams,
    ModelSODefensivePilotParams,
    ModelSOPilotSpec,
    ModelSOPredictivePilotParams,
)
from steel_onslaught.learning.protocols import (
    BoundsDict,
    ModelSOCategoricalBound,
    ModelSONumericBound,
)

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 lattice step declaration — declared exactly once (Decision #3).
# Int parameters always step 1; they need no entry here.
# ─────────────────────────────────────────────────────────────────────────────

FLOAT_STEPS: dict[str, float] = {
    # ModelSODefensivePilotParams
    "fire_confidence_floor": 0.05,
    # ModelSOPredictivePilotParams
    "lock_confidence_floor": 0.05,
    "predicted_hit_floor": 0.05,
}
"""Search-lattice step per float-typed tunable field, declared exactly once.

Phase 2 decision (Architectural Decision #3): every float parameter steps 0.05;
int parameters always step 1 and need no entry. Keyed by field name; the
completeness test pins this table against the parameter models.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Archetype → parameter model map (single source)
# ─────────────────────────────────────────────────────────────────────────────

_ARCHETYPE_PARAM_MODELS: dict[
    str,
    type[ModelSOAggressivePilotParams]
    | type[ModelSODefensivePilotParams]
    | type[ModelSOPredictivePilotParams],
] = {
    "aggressive": ModelSOAggressivePilotParams,
    "defensive": ModelSODefensivePilotParams,
    "predictive": ModelSOPredictivePilotParams,
}

# Resolved type-hints cache — avoids repeated get_type_hints() calls.
# get_type_hints() is needed because pilot.py uses `from __future__ import
# annotations`, which makes __annotations__ return bare strings.
_RESOLVED_HINTS: dict[str, dict[str, type]] = {
    archetype: typing.get_type_hints(model) for archetype, model in _ARCHETYPE_PARAM_MODELS.items()
}


def bounds_for_archetype(archetype: str) -> BoundsDict:
    """Derive the search BoundsDict for an archetype from its ModelSO*PilotParams
    model_fields metadata: numeric fields -> ModelSONumericBound(minimum=ge,
    maximum=le, step=1 for int / FLOAT_STEPS[name] for float); StrEnum fields ->
    ModelSOCategoricalBound(choices=enum values in declaration order).
    Unknown archetype raises ValueError. NEVER retypes the addendum bounds tables.
    """
    if archetype not in _ARCHETYPE_PARAM_MODELS:
        raise ValueError(
            f"unknown archetype {archetype!r}; must be one of {sorted(_ARCHETYPE_PARAM_MODELS)}"
        )
    param_model = _ARCHETYPE_PARAM_MODELS[archetype]
    resolved = _RESOLVED_HINTS[archetype]
    bounds: BoundsDict = {}

    for field_name, field_info in param_model.model_fields.items():
        resolved_type = resolved[field_name]

        # StrEnum -> categorical bound, choices in declaration order
        if isinstance(resolved_type, EnumMeta) and issubclass(resolved_type, str):
            choices = tuple(m.value for m in resolved_type)  # type: ignore[attr-defined]
            bounds[field_name] = ModelSOCategoricalBound(choices=choices)
            continue

        # Numeric: extract ge/le from Pydantic field metadata
        ge_val: float | None = None
        le_val: float | None = None
        for meta in field_info.metadata:
            if hasattr(meta, "ge") and meta.ge is not None:
                ge_val = float(meta.ge)
            if hasattr(meta, "le") and meta.le is not None:
                le_val = float(meta.le)

        if ge_val is None or le_val is None:
            raise ValueError(
                f"field {field_name!r} in {param_model.__name__} is missing ge or le metadata"
            )

        # Step: float fields use FLOAT_STEPS; int fields step 1
        if resolved_type is float:
            step = FLOAT_STEPS[field_name]
        else:
            step = 1.0

        bounds[field_name] = ModelSONumericBound(
            minimum=ge_val,
            maximum=le_val,
            step=step,
        )

    return bounds


# ─────────────────────────────────────────────────────────────────────────────
# params_from_spec / spec_from_params
# ─────────────────────────────────────────────────────────────────────────────


def params_from_spec(spec: ModelSOPilotSpec) -> ParamDict:
    """spec.parameters via model_dump(mode="json") shaped to ParamDict: ints stay
    int, floats stay float, enums become their str values — the exact JSON-native
    types Phase 1's spec_hash identity contract requires (its int-vs-float test).
    """
    raw = spec.parameters.model_dump(mode="json")
    result: ParamDict = {}
    resolved = _RESOLVED_HINTS[spec.archetype]

    for field_name in _ARCHETYPE_PARAM_MODELS[spec.archetype].model_fields:
        resolved_type = resolved[field_name]
        value = raw[field_name]
        if resolved_type is float:
            result[field_name] = float(value)
        elif resolved_type is int:
            result[field_name] = int(value)
        else:
            # StrEnum -> str value (model_dump(mode="json") already gives the string)
            result[field_name] = str(value)

    return result


def spec_from_params(
    *,
    archetype: str,
    params: ParamDict,
    spec_id: str,
    parent_id: str | None,
    display_name: str,
) -> ModelSOPilotSpec:
    """Inverse construction; ValidationError propagates (bounds are the contract
    gate — an out-of-bounds candidate is a generator bug, fail fast).
    """
    if archetype not in _ARCHETYPE_PARAM_MODELS:
        raise ValueError(
            f"unknown archetype {archetype!r}; must be one of {sorted(_ARCHETYPE_PARAM_MODELS)}"
        )
    param_model = _ARCHETYPE_PARAM_MODELS[archetype]
    # Construct and validate the parameter model first
    parameters = param_model.model_validate(params)

    return ModelSOPilotSpec.model_validate(
        {
            "id": spec_id,
            "display_name": display_name,
            "archetype": archetype,
            "lineage": {"parent": parent_id},
            "parameters": parameters.model_dump(),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# PilotSpecView — SpecLike adapter
# ─────────────────────────────────────────────────────────────────────────────


class PilotSpecView:
    """SpecLike over a ModelSOPilotSpec: archetype/parameters/bounds properties,
    parameters via params_from_spec, bounds via bounds_for_archetype.
    """

    def __init__(self, spec: ModelSOPilotSpec) -> None:
        self._spec = spec
        self._params: ParamDict | None = None
        self._bounds: BoundsDict | None = None

    @property
    def archetype(self) -> str:
        return self._spec.archetype

    @property
    def parameters(self) -> ParamDict:
        if self._params is None:
            self._params = params_from_spec(self._spec)
        return self._params

    @property
    def bounds(self) -> BoundsDict:
        if self._bounds is None:
            self._bounds = bounds_for_archetype(self._spec.archetype)
        return self._bounds
