"""Contract tests for OMN-15488's L-GATE-2 decisive battery overlay + driver.

``tactical_split_overdeal_v1_delegation_learning.yaml`` is a NEW overlay,
authored directly on the ``onex_delegation`` provider shape -- it is NOT a
migration of ``tactical_split_overdeal_v1_qwen.yaml`` (never had an
``openai_compatible`` ancestor; see
``tests/contracts/test_overlay_delegation_migration_omn15174.py``'s census
for the corpus-level accounting). Five claims are load-bearing here:

  1. the new overlay loads cleanly via ``load_application_overlay`` and holds
     the sections the deliverable named byte-constant (arena, card content
     roots/mode/cadence, the RED programmer/deck-seat assignment, pilot
     registry dir, personas dir, balance rule pack) field-identical to
     ``tactical_split_overdeal_v1_qwen.yaml`` -- proven by
     ``test_new_overlay_holds_declared_sections_constant_vs_qwen_overlay``;
  2. its provider stanza is the ``onex_delegation`` shape, and the prepended
     pre-registration header is byte-stable and carries the pre-registered
     markers -- proven by the ``TestProviderStanzaAndPreregHeader`` tests;
  3. the mirror pairing (player.blue flies the SAME berserker persona as
     player.red) actually COMPOSES over the real ``assemble_match_live`` seam
     -- and a literal same-pilot-spec-both-seats mirror does NOT, proven by
     ``TestMirrorPairingComposition`` (see its docstring for the
     ``SeatIdentityError`` this empirically surfaced while building this
     overlay -- the reason a distinct mirror pilot spec + loadout exist);
  4. the driver's new ``--genesis`` knob flows to the baseline/post evaluator
     caps exactly as pre-registered (0.5 -> 2.5 for ``--step 2.0``), proven
     by ``TestGenesisPhaseCaps`` (with ``TestPromotePhaseCapTracksGenesisAndStep``
     proving the promote-phase cap specifically, against the real,
     pre-existing ``WinDamageDifferentialEvaluator``);
  5. ``_run_battery`` itself -- not just ``_phase_caps``/``_lane_overlay`` in
     isolation -- threads that same cap sequence into the overlay at each of
     its three phase call sites and reaches the post phase on a stubbed
     decisive promotion, proven by
     ``TestRunBatteryWiresPhaseCapsAtEveryCallSite`` (remediation round 2 --
     closes a surrogate-test gap: the round-1 tests above never actually
     called ``_run_battery``).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.run_lgate2_adaptation_battery import _build_parser, _lane_overlay
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSODelegationProviderBinding,
)
from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.payloads import ModelSOPlayerScore
from steel_onslaught.learning.evidence import ModelSOAfterMatchLearningEvidence
from steel_onslaught.learning.live_evaluator import WinDamageDifferentialEvaluator
from steel_onslaught.llm.client_http import NoSecretResolver
from steel_onslaught.match.composition import assemble_match_live, load_application_overlay

# ``_phase_caps`` is intentionally NOT imported at module scope. It is a
# wholly new symbol (OMN-15488); importing it here would make an
# ImportError against the pre-patch driver block collection of every other
# test in this module (a real defect flagged in this ticket's remediation
# round -- RED for the genesis-cap tests must not swallow the RED/GREEN
# signal of every unrelated test in the file). Each test that needs it
# imports it locally instead, so its own ImportError/AttributeError is
# scoped to exactly the tests exercising that new surface.

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"
_NEW_OVERLAY = _OVERLAYS / "tactical_split_overdeal_v1_delegation_learning.yaml"
_QWEN_OVERLAY = _OVERLAYS / "tactical_split_overdeal_v1_qwen.yaml"
_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/llm_qwen35_berserker.yaml"
_BLUE_MIRROR_LOADOUT = (
    _REPO_ROOT / "contracts_data/loadouts/qwen35/llm_qwen35_berserker_mirror_blue.yaml"
)

# Prepended from the pre-registration text handed to this build lane
# (OMN-15488 ticket amendment comment, 2026-07-30 ~15:0xZ), via the
# dispatch prompt's scratchpad reference -- NOT embedded verbatim in the
# Linear amendment comment itself (the comment states the text "is authored
# and handed to the build lane" but does not carry it; there is no durable,
# citable surface for "the handed source" beyond this build lane's own
# session artifacts). The "verbatim/byte-identical" claim in a prior PR
# revision was therefore unfalsifiable against any durable surface and has
# been withdrawn (remediation round, 2026-07-30) -- what this pin actually
# proves is narrower and honest: SELF-CONSISTENCY going forward (an edit to
# the committed header changes this hash and fails loudly), not fidelity to
# an upstream source this test has no way to check.
#
# The header text as handed also contained real defects, independently
# discovered and corrected across two remediation rounds; each is disclosed
# inline in the overlay's own header at its exact location, and this pin is
# re-taken after every correction:
#   round 1 -- the "PHASES AND SEEDS" launch command omitted
#     `--overlay`/`--blue-loadout`, which -- run as originally written --
#     would have silently executed the OLD openai_compatible overlay's
#     red-berserker-vs-sniper pairing (guaranteed NO-PROMOTION) instead of
#     this battery's onex_delegation/mirror-pairing design.
#   round 2 -- the promote-phase line still read "max_value = 3.0" after
#     round 1 made the driver's actual promote-phase cap genesis + step
#     (`_phase_caps`); arithmetically inert for this battery's own config
#     (2.5 <= both 3.0 and 2.5) but a mismatch between the pre-registration
#     of record and the executing configuration -- corrected to 2.5.
#   round 3 -- pre-launch AMENDMENT block appended verbatim (per the
#     display-salience precedent for post-filing, pre-first-scored-match
#     amendments): the canary's SCHEMA_VIOLATION root cause superseded
#     (contract mis-selection, not persona-vocabulary echo -- OMN-15522),
#     the executing driver command pinned in full (state-root discipline),
#     and the AC6 ledger-provider-literal correction. This is a genuine
#     content change to the pre-registration of record -- not an inline
#     defect correction -- so the pin is re-taken to cover the amended
#     header rather than left stale against pre-amendment text.
_PREREG_HEADER_SHA256 = "36c8a569c87ca599ecd48a847da31bf00002d82982ce23dc4acfcf954174589c"

_PREREG_MARKERS = (
    "PRE-REGISTERED HYPOTHESES",
    "D_ws",
    "D_vent",
    "NO-PROMOTION",
    "CEILING",
    "terminal for the prompt-guidance mechanism",
)


def _raw_overlay(path: Path) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw


def _header_block(path: Path) -> list[str]:
    """Every leading ``#``-prefixed line, in order, before the first YAML key."""
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# 1. Held-constant sections vs the qwen overlay
# ---------------------------------------------------------------------------


