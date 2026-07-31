"""Contract tests for OMN-15488 leg (a) — the blue-seat endpoint-contrast lane.

Leg (a) is the second half of the SERIES operator ruling 25 resolved: the
blue/sniper cell of the seat x step matrix, holding genesis, step, binding,
overlay shape, pairing structure, phase/seed/cap structure, driver, and
instruments constant against the merged OMN-15488 red battery and varying
persona only.

Six claims are load-bearing here, and each is a thing that was either wrong or
absent before this module existed:

  1. **The overlay header is the pre-registration of record, and it still
     matches its source.** The AC1 timing gate reads the OVERLAY file's commit
     timestamp, never the evidence document's, so prereg §12 requires §2-§7 of
     the document to be embedded VERBATIM in the header.
     ``TestVerbatimEmbed`` recovers the embed and asserts byte-equality against
     the document. This is strictly stronger than the red battery's header-sha
     pin, which could prove the header had not changed but never that it still
     agreed with anything.
  2. **The §7.1 interpretation map is decidable.** Its five rows overlap and
     the table declares no precedence, so a run with primary SUPPORTED and vent
     DIRECTIONAL-ONLY matches two rows with opposite readings. The red
     pre-registration had no such ambiguity (named rows, then a closing
     DIRECTIONAL-ONLY clause); the table format dropped that ordering.
     ``TestInterpretationMapPrecedenceAmendment`` pins the restoring amendment
     and all nine resolved cells.
  3. **The pre-registered seed blocks are reachable.** §2.1 FD3 / §3 pre-register
     6001-6030 / 6101-6115 / 6201-6230 and AC2 asserts them exactly; the driver
     hardcoded base 4000 three times inline. ``TestSeedBase`` proves
     ``--seed-base`` produces exactly the pre-registered blocks and that the
     default reproduces the pre-existing behaviour byte-identically.
  4. **The watchdog row contract matches the phase plan.** §10.1 pins
     ``--expected-rows 61``, copied from a red run that promoted on its first
     attempt; the promote phase stops at the first promotion, so a clean run
     writes 61-75 rows and the watchdog's strict ``!=`` would call 14 of the 15
     clean outcomes INCOMPLETE. ``TestExpectedRowContract`` proves the range
     mechanism, proves the old literal was wrong, and proves the NO-PROMOTION
     escape does not hide inside the range.
  5. **The mirror pairing composes over the real seam** — and the naive
     same-pilot-spec-both-seats form does not (``TestMirrorPairingComposition``).
  6. **The launch runbook's numbers are derived, not restated**
     (``TestRunbookAgreesWithTheDerivation``).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.run_lgate2_adaptation_battery import (
    _DEFAULT_SEED_BASE,
    _build_parser,
    expected_row_bounds,
    phase_seeds,
)
from steel_onslaught.battery.watchdog import (
    expected_rows_label,
    rows_satisfy_contract,
)
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.llm.client_http import NoSecretResolver
from steel_onslaught.match.composition import assemble_match_live, load_application_overlay

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OVERLAY = (
    _REPO_ROOT / "contracts_data/overlays/tactical_split_overdeal_v1_delegation_learning_blue.yaml"
)
_PREREG_DOC = (
    _REPO_ROOT / "docs/evidence/2026-07-31-lgate2-legA-blue-seat-endpoint-contrast-prereg.md"
)
_RUNBOOK = _REPO_ROOT / "docs/runbooks/2026-07-31-lgate2-legA-blue-seat-launch.md"
_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen35/sniper_ironclad_lega_blue.yaml"
_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen35/sniper_ironclad_lega_mirror_red.yaml"
_SHARED_REGISTRY = _REPO_ROOT / "contracts_data/pilots/fire_dense_qwen"

_EMBED_BEGIN = "# ===== BEGIN VERBATIM EMBED: prereg §2-§7 ====="
_EMBED_END = "# ===== END VERBATIM EMBED: prereg §2-§7 ====="

# The pre-registered configuration (§2.1, §3, §10.1). Restated here ONCE, as the
# thing the tests assert against — every other number in this module is derived.
_N = 30
_PROMOTE_ATTEMPTS = 15
_SEED_BASE = 6000


def _overlay_lines() -> list[str]:
    return _OVERLAY.read_text(encoding="utf-8").splitlines()


def _embed_lines() -> list[str]:
    """The embedded block, with its ``# `` comment prefix stripped back off."""
    lines = _overlay_lines()
    begin = lines.index(_EMBED_BEGIN)
    end = lines.index(_EMBED_END)
    recovered: list[str] = []
    for line in lines[begin + 1 : end]:
        assert line.startswith("#"), f"non-comment line inside the verbatim embed: {line!r}"
        recovered.append(line[2:] if line.startswith("# ") else line[1:])
    return recovered


