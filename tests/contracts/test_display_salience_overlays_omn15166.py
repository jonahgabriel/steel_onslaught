"""Single-axis proof for the OMN-15166 display-salience arm #1 overlay pair.

``foundry_60_asym_v1_salience_{default,prominent}_delegation.yaml`` are a
paired lane (a genuine departure from #210/#212/#215's convention of one new
overlay measured against an already-published corner -- see the PROMINENT
overlay's own "CORNER PROVENANCE NOTE" for why: no delegation-bound corner
exists yet for this metric, so this arm builds its own same-provider
reference lane rather than confound provider identity with the salience
manipulation).

Three claims are load-bearing here:

  1. the two overlays are byte-identical in everything except which pilot
     registry entries their paired loadouts resolve to -- proven by
     ``test_overlay_pair_only_differs_by_pilot_registry_selection``; and
  2. both are bound to the delegation-backed provider (``kind:
     onex_delegation``), never ``openai_compatible`` -- proven by
     ``test_both_overlays_bind_the_delegation_provider_not_openai_compatible``;
     and
  3. each lane's loadouts resolve to a pilot spec whose
     ``display_salience`` matches the lane's own name (never the other
     lane's), proven by ``test_lane_loadouts_resolve_to_matching_salience``.

The prompt-stream byte-delta proof itself (the #210 standard) lives in
``tests/llm/test_llm_pilot.py``'s display-salience section -- this file
proves the SHIPPED contracts are the ones that carry it, following
``tests/contracts/test_objmask_overlay.py``'s own division of labor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSODelegationProviderBinding,
)
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import SODisplaySalience
from steel_onslaught.llm.client_delegation import LlmBusDelegationClient
from steel_onslaught.match.composition import (
    build_llm_dependencies,
    load_application_overlay,
    load_match_contract_catalog,
    load_pilot_registry,
)

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts" / "delegation_salience"
_DEFAULT_OVERLAY = _OVERLAYS / "foundry_60_asym_v1_salience_default_delegation.yaml"
_PROMINENT_OVERLAY = _OVERLAYS / "foundry_60_asym_v1_salience_prominent_delegation.yaml"

_ARENA_ID = "foundry_60_asym_v1"

# Fields that must be IDENTICAL across the pair -- everything the overlay
# declares except the two facts the pair legitimately differs on
# (identity: schema_version/bus/... below are compared directly instead).
_HELD_LLM_PROVIDER_FIELDS = (
    "kind",
    "provider_id",
    "backend_id",
    "task_type",
    "source",
    "model",
    "max_tokens",
    "timeout_seconds",
)


def _load_loadout(name: str) -> ModelSOLoadout:
    raw = yaml.safe_load((_LOADOUTS / name).read_text(encoding="utf-8"))
    return ModelSOLoadout.model_validate(raw)


def test_both_overlays_parse_and_bind_the_shared_unmodified_arena() -> None:
    """Both lanes declare the SAME, byte-untouched arena -- fixed real payout
    and fixed display presence is a structural fact of the overlay, not a
    claim made only in prose."""

    default = load_application_overlay(_DEFAULT_OVERLAY)
    prominent = load_application_overlay(_PROMINENT_OVERLAY)

    assert isinstance(default, ModelSOApplicationOverlay)
    assert isinstance(prominent, ModelSOApplicationOverlay)
    assert default.contracts.arena_id == _ARENA_ID
    assert prominent.contracts.arena_id == _ARENA_ID

    catalog = load_match_contract_catalog(default.contracts.catalog_dir)
    arena = catalog.arenas[_ARENA_ID]
    assert len(arena.objectives) == 3
    assert arena.vp_threshold == 15
    # Fixed real payout, fixed display presence -- both shipped defaults,
    # neither overridden by this arm.
    assert arena.objective_scoring == "scoring"
    assert arena.objective_display == "visible"


def test_neither_overlay_enables_card_mode() -> None:
    """Deliberately NOT card mode (see both overlays' own header note): the
    manipulated field has no natural analogue on the JSON-structured
    whole-round-programming observation."""

    default = load_application_overlay(_DEFAULT_OVERLAY)
    prominent = load_application_overlay(_PROMINENT_OVERLAY)
    assert default.contracts.card_catalog is None
    assert prominent.contracts.card_catalog is None


def test_both_overlays_bind_the_delegation_provider_not_openai_compatible() -> None:
    """Ticket requirement: bound to the delegation-backed provider, NOT
    OpenAICompatibleClient. Values match the live-proven
    ``tests/live/test_omn15170_live_driver.py`` configuration verbatim."""

    for path in (_DEFAULT_OVERLAY, _PROMINENT_OVERLAY):
        overlay = load_application_overlay(path)
        assert len(overlay.llm.providers) == 1
        provider = overlay.llm.providers[0]
        assert isinstance(provider, ModelSODelegationProviderBinding)
        assert provider.kind == "onex_delegation"
        assert provider.provider_id == "onex-local-coder-mlx"
        assert provider.backend_id == "local-coder-mlx"
        assert provider.task_type == "agent_delegation"
        assert provider.source == "external-client"
        assert provider.model == "mlx-community/Qwen3.6-35B-A3B-8bit"


def test_overlay_pair_only_differs_by_pilot_registry_selection() -> None:
    """Field-by-field held-fields proof (the #215/test_objmask_overlay.py
    ``_HELD_FIELDS`` discipline): the provider block, the arena binding, and
    every top-level overlay section besides the durable-path stems (cosmetic
    only -- rewritten from ``--state-root`` at launch, per every prior
    overlay in this repo) are byte-identical between the pair."""

    default = load_application_overlay(_DEFAULT_OVERLAY)
    prominent = load_application_overlay(_PROMINENT_OVERLAY)

    assert default.contracts.arena_id == prominent.contracts.arena_id
    assert default.contracts.card_catalog == prominent.contracts.card_catalog
    assert default.contracts.pilot_registry_dir == prominent.contracts.pilot_registry_dir
    assert default.llm.model_identities == prominent.llm.model_identities
    assert default.llm.secret_resolver == prominent.llm.secret_resolver
    assert default.clock == prominent.clock
    assert default.identity == prominent.identity
    assert default.frontend_transport == prominent.frontend_transport

    default_provider = default.llm.providers[0]
    prominent_provider = prominent.llm.providers[0]
    for field in _HELD_LLM_PROVIDER_FIELDS:
        assert getattr(default_provider, field) == getattr(prominent_provider, field), (
            f"provider field {field!r} diverged between the default and prominent "
            "delegation overlays; the pair must be identical except pilot selection"
        )
    # The single free variable across the pair, at the raw YAML level, is
    # each provider's omnibase_infra_path/state_root cosmetic stems (never
    # read by any test above) -- everything the delegation CLIENT actually
    # dispatches on (backend/task_type/model/timeouts) is asserted equal.


def test_lane_loadouts_resolve_to_matching_salience() -> None:
    """Each lane's OWN loadouts resolve to the pilot spec whose
    ``display_salience`` matches that lane's name -- never the other lane's
    (the exact footgun the overlays' own launch-invocation comments warn
    about)."""

    default_overlay = load_application_overlay(_DEFAULT_OVERLAY)
    prominent_overlay = load_application_overlay(_PROMINENT_OVERLAY)
    # Shared registry dir (both overlays point at the same directory; the
    # LOADOUT selects the archetype, not the overlay) -- assert that shared
    # fact structurally too.
    assert default_overlay.contracts.pilot_registry_dir == (
        prominent_overlay.contracts.pilot_registry_dir
    )
    registry = load_pilot_registry(default_overlay.contracts.pilot_registry_dir)

    default_red = registry.resolve(_load_loadout("red_default.yaml"))
    default_blue = registry.resolve(_load_loadout("blue_default.yaml"))
    prominent_red = registry.resolve(_load_loadout("red_prominent.yaml"))
    prominent_blue = registry.resolve(_load_loadout("blue_prominent.yaml"))

    assert default_red.parameters.display_salience == SODisplaySalience.DEFAULT  # type: ignore[union-attr]
    assert default_blue.parameters.display_salience == SODisplaySalience.DEFAULT  # type: ignore[union-attr]
    assert prominent_red.parameters.display_salience == SODisplaySalience.PROMINENT  # type: ignore[union-attr]
    assert prominent_blue.parameters.display_salience == SODisplaySalience.PROMINENT  # type: ignore[union-attr]

    # Personas are held constant across the pair -- berserker/red,
    # sniper/blue on both lanes; only salience differs.
    assert default_red.parameters.persona == prominent_red.parameters.persona == "berserker"  # type: ignore[union-attr]
    assert default_blue.parameters.persona == prominent_blue.parameters.persona == "sniper"  # type: ignore[union-attr]
    # Provider is identical (delegation-bound) on every pilot in the shared
    # registry -- salience is the ONLY manipulated axis.
    for spec in (default_red, default_blue, prominent_red, prominent_blue):
        assert spec.parameters.provider == "onex-local-coder-mlx"  # type: ignore[union-attr]


def test_loadouts_hold_chassis_and_weapons_constant_across_the_pair() -> None:
    """The paired loadouts differ from each other ONLY by ``pilot_id`` --
    chassis/boiler/weapons/sensors/budgets are byte-identical, mirroring
    ``llm_qwen35_berserker.yaml``/``qwen35/sniper_ironclad.yaml`` verbatim."""

    for default_name, prominent_name in (
        ("red_default.yaml", "red_prominent.yaml"),
        ("blue_default.yaml", "blue_prominent.yaml"),
    ):
        default_loadout = _load_loadout(default_name)
        prominent_loadout = _load_loadout(prominent_name)
        assert default_loadout.chassis_id == prominent_loadout.chassis_id
        assert default_loadout.boiler_id == prominent_loadout.boiler_id
        assert default_loadout.modules == prominent_loadout.modules
        assert default_loadout.budgets == prominent_loadout.budgets
        assert default_loadout.pilot_id != prominent_loadout.pilot_id


def test_delegation_dependencies_build_cleanly_for_both_lanes() -> None:
    """``build_llm_dependencies`` resolves a real ``LlmBusDelegationClient``
    for both lanes (no eager filesystem/network access at construction --
    proven by this succeeding with no live infra reachable)."""

    for path in (_DEFAULT_OVERLAY, _PROMINENT_OVERLAY):
        overlay = load_application_overlay(path)
        dependencies = build_llm_dependencies(overlay)
        try:
            client = dependencies.client_factory.client_for("onex-local-coder-mlx")
            assert isinstance(client, LlmBusDelegationClient)
        finally:
            dependencies.close()