def test_new_overlay_parses_via_load_application_overlay() -> None:
    """AC(a): the overlay loads cleanly through the real typed loader."""
    overlay = load_application_overlay(_NEW_OVERLAY)
    assert isinstance(overlay, ModelSOApplicationOverlay)
    assert overlay.contracts.arena_id == "foundry_60"
    assert overlay.contracts.card_catalog is not None
    assert overlay.contracts.card_catalog.card_mode_enabled is True


def test_new_overlay_holds_declared_sections_constant_vs_qwen_overlay() -> None:
    """Deliverable text: arena/cards/pilot registry/personas/balance sections
    are byte-constant vs ``tactical_split_overdeal_v1_qwen.yaml``. The RED
    seat's card-catalog assignment (programmer + deck-policy archetype) is
    ALSO held constant -- only the BLUE seat's mirror-pairing assignment is a
    deliberate, disclosed delta (see ``TestMirrorPairingComposition``).

    ``pilot_registry_dir`` itself is the ONE named-constant field that
    deliberately differs (a dedicated directory, not the shared
    ``fire_dense_qwen/`` -- see
    ``test_pilot_registry_dir_is_dedicated_not_shared_but_holds_identical_red_spec_content``
    for why and for the byte-identity proof over its actual content)."""
    new = load_application_overlay(_NEW_OVERLAY)
    qwen = load_application_overlay(_QWEN_OVERLAY)

    assert new.contracts.catalog_dir == qwen.contracts.catalog_dir
    assert new.contracts.arena_id == qwen.contracts.arena_id
    assert new.contracts.balance_rule_pack == qwen.contracts.balance_rule_pack
    assert new.llm.personas_dir == qwen.llm.personas_dir

    new_cc, qwen_cc = new.contracts.card_catalog, qwen.contracts.card_catalog
    assert new_cc is not None and qwen_cc is not None
    assert new_cc.kind == qwen_cc.kind
    assert new_cc.cards_dir == qwen_cc.cards_dir
    assert new_cc.decks_dir == qwen_cc.decks_dir
    assert new_cc.card_mode_enabled == qwen_cc.card_mode_enabled
    assert new_cc.card_cadence == qwen_cc.card_cadence
    assert new_cc.deck_policy is not None and qwen_cc.deck_policy is not None
    assert new_cc.deck_policy.schema_version == qwen_cc.deck_policy.schema_version
    assert new_cc.deck_policy.kind == qwen_cc.deck_policy.kind

    new_seats = {seat.side: seat for seat in new_cc.deck_policy.seats}
    qwen_seats = {seat.side: seat for seat in qwen_cc.deck_policy.seats}
    # RED seat: fully byte-constant, including its archetype label.
    assert new_seats["red"] == qwen_seats["red"]
    # BLUE seat: hand_quota/register_count/deck ids constant; ONLY archetype
    # differs (sniper -> berserker, the mirror-pairing manipulation).
    assert new_seats["blue"].movement_deck_id == qwen_seats["blue"].movement_deck_id
    assert new_seats["blue"].weapon_deck_id == qwen_seats["blue"].weapon_deck_id
    assert new_seats["blue"].hand_quota == qwen_seats["blue"].hand_quota
    assert new_seats["blue"].register_count == qwen_seats["blue"].register_count
    assert qwen_seats["blue"].archetype == "sniper"
    assert new_seats["blue"].archetype == "berserker"

    new_programmers = {p.side: p for p in new_cc.programmers}
    qwen_programmers = {p.side: p for p in qwen_cc.programmers}
    # RED programmer assignment is byte-constant.
    assert new_programmers["red"] == qwen_programmers["red"]
    # BLUE programmer is the deliberate mirror-pairing delta.
    assert qwen_programmers["blue"].pilot_spec_id == "pilot.llm.qwen35_sniper"
    assert new_programmers["blue"].pilot_spec_id == "pilot.llm.qwen35_berserker_mirror_blue"


