"""Contract proof for the show-dont-tell spatial representation ARM R1/R2
battery config (2026-07-24).

Hypothesis under test (operator): the pilot CAN reason spatially but has
never been SHOWN the space in a usable form -- the ARM S/surfacing lane
(PR #160, ``tactical_split_overdeal_utility_asym_v2_qwen.yaml``) closed the
raw-data gaps (cover_cells list, enemy_weapon_threat list) but left qwen35 to
do all the spatial math itself; that battery produced 0/209 plan rationales
mentioning terrain and 85/107 out-of-range red fire attempts.

- ARM R1 ("grid"): a rendered per-round ASCII viewport map (obstacles, both
  mechs, objectives, enemy-LOS shadow cells), resolver-backed per-dealt-
  movement-card consequence previews, and in-range-now flags on dealt weapon
  cards. Representation only -- no ``programming_guidance``/steering text.
- ARM R2 ("grid_scaffold"): R1 plus a required one-line spatial-read field in
  the response format before register selection.

Both arms apply symmetrically to BOTH seats (fairness) via new, additive
pilot specs and a new, additive overlay per arm; the v2/surfacing overlay and
every pilot.llm.qwen35* spec it references stay byte-untouched.

This suite proves, without a live battery (CI-safe):
  1. each spatial pilot spec parses, shares persona/provider with its
     v2/surfacing counterpart, and carries the expected
     ``spatial_representation`` value;
  2. each spatial overlay parses, binds arena_id=foundry_60_asym_v2, and its
     ONLY difference from the v2/surfacing overlay is the two seats'
     pilot_spec_id (deck policy, utility pack, LLM provider/retry all
     identical);
  3. pilot.llm.qwen35 / pilot.llm.qwen35_sniper (used by the v1/v2/surfacing
     lanes) carry ``spatial_representation == "none"`` -- untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_pilot_registry,
)

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"
_PILOT_REGISTRY_DIR = _REPO_ROOT / "contracts_data" / "pilots" / "fire_dense_qwen"

_ARENA_V2_ID = "foundry_60_asym_v2"
_OVERLAY_SURFACING = _OVERLAYS / "tactical_split_overdeal_utility_asym_v2_qwen.yaml"

_UNGATED_BERSERKER_SPEC_ID = "pilot.llm.qwen35"
_UNGATED_SNIPER_SPEC_ID = "pilot.llm.qwen35_sniper"


@pytest.mark.parametrize(
    ("arm", "expected_representation", "overlay_filename"),
    [
        ("r1", "grid", "tactical_split_overdeal_utility_asym_v2_spatial_r1_qwen.yaml"),
        ("r2", "grid_scaffold", "tactical_split_overdeal_utility_asym_v2_spatial_r2_qwen.yaml"),
    ],
)
class TestSpatialRepresentationArm:
    """Parametrized over both arms so R1/R2 share one proof shape."""

    def _berserker_spec_id(self, arm: str) -> str:
        return f"pilot.llm.qwen35_berserker_spatial_{arm}"

    def _sniper_spec_id(self, arm: str) -> str:
        return f"pilot.llm.qwen35_sniper_spatial_{arm}"

    def test_spatial_specs_parse_and_share_persona_and_provider(
        self, arm: str, expected_representation: str, overlay_filename: str
    ) -> None:
        del overlay_filename
        registry = load_pilot_registry(_PILOT_REGISTRY_DIR)
        ungated_berserker = registry.get(_UNGATED_BERSERKER_SPEC_ID)
        ungated_sniper = registry.get(_UNGATED_SNIPER_SPEC_ID)
        spatial_berserker = registry.get(self._berserker_spec_id(arm))
        spatial_sniper = registry.get(self._sniper_spec_id(arm))
        assert ungated_berserker is not None
        assert ungated_sniper is not None
        assert spatial_berserker is not None
        assert spatial_sniper is not None

        assert isinstance(ungated_berserker.parameters, ModelSOLlmPilotParams)
        assert isinstance(ungated_sniper.parameters, ModelSOLlmPilotParams)
        assert isinstance(spatial_berserker.parameters, ModelSOLlmPilotParams)
        assert isinstance(spatial_sniper.parameters, ModelSOLlmPilotParams)

        assert spatial_berserker.parameters.persona == ungated_berserker.parameters.persona
        assert spatial_berserker.parameters.provider == ungated_berserker.parameters.provider
        assert spatial_sniper.parameters.persona == ungated_sniper.parameters.persona
        assert spatial_sniper.parameters.provider == ungated_sniper.parameters.provider

    def test_spatial_specs_carry_expected_representation_and_no_guidance(
        self, arm: str, expected_representation: str, overlay_filename: str
    ) -> None:
        del overlay_filename
        registry = load_pilot_registry(_PILOT_REGISTRY_DIR)
        for spec_id in (self._berserker_spec_id(arm), self._sniper_spec_id(arm)):
            spec = registry.get(spec_id)
            assert spec is not None
            assert isinstance(spec.parameters, ModelSOLlmPilotParams)
            assert spec.parameters.spatial_representation == expected_representation
            # Representation-only arm: no steering text riding along with it.
            assert spec.parameters.programming_guidance is None

    def test_spatial_overlay_parses_and_binds_arena_v2(
        self, arm: str, expected_representation: str, overlay_filename: str
    ) -> None:
        del arm, expected_representation
        overlay = load_application_overlay(_OVERLAYS / overlay_filename)
        assert isinstance(overlay, ModelSOApplicationOverlay)
        assert overlay.contracts.arena_id == _ARENA_V2_ID

    def test_spatial_overlay_binds_both_seats_to_the_spatial_specs(
        self, arm: str, expected_representation: str, overlay_filename: str
    ) -> None:
        del expected_representation
        overlay = load_application_overlay(_OVERLAYS / overlay_filename)
        assert overlay.contracts.card_catalog is not None
        bindings = {p.side: p.pilot_spec_id for p in overlay.contracts.card_catalog.programmers}
        assert bindings["red"] == self._berserker_spec_id(arm)
        assert bindings["blue"] == self._sniper_spec_id(arm)

    def test_spatial_overlay_only_differs_from_surfacing_overlay_by_pilot_spec_ids(
        self, arm: str, expected_representation: str, overlay_filename: str
    ) -> None:
        """Everything else the runtime consumes stays byte-identical between
        the surfacing overlay and this arm's overlay; BOTH seats' pilot spec
        ids are the free variable this arm isolates (unlike ARM G's
        seat-scoped pattern -- fairness requires both seats change)."""
        del expected_representation
        surfacing = load_application_overlay(_OVERLAY_SURFACING)
        spatial = load_application_overlay(_OVERLAYS / overlay_filename)

        assert surfacing.contracts.arena_id == spatial.contracts.arena_id
        assert surfacing.llm.providers == spatial.llm.providers
        assert surfacing.contracts.card_catalog is not None
        assert spatial.contracts.card_catalog is not None
        assert (
            surfacing.contracts.card_catalog.deck_policy
            == spatial.contracts.card_catalog.deck_policy
        )
        assert surfacing.contracts.utility_handler_pack == spatial.contracts.utility_handler_pack

        surfacing_bindings = {
            p.side: p.pilot_spec_id for p in surfacing.contracts.card_catalog.programmers
        }
        spatial_bindings = {
            p.side: p.pilot_spec_id for p in spatial.contracts.card_catalog.programmers
        }
        diff_sides = {
            side
            for side in surfacing_bindings
            if surfacing_bindings[side] != spatial_bindings.get(side)
        }
        assert diff_sides == {"red", "blue"}


@pytest.mark.unit
def test_ungated_specs_default_to_no_spatial_representation() -> None:
    """pilot.llm.qwen35 / pilot.llm.qwen35_sniper (v1/v2/surfacing lanes) are
    untouched: their resolved observation/prompt stays byte-identical."""
    registry = load_pilot_registry(_PILOT_REGISTRY_DIR)
    for spec_id in (_UNGATED_BERSERKER_SPEC_ID, _UNGATED_SNIPER_SPEC_ID):
        spec = registry.get(spec_id)
        assert spec is not None
        assert isinstance(spec.parameters, ModelSOLlmPilotParams)
        assert spec.parameters.spatial_representation == "none"


@pytest.mark.unit
def test_surfacing_overlay_is_untouched() -> None:
    """The ARM S/surfacing v2 overlay this arm is measured against is
    unmodified by either spatial overlay's addition."""
    overlay = load_application_overlay(_OVERLAY_SURFACING)
    assert overlay.contracts.arena_id == _ARENA_V2_ID
    assert overlay.contracts.card_catalog is not None
    bindings = {p.side: p.pilot_spec_id for p in overlay.contracts.card_catalog.programmers}
    assert bindings["red"] == _UNGATED_BERSERKER_SPEC_ID
    assert bindings["blue"] == _UNGATED_SNIPER_SPEC_ID
