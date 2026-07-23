"""Contract tests for the two-kind live-learning overlay binding (L-GATE-2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.application import (
    ModelSOLiveLearningBinding,
    ModelSOSelectionOutcomeThresholds,
)
from steel_onslaught.learning.promotion import ModelSOPromotionThresholds

pytestmark = pytest.mark.unit


def _raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "kind": "win_damage_differential_v1",
        "archetype": "aggressive",
        "learning_player_id": "player.red",
        "genesis_parameters": {"aggression": 1.0},
    }
    raw.update(overrides)
    return raw


def test_win_damage_kind_validates_without_selection_outcome_fields() -> None:
    binding = ModelSOLiveLearningBinding.model_validate(_raw())

    assert binding.kind == "win_damage_differential_v1"
    assert binding.base_loadout_path is None


def test_selection_outcome_kind_requires_base_loadout_path() -> None:
    with pytest.raises(ValidationError, match="base_loadout_path"):
        ModelSOLiveLearningBinding.model_validate(_raw(kind="selection_outcome_v1"))

    binding = ModelSOLiveLearningBinding.model_validate(
        _raw(
            kind="selection_outcome_v1",
            base_loadout_path=Path("loadouts/base.yaml"),
            parameter="mode_switch_heat_ceiling",
        )
    )
    assert binding.base_loadout_path == Path("loadouts/base.yaml")
    assert binding.n_search_seeds == 3
    assert binding.n_holdout_seeds == 2


def test_win_damage_kind_rejects_selection_outcome_only_fields() -> None:
    with pytest.raises(ValidationError, match="base_loadout_path"):
        ModelSOLiveLearningBinding.model_validate(
            _raw(base_loadout_path=Path("loadouts/base.yaml"))
        )
    with pytest.raises(ValidationError, match="thresholds"):
        ModelSOLiveLearningBinding.model_validate(_raw(thresholds={}))


def test_unknown_kind_fails_closed() -> None:
    with pytest.raises(ValidationError, match="kind"):
        ModelSOLiveLearningBinding.model_validate(_raw(kind="forged_evaluator_v9"))


def test_threshold_mirror_matches_the_learning_gate_field_for_field() -> None:
    """The overlay-layer mirror must track ModelSOPromotionThresholds exactly:
    same field names AND same defaults, so an overlay with no overrides gates
    identically to the offline loop."""

    mirror_fields = set(ModelSOSelectionOutcomeThresholds.model_fields)
    gate_fields = set(ModelSOPromotionThresholds.model_fields)
    assert mirror_fields == gate_fields

    mirror_defaults = ModelSOSelectionOutcomeThresholds().model_dump(mode="python")
    gate_defaults = ModelSOPromotionThresholds().model_dump(mode="python")
    assert mirror_defaults == gate_defaults

    # And the mirror round-trips into the real gate model.
    assert ModelSOPromotionThresholds(**mirror_defaults) == ModelSOPromotionThresholds()