def test_new_overlay_does_not_modify_the_shared_fire_dense_qwen_registry() -> None:
    """Every pilot spec the qwen overlay's programmers reference still
    exists byte-unmodified in the SHARED ``fire_dense_qwen/`` registry, and
    that directory gained NO new file from this ticket (asserted by file
    count, not just content) -- the whole reason this overlay uses its own
    dedicated registry directory instead of adding to the shared one."""
    registry_dir = load_application_overlay(_QWEN_OVERLAY).contracts.pilot_registry_dir
    berserker = _raw_overlay(registry_dir / "llm_qwen35.yaml")
    sniper = _raw_overlay(registry_dir / "llm_qwen35_sniper.yaml")
    assert berserker["parameters"] == {"persona": "berserker", "provider": "qwen35"}
    assert sniper["parameters"] == {"persona": "sniper", "provider": "qwen35"}
    # No mirror-pairing spec (or anything else new) leaked into the shared dir.
    assert sorted(p.name for p in registry_dir.glob("*.yaml")) == [
        "llm_qwen35.yaml",
        "llm_qwen35_berserker_guided.yaml",
        "llm_qwen35_berserker_spatial_r1.yaml",
        "llm_qwen35_berserker_spatial_r2.yaml",
        "llm_qwen35_sniper.yaml",
        "llm_qwen35_sniper_spatial_r1.yaml",
        "llm_qwen35_sniper_spatial_r2.yaml",
    ]


def test_pilot_registry_dir_is_dedicated_not_shared_but_holds_identical_red_spec_content() -> None:
    """The new overlay's ``pilot_registry_dir`` is a DEDICATED directory, not
    ``fire_dense_qwen/`` -- an empirical finding (see the overlay's own inline
    comment on that field and the mirror pilot spec's header): the shared
    registry is validated in full by every overlay that references it
    (``_validate_llm_pilot_bindings`` has no per-overlay narrowing), so
    adding a provider-id-only-differing spec to it breaks sibling overlays
    that do not declare that provider (proven against
    ``tests/match/test_objective_scoring_decoy.py`` while building this PR).
    The dedicated directory's copy of the RED pilot spec is nonetheless
    BYTE-IDENTICAL to the shared registry's, so the RED seat's actual
    programming identity (persona=berserker, provider=qwen35) is held
    constant even though the directory VALUE differs."""
    new = load_application_overlay(_NEW_OVERLAY)
    qwen = load_application_overlay(_QWEN_OVERLAY)
    assert new.contracts.pilot_registry_dir != qwen.contracts.pilot_registry_dir
    assert new.contracts.pilot_registry_dir.name == (
        "tactical_split_overdeal_v1_delegation_learning"
    )

    new_red_spec_path = new.contracts.pilot_registry_dir / "llm_qwen35.yaml"
    qwen_red_spec_path = qwen.contracts.pilot_registry_dir / "llm_qwen35.yaml"
    assert new_red_spec_path.read_bytes() == qwen_red_spec_path.read_bytes()