def _prereg_sections_2_through_7() -> list[str]:
    """§2 through the end of §7 of the merged pre-registration document."""
    lines = _PREREG_DOC.read_text(encoding="utf-8").splitlines()
    begin = next(index for index, line in enumerate(lines) if line.startswith("## 2. Design"))
    end = next(index for index, line in enumerate(lines) if line.startswith("## 8. "))
    # Trim the blank line and the horizontal rule that close the §7 block.
    block = lines[begin:end]
    while block and block[-1].strip() in {"", "---"}:
        block.pop()
    return block


def _raw_overlay() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(_OVERLAY.read_text(encoding="utf-8"))
    return raw


# ---------------------------------------------------------------------------
# 1. The verbatim embed — the AC1 seam prereg §12 creates
# ---------------------------------------------------------------------------


class TestVerbatimEmbed:
    def test_embed_is_byte_identical_to_the_merged_prereg_sections(self) -> None:
        """§12 clause 1, mechanically.

        A pre-registration the timing gate cannot see is a pre-registration on
        the honour system: ``check_preregistration_timing.py`` reads the
        OVERLAY's commit timestamp and nothing reads the document. This test
        is what makes "embedded verbatim" a fact rather than a claim, and it
        fails if EITHER surface is edited without the other.
        """
        assert _embed_lines() == _prereg_sections_2_through_7()

    def test_embed_covers_every_criterion_region(self) -> None:
        """The embed must carry the hypothesis/endpoint/band/escape/map text.

        Section-header spot-checks, so a truncated or reordered embed fails
        loudly rather than passing on a prefix match.
        """
        embedded = "\n".join(_embed_lines())
        for marker in (
            "## 2. Design",
            "### 2.4 Rejected alternative",
            "## 3. Phases, seeds, and caps",
            "### 4.1 PRIMARY",
            "### 4.2 CONFIRMATORY-SECONDARY",
            "### 4.5 MULTIPLICITY",
            "## 5. Statistical honesty",
            "### 6.1 NO-PROMOTION",
            "### 6.3 CANARY DECISIVENESS GATE",
            "### 7.1 Within leg (a)",
            "### 7.3 What leg (a) **cannot** conclude",
        ):
            assert marker in embedded, f"criterion region missing from the embed: {marker}"
        for endpoint in ("D_ws", "D_vent", "SUPPORTED", "DIRECTIONAL-ONLY", "NOT-CONFIRMED"):
            assert endpoint in embedded

    def test_amendments_are_appended_after_the_embed_never_inside_it(self) -> None:
        """§12 clause 2: amendments append, they do not edit a criterion region."""
        lines = _overlay_lines()
        end = lines.index(_EMBED_END)
        embedded = "\n".join(_embed_lines())
        assert "AMENDMENT 1" not in embedded
        assert "AMENDMENT 2" not in embedded
        after = "\n".join(lines[end:])
        assert "# AMENDMENT 1 (2026-07-31" in after
        assert "# AMENDMENT 2 (2026-07-31" in after

    def test_2_4_blue_sniper_persona_reading_is_the_one_embedded(self) -> None:
        """Operator ruling (2026-07-31): §2.4 as written — the pure side swap
        is REJECTED and the sniper persona is the manipulation, on both seats.
        """
        embedded = "\n".join(_embed_lines())
        assert "**Pure side swap" in embedded
        assert "**Rejected** because inside a berserker mirror" in embedded
        assert "persona `berserker` → `sniper` on BOTH seats" in embedded


