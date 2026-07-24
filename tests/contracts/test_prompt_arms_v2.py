"""Contract proof for the brawler prompt-arms v2 battery config (2026-07-24).

Session 2026-07-24: two measured prompt-layer interventions stacked on top of
the PR #157 brawler-recut v2 config (``foundry_60_asym_v2`` + brawler loadout
v2 + the v2 combined overlay), which battery-tested 0/30 for red.

- ARM S (surfacing): closes prompt-content-audit gaps #1-#4 (cover/obstacle
  map) and #2 (enemy weapon range) in the whole-round programming prompt
  serializer. This is a pure code change applying to EVERY match regardless
  of overlay/pilot-spec config -- see ``tests/llm/test_llm_programming.py``
  and ``tests/reducers/test_pilot_tick.py`` for its unit coverage. No new
  contract file is needed to "activate" it: the existing v2 overlay
  (``tactical_split_overdeal_utility_asym_v2_qwen.yaml``) already exercises
  it once merged, isolated to its own state-root via ``--state-root``.
- ARM G (surfacing + steering): a NEW, additive pilot spec
  (``pilot.llm.qwen35_berserker_guided``) adds a declarative, seat-scoped
  ``programming_guidance`` block on top of the same persona/provider as
  ``pilot.llm.qwen35``, and a NEW, additive overlay
  (``tactical_split_overdeal_utility_asym_v2_guided_qwen.yaml``) binds it to
  the red seat only -- the blue (sniper) seat and every other config
  dimension are byte-identical to the v2/surfacing overlay.

This suite proves, without a live battery (CI-safe):

  1. the guided pilot spec parses, shares persona=berserker/provider=qwen35
     with pilot.llm.qwen35, and carries a non-blank programming_guidance;
  2. the ARM G overlay parses, binds arena_id=foundry_60_asym_v2, and its
     ONLY difference from the ARM S/surfacing overlay is the red seat's
     pilot_spec_id (blue, deck policy, utility pack, LLM provider/retry all
     identical);
  3. pilot.llm.qwen35 (used by both the v1 and v2/surfacing lanes) is
     untouched -- no ``programming_guidance`` leaks onto the ungated spec.
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
_OVERLAY_GUIDED = _OVERLAYS / "tactical_split_overdeal_utility_asym_v2_guided_qwen.yaml"

_UNGATED_SPEC_ID = "pilot.llm.qwen35"
_GUIDED_SPEC_ID = "pilot.llm.qwen35_berserker_guided"


# ---------------------------------------------------------------------------
# ARM G pilot spec: pilot.llm.qwen35_berserker_guided
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_guided_spec_parses_and_shares_persona_and_provider_with_ungated_spec() -> None:
    registry = load_pilot_registry(_PILOT_REGISTRY_DIR)
    ungated = registry.get(_UNGATED_SPEC_ID)
    guided = registry.get(_GUIDED_SPEC_ID)
    assert ungated is not None
    assert guided is not None

    assert isinstance(ungated.parameters, ModelSOLlmPilotParams)
    assert isinstance(guided.parameters, ModelSOLlmPilotParams)
    assert guided.parameters.persona == ungated.parameters.persona == "berserker"
    assert guided.parameters.provider == ungated.parameters.provider == "qwen35"


@pytest.mark.unit
def test_guided_spec_carries_non_blank_seat_scoped_guidance() -> None:
    registry = load_pilot_registry(_PILOT_REGISTRY_DIR)
    guided = registry.get(_GUIDED_SPEC_ID)
    assert guided is not None
    assert isinstance(guided.parameters, ModelSOLlmPilotParams)
    guidance = guided.parameters.programming_guidance
    assert guidance is not None
    assert guidance.strip()
    # References the actual legal card ids / observation fields the model can
    # act on -- not aspirational text about cards/verbs that don't exist
    # (audit gap #1: there is no "move to cover" card).
    assert "card.movement.flank_left" in guidance or "card.movement.flank_right" in guidance
    assert "card.attack.fire_primary" in guidance or "card.attack.fire_secondary" in guidance


@pytest.mark.unit
def test_ungated_spec_carries_no_programming_guidance() -> None:
    """pilot.llm.qwen35 (used by the v1 and v2/surfacing lanes) is untouched."""
    registry = load_pilot_registry(_PILOT_REGISTRY_DIR)
    ungated = registry.get(_UNGATED_SPEC_ID)
    assert ungated is not None
    assert isinstance(ungated.parameters, ModelSOLlmPilotParams)
    assert ungated.parameters.programming_guidance is None


# ---------------------------------------------------------------------------
# ARM G overlay: tactical_split_overdeal_utility_asym_v2_guided_qwen.yaml
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_guided_overlay_parses_and_binds_arena_v2() -> None:
    overlay = load_application_overlay(_OVERLAY_GUIDED)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == _ARENA_V2_ID


@pytest.mark.unit
def test_guided_overlay_binds_red_to_the_guided_spec_and_leaves_blue_unchanged() -> None:
    surfacing = load_application_overlay(_OVERLAY_SURFACING)
    guided = load_application_overlay(_OVERLAY_GUIDED)
    assert surfacing.contracts.card_catalog is not None
    assert guided.contracts.card_catalog is not None

    surfacing_bindings = {
        p.side: p.pilot_spec_id for p in surfacing.contracts.card_catalog.programmers
    }
    guided_bindings = {p.side: p.pilot_spec_id for p in guided.contracts.card_catalog.programmers}

    assert surfacing_bindings["red"] == _UNGATED_SPEC_ID
    assert guided_bindings["red"] == _GUIDED_SPEC_ID
    assert guided_bindings["blue"] == surfacing_bindings["blue"]


@pytest.mark.unit
def test_guided_overlay_only_differs_from_surfacing_overlay_by_red_pilot_spec_id() -> None:
    """Everything else the runtime consumes -- deck policy, utility pack, LLM
    provider/retry -- stays byte-identical between the two overlays; the red
    seat's ``pilot_spec_id`` is the single free variable ARM G isolates."""
    surfacing = load_application_overlay(_OVERLAY_SURFACING)
    guided = load_application_overlay(_OVERLAY_GUIDED)

    assert surfacing.contracts.arena_id == guided.contracts.arena_id
    assert surfacing.llm.providers == guided.llm.providers
    assert surfacing.contracts.card_catalog is not None
    assert guided.contracts.card_catalog is not None
    assert surfacing.contracts.card_catalog.deck_policy == guided.contracts.card_catalog.deck_policy
    assert surfacing.contracts.utility_handler_pack == guided.contracts.utility_handler_pack

    surfacing_bindings = {
        p.side: p.pilot_spec_id for p in surfacing.contracts.card_catalog.programmers
    }
    guided_bindings = {p.side: p.pilot_spec_id for p in guided.contracts.card_catalog.programmers}
    diff_sides = {
        side for side in surfacing_bindings if surfacing_bindings[side] != guided_bindings.get(side)
    }
    assert diff_sides == {"red"}


@pytest.mark.unit
def test_surfacing_overlay_is_untouched() -> None:
    """PR #157's v2 overlay is the ARM S surfacing lane; this proves it is
    unmodified by the ARM G overlay's addition."""
    overlay = load_application_overlay(_OVERLAY_SURFACING)
    assert overlay.contracts.arena_id == _ARENA_V2_ID
    assert overlay.contracts.card_catalog is not None
    bindings = {p.side: p.pilot_spec_id for p in overlay.contracts.card_catalog.programmers}
    assert bindings["red"] == _UNGATED_SPEC_ID