# ---------------------------------------------------------------------------
# 2. Provider stanza shape + pre-registration header
# ---------------------------------------------------------------------------


class TestProviderStanzaAndPreregHeader:
    def test_provider_stanza_is_onex_delegation_shape(self) -> None:
        overlay = load_application_overlay(_NEW_OVERLAY)
        assert len(overlay.llm.providers) == 2
        for provider in overlay.llm.providers:
            assert isinstance(provider, ModelSODelegationProviderBinding)
            assert provider.kind == "onex_delegation"
            assert provider.backend_id == "local-coder-mlx"
            assert provider.task_type == "agent_delegation"
            assert provider.source == "external-client"
            assert provider.timeout_seconds == 180.0
            assert provider.model == "mlx-community/Qwen3.6-35B-A3B-8bit"
        provider_ids = {p.provider_id for p in overlay.llm.providers}
        assert provider_ids == {"qwen35", "qwen35_mirror_blue"}

    def test_model_identities_bind_both_provider_ids(self) -> None:
        overlay = load_application_overlay(_NEW_OVERLAY)
        bound = {mi.provider_binding_id for mi in overlay.llm.model_identities}
        assert bound == {"qwen35", "qwen35_mirror_blue"}
        for identity in overlay.llm.model_identities:
            assert "Qwen3.6-35B-A3B-8bit" in identity.display_name
            assert "stickybeatz-studio" in identity.display_name

    def test_prereg_header_is_byte_stable(self) -> None:
        header_lines = _header_block(_NEW_OVERLAY)
        digest = hashlib.sha256(("\n".join(header_lines) + "\n").encode("utf-8")).hexdigest()
        assert digest == _PREREG_HEADER_SHA256, (
            "the prepended pre-registration header changed -- it is the "
            "pre-registration of record and must not be edited/reflowed "
            "after the fact"
        )

    def test_prereg_header_carries_the_preregistered_markers(self) -> None:
        header_lines = _header_block(_NEW_OVERLAY)
        # Join with a single space so markers split across a wrapped comment
        # line (e.g. "TERMINAL for the\n# prompt-guidance mechanism") are
        # still found as one contiguous phrase.
        joined = " ".join(line.lstrip("#").strip() for line in header_lines).lower()
        for marker in _PREREG_MARKERS:
            assert marker.lower() in joined, f"pre-registration header missing marker {marker!r}"


# ---------------------------------------------------------------------------
# 3. Mirror pairing composes over the real seam
# ---------------------------------------------------------------------------