# ---------------------------------------------------------------------------
# 2. The restored interpretation-map precedence clause
# ---------------------------------------------------------------------------


class TestInterpretationMapPrecedenceAmendment:
    """§7.1's rows overlap; the table states no precedence.

    Row 1 (``SUPPORTED | any``) and row 4 (``any | DIRECTIONAL-ONLY``) both
    match a SUPPORTED-primary / DIRECTIONAL-ONLY-vent result and give opposite
    readings — PASSES versus unresolved. The red pre-registration did not have
    this hole because it was written as three named rows plus a CLOSING
    DIRECTIONAL-ONLY clause, and its scoring document applied exactly that
    ordering ("none of the three named rows apply and the closing clause
    governs"). Reformatting into a flat table dropped it.
    """

    def test_amendment_states_the_first_matching_row_rule(self) -> None:
        header = "\n".join(_overlay_lines())
        assert "§7.1 INTERPRETATION-MAP ROW PRECEDENCE" in header
        assert "the FIRST row whose" in header
        assert "no later row is consulted" in header

    def test_amendment_resolves_all_nine_cells(self) -> None:
        """Every {primary} x {vent} cell is named, so none is left to taste."""
        header = "\n".join(_overlay_lines())
        for primary in ("SUPPORTED", "NOT-SUPPORTED", "DIRECTIONAL-ONLY"):
            for vent in ("CONFIRMED", "NOT-CONFIRMED", "DIRECTIONAL-ONLY"):
                cell = f"primary {primary:<16} + vent {vent:<16} ->"
                assert cell in header, f"unresolved interpretation-map cell: {primary} x {vent}"

    def test_amendment_cites_the_red_preregistrations_closing_clause(self) -> None:
        """It is a restoration, and the source of the semantics is named."""
        header = "\n".join(_overlay_lines())
        assert "the terminal/" in header and "non-terminal call is NOT made from an" in header
        assert "2026-07-31-lgate2-decisive-battery-scoring.md" in header

    def test_prereg_document_carries_the_same_amendment(self) -> None:
        """§12 makes a header/document disagreement a reportable defect, so the
        clause is recorded on both surfaces rather than only the binding one —
        a scorer reading the document alone would otherwise still face the
        ambiguous table."""
        doc = _PREREG_DOC.read_text(encoding="utf-8")
        assert "§7.1 INTERPRETATION-MAP ROW PRECEDENCE" in doc
        assert "the FIRST row whose" in doc


# ---------------------------------------------------------------------------
# 3. Seed blocks — FD3, and AC2's exactness requirement
# ---------------------------------------------------------------------------


