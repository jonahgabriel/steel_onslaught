"""Contract tests for OMN-15488's L-GATE-2 decisive battery overlay + driver.

``tactical_split_overdeal_v1_delegation_learning.yaml`` is a NEW overlay,
authored directly on the ``onex_delegation`` provider shape -- it is NOT a
migration of ``tactical_split_overdeal_v1_qwen.yaml`` (never had an
``openai_compatible`` ancestor; see
``tests/contracts/test_overlay_delegation_migration_omn15174.py``'s census
for the corpus-level accounting). Four claims are load-bearing here:

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
     by ``TestGenesisPhaseCaps``.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.run_lgate2_adaptation_battery import _build_parser, _lane_overlay, _phase_caps
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSODelegationProviderBinding,
)
from steel_onslaught.match.composition import assemble_match_live, load_application_overlay

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).parent.parent.parent
_OVERLAYS = _REPO_ROOT / "contracts_data" / "overlays"
_NEW_OVERLAY = _OVERLAYS / "tactical_split_overdeal_v1_delegation_learning.yaml"
_QWEN_OVERLAY = _OVERLAYS / "tactical_split_overdeal_v1_qwen.yaml"
_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/llm_qwen35_berserker.yaml"
_BLUE_MIRROR_LOADOUT = (
    _REPO_ROOT / "contracts_data/loadouts/qwen35/llm_qwen35_berserker_mirror_blue.yaml"
)

# Prepended verbatim from the amendment-authored pre-registration text
# (OMN-15488 ticket amendment, 2026-07-30 ~15:0xZ). Pinned hash proves the
# header stays byte-stable going forward -- any edit to the pre-registration
# of record changes this hash and fails the test loudly, rather than
# silently drifting.
_PREREG_HEADER_SHA256 = "ef942396e642432fd334fb668d7b65e56bfd443e285aa25f135ab841ae5b3613"

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
                )
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. --genesis flows to the baseline/post evaluator caps
# ---------------------------------------------------------------------------


class TestGenesisPhaseCaps:
    def test_default_genesis_preserves_prior_behavior(self) -> None:
        """--genesis default 1.0 leaves every existing invocation's baseline/
        post cap arithmetic unchanged (the #126/#128 configuration)."""
        args = _build_parser().parse_args([])
        assert args.genesis == 1.0
        baseline_cap, post_cap = _phase_caps(args)
        assert baseline_cap == 1.0
        assert post_cap == 1.0 + args.step

    def test_genesis_flag_sets_the_decisive_endpoint_regime_caps(self) -> None:
        """The decisive battery's own configuration: --genesis 0.5 --step 2.0
        must cap baseline at 0.5 and post at 2.5 (the two named regimes of
        the aggression semantics sentence)."""
        args = _build_parser().parse_args(["--genesis", "0.5", "--step", "2.0"])
        assert args.genesis == 0.5
        baseline_cap, post_cap = _phase_caps(args)
        assert baseline_cap == 0.5
        assert post_cap == 2.5

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