class TestMirrorPairingComposition:
    """``assemble_match_live`` may require distinct loadout ids" (deliverable
    text) undersold the actual blocker: the real failure is
    ``validate_seat_programmer_identity``'s unconditional rejection of two
    card seats resolving to the SAME (provider, persona) identity --
    "the check that stops a live match from running an unannounced mirror"
    (its own docstring, src/steel_onslaught/match/composition.py). Reusing
    ``pilot.llm.qwen35`` verbatim on both seats raises ``SeatIdentityError``
    regardless of loadout distinctness. The fix actually shipped: a SECOND,
    functionally-identical ``onex_delegation`` provider entry
    (``qwen35_mirror_blue``, same backend/model/task_type/timeout as
    ``qwen35``) bound by a new, additive pilot spec
    (``pilot.llm.qwen35_berserker_mirror_blue``) and a new, additive mirror
    loadout -- an ANNOUNCED mirror, not an unannounced one."""

    def _composed_overlay(self) -> ModelSOApplicationOverlay:
        overlay = load_application_overlay(_NEW_OVERLAY)
        tmp = Path(tempfile.mkdtemp())
        updates = {
            "event_ledger": overlay.event_ledger.model_copy(
                update={"path": tmp / "events.sqlite3"}
            ),
            "leaderboard": overlay.leaderboard.model_copy(
                update={"path": tmp / "leaderboard.sqlite3"}
            ),
            "learning_artifacts": overlay.learning_artifacts.model_copy(
                update={
                    "evaluation_root": tmp / "evaluations",
                    "lineage_root": tmp / "lineage",
                    "experiment_root": tmp / "experiments",
                }
            ),
            "evaluation_storage": overlay.evaluation_storage.model_copy(
                update={"root": tmp / "evaluation_storage"}
            ),
        }
        self._tmp = tmp
        return overlay.model_copy(update=updates)

    def test_mirror_pairing_composes_cleanly(self) -> None:
        """The shipped design (distinct mirror pilot spec/loadout) composes
        without error over ``assemble_match_live`` -- no live LLM call is made
        (composition only; the stack is closed before ``.runner.run()``)."""
        overlay = self._composed_overlay()
        try:
            stack = assemble_match_live(
                overlay=overlay,
                red_loadout_path=_RED_LOADOUT,
                blue_loadout_path=_BLUE_MIRROR_LOADOUT,
                seed=1,
                max_ticks=None,
                secret_resolver=NoSecretResolver(),  # overlay declares kind: injected
            )
            stack.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def test_literal_same_pilot_spec_both_seats_raises_seat_identity_error(self) -> None:
        """Proves the blocker this design works around: naively pointing
        BOTH seats' card programmer at ``pilot.llm.qwen35`` (same provider,
        same persona) -- rather than the shipped mirror pilot spec -- raises
        ``SeatIdentityError`` at composition, unconditionally."""
        from steel_onslaught.contracts.application import ModelSOCardProgrammerBinding
        from steel_onslaught.match.composition import SeatIdentityError

        overlay = self._composed_overlay()
        card_catalog = overlay.contracts.card_catalog
        assert card_catalog is not None
        deck_policy = card_catalog.deck_policy
        assert deck_policy is not None
        naive_programmers = tuple(
            ModelSOCardProgrammerBinding(
                side=binding.side,
                pilot_spec_id="pilot.llm.qwen35",
                failure_policy=binding.failure_policy,
            )
            for binding in card_catalog.programmers
        )
        naive_seats = tuple(
            seat.model_copy(update={"archetype": "berserker"}) for seat in deck_policy.seats
        )
        naive_deck_policy = deck_policy.model_copy(update={"seats": naive_seats})
        naive_card_catalog = card_catalog.model_copy(
            update={"programmers": naive_programmers, "deck_policy": naive_deck_policy}
        )
        naive_contracts = overlay.contracts.model_copy(update={"card_catalog": naive_card_catalog})
        naive_overlay = overlay.model_copy(update={"contracts": naive_contracts})

        try:
            with pytest.raises(SeatIdentityError, match="distinct card programmer identities"):
                assemble_match_live(
                    overlay=naive_overlay,
                    red_loadout_path=_RED_LOADOUT,
                    blue_loadout_path=_RED_LOADOUT,  # literal same file, both seats
                    seed=1,
                    max_ticks=None,
                    secret_resolver=NoSecretResolver(),
                )
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. --genesis flows to the baseline/post evaluator caps
# ---------------------------------------------------------------------------


class TestGenesisPhaseCaps:
    """RED-before note: ``_phase_caps`` is a wholly new symbol (no prior
    "wrong-but-present" implementation existed to contrast against), so
    these tests are legitimately absence-based RED against base -- an
    ``ImportError``/``ModuleNotFoundError`` on the local import below, not
    an assertion failure. See ``TestPromotePhaseCapTracksGenesisAndStep``
    below for the exists-but-wrong regression proof against the
    PRE-EXISTING ``WinDamageDifferentialEvaluator`` this knob's promote-cap
    defect actually lived in."""

    def test_default_genesis_preserves_prior_behavior(self) -> None:
        """--genesis default 1.0 leaves every existing invocation's baseline/
        post cap arithmetic unchanged (the #126/#128 configuration)."""
        from scripts.run_lgate2_adaptation_battery import _phase_caps

        args = _build_parser().parse_args([])
        assert args.genesis == 1.0
        baseline_cap, promote_cap, post_cap = _phase_caps(args)
        assert baseline_cap == 1.0
        assert post_cap == 1.0 + args.step
        assert promote_cap == post_cap

    def test_genesis_flag_sets_the_decisive_endpoint_regime_caps(self) -> None:
        """The decisive battery's own configuration: --genesis 0.5 --step 2.0
        must cap baseline at 0.5 and post (and promote) at 2.5 (the two
        named regimes of the aggression semantics sentence)."""
        from scripts.run_lgate2_adaptation_battery import _phase_caps

        args = _build_parser().parse_args(["--genesis", "0.5", "--step", "2.0"])
        assert args.genesis == 0.5
        baseline_cap, promote_cap, post_cap = _phase_caps(args)
        assert baseline_cap == 0.5
        assert post_cap == 2.5
        assert promote_cap == 2.5

    def test_genesis_flows_into_the_lane_overlays_live_learning_binding(
        self, tmp_path: Path
    ) -> None:
        overlay = _lane_overlay(
            tmp_path,
            overlay_path=_QWEN_OVERLAY,
            max_value=0.5,
            learning_player="player.red",
            step=2.0,
            genesis=0.5,
        )
        assert overlay.live_learning is not None
        assert overlay.live_learning.genesis_parameters == {"aggression": 0.5}
        assert overlay.live_learning.max_value == 0.5


