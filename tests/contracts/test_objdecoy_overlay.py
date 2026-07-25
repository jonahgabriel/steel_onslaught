"""Single-axis proof for the SO-OBJ-DECOY non-scoring-objectives arm.

``tactical_split_overdeal_utility_asym_v1_decoyobj_qwen.yaml`` +
``foundry_60_asym_v1_decoyobj.yaml`` exist to answer the follow-up
``docs/evidence/2026-07-25-scenobj-asym-noobj-battery.md`` names in its own
§6a: objectives were declared and essentially never captured (2
``objective_scored`` events in 30 matches, zero VP terminals) yet REMOVING them
was the larger measured effect on utility keep-rate.  That doc explicitly
defers the isolating arm — "objectives present in the observation space but
non-scoring" — and this is it.

Where the SCEN-OBJ control held geometry fixed and removed objectives, this arm
holds geometry AND objectives fixed and removes only the PAYOUT.  Two claims are
load-bearing, and prose cannot carry either:

  1. the observation the pilot reads is unchanged — proven by
     ``test_decoy_pilot_prompt_stream_is_byte_identical_to_scoring_arena``,
     which runs a REAL match on each arena through the real runner and compares
     the serialized pilot prompts tick by tick; and
  2. everything except the payout is held constant — proven field by field
     against ``foundry_60_asym_v1``, INCLUDING the objectives tuple and
     ``vp_threshold``, so an edit that moves a rect or an objective cell fails
     CI rather than silently invalidating the isolation.

The suppression half of the arm (no VP, no ``OBJECTIVE_SCORED``, no VP victory,
replay-durable) is proven in ``tests/match/test_objective_scoring_decoy.py``;
this file proves the SHIPPED contracts are the ones that carry it.

Retry note, inherited from ``test_scenobj_noobj_overlay.py``: the live
provider-selection path ``SelectedOnlyLlmClientBuilder.select`` HARD-REQUIRES
``max_attempts == 1``, so equality with the ASYM provider block is the assertion
that proves genuine inheritance rather than a divergent, un-runnable retry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOOpenAICompatibleProviderBinding,
)
from steel_onslaught.llm.pilot import _serialize_observation
from steel_onslaught.match.composition import (
    load_application_overlay,
    load_loadout,
    load_match_contract_catalog,
)
from steel_onslaught.pilots.schemas import (
    ModelSOConsideredAction,
    ModelSOPilotDecision,
    ModelSOPilotObservation,
    SOPilotAction,
    SOPilotReasonCode,
)
from tests.runtime import match_runner

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"
_DECOY_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_decoyobj_qwen.yaml"
_ASYM_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"
_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")

_ASYM_ARENA_ID = "foundry_60_asym_v1"
_DECOY_ARENA_ID = "foundry_60_asym_v1_decoyobj"
_QWEN35_PROVIDER_ID = "qwen35"

# Everything the two arenas must share.  ``objective_scoring`` is the toggled
# axis; ``arena_id``/``display_name`` are identity, not contract.  Note that
# ``objectives`` and ``vp_threshold`` are INSIDE this list — that is what
# separates this arm from the SCEN-OBJ control, which toggled them.
_HELD_FIELDS = (
    "size",
    "spawn_a",
    "spawn_b",
    "obstacles",
    "rects",
    "sudden_death_start_tick",
    "sudden_death_damage_base",
    "objectives",
    "vp_threshold",
)


class _HoldPilot:
    """Deterministic pilot that stands its ground and records what it saw."""

    def __init__(self) -> None:
        self.observations: list[ModelSOPilotObservation] = []

    def decide(self, observation: ModelSOPilotObservation) -> ModelSOPilotDecision:
        self.observations.append(observation)
        return ModelSOPilotDecision(
            action=SOPilotAction.REMAIN,
            reason_code=SOPilotReasonCode.NO_VIABLE_ACTION,
            confidence=1.0,
            considered_actions=(ModelSOConsideredAction(action=SOPilotAction.REMAIN, score=1.0),),
        )


def _qwen35_provider(
    overlay: ModelSOApplicationOverlay,
) -> ModelSOOpenAICompatibleProviderBinding:
    selected = [
        provider
        for provider in overlay.llm.providers
        if provider.provider_id == _QWEN35_PROVIDER_ID
    ]
    assert len(selected) == 1, "overlay must declare exactly one qwen35 provider"
    provider = selected[0]
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    return provider


def _prompt_stream(arena_id: str) -> list[str]:
    """Run a real match on ``arena_id`` and return the red seat's prompts.

    Deliberately the RUNNER path, not a hand-built observation: the claim is
    that the decoy mode never reaches the observation builder, and only driving
    the same call site the live battery drives can prove that.
    """

    catalog = load_match_contract_catalog(Path("contracts_data"))
    loadout = load_loadout(_LOADOUT)
    pilot = _HoldPilot()
    bus = InProcessEventBus()
    runner, _ = match_runner(
        bus=bus,
        match_id=f"match.test.decoy-prompt.{arena_id}",
        seed=11,
        loadout_a=loadout,
        loadout_b=loadout,
        max_ticks=6,
        arena_override=catalog.arenas[arena_id],
        pilots_override={"mech.a.01": pilot, "mech.b.01": _HoldPilot()},
    )
    runner.run()
    assert pilot.observations, "the pilot must have been asked to decide"
    return [_serialize_observation(o, persona_id="berserker") for o in pilot.observations]


def test_decoy_overlay_parses_and_binds_the_decoy_arena() -> None:
    """It validates and binds an arena that HAS objectives and never pays."""

    overlay = load_application_overlay(_DECOY_OVERLAY)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == _DECOY_ARENA_ID

    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    arena = catalog.arenas[overlay.contracts.arena_id]
    # The manipulation landed: objectives are PRESENT, and non-scoring.
    assert len(arena.objectives) == 3
    assert arena.vp_threshold == 15
    assert arena.objective_scoring == "decoy"

    # And the arena it was cut from still scores, unmodified.
    asym_arena = catalog.arenas[_ASYM_ARENA_ID]
    assert asym_arena.objective_scoring == "scoring"


def test_decoy_arena_holds_geometry_and_objectives_exactly_constant() -> None:
    """Only the payout differs — the arm's load-bearing claim.

    If terrain, spawns, size, sudden death, an objective cell, a
    ``vp_per_round`` or the threshold diverged, this would no longer isolate
    "goal context vs realized capture"; it would be another two-axis contrast of
    the kind SO-SCEN-OBJ was built to decompose.
    """

    catalog = load_match_contract_catalog(Path("contracts_data"))
    asym = catalog.arenas[_ASYM_ARENA_ID]
    decoy = catalog.arenas[_DECOY_ARENA_ID]

    for field in _HELD_FIELDS:
        assert getattr(decoy, field) == getattr(asym, field), (
            f"field {field!r} diverged between {_ASYM_ARENA_ID} and "
            f"{_DECOY_ARENA_ID}; the SO-OBJ-DECOY arm requires everything except "
            "objective_scoring to be byte-equal"
        )

    # Derived terrain must match too, not just the authored rect list.
    assert decoy.obstacle_cells == asym.obstacle_cells

    # The ONLY differences are identity + the toggled axis.
    assert decoy.arena_id != asym.arena_id
    assert decoy.objective_scoring != asym.objective_scoring


def test_decoy_pilot_prompt_stream_is_byte_identical_to_scoring_arena() -> None:
    """What the pilot READS is unchanged, proven through the real runner.

    This is the whole isolation: if the decoy mode leaked into the observation
    (an absent objectives block, a suppressed scoreboard, an extra flag), the
    arm would be measuring blindness rather than a goal without a payout, and
    would collapse into a slower ``foundry_60_asym_v1_noobj``.

    The comparison is exact because neither run captures an objective — both
    seats hold their spawn, 48 cells apart from each other and far from all
    three cells — so the scoring arena has nothing to pay and the two streams
    can be compared byte for byte.  Where capture DOES occur the streams
    legitimately diverge (own_vp moves on one and not the other); that
    divergence is the manipulation, and it is proven separately in
    ``tests/match/test_objective_scoring_decoy.py``.
    """

    scoring_prompts = _prompt_stream(_ASYM_ARENA_ID)
    decoy_prompts = _prompt_stream(_DECOY_ARENA_ID)

    assert decoy_prompts == scoring_prompts
    # Non-vacuity: the compared prompts actually CARRY the objectives block, so
    # equality is not two objective-free strings agreeing.
    assert "OBJECTIVES" in decoy_prompts[0]
    assert "first to 15 VP wins" in decoy_prompts[0]
    assert "objective.west_yard" in decoy_prompts[0]


def test_decoy_overlay_still_deals_a_utility_pile() -> None:
    """Every seat is dealt a positive utility quota and the pack is selected."""

    overlay = load_application_overlay(_DECOY_OVERLAY)
    card_binding = overlay.contracts.card_catalog
    assert card_binding is not None
    deck_policy = card_binding.deck_policy
    assert deck_policy is not None
    assert deck_policy.seats, "the deck policy must declare seats"
    for seat in deck_policy.seats:
        assert seat.utility_deck_id is not None
        assert seat.hand_quota.utility > 0

    utility_pack = overlay.contracts.utility_handler_pack
    assert utility_pack is not None
    assert tuple(utility_pack.handler_ids) == (
        "utility.smoke.v1",
        "utility.chaff.v1",
        "utility.flares.v1",
    )


def test_decoy_overlay_inherits_asym_provider_and_retry_verbatim() -> None:
    """The provider block is the SAME one the ASYM baseline ran 30 matches on."""

    decoy_provider = _qwen35_provider(load_application_overlay(_DECOY_OVERLAY))
    asym_provider = _qwen35_provider(load_application_overlay(_ASYM_OVERLAY))

    assert decoy_provider.retry.max_attempts == 1
    assert decoy_provider.retry == asym_provider.retry
    assert decoy_provider.timeout_seconds == asym_provider.timeout_seconds
    assert decoy_provider == asym_provider


def test_decoy_overlay_only_differs_from_asym_by_arena_binding() -> None:
    """The single free variable across the two lanes is the arena binding.

    Everything the match runtime consumes — providers/retry, the deck policy
    (piles, over-deal quotas), and the utility handler pack — is identical to
    the ASYM overlay; only ``arena_id`` differs.  The ``.onex_state`` path stems
    also differ, but the battery driver rewrites every durable path from
    ``--state-root``, so those strings never reach the runtime.
    """

    decoy = load_application_overlay(_DECOY_OVERLAY)
    asym = load_application_overlay(_ASYM_OVERLAY)

    assert decoy.contracts.arena_id == _DECOY_ARENA_ID
    assert asym.contracts.arena_id == _ASYM_ARENA_ID

    assert decoy.llm.providers == asym.llm.providers
    assert decoy.contracts.card_catalog is not None
    assert asym.contracts.card_catalog is not None
    assert decoy.contracts.card_catalog.deck_policy == asym.contracts.card_catalog.deck_policy
    assert decoy.contracts.utility_handler_pack == asym.contracts.utility_handler_pack
    assert decoy.contracts.pilot_registry_dir == asym.contracts.pilot_registry_dir
    assert decoy.contracts.balance_rule_pack == asym.contracts.balance_rule_pack


def test_no_utility_incentive_is_bound_on_the_decoy_lane() -> None:
    """A bounty here would be a configured no-op, and composition rejects it.

    Recorded as a test rather than a comment because the failure mode is
    silent-by-construction on every other lane: the SO-UTIL-MECH bounty pays
    into ``vp_totals``, which a decoy arena never settles.
    """

    overlay = load_application_overlay(_DECOY_OVERLAY)
    assert overlay.contracts.utility_incentive is None