class TestSeedBase:
    def test_seed_base_6000_yields_exactly_the_preregistered_blocks(self) -> None:
        assert phase_seeds(_SEED_BASE, "baseline", _N) == list(range(6001, 6031))
        assert phase_seeds(_SEED_BASE, "promote", _PROMOTE_ATTEMPTS) == list(range(6101, 6116))
        assert phase_seeds(_SEED_BASE, "post", _N) == list(range(6201, 6231))

    def test_default_base_reproduces_the_pre_existing_hardcoded_blocks(self) -> None:
        """The literals this flag replaced: ``4000 + index`` / ``4100 + index``
        / ``4200 + index``. A default that moved would silently re-lane every
        prior battery on this driver."""
        assert _DEFAULT_SEED_BASE == 4000
        assert phase_seeds(_DEFAULT_SEED_BASE, "baseline", 30) == [
            4000 + index for index in range(1, 31)
        ]
        assert phase_seeds(_DEFAULT_SEED_BASE, "promote", 15) == [
            4100 + index for index in range(1, 16)
        ]
        assert phase_seeds(_DEFAULT_SEED_BASE, "post", 30) == [
            4200 + index for index in range(1, 31)
        ]

    def test_blocks_are_disjoint_from_the_red_battery_and_from_each_other(self) -> None:
        """FD3's actual claim: 6xxx is unused by any prior steel battery, which
        is what keeps the contamination/bijection gate meaningful rather than
        vacuous."""
        leg_a = (
            set(phase_seeds(_SEED_BASE, "baseline", _N))
            | set(phase_seeds(_SEED_BASE, "promote", _PROMOTE_ATTEMPTS))
            | set(phase_seeds(_SEED_BASE, "post", _N))
        )
        red = (
            set(phase_seeds(4000, "baseline", 30))
            | set(phase_seeds(4000, "promote", 15))
            | set(phase_seeds(4000, "post", 30))
        )
        canary = set(phase_seeds(9100, "baseline", 2))
        assert len(leg_a) == 2 * _N + _PROMOTE_ATTEMPTS  # no intra-lane collisions
        assert not leg_a & red
        assert not leg_a & canary
        assert canary == {9101, 9102}  # §6.3's pre-registered canary seeds, exactly

    def test_driver_exposes_seed_base_and_defaults_it(self) -> None:
        args = _build_parser().parse_args(["--mode", "battery"])
        assert args.seed_base == _DEFAULT_SEED_BASE
        args = _build_parser().parse_args(["--mode", "battery", "--seed-base", "6000"])
        assert args.seed_base == _SEED_BASE


# ---------------------------------------------------------------------------
# 4. The watchdog row contract
# ---------------------------------------------------------------------------


class TestExpectedRowContract:
    def test_bounds_are_derived_from_the_phase_plan(self) -> None:
        assert expected_row_bounds(n=_N, promote_attempts=_PROMOTE_ATTEMPTS) == (61, 75)

    def test_the_preregistered_literal_61_would_misreport_every_k_above_one(self) -> None:
        """RED-before proof for the whole change: under the old exact-match
        contract, 14 of the 15 clean outcomes are called INCOMPLETE."""
        clean_row_counts = [2 * _N + k for k in range(1, _PROMOTE_ATTEMPTS + 1)]
        misreported = [
            rows for rows in clean_row_counts if not rows_satisfy_contract(rows, 61, None)
        ]
        assert misreported == list(range(62, 76))
        assert len(misreported) == len(clean_row_counts) - 1

    def test_the_range_accepts_exactly_the_clean_outcomes(self) -> None:
        minimum, maximum = expected_row_bounds(n=_N, promote_attempts=_PROMOTE_ATTEMPTS)
        for k in range(1, _PROMOTE_ATTEMPTS + 1):
            assert rows_satisfy_contract(2 * _N + k, minimum, maximum)
        # A short clean exit is still INCOMPLETE — the floor is what OMN-15588
        # was built for, and dropping --expected-rows entirely would lose it.
        assert not rows_satisfy_contract(27, minimum, maximum)
        assert not rows_satisfy_contract(60, minimum, maximum)
        assert not rows_satisfy_contract(76, minimum, maximum)

    def test_equality_semantics_are_unchanged_without_an_upper_bound(self) -> None:
        assert rows_satisfy_contract(30, 30, None)
        assert not rows_satisfy_contract(29, 30, None)
        assert rows_satisfy_contract(29, None, None)  # no contract declared

    def test_summary_label_renders_a_range_as_a_range(self) -> None:
        assert expected_rows_label(61, 75) == "61-75"
        assert expected_rows_label(30, None) == "30"
        assert expected_rows_label(30, 30) == "30"
        assert expected_rows_label(None, None) == "?"

    def test_no_promotion_escape_cannot_hide_inside_the_range(self) -> None:
        """§6.1 exhausts the budget and the driver returns 1, so the watchdog
        reports CRASHED. The row count it would have written is deliberately
        NOT inside the clean range."""
        no_promotion_rows = _N + _PROMOTE_ATTEMPTS  # baseline + full promote budget, no post
        minimum, maximum = expected_row_bounds(n=_N, promote_attempts=_PROMOTE_ATTEMPTS)
        assert not rows_satisfy_contract(no_promotion_rows, minimum, maximum)

    def test_bounds_reject_an_impossible_configuration(self) -> None:
        with pytest.raises(ValueError):
            expected_row_bounds(n=30, promote_attempts=0)