# ---------------------------------------------------------------------------
# 5. Promote-phase cap tracks genesis+step (remediation-round regression)
# ---------------------------------------------------------------------------

_EVAL_LEARNER = "player.red"
_EVAL_OPPONENT = "player.blue"


def _decisive_win_evidence() -> ModelSOAfterMatchLearningEvidence:
    """Learner wins decisively with a positive damage differential -- the
    only evidence shape ``WinDamageDifferentialEvaluator.evaluate`` ever
    proposes a candidate for. Mirrors the pattern in
    ``tests/learning/test_live_evaluator.py``."""

    def _score(damage_dealt: int, *, victory: int) -> ModelSOPlayerScore:
        return ModelSOPlayerScore(
            victory=victory,
            damage_dealt=damage_dealt,
            damage_efficiency=1.0,
            pressure_efficiency=1.0,
            overload_penalty=0,
            replay_validity=1,
            final_score=damage_dealt,
        )

    return ModelSOAfterMatchLearningEvidence(
        match_id="match.omn15488.canary-unit.001",
        scored_event_id="01HZY3E9ZTAV5J6BQF8KM2WXSC",
        correlation_id=UUID("00000000-0000-0000-0000-000000015488"),
        duration_ticks=12,
        winner_player_id=_EVAL_LEARNER,
        is_draw=False,
        scores={
            _EVAL_LEARNER: _score(100, victory=1),
            _EVAL_OPPONENT: _score(40, victory=0),
        },
        event_counts={"match_scored": 1},
        decision_action_counts={},
        decision_reason_counts={},
    )


def _generation0_policy(parameters: ParamDict) -> ModelSOLiveLearningPolicy:
    return ModelSOLiveLearningPolicy(
        policy_id="policy.aggressive.genesis",
        archetype="aggressive",
        parameters=parameters,
        spec_hash=spec_hash("aggressive", parameters),
        generation=0,
    )


