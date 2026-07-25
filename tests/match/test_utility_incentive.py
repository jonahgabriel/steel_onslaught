"""SO-UTIL-MECH — the structural in-register utility incentive.

What this file proves, in the order the mechanism has to earn trust:

A. **Default OFF is byte-stable.**  Two goldens under ``tests/match/golden/``
   were MINTED FROM ``main`` (the pre-incentive tree) by the shared builder in
   ``tests.match.utility_incentive_fixtures``, which is importable on both
   trees.  With no incentive bound, this tree must reproduce those bytes
   exactly — the serialized programming prompt and the ``MATCH_STARTED``
   payload.  A golden minted from the new code's own output would prove
   nothing; these were not.

B. **Enabling it changes exactly the designed fields, deterministically.**
   The off/on prompt diff is asserted key-by-key: one new top-level
   ``incentives`` block and one new ``deploy_vp_bounty`` number per card row,
   nothing else, with the utility row paying the bounty and every other row
   reading 0.

C. **The reward is structural, not cosmetic.**  A resolved ``UTILITY_DEPLOYED``
   pays VP into the same ``vp_totals`` objective control scores into, against
   the same ``vp_threshold``, and a bus-less refold of the identical stream
   reproduces the state (replay identity).  Off, the same stream pays nothing.

D. **It is fail-closed.**  An incentive on an arena that cannot settle VP is
   rejected at the payload boundary rather than paying into a total nothing
   reads.

E. **Zero prompt leakage.**  No instruction text, persona prompt, or
   code-owned block gains a single byte — asserted against the module's own
   published digests and by scanning every prompt-carrying constant/contract
   for the incentive vocabulary.  This is the experimental point: L-GATE-2
   already showed telling this model what to value does not move its
   drafting, so the arm must present the reward as state, not as advice.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import ulid
from omnibase_core.models.common.model_envelope import ModelEnvelope
from pydantic import ValidationError

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.contracts.arena import ModelSOArenaSpec
from steel_onslaught.contracts.incentive import ModelSOUtilityIncentive
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.events.payloads import ModelSOMatchStartedPayload
from steel_onslaught.llm import programming as llm_programming
from steel_onslaught.llm.personas import Persona
from steel_onslaught.llm.programming import (
    PROGRAMMING_INSTRUCTIONS_SHA256,
    SPATIAL_GRID_INSTRUCTIONS_SHA256,
    SPATIAL_SCAFFOLD_INSTRUCTIONS_SHA256,
    _serialize_programming_observation,
    programming_system_prompt,
)
from steel_onslaught.match.fold import MatchContractCatalog, MatchStateFold
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from tests.match.utility_incentive_fixtures import (
    MATCH_ID,
    VP_THRESHOLD,
    arena_payload,
    match_started_payload,
    pilot_observation,
    programming_observation,
)
from tests.runtime import TestRuntime as _TestRuntime
from tests.runtime import runtime_dependencies

_GOLDEN_DIR = Path(__file__).parent / "golden"
_MATCH_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")
_BOUNTY = 2


def _incentive(vp_per_deploy: int = _BOUNTY) -> ModelSOUtilityIncentive:
    return ModelSOUtilityIncentive(vp_per_deploy=vp_per_deploy)


# ---------------------------------------------------------------------------
# A. Default OFF is byte-stable against goldens minted from the pre-change tree
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_incentive_off_programming_prompt_matches_pre_change_golden() -> None:
    """The exact prompt bytes ``main`` produced, reproduced with no incentive bound."""

    golden = (_GOLDEN_DIR / "utility_incentive_off_prompt.json").read_text(encoding="utf-8")
    assert _serialize_programming_observation(programming_observation()) == golden


@pytest.mark.unit
def test_incentive_off_match_started_payload_matches_pre_change_golden() -> None:
    """An incentive-free MATCH_STARTED re-serializes to the pre-change bytes."""

    golden = (_GOLDEN_DIR / "utility_incentive_off_match_started.json").read_text(encoding="utf-8")
    payload = ModelSOMatchStartedPayload.model_validate(match_started_payload())
    assert payload.utility_incentive is None
    dumped = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    assert dumped == golden
    # The optional field must not merely default to None — it must be ABSENT
    # from the serialized payload, or every historical ledger's re-dump drifts.
    assert "utility_incentive" not in json.loads(dumped)


@pytest.mark.unit
def test_incentive_off_observation_has_no_incentive_state() -> None:
    assert programming_observation().utility_incentive is None


# ---------------------------------------------------------------------------
# B. Enabled changes exactly the designed fields, deterministically
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_incentive_adds_exactly_the_designed_prompt_fields() -> None:
    """Off -> on changes the ``incentives`` block and the per-card bounty. Nothing else."""

    off = json.loads(_serialize_programming_observation(programming_observation()))
    on = json.loads(_serialize_programming_observation(programming_observation(_incentive())))

    assert set(on) - set(off) == {"incentives"}
    assert set(off) - set(on) == set()
    assert on["incentives"] == {
        "utility_deploy_vp_bounty": _BOUNTY,
        "own_vp": 2,
        "enemy_vp": 1,
        "vp_threshold": VP_THRESHOLD,
    }

    for section in ("legal_hand", "hand"):
        assert len(on[section]) == len(off[section])
        for on_row, off_row in zip(on[section], off[section], strict=True):
            assert set(on_row) - set(off_row) == {"deploy_vp_bounty"}
            # Everything else on the row — including the nested card
            # definition — is untouched.
            assert {k: v for k, v in on_row.items() if k != "deploy_vp_bounty"} == off_row
            expected = _BOUNTY if on_row["definition"]["category"] == "utility" else 0
            assert on_row["deploy_vp_bounty"] == expected

    # Every other top-level block is byte-identical.
    for key in set(off) - {"legal_hand", "hand"}:
        assert on[key] == off[key], f"incentive perturbed unrelated block {key!r}"


@pytest.mark.unit
def test_bounty_is_emitted_on_every_card_row_not_only_utility_rows() -> None:
    """A number only present where positive reads as a tag, not a comparable stat."""

    on = json.loads(_serialize_programming_observation(programming_observation(_incentive())))
    categories = {
        row["definition"]["category"]: row["deploy_vp_bounty"] for row in on["legal_hand"]
    }
    assert categories == {"utility": _BOUNTY, "movement": 0, "attack": 0}


@pytest.mark.unit
def test_incentive_render_is_deterministic_across_two_runs() -> None:
    """Two independent constructions of the same state serialize to the same bytes."""

    first = _serialize_programming_observation(programming_observation(_incentive()))
    second = _serialize_programming_observation(programming_observation(_incentive()))
    assert first == second
    # And a different rate produces a different, still-deterministic render:
    other = _serialize_programming_observation(programming_observation(_incentive(5)))
    assert other != first
    assert other == _serialize_programming_observation(programming_observation(_incentive(5)))


@pytest.mark.unit
def test_incentive_rate_is_positive_or_absent() -> None:
    """'Configured' and 'off' must never be the same state."""

    with pytest.raises(ValidationError):
        ModelSOUtilityIncentive(vp_per_deploy=0)
    with pytest.raises(ValidationError):
        ModelSOUtilityIncentive(vp_per_deploy=-1)


# ---------------------------------------------------------------------------
# C. The reward is structural: the fold pays it, and replay re-derives it
# ---------------------------------------------------------------------------


def _objective_arena() -> ModelSOArenaSpec:
    payload = arena_payload()
    return ModelSOArenaSpec.model_validate(
        {
            **{k: v for k, v in payload.items() if k != "kind"},
            "kind": "steel_onslaught.arena",
            "display_name": "Utility incentive arena",
            "rects": [],
        }
    )


def _runtime_with(arena: ModelSOArenaSpec) -> _TestRuntime:
    runtime = runtime_dependencies()
    return _TestRuntime(
        event_factory=runtime.event_factory,
        catalog=MatchContractCatalog(
            arenas={**runtime.catalog.arenas, arena.arena_id: arena},
            chassis=runtime.catalog.chassis,
            boilers=runtime.catalog.boilers,
            sensors=runtime.catalog.sensors,
            weapons=runtime.catalog.weapons,
            gizmos=runtime.catalog.gizmos,
            transitions=runtime.catalog.transitions,
        ),
        arena=arena,
    )


def _env(
    event_type: SOEventType,
    *,
    tick: int,
    subject: ModelSOEventSubject = _MATCH_SUBJECT,
    payload: dict[str, Any] | None = None,
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=ulid.new().str,
        match_id=MATCH_ID,
        tick=tick,
        sequence_in_tick=0,
        event_type=event_type,
        producer_node="node.test",
        subject=subject,
        payload=payload or {},
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
            entity_id=MATCH_ID,
            emitted_at=datetime.now(UTC),
        ),
    )


def _deploy_event(tick: int, *, player_id: str, mech_id: str) -> ModelSOEventEnvelope:
    return _env(
        SOEventType.UTILITY_DEPLOYED,
        tick=tick,
        subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
        payload={
            "card_id": "card.utility.smoke",
            "utility_kind": "smoke",
            "origin": {"x": 5, "y": 5},
            "radius": 2,
            "duration_ticks": 2,
        },
    )


def _start(
    bus: InProcessEventBus,
    runtime: _TestRuntime,
    *,
    incentive: ModelSOUtilityIncentive | None,
) -> tuple[MatchStateFold, list[ModelSOEventEnvelope], ModelSOEventEnvelope]:
    captured: list[ModelSOEventEnvelope] = []
    bus.subscribe(captured.append)
    fold = MatchStateFold(
        MATCH_ID,
        UUID("11111111-1111-1111-1111-111111111111"),
        bus=bus,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )
    bus.subscribe(fold.handle)
    started = _env(
        SOEventType.MATCH_STARTED,
        tick=0,
        payload=match_started_payload(
            None if incentive is None else incentive.model_dump(mode="json")
        ),
    )
    bus.publish(started)
    assert fold.state.status is SOMatchStatus.RUNNING
    return fold, captured, started


@pytest.mark.unit
def test_resolved_utility_deploy_pays_the_vp_bounty() -> None:
    runtime = _runtime_with(_objective_arena())
    bus = InProcessEventBus()
    fold, _captured, _started = _start(bus, runtime, incentive=_incentive())

    assert fold.state.vp_totals == {"player.blue": 0, "player.red": 0}
    bus.publish(_deploy_event(1, player_id="player.red", mech_id="mech.red.01"))
    assert fold.state.vp_totals == {"player.blue": 0, "player.red": _BOUNTY}
    bus.publish(_deploy_event(2, player_id="player.blue", mech_id="mech.blue.01"))
    assert fold.state.vp_totals == {"player.blue": _BOUNTY, "player.red": _BOUNTY}


@pytest.mark.unit
def test_same_stream_pays_nothing_when_the_incentive_is_absent() -> None:
    """The ONLY difference is the MATCH_STARTED field; the deploys are identical."""

    runtime = _runtime_with(_objective_arena())
    bus = InProcessEventBus()
    fold, _captured, _started = _start(bus, runtime, incentive=None)

    bus.publish(_deploy_event(1, player_id="player.red", mech_id="mech.red.01"))
    bus.publish(_deploy_event(2, player_id="player.red", mech_id="mech.red.01"))
    assert fold.state.vp_totals == {"player.blue": 0, "player.red": 0}
    # The utility effect itself still folds — only the reward is off.
    assert len(fold.state.active_utility_effects) == 2


@pytest.mark.unit
def test_bounty_alone_reaches_the_threshold_and_declares_victory() -> None:
    """Structural, not cosmetic: bounty VP settles the match on its own.

    No objective is ever held in this stream, so the pre-incentive code would
    never evaluate the threshold at all — the settlement path is the reason
    ``_score_objectives`` also drains the bounty flag.
    """

    runtime = _runtime_with(_objective_arena())
    bus = InProcessEventBus()
    fold, captured, _started = _start(bus, runtime, incentive=_incentive())

    deploys = VP_THRESHOLD // _BOUNTY
    for tick in range(1, deploys + 1):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))
        bus.publish(_deploy_event(tick, player_id="player.red", mech_id="mech.red.01"))
    assert fold.state.vp_totals["player.red"] == VP_THRESHOLD
    # Still running: VP mutates on the deploy, the threshold settles on the
    # next MATCH_TICK derivation.
    assert fold.state.status is SOMatchStatus.RUNNING

    bus.publish(_env(SOEventType.MATCH_TICK, tick=deploys + 1))

    declared = [e for e in captured if e.event_type is SOEventType.VICTORY_DECLARED]
    assert len(declared) == 1
    assert declared[0].payload["winner_player_id"] == "player.red"
    assert declared[0].payload["reason"] == SOMatchEndReason.VP_THRESHOLD.value
    assert not [e for e in captured if e.event_type is SOEventType.OBJECTIVE_SCORED]


@pytest.mark.unit
def test_bounty_vp_replays_identically_from_the_ledger_alone() -> None:
    """A bus-less refold of the SAME stream reproduces the VP totals.

    This is the property that forced the rate onto ``MATCH_STARTED``: the
    replay fold is handed no overlay and no config, only the recorded events.
    """

    runtime = _runtime_with(_objective_arena())
    bus = InProcessEventBus()
    fold, captured, _started = _start(bus, runtime, incentive=_incentive())
    for tick in (1, 2):
        bus.publish(_env(SOEventType.MATCH_TICK, tick=tick))
        bus.publish(_deploy_event(tick, player_id="player.red", mech_id="mech.red.01"))
    bus.publish(_env(SOEventType.MATCH_TICK, tick=3))
    bus.publish(_deploy_event(3, player_id="player.blue", mech_id="mech.blue.01"))
    bus.publish(_env(SOEventType.MATCH_TICK, tick=4))
    live = fold.state

    replay = MatchStateFold(
        MATCH_ID,
        UUID("11111111-1111-1111-1111-111111111111"),
        bus=None,
        event_factory=runtime.event_factory,
        catalog=runtime.catalog,
    )
    for event in list(captured):
        replay.apply(event)

    assert replay.state.vp_totals == live.vp_totals
    assert replay.state.vp_totals == {"player.blue": _BOUNTY, "player.red": 2 * _BOUNTY}
    assert replay.state.status is live.status


# ---------------------------------------------------------------------------
# D. Fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_incentive_is_rejected_on_an_arena_that_cannot_settle_vp() -> None:
    """Paying into a VP total no arena reads is the 'configured but inert' class."""

    payload = match_started_payload(_incentive().model_dump(mode="json"))
    payload["arena"] = {**arena_payload(), "objectives": [], "vp_threshold": None}
    with pytest.raises(ValidationError, match="objectives and vp_threshold"):
        ModelSOMatchStartedPayload.model_validate(payload)


def _overlay_raw(tmp_path: Path, *, contracts_extra: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    return {
        "schema_version": "1",
        "bus": {"kind": "in_process"},
        "event_ledger": {
            "kind": "sqlite",
            "path": tmp_path / "events.sqlite",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
        },
        "leaderboard": {
            "kind": "sqlite",
            "path": tmp_path / "leaderboard.sqlite",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "storage_schema": "leaderboard_v1",
        },
        "learning_artifacts": {
            "kind": "filesystem_yaml",
            "evaluation_root": tmp_path / "evaluations",
            "lineage_root": tmp_path / "lineage",
        },
        "evaluation_storage": {
            "kind": "sqlite",
            "root": tmp_path / "evaluations",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
            "leaderboard_schema": "leaderboard_v1",
        },
        "contracts": {
            "catalog_dir": repo_root / "contracts_data",
            "pilot_registry_dir": repo_root / "contracts_data/pilots",
            **contracts_extra,
        },
        "clock": {"kind": "system_utc"},
        "identity": {"kind": "system"},
    }


@pytest.mark.unit
def test_composition_rejects_an_incentive_without_card_mode(tmp_path: Path) -> None:
    """Utility cards only exist on the split deck; no card mode, no trigger."""

    from steel_onslaught.contracts.application import ModelSOApplicationOverlay
    from steel_onslaught.match.composition import build_runtime_dependencies
    from tests.overlay import complete_test_overlay

    raw = _overlay_raw(
        tmp_path,
        contracts_extra={
            "utility_incentive": {"kind": "utility_deploy_vp_bounty", "vp_per_deploy": 2}
        },
    )
    overlay = ModelSOApplicationOverlay.model_validate(complete_test_overlay(raw, tmp_path))
    assert overlay.contracts.utility_incentive is not None
    with pytest.raises(ValueError, match="requires an explicitly enabled card catalog"):
        build_runtime_dependencies(overlay)


# ---------------------------------------------------------------------------
# E. Zero prompt leakage — the incentive is state, never instruction
# ---------------------------------------------------------------------------

# Vocabulary that must never appear in prompt TEXT. The values are rendered
# as JSON numbers under these key names; the keys themselves live only in the
# serializer, never in an English sentence handed to the model.
_INCENTIVE_VOCAB = (
    "deploy_vp_bounty",
    "utility_deploy_vp_bounty",
    "vp_per_deploy",
    "bounty",
    "incentive",
    "reward",
)


@pytest.mark.unit
def test_code_owned_instruction_digests_are_unchanged() -> None:
    """The wire-contract blocks are hash-locked; the incentive touched none of them."""

    # Read off the pre-incentive tree (``main`` @ 7787cea) and pinned here, so
    # any future edit to a code-owned instruction block has to change this
    # test deliberately.
    assert (
        PROGRAMMING_INSTRUCTIONS_SHA256
        == "afb0ea8772a5a1b37ff4bfeaadaddf7641b916fd95e0c9f0382e0e7bd93675dc"
    )
    assert (
        SPATIAL_GRID_INSTRUCTIONS_SHA256
        == "2c6bcf3e11d6e3bb7e35f26b4cf5c27f6093efe473b7494cc394fb29830ee46b"
    )
    assert (
        SPATIAL_SCAFFOLD_INSTRUCTIONS_SHA256
        == "dd24c2854f4c6e3ed814e10dd709dd30e650c681543778be05ec625edbb6c4da"
    )


@pytest.mark.unit
def test_no_incentive_vocabulary_in_any_prompt_text() -> None:
    """Neither the code-owned blocks nor a persona prompt mention the reward."""

    blocks = (
        llm_programming._PROGRAMMING_INSTRUCTIONS,
        llm_programming._SPATIAL_GRID_INSTRUCTIONS,
        llm_programming._SPATIAL_SCAFFOLD_INSTRUCTIONS,
        llm_programming._PROGRAMMING_REPAIR_INSTRUCTIONS,
    )
    for block in blocks:
        lowered = block.lower()
        for token in _INCENTIVE_VOCAB:
            assert token not in lowered, f"incentive vocabulary {token!r} leaked into prompt text"

    persona_dir = Path(__file__).resolve().parents[2] / "contracts_data" / "pilots" / "personas"
    persona_files = sorted(persona_dir.glob("*.yaml"))
    assert persona_files, "persona prompt contracts not found — leakage scan would be vacuous"
    for path in persona_files:
        lowered = path.read_text(encoding="utf-8").lower()
        for token in _INCENTIVE_VOCAB:
            assert token not in lowered, f"{token!r} leaked into persona prompt {path.name}"


@pytest.mark.unit
def test_system_prompt_is_byte_identical_with_and_without_an_incentive() -> None:
    """The incentive lives in the USER payload's state, never in the system prompt.

    The system prompt does not even take the incentive as an input — asserted
    here so a future refactor that threads it in has to delete this test on
    purpose rather than by accident.
    """

    persona = Persona(
        persona_id="berserker",
        display_name="Berserker",
        system_prompt="Close and destroy.",
        temperature=0.4,
    )
    baseline = programming_system_prompt(persona)
    assert baseline == programming_system_prompt(persona)
    for token in _INCENTIVE_VOCAB:
        assert token not in baseline.lower()


@pytest.mark.unit
def test_incentive_block_carries_no_prose() -> None:
    """Unlike ``objectives``, the incentive block has no ``rule`` sentence.

    The O-GATE battery measured the cost of an imperative inside the user
    payload (11/413 completions answered the imperative instead of the wire
    contract). This arm's block is numbers only — which is also the thing
    that makes it a test of state-reading rather than of instruction-following.
    """

    on = json.loads(_serialize_programming_observation(programming_observation(_incentive())))
    assert "rule" in on["objectives"]  # the pre-existing block, unchanged
    for value in on["incentives"].values():
        assert isinstance(value, int), "incentive block must carry numbers only, never prose"


# ---------------------------------------------------------------------------
# F. The config path is wired end to end (never "configured but inert")
# ---------------------------------------------------------------------------


def _seat_request(seat: str) -> Any:
    from steel_onslaught.cards.dealer import ModelSODealerScope
    from steel_onslaught.match.card_adapter import ModelSOCardSeatRequest

    return ModelSOCardSeatRequest(
        seat=seat,
        dealer_scope=ModelSODealerScope(
            match_id=MATCH_ID,
            match_seed=77,
            tick=3,
            seat=seat,
        ),
        pilot_observation=pilot_observation(),
        initiative=1,
        weapon_ids=("weapon.test.primary",),
    )


class _CapturingProgrammer:
    """Records the observation the adapter actually handed the pilot."""

    def __init__(self) -> None:
        self.observations: list[Any] = []

    def program(self, observation: Any) -> Any:
        from steel_onslaught.events.card_payloads import (
            ModelSOPlanCommittedPayload,
            ModelSOPlanRegister,
        )

        self.observations.append(observation)
        return ModelSOPlanCommittedPayload(
            seat=observation.seat,
            registers=tuple(
                ModelSOPlanRegister(register_index=index, card_id=card_id)
                for index, card_id in zip(observation.free_indices, observation.hand, strict=False)
            ),
            rationale="capturing test program",
            confidence=1.0,
        )


@pytest.mark.parametrize("bound", (True, False))
@pytest.mark.unit
def test_adapter_threads_the_incentive_onto_the_observation_it_builds(bound: bool) -> None:
    """The overlay -> adapter -> observation seam, driven through the real adapter.

    A field the composition sets but the observation never carries would make
    every battery measure the baseline while reporting the arm.
    """

    from steel_onslaught.match.composition import build_card_runner_adapter
    from tests.match.utility_incentive_fixtures import card_runtime_snapshot

    programmer = _CapturingProgrammer()
    incentive = _incentive() if bound else None
    adapter = build_card_runner_adapter(
        snapshot=card_runtime_snapshot(),
        programmers={"red": programmer},
        utility_incentive=incentive,
    )
    adapter.produce(
        seats=(_seat_request("red"),),
        round_index=0,
        tick=3,
        causation_id="round.test.0",
    )

    assert len(programmer.observations) == 1
    assert programmer.observations[0].utility_incentive == incentive


@pytest.mark.unit
def test_shipped_arm_overlay_binds_the_incentive_and_nothing_else() -> None:
    """The arm overlay differs from its baseline ONLY by the incentive + ledger paths."""

    import yaml  # type: ignore[import-untyped]

    from steel_onslaught.match.composition import load_application_overlay

    root = Path(__file__).resolve().parents[2]
    overlays = root / "contracts_data" / "overlays"
    arm_path = overlays / "tactical_split_overdeal_utility_asym_incentive_vp2_qwen.yaml"
    base_path = overlays / "tactical_split_overdeal_utility_asym_v1_qwen.yaml"

    arm = load_application_overlay(arm_path)
    assert arm.contracts.utility_incentive is not None
    assert arm.contracts.utility_incentive.kind == "utility_deploy_vp_bounty"
    assert arm.contracts.utility_incentive.vp_per_deploy == 2

    base = load_application_overlay(base_path)
    assert base.contracts.utility_incentive is None

    # The raw contracts blocks must be identical apart from the one binding —
    # an arm that silently also moved the arena or the deck quota would not be
    # a single-axis manipulation.
    arm_raw = yaml.safe_load(arm_path.read_text(encoding="utf-8"))["contracts"]
    base_raw = yaml.safe_load(base_path.read_text(encoding="utf-8"))["contracts"]
    assert arm_raw.pop("utility_incentive") == {
        "kind": "utility_deploy_vp_bounty",
        "vp_per_deploy": 2,
    }
    assert arm_raw == base_raw

    # And the arena it names must be able to settle VP, or the bounty is inert.
    arena_path = root / "contracts_data" / "arenas" / f"{arm.contracts.arena_id}.yaml"
    arena_raw = yaml.safe_load(arena_path.read_text(encoding="utf-8"))
    assert arena_raw["objectives"]
    assert arena_raw["vp_threshold"] > 0


@pytest.mark.unit
def test_arm_overlay_ledger_paths_are_isolated_from_the_baseline() -> None:
    """A shared ledger path would merge two arms' evidence into one database."""

    root = Path(__file__).resolve().parents[2]
    overlays = root / "contracts_data" / "overlays"
    arm = (overlays / "tactical_split_overdeal_utility_asym_incentive_vp2_qwen.yaml").read_text(
        encoding="utf-8"
    )
    assert "tactical_split_overdeal_utility_asym_v1_qwen/" not in arm
    assert "util_incentive_vp2/" in arm
