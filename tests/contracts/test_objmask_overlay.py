"""Single-axis proof for the SO-OBJ-MASK masked-objective-display arm.

``tactical_split_overdeal_utility_asym_v1_objmask_qwen.yaml`` +
``foundry_60_asym_v1_objmask.yaml`` are the live-stakes complement to
SO-OBJ-DECOY (``tests/contracts/test_objdecoy_overlay.py``, PR #210/#212).
DECOY held the pilot's VIEW of objectives fixed and removed the payout;
this arm holds the payout fixed (the fold scores VP exactly as
``foundry_60_asym_v1``) and removes only what the pilot is TOLD.

Two claims are load-bearing here, mirrored and inverted from DECOY's own two:

  1. everything except the display mode is held constant against
     ``foundry_60_asym_v1`` field by field, INCLUDING the objectives tuple and
     ``vp_threshold`` -- proven by
     ``test_objmask_arena_holds_geometry_and_objectives_exactly_constant``; and
  2. the observation the pilot reads is the SAME shape a no-objectives arena
     already produces -- proven by
     ``test_objmask_pilot_prompt_stream_is_byte_identical_to_noobj_arena``,
     which runs a REAL match on each arena through the real runner and
     compares the serialized pilot prompts tick by tick.

The payout half of the arm (real VP accrual, real OBJECTIVE_SCORED, a real VP
victory, all while the observation stays empty) is proven in
``tests/match/test_objective_scoring_masked.py``; this file proves the
SHIPPED contracts are the ones that carry it.
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
_MASK_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_objmask_qwen.yaml"
_ASYM_OVERLAY = _OVERLAYS / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"
_LOADOUT = Path("contracts_data/loadouts/example_aggressive_light.yaml")

_ASYM_ARENA_ID = "foundry_60_asym_v1"
_MASK_ARENA_ID = "foundry_60_asym_v1_objmask"
_NOOBJ_ARENA_ID = "foundry_60_asym_v1_noobj"
_QWEN35_PROVIDER_ID = "qwen35"

# Everything the two arenas must share.  ``objective_display`` is the toggled
# axis; ``arena_id``/``display_name`` are identity, not contract.
# ``objectives``/``vp_threshold`` are INSIDE this list, same as DECOY's own
# held-field census: the objectives are still declared and still scored here,
# only the pilot's view of them differs.
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
    "objective_scoring",
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
    that masking never reaches the observation builder differently than a
    genuinely objective-free arena does, and only driving the same call site
    the live battery drives can prove that.
    """

    catalog = load_match_contract_catalog(Path("contracts_data"))
    loadout = load_loadout(_LOADOUT)
    pilot = _HoldPilot()
    bus = InProcessEventBus()
    runner, _ = match_runner(
        bus=bus,
        match_id=f"match.test.objmask-prompt.{arena_id}",
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


def test_objmask_overlay_parses_and_binds_the_masked_arena() -> None:
    """It validates and binds an arena that HAS objectives, scores them, and
    hides them."""

    overlay = load_application_overlay(_MASK_OVERLAY)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == _MASK_ARENA_ID

    catalog = load_match_contract_catalog(overlay.contracts.catalog_dir)
    arena = catalog.arenas[overlay.contracts.arena_id]
    # The manipulation landed: objectives are PRESENT, scored normally, and
    # the display is masked.
    assert len(arena.objectives) == 3
    assert arena.vp_threshold == 15
    assert arena.objective_scoring == "scoring"
    assert arena.objective_display == "masked"

    # And the arena it was cut from still shows objectives, unmodified.
    asym_arena = catalog.arenas[_ASYM_ARENA_ID]
    assert asym_arena.objective_display == "visible"


def test_objmask_arena_holds_geometry_and_objectives_exactly_constant() -> None:
    """Only the display mode differs — the arm's load-bearing claim.

    If terrain, spawns, size, sudden death, an objective cell, a
    ``vp_per_round``, the threshold, or the SCORING mode diverged, this would
    no longer isolate "hidden incentive vs visible feedback"; it would
    confound the display axis with either a geometry change or DECOY's own
    payout axis.
    """

    catalog = load_match_contract_catalog(Path("contracts_data"))
    asym = catalog.arenas[_ASYM_ARENA_ID]
    mask = catalog.arenas[_MASK_ARENA_ID]

    for field in _HELD_FIELDS:
        assert getattr(mask, field) == getattr(asym, field), (
            f"field {field!r} diverged between {_ASYM_ARENA_ID} and "
            f"{_MASK_ARENA_ID}; the SO-OBJ-MASK arm requires everything except "
            "objective_display to be byte-equal"
        )

    # Derived terrain must match too, not just the authored rect list.
    assert mask.obstacle_cells == asym.obstacle_cells

    # The ONLY differences are identity + the toggled axis.
    assert mask.arena_id != asym.arena_id
    assert mask.objective_display != asym.objective_display


def test_objmask_pilot_prompt_stream_is_byte_identical_to_noobj_arena() -> None:
    """What the pilot READS on the masked arena is the SAME shape a genuinely
    objective-free arena already produces, proven through the real runner.

    This is the whole isolation, inverted from DECOY's own proof: DECOY showed
    the payout-suppressed arena's prompt equals the PAYING corner's prompt
    (display carried, payout didn't). This shows the display-suppressed arena's
    prompt equals the NO-OBJECTIVES corner's prompt (payout carried, display
    didn't) -- if masking leaked ANY objective/VP field into the observation,
    this equality would fail.

    The comparison is exact because neither run captures an objective — both
    seats hold their spawn, 48 cells apart from each other and far from all
    three cells — so nothing in either match's own state ever diverges from
    the objective-free baseline, and the two streams can be compared byte for
    byte.
    """

    mask_prompts = _prompt_stream(_MASK_ARENA_ID)
    noobj_prompts = _prompt_stream(_NOOBJ_ARENA_ID)

    assert mask_prompts == noobj_prompts
    # Non-vacuity: the masked run's underlying arena DOES carry objectives (it
    # is not simply another no-objectives arena in disguise) — only its
    # rendered prompt is silent about them.
    assert "OBJECTIVES" not in mask_prompts[0]
    assert "objective.west_yard" not in mask_prompts[0]
    assert "victory_points" not in mask_prompts[0]


def test_objmask_prompt_stream_delta_from_the_paying_corner_is_exactly_the_display_block() -> None:
    """Byte-level proof, run against the PAYING corner directly (the same
    proof standard #210 set): the ONLY difference between the masked prompt
    and the paying-visible prompt is the presence/absence of the objectives
    block -- nothing else in the prompt moves.

    Constructed by stripping the exact contiguous objectives span
    (``--- OBJECTIVES ... ---`` through the last per-objective line, inclusive
    of the ``victory_points`` line) out of the ASYM_OBJ prompt and asserting
    what remains is byte-identical to the masked prompt at the same tick.
    """

    asym_prompts = _prompt_stream(_ASYM_ARENA_ID)
    mask_prompts = _prompt_stream(_MASK_ARENA_ID)
    assert len(asym_prompts) == len(mask_prompts)

    for asym_prompt, mask_prompt in zip(asym_prompts, mask_prompts, strict=True):
        asym_lines = asym_prompt.split("\n")
        objectives_start = next(
            i for i, line in enumerate(asym_lines) if line.startswith("--- OBJECTIVES")
        )
        enemy_start = next(i for i, line in enumerate(asym_lines) if line.startswith("--- ENEMY"))
        # Sanity: the block is exactly [OBJECTIVES header, victory_points,
        # one line per objective] -- 3 objectives here, so 5 lines total.
        assert enemy_start - objectives_start == 5
        stripped = asym_lines[:objectives_start] + asym_lines[enemy_start:]
        assert "\n".join(stripped) == mask_prompt


def test_objmask_overlay_still_deals_a_utility_pile() -> None:
    """Every seat is dealt a positive utility quota and the pack is selected."""

    overlay = load_application_overlay(_MASK_OVERLAY)
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


def test_objmask_overlay_inherits_asym_provider_and_retry_verbatim() -> None:
    """The provider block is the SAME one the ASYM baseline ran 30 matches on."""

    mask_provider = _qwen35_provider(load_application_overlay(_MASK_OVERLAY))
    asym_provider = _qwen35_provider(load_application_overlay(_ASYM_OVERLAY))

    assert mask_provider.retry.max_attempts == 1
    assert mask_provider.retry == asym_provider.retry
    assert mask_provider.timeout_seconds == asym_provider.timeout_seconds
    assert mask_provider == asym_provider


def test_objmask_overlay_only_differs_from_asym_by_arena_binding() -> None:
    """The single free variable across the two lanes is the arena binding.

    Everything the match runtime consumes — providers/retry, the deck policy
    (piles, over-deal quotas), and the utility handler pack — is identical to
    the ASYM overlay; only ``arena_id`` differs.  The ``.onex_state`` path
    stems also differ, but the battery driver rewrites every durable path from
    ``--state-root``, so those strings never reach the runtime.
    """

    mask = load_application_overlay(_MASK_OVERLAY)
    asym = load_application_overlay(_ASYM_OVERLAY)

    assert mask.contracts.arena_id == _MASK_ARENA_ID
    assert asym.contracts.arena_id == _ASYM_ARENA_ID

    assert mask.llm.providers == asym.llm.providers
    assert mask.contracts.card_catalog is not None
    assert asym.contracts.card_catalog is not None
    assert mask.contracts.card_catalog.deck_policy == asym.contracts.card_catalog.deck_policy
    assert mask.contracts.utility_handler_pack == asym.contracts.utility_handler_pack
    assert mask.contracts.pilot_registry_dir == asym.contracts.pilot_registry_dir
    assert mask.contracts.balance_rule_pack == asym.contracts.balance_rule_pack
    # Neither lane binds a SO-UTIL-MECH bounty; this arm measures the
    # objectives-display axis alone, not a compound with the incentive arm.
    assert mask.contracts.utility_incentive is None
    assert asym.contracts.utility_incentive is None