class TestPromotePhaseCapTracksGenesisAndStep:
    """Exists-but-wrong regression proof for the remediation-round defect:
    an earlier version of ``--genesis`` threaded ``genesis``/``step`` into
    the baseline/post evaluator caps only and left the promote phase's cap
    hardcoded at the driver's ORIGINAL literal (``max_value=3.0``,
    independent of ``--genesis``/``--step``). ``WinDamageDifferentialEvaluator``
    is PRE-EXISTING code (unmodified by OMN-15488, present before this
    ticket) -- the defect was entirely in which ``max_value`` the driver
    passed it, so exercising the real evaluator with each literal is a
    genuine exists-but-wrong contrast, not an absence-based one."""

    def test_old_hardcoded_3_0_literal_silently_blocks_a_valid_genesis_step_pair(
        self,
    ) -> None:
        """Characterizes the DEFECT this remediation round fixed, against
        the real (unmodified) evaluator: with the driver's ORIGINAL
        promote-phase literal (max_value=3.0) and a genesis/step pair whose
        target exceeds it (genesis=1.5, step=2.0 -> candidate 3.5), a
        decisive learner win proposes NO candidate at all -- the evaluator
        silently returns ``None``, which the driver reports as the
        pre-declared NO-PROMOTION escape even though nothing about the
        hypothesis failed."""
        evaluator = WinDamageDifferentialEvaluator(
            learning_player_id=_EVAL_LEARNER,
            parameter="aggression",
            step=2.0,
            max_value=3.0,  # the driver's pre-remediation hardcoded promote-phase literal
        )
        policy = _generation0_policy({"aggression": 1.5})  # genesis == 1.5
        record = evaluator.evaluate(evidence=_decisive_win_evidence(), policy=policy)
        assert record is None, "candidate 3.5 > hardcoded cap 3.0 -- reproduces the unfixed defect"

    def test_phase_caps_promote_cap_fixes_the_same_scenario(self) -> None:
        """The FIX: ``_phase_caps``'s ``promote_cap`` (== genesis + step,
        not a fixed literal) passed as ``max_value`` lets the IDENTICAL
        decisive win actually promote for the same genesis/step pair."""
        from scripts.run_lgate2_adaptation_battery import _phase_caps

        args = _build_parser().parse_args(["--genesis", "1.5", "--step", "2.0"])
        _baseline_cap, promote_cap, post_cap = _phase_caps(args)
        assert promote_cap == post_cap == 3.5

        evaluator = WinDamageDifferentialEvaluator(
            learning_player_id=_EVAL_LEARNER,
            parameter="aggression",
            step=2.0,
            max_value=promote_cap,
        )
        policy = _generation0_policy({"aggression": 1.5})
        record = evaluator.evaluate(evidence=_decisive_win_evidence(), policy=policy)
        assert record is not None, "promote_cap (3.5) must admit the exact candidate 3.5"
        assert record.parameters["aggression"] == 3.5

    def test_this_battery_own_config_was_never_affected_by_the_defect(self) -> None:
        """Disclosure test: the decisive battery's OWN configuration
        (genesis=0.5, step=2.0 -> candidate 2.5) never tripped the defect
        (2.5 <= the old hardcoded 3.0) -- the bug was latent for this
        battery, not active. Both the old literal and the fixed promote_cap
        admit this battery's actual candidate."""
        from scripts.run_lgate2_adaptation_battery import _phase_caps

        args = _build_parser().parse_args(["--genesis", "0.5", "--step", "2.0"])
        _baseline_cap, promote_cap, _post_cap = _phase_caps(args)
        assert promote_cap == 2.5

        policy = _generation0_policy({"aggression": 0.5})
        for max_value in (3.0, promote_cap):
            evaluator = WinDamageDifferentialEvaluator(
                learning_player_id=_EVAL_LEARNER,
                parameter="aggression",
                step=2.0,
                max_value=max_value,
            )
            record = evaluator.evaluate(evidence=_decisive_win_evidence(), policy=policy)
            assert record is not None
            assert record.parameters["aggression"] == 2.5


# ---------------------------------------------------------------------------
# 6. `_run_battery` itself wires `_phase_caps`' output into every call site
#    (remediation round 2: the round-1 tests above exercise `_phase_caps` and
#    `_lane_overlay` directly with hand-supplied arguments -- they never
#    drive `_run_battery`, so the four literal call sites that actually
#    thread that output through the battery (baseline_cap/promote_cap/
#    post_cap at scripts/run_lgate2_adaptation_battery.py:437/448/463 and the
#    `genesis=args.genesis` kwarg at :405) had ZERO test coverage.
#    MUTATION-PROVED (manually, this remediation round): reverting all four
#    sites to their pre-OMN-15488 form (`max_value=_GENESIS["aggression"]`,
#    `max_value=3.0`, `max_value=_GENESIS["aggression"]+args.step`, and
#    dropping the `genesis=` kwarg entirely) leaves the test below FAILING
#    (RED) -- see the PR body's "RED-before" section for the exact revert/
#    restore transcript.
# ---------------------------------------------------------------------------