# ---------------------------------------------------------------------------
# 5. The overlay itself
# ---------------------------------------------------------------------------


class TestOverlayShape:
    def test_overlay_parses_via_the_real_typed_loader(self) -> None:
        overlay = load_application_overlay(_OVERLAY)
        assert isinstance(overlay, ModelSOApplicationOverlay)

    def test_both_seats_are_snipers_and_the_mirror_is_preserved(self) -> None:
        """FD2: persona flips on BOTH seats, so the pairing stays a mirror —
        the property §1 holds constant against the red battery."""
        card_catalog = load_application_overlay(_OVERLAY).contracts.card_catalog
        assert card_catalog is not None
        deck_policy = card_catalog.deck_policy
        assert deck_policy is not None
        assert {seat.side: seat.archetype for seat in deck_policy.seats} == {
            "red": "sniper",
            "blue": "sniper",
        }
        assert {binding.side: binding.pilot_spec_id for binding in card_catalog.programmers} == {
            "blue": "pilot.llm.qwen35_sniper",
            "red": "pilot.llm.qwen35_sniper_mirror_red",
        }

    def test_deck_partition_is_held_byte_constant_with_the_red_battery(self) -> None:
        """FD2 changes chassis and persona, NOT the decision space: 4/4 over-deal,
        register_count 5, same deck ids, on both sides (prereg §2.2)."""
        card_catalog = load_application_overlay(_OVERLAY).contracts.card_catalog
        assert card_catalog is not None
        deck_policy = card_catalog.deck_policy
        assert deck_policy is not None
        for seat in deck_policy.seats:
            assert seat.movement_deck_id == "deck.movement.v1"
            assert seat.weapon_deck_id == "deck.weapon.v1"
            assert seat.hand_quota.movement == 4
            assert seat.hand_quota.weapon == 4
            assert seat.register_count == 5

    def test_card_cadence_is_paced(self) -> None:
        """LOAD-BEARING (§2.1, §9.3): the OMN-15591 disposition is
        cadence-conditional and void on atomic cadence."""
        card_catalog = load_application_overlay(_OVERLAY).contracts.card_catalog
        assert card_catalog is not None
        assert card_catalog.card_cadence == "paced"

    def test_provider_binding_is_the_announced_delegation_mirror(self) -> None:
        overlay = load_application_overlay(_OVERLAY)
        providers = {provider.provider_id: provider for provider in overlay.llm.providers}
        assert set(providers) == {"qwen35", "qwen35_sniper_mirror_red"}
        learning, mirror = providers["qwen35"], providers["qwen35_sniper_mirror_red"]
        for field in ("kind", "backend_id", "model", "task_type", "max_tokens", "timeout_seconds"):
            assert getattr(learning, field) == getattr(mirror, field), (
                f"the announced mirror must be identical in every dispatched field; {field} differs"
            )

    def test_registry_is_dedicated_and_does_not_touch_the_shared_one(self) -> None:
        """The empirical trap the red overlay's header records:
        ``_validate_llm_pilot_bindings`` validates EVERY spec in a registry
        directory, so a leg-(a) provider leaked into ``fire_dense_qwen/`` would
        break every sibling overlay that does not declare it."""
        raw = _raw_overlay()
        registry = str(raw["contracts"]["pilot_registry_dir"])
        assert registry.endswith("tactical_split_overdeal_v1_delegation_learning_blue")
        shared = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(_SHARED_REGISTRY.glob("*.yaml"))
        )
        assert "qwen35_sniper_mirror_red" not in shared

    def test_secret_resolver_is_injected_not_none(self) -> None:
        """The driver passes ``NoSecretResolver()`` unconditionally, and
        ``kind: none`` rejects an injected resolver — the red battery's first
        canary died at composition on exactly this."""
        assert _raw_overlay()["llm"]["secret_resolver"]["kind"] == "injected"

    def test_loadouts_differ_only_in_id_and_pilot_id(self) -> None:
        """prereg §2.3 item 3, and what makes §4.7's "win rate is uninformative
        by construction" structurally true."""
        blue = yaml.safe_load(_BLUE_LOADOUT.read_text(encoding="utf-8"))
        red = yaml.safe_load(_RED_LOADOUT.read_text(encoding="utf-8"))
        assert blue.pop("id") != red.pop("id")
        assert blue.pop("pilot_id") == "pilot.llm.qwen35_sniper"
        assert red.pop("pilot_id") == "pilot.llm.qwen35_sniper_mirror_red"
        assert blue == red


# ---------------------------------------------------------------------------
# 6. The mirror pairing over the real composition seam
# ---------------------------------------------------------------------------


class TestMirrorPairingComposition:
    def _composed_overlay(self) -> ModelSOApplicationOverlay:
        overlay = load_application_overlay(_OVERLAY)
        tmp = Path(tempfile.mkdtemp())
        self._tmp = tmp
        return overlay.model_copy(
            update={
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
        )

    def test_sniper_mirror_composes_cleanly(self) -> None:
        """Composition only — the stack is closed before ``runner.run()``, so
        no LLM call is made."""
        overlay = self._composed_overlay()
        try:
            stack = assemble_match_live(
                overlay=overlay,
                red_loadout_path=_RED_LOADOUT,
                blue_loadout_path=_BLUE_LOADOUT,
                seed=6001,
                max_ticks=None,
                secret_resolver=NoSecretResolver(),
            )
            stack.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def test_literal_same_pilot_spec_both_seats_raises_seat_identity_error(self) -> None:
        """The trap prereg §2.3 item 2 pre-records: a literal reuse of one
        sniper spec on both sides is an UNANNOUNCED mirror and is rejected
        unconditionally, regardless of loadout distinctness."""
        from steel_onslaught.contracts.application import ModelSOCardProgrammerBinding
        from steel_onslaught.match.composition import SeatIdentityError

        overlay = self._composed_overlay()
        card_catalog = overlay.contracts.card_catalog
        assert card_catalog is not None
        naive_catalog = card_catalog.model_copy(
            update={
                "programmers": tuple(
                    ModelSOCardProgrammerBinding(
                        side=binding.side,
                        pilot_spec_id="pilot.llm.qwen35_sniper",
                        failure_policy=binding.failure_policy,
                    )
                    for binding in card_catalog.programmers
                )
            }
        )
        naive_overlay = overlay.model_copy(
            update={
                "contracts": overlay.contracts.model_copy(update={"card_catalog": naive_catalog})
            }
        )
        try:
            with pytest.raises(SeatIdentityError, match="distinct card programmer identities"):
                assemble_match_live(
                    overlay=naive_overlay,
                    red_loadout_path=_BLUE_LOADOUT,
                    blue_loadout_path=_BLUE_LOADOUT,
                    seed=6001,
                    max_ticks=None,
                    secret_resolver=NoSecretResolver(),
                )
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. The launch runbook must not restate what the driver derives
# ---------------------------------------------------------------------------


class TestRunbookAgreesWithTheDerivation:
    def test_runbook_pins_the_derived_row_range_and_seed_base(self) -> None:
        text = _RUNBOOK.read_text(encoding="utf-8")
        minimum, maximum = expected_row_bounds(n=_N, promote_attempts=_PROMOTE_ATTEMPTS)
        assert f"--expected-rows {minimum} --expected-rows-max {maximum}" in text
        assert f"--seed-base {_SEED_BASE}" in text
        assert "--seed-base 9100" in text  # the canary lane

    def test_runbook_launches_only_through_the_supervised_entrypoint(self) -> None:
        """§10.1 / AC7, and the net-negative-surface rule the hermetic runbook
        already carries: no disk-sentinel wrapper may come back."""
        text = _RUNBOOK.read_text(encoding="utf-8")
        assert "so battery-watch" in text
        assert "NEEDS_ATTENTION" not in text
        assert "BATTERY_DONE" not in text
        assert "</dev/null" in text
        assert "pgrep -f" in text

    def test_runbook_gates_the_battery_behind_the_canary_check(self) -> None:
        text = _RUNBOOK.read_text(encoding="utf-8")
        assert "scripts/check_canary_decisiveness.py" in text
        assert "do not\nlaunch" in text.lower() or "do not launch" in text.lower()


# ---------------------------------------------------------------------------
# 8. The REAL _run_battery, driven end to end
# ---------------------------------------------------------------------------


_PROMOTED_PAYLOAD: dict[str, Any] = {
    "kind": "steel_onslaught.policy_promoted",
    "match_id": "match.stub.promote.6101",
    "policy_id": "policy.aggressive.gen1-stub",
    "archetype": "aggressive",
    "generation": 1,
    "spec_hash": "a" * 64,
    "parent_spec_hash": "b" * 64,
    "source_lineage_digest": "c" * 64,
    "evidence_scored_event_id": "01HZY3E9ZTAV5J6BQF8KM2WXSC",
}


def _stub_row(
    *, phase: str, seed: int, generation: int, promoted: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "phase": phase,
        "seed": seed,
        "match_id": f"match.stub.{phase}.{seed}",
        "policy_provenance": {
            "player_id": "player.blue",
            "generation": generation,
            "policy_id": (
                str(_PROMOTED_PAYLOAD["policy_id"]) if generation else "policy.aggressive.genesis"
            ),
            "spec_hash": _PROMOTED_PAYLOAD["spec_hash"] if generation else "genesis-hash",
            "source_lineage_digest": (
                _PROMOTED_PAYLOAD["source_lineage_digest"] if generation else "genesis-lin"
            ),
        },
        "winner_player_id": "player.blue",
        "is_draw": False,
        "end_reason": "last_mech_standing",
        "duration_ticks": 10,
        "replay_validity": {"player.red": 1, "player.blue": 1},
        "learning_seat": {
            "seat": "blue",
            "dealt": {},
            "planned": {},
            "keep_rates": {},
            "planned_share": {},
        },
        "failed_completions": 0,
        "empty_content_completions": {},
        "policy_promoted": promoted,
    }


class TestRunBatteryFliesThePreregisteredSeeds:
    """Drives the REAL ``_run_battery`` with ONLY the LLM-calling boundary
    (``_measure_match``) stubbed. ``--seed-base`` is asserted where it actually
    matters -- the seeds the driver passes to the match seam -- not against a
    hand-rolled reimplementation of the arithmetic."""

    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        *,
        argv: list[str],
        promote_on_attempt: int | None = 1,
    ) -> tuple[int, list[tuple[str, int]], Path]:
        import scripts.run_lgate2_adaptation_battery as driver

        flown: list[tuple[str, int]] = []
        attempts = {"promote": 0}

        def _stub_measure_match(overlay: Any, **kwargs: Any) -> dict[str, Any]:
            del overlay
            phase, seed = kwargs["phase"], kwargs["seed"]
            flown.append((phase, seed))
            if phase == "baseline":
                return _stub_row(phase=phase, seed=seed, generation=0, promoted=None)
            if phase == "promote":
                attempts["promote"] += 1
                fires = promote_on_attempt is not None and attempts["promote"] >= promote_on_attempt
                return _stub_row(
                    phase=phase,
                    seed=seed,
                    generation=0,
                    promoted=dict(_PROMOTED_PAYLOAD) if fires else None,
                )
            return _stub_row(phase=phase, seed=seed, generation=1, promoted=None)

        monkeypatch.setattr(driver, "_measure_match", _stub_measure_match)
        args = driver._build_parser().parse_args(
            [
                "--seat",
                "blue",
                "--genesis",
                "0.5",
                "--step",
                "2.0",
                "--overlay",
                str(_OVERLAY),
                "--blue-loadout",
                str(_BLUE_LOADOUT),
                "--red-loadout",
                str(_RED_LOADOUT),
                *argv,
            ]
        )
        state_root = tmp_path / "state"
        state_root.mkdir()
        raw_path = state_root / "battery_raw.jsonl"
        exit_code = driver._run_battery(args, state_root, raw_path)
        return exit_code, flown, raw_path

    def test_seed_base_6000_flies_exactly_the_preregistered_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC2 asserts the seeds are exactly 6001-6030 / 6101-6115 / 6201-6230.
        Before ``--seed-base`` the driver could only fly 4xxx."""
        exit_code, flown, raw_path = self._run(
            monkeypatch,
            tmp_path,
            argv=["--n", "30", "--promote-attempts", "15", "--seed-base", "6000"],
        )
        assert exit_code == 0
        assert [seed for phase, seed in flown if phase == "baseline"] == list(range(6001, 6031))
        assert [seed for phase, seed in flown if phase == "promote"] == [6101]
        assert [seed for phase, seed in flown if phase == "post"] == list(range(6201, 6231))
        rows = raw_path.read_text(encoding="utf-8").strip().splitlines()
        minimum, maximum = expected_row_bounds(n=30, promote_attempts=15)
        assert len(rows) == 61
        assert rows_satisfy_contract(len(rows), minimum, maximum)

    def test_a_later_promotion_still_lands_inside_the_derived_range(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The case the copied ``--expected-rows 61`` would have called
        INCOMPLETE: a clean battery that needed four promote attempts."""
        exit_code, flown, raw_path = self._run(
            monkeypatch,
            tmp_path,
            argv=["--n", "30", "--promote-attempts", "15", "--seed-base", "6000"],
            promote_on_attempt=4,
        )
        assert exit_code == 0
        assert [seed for phase, seed in flown if phase == "promote"] == [6101, 6102, 6103, 6104]
        rows = raw_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == 64
        minimum, maximum = expected_row_bounds(n=30, promote_attempts=15)
        assert rows_satisfy_contract(len(rows), minimum, maximum)
        assert not rows_satisfy_contract(len(rows), 61, None)  # the old exact contract

    def test_the_canary_configuration_flies_exactly_two_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§6.3's canary is n=2 at seeds 9101/9102. ``--promote-attempts 0``
        gives the promote phase an empty seed list, so the driver stops with
        its NO-PROMOTION finding and never reaches post -- which is what keeps
        a quarantined canary from touching the policy chain at all."""
        exit_code, flown, raw_path = self._run(
            monkeypatch,
            tmp_path,
            argv=["--n", "2", "--promote-attempts", "0", "--seed-base", "9100"],
        )
        assert exit_code == 1  # NO-PROMOTION by construction; the gate is the checker, not this
        assert flown == [("baseline", 9101), ("baseline", 9102)]
        assert len(raw_path.read_text(encoding="utf-8").strip().splitlines()) == 2

    def test_no_promotion_row_count_is_outside_the_clean_range(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§6.1: the escape exits nonzero AND writes a row count the clean
        range rejects, so it can never present as a short COMPLETED."""
        exit_code, flown, raw_path = self._run(
            monkeypatch,
            tmp_path,
            argv=["--n", "30", "--promote-attempts", "15", "--seed-base", "6000"],
            promote_on_attempt=None,
        )
        assert exit_code == 1
        assert [seed for phase, seed in flown if phase == "promote"] == list(range(6101, 6116))
        assert not any(phase == "post" for phase, _ in flown)
        rows = raw_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == 45
        minimum, maximum = expected_row_bounds(n=30, promote_attempts=15)
        assert not rows_satisfy_contract(len(rows), minimum, maximum)

    def test_summary_publishes_the_executed_seed_base_and_row_bounds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falsifiable from the artifact alone, the OMN-15587 discipline: an
        acceptance gate should not have to infer the flown lane from the seeds
        it happens to find."""
        import json

        _, _, raw_path = self._run(
            monkeypatch,
            tmp_path,
            argv=["--n", "30", "--promote-attempts", "15", "--seed-base", "6000"],
        )
        summary = json.loads((raw_path.parent / "battery_summary.json").read_text(encoding="utf-8"))
        assert summary["seed_base"] == 6000
        assert summary["expected_row_bounds"] == [61, 75]