class TestRunBatteryWiresPhaseCapsAtEveryCallSite:
    """Drives the REAL ``_run_battery`` end to end (baseline -> promote ->
    post) with ONLY the LLM-calling boundary (``_measure_match``) stubbed --
    ``_phase_caps``, ``_run_phase``, and ``_lane_overlay`` all run unmodified.
    A spy wraps (never replaces) ``_lane_overlay`` so the ``max_value``/
    ``genesis`` it is actually invoked with, per phase, is captured from the
    real call sites rather than asserted against a hand-rolled substitute --
    the surrogate-test defect this class exists to close."""

    def test_wires_phase_caps_into_the_overlay_at_every_call_site(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.run_lgate2_adaptation_battery as driver

        real_lane_overlay = driver._lane_overlay
        seen: list[dict[str, Any]] = []

        def _spy_lane_overlay(*args: Any, **kwargs: Any) -> ModelSOApplicationOverlay:
            overlay = real_lane_overlay(*args, **kwargs)
            assert overlay.live_learning is not None
            seen.append(
                {
                    "max_value": kwargs["max_value"],
                    "genesis": kwargs["genesis"],
                    "overlay_max_value": overlay.live_learning.max_value,
                    "overlay_genesis": overlay.live_learning.genesis_parameters,
                }
            )
            return overlay

        monkeypatch.setattr(driver, "_lane_overlay", _spy_lane_overlay)

        promoted_payload = {
            "kind": "steel_onslaught.policy_promoted",
            "match_id": "match.stub.promote.4101",
            "policy_id": "policy.aggressive.gen1-stub",
            "archetype": "aggressive",
            "generation": 1,
            "spec_hash": "a" * 64,
            "parent_spec_hash": "b" * 64,
            "source_lineage_digest": "c" * 64,
            "evidence_scored_event_id": "01HZY3E9ZTAV5J6BQF8KM2WXSC",
        }

        def _stub_row(
            *,
            phase: str,
            seed: int,
            generation: int,
            policy_id: str,
            promoted: dict[str, Any] | None,
        ) -> dict[str, Any]:
            return {
                "phase": phase,
                "seed": seed,
                "match_id": f"match.stub.{phase}.{seed}",
                "policy_provenance": {
                    "player_id": "player.red",
                    "generation": generation,
                    "policy_id": policy_id,
                    "spec_hash": promoted_payload["spec_hash"] if generation else "genesis-hash",
                    "source_lineage_digest": (
                        promoted_payload["source_lineage_digest"] if generation else "genesis-lin"
                    ),
                },
                "winner_player_id": "player.red",
                "is_draw": False,
                "end_reason": "victory",
                "duration_ticks": 10,
                "replay_validity": {"player.red": 1, "player.blue": 1},
                "learning_seat": {
                    "seat": "red",
                    "dealt": {},
                    "planned": {},
                    "keep_rates": {},
                    "planned_share": {},
                },
                "failed_completions": 0,
                "empty_content_completions": {},
                "policy_promoted": promoted,
            }

        def _stub_measure_match(
            overlay: Any,
            *,
            red_loadout_path: Path,
            blue_loadout_path: Path,
            seed: int,
            phase: str,
            learning_player: str,
            learning_seat: str,
            learning_mech: str,
        ) -> dict[str, Any]:
            del overlay, red_loadout_path, blue_loadout_path, learning_player, learning_seat
            del learning_mech
            if phase == "baseline":
                return _stub_row(
                    phase=phase,
                    seed=seed,
                    generation=0,
                    policy_id="policy.aggressive.genesis",
                    promoted=None,
                )
            if phase == "promote":
                return _stub_row(
                    phase=phase,
                    seed=seed,
                    generation=0,
                    policy_id="policy.aggressive.genesis",
                    promoted=dict(promoted_payload),
                )
            assert phase == "post"
            return _stub_row(
                phase=phase,
                seed=seed,
                generation=1,
                policy_id=str(promoted_payload["policy_id"]),
                promoted=None,
            )

        monkeypatch.setattr(driver, "_measure_match", _stub_measure_match)

        args = driver._build_parser().parse_args(
            [
                "--genesis",
                "0.5",
                "--step",
                "2.0",
                "--n",
                "2",
                "--promote-attempts",
                "1",
                "--overlay",
                str(_NEW_OVERLAY),
                "--red-loadout",
                str(_RED_LOADOUT),
                "--blue-loadout",
                str(_BLUE_MIRROR_LOADOUT),
            ]
        )
        state_root = tmp_path / "state"
        state_root.mkdir()
        raw_path = state_root / "battery_raw.jsonl"

        exit_code = driver._run_battery(args, state_root, raw_path)
        assert exit_code == 0, "the stubbed decisive promotion must let the battery reach post"

        assert [entry["max_value"] for entry in seen] == [0.5, 2.5, 2.5], (
            "baseline/promote/post must each receive _phase_caps()'s exact output -- a "
            "hardcoded literal at any of scripts/run_lgate2_adaptation_battery.py:437/448/463 "
            "would diverge from this sequence"
        )
        assert [entry["genesis"] for entry in seen] == [0.5, 0.5, 0.5], (
            "every phase must thread args.genesis (line 405) into _lane_overlay, not the "
            "module-level _GENESIS default"
        )
        for entry in seen:
            assert entry["overlay_max_value"] == entry["max_value"]
            assert entry["overlay_genesis"] == {"aggression": 0.5}
