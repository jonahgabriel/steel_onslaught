"""L-GATE-2 before/after adaptation battery on live keyless Qwen.

Answers the gate's empirical question (design 2026-07-22 §5, speculation
register item 3): does a promotion change a later live decision, auditably?

Two modes:

``--mode battery`` (default) — three phases over ONE durable battery lane
(shared event ledger + lineage store, so the promotion chain carries across
phases exactly as it does across production processes), using the
``win_damage_differential_v1`` evaluator:

1. ``baseline``  — live-learning ON, evaluator capped at ``max_value == genesis``
   so promotion is impossible; every match flies the generation-0 policy
   (aggression == ``--genesis``, default ``1.0``) WITH its guidance block.
   N matches.
2. ``promote``   — cap lifted to ``max_value == genesis + step`` (the SAME
   value the ``post`` phase re-pins, OMN-15488: previously a hardcoded
   ``3.0`` independent of ``--genesis``/``--step``, which silently made
   promotion impossible whenever ``genesis + step > 3.0`` — see
   ``_phase_caps``); matches run until the first ``POLICY_PROMOTED`` lands
   on the ledger (bounded attempts).
3. ``post``      — cap re-pinned at the promoted value (genesis + step) so
   the chain freezes at generation 1; every match flies the promoted policy.
   N matches.

``--seat`` selects the learning seat (blue sniper / red berserker) and
``--step`` the perturbation size, so effect-size reruns can vary exactly one
knob per comparison.

``--mode live-fire`` — first live run of the ``selection_outcome_v1``
evaluator lane: real evidence-directed candidate proposal gated through the
offline duel machinery (``DuelEvaluator`` over the composition-built duel
executor), on the same live overlay.  Runs matches until the duel gate
promotes once (or the match budget is exhausted — a legitimate decline is a
reported finding), then flies ONE confirm match proving the promoted policy
governs the next admission.  This is a spine proof for the real judgment
path, not an effect-size battery.

The measured observable is the learning seat's card-selection behavior using
the #117 instruments: per-category keep-rates (planned/dealt) and category
selection distribution, read from the canonical event ledger.  The audit
chain (MATCH_STARTED policy provenance -> POLICY_PROMOTED -> lineage record
digest -> per-match replay validity) is verified inline.  An inconclusive
shift is a reported finding, not a failure to hide.

Run (battery defaults: 10+10, ~35 s/match on the AI-PC endpoint):

    uv run python scripts/run_lgate2_adaptation_battery.py --n 10
    uv run python scripts/run_lgate2_adaptation_battery.py \
        --mode battery --seat red --step 0.5 --n 30
    uv run python scripts/run_lgate2_adaptation_battery.py \
        --mode live-fire --seat red --lf-matches 8
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOLiveLearningBinding,
    ModelSOSelectionOutcomeThresholds,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOLlmCompletionResolvedPayload,
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOPolicyPromotedPayload,
)
from steel_onslaught.llm.client_http import NoSecretResolver
from steel_onslaught.match.composition import assemble_match_live, load_application_overlay

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Defaults preserve the #126/#128 configuration (qwen35 on both seats).  All
# three are CLI-selectable (``--overlay`` / ``--red-loadout`` / ``--blue-loadout``)
# so the same battery can run under a different provider binding per the
# cross-model design (docs/steel_onslaught cross-model design, prerequisite B1).
_OVERLAY = _REPO_ROOT / "contracts_data/overlays/tactical_split_overdeal_v1_qwen.yaml"
_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/llm_qwen35_berserker.yaml"
_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen35/sniper_ironclad.yaml"

# seat -> (player_id, mech_id)
_SEATS = {
    "blue": ("player.blue", "mech.blue.01"),
    "red": ("player.red", "mech.red.01"),
}
_ARCHETYPE = "aggressive"
_GENESIS = {"aggression": 1.0}
_MAX_PROMOTE_ATTEMPTS = 5

# selection_outcome_v1 (live-fire) genesis: the complete aggressive
# spec-parameter set, values from contracts_data/pilots/template_aggressive.yaml
# (the archetype's canonical template) — the duel gate materializes real pilot
# specs, so a partial parameter set fails closed at composition.
_LIVE_FIRE_GENESIS: dict[str, int | float | str] = {
    "vent_at_heat_margin": 5,
    "idle_vent_heat_threshold": 90,
    "mode_switch_pressure_floor": 12,
    "mode_switch_heat_ceiling": 80,
    "weapon_preference": "highest_damage",
}


def _base_overlay_updates(base: ModelSOApplicationOverlay, state_root: Path) -> dict[str, Any]:
    """Repoint every durable surface of the overlay into the battery lane."""
    return {
        "event_ledger": base.event_ledger.model_copy(
            update={"path": state_root / "events.sqlite3"}
        ),
        "leaderboard": base.leaderboard.model_copy(
            update={"path": state_root / "leaderboard.sqlite3"}
        ),
        "learning_artifacts": base.learning_artifacts.model_copy(
            update={
                "evaluation_root": state_root / "evaluations",
                "lineage_root": state_root / "lineage",
                "experiment_root": state_root / "experiments",
            }
        ),
        "evaluation_storage": base.evaluation_storage.model_copy(
            update={"root": state_root / "evaluation_storage"}
        ),
    }


def _lane_overlay(
    state_root: Path,
    *,
    overlay_path: Path,
    max_value: float,
    learning_player: str,
    step: float,
    genesis: float = _GENESIS["aggression"],
) -> ModelSOApplicationOverlay:
    base = load_application_overlay(overlay_path)
    updates = _base_overlay_updates(base, state_root)
    updates["live_learning"] = ModelSOLiveLearningBinding(
        kind="win_damage_differential_v1",
        archetype=_ARCHETYPE,
        learning_player_id=learning_player,
        genesis_parameters={"aggression": genesis},
        parameter="aggression",
        step=step,
        max_value=max_value,
    )
    return base.model_copy(update=updates)


def _live_fire_overlay(
    state_root: Path, *, learning_player: str, args: argparse.Namespace
) -> ModelSOApplicationOverlay:
    base = load_application_overlay(args.overlay)
    updates = _base_overlay_updates(base, state_root)
    updates["live_learning"] = ModelSOLiveLearningBinding(
        kind="selection_outcome_v1",
        archetype=_ARCHETYPE,
        learning_player_id=learning_player,
        genesis_parameters=dict(_LIVE_FIRE_GENESIS),
        parameter=args.lf_parameter,
        base_loadout_path=args.red_loadout,
        duel_max_ticks=args.lf_duel_max_ticks,
        n_search_seeds=args.lf_search_seeds,
        n_holdout_seeds=args.lf_holdout_seeds,
        step_multiplier=1,
        thresholds=ModelSOSelectionOutcomeThresholds(
            p_value_max=args.lf_p_value_max,
            min_decisive_n=args.lf_min_decisive_n,
            max_draw_rate=args.lf_max_draw_rate,
        ),
    )
    return base.model_copy(update=updates)


def _category(card_id: str, catalog: Any) -> str:
    return str(catalog.require(card_id).category.value)


def _empty_content_counts(
    events: tuple[ModelSOEventEnvelope, ...],
) -> dict[str, dict[str, int]]:
    """Per-provider count of RESOLVED completions with empty ``content``.

    llama.cpp-style servers route chain-of-thought to ``reasoning_content`` and
    can return an empty ``content`` on an otherwise-successful completion; the
    strict wire contract reads only ``content``, so these are silent-empty
    failures unless counted (cross-model design, prerequisite B4).  Keyed
    ``provider_id -> finish_reason -> count`` so budget starvation
    (``length``) is distinguishable from silent-empty success (``stop``).
    """
    counts: dict[str, dict[str, int]] = {}
    for event in events:
        if event.event_type is not SOEventType.LLM_COMPLETION_RESOLVED:
            continue
        payload = ModelSOLlmCompletionResolvedPayload.model_validate(event.payload)
        if payload.response_length == 0:
            by_finish = counts.setdefault(payload.provider_id, {})
            by_finish[payload.finish_reason] = by_finish.get(payload.finish_reason, 0) + 1
    return counts


def _merge_empty_content(
    total: dict[str, dict[str, int]], row_counts: dict[str, dict[str, int]]
) -> None:
    for provider_id, by_finish in row_counts.items():
        bucket = total.setdefault(provider_id, {})
        for finish_reason, count in by_finish.items():
            bucket[finish_reason] = bucket.get(finish_reason, 0) + count


def _planned_share(*, planned: Counter[str], dealt: Counter[str]) -> dict[str, float | None]:
    """Per-category share of the seat's programmed registers (OMN-15587).

    The key set is the UNION of the dealt and planned categories, NOT just the
    planned ones: a category the seat held in hand and never programmed has a
    share of exactly ``0.0``, and saying so explicitly is what keeps a
    downstream mean honest.  The earlier form iterated ``sorted(planned)``
    alone, so such a category was simply ABSENT from the row -- and
    ``_summarize`` then averaged the category over only the rows carrying the
    key, i.e. over the matches where it appeared at all.  On the merged
    OMN-15488 battery that inflated ``vent`` 15.4x (baseline: 0.0154 over 2
    present rows, against 0.0010 over the 30 rows actually flown) and 6.0x
    (post: 0.0223 over 5, against 0.0037 over 30).

    ``None`` is reserved for the one genuinely undefined case: a match in which
    the seat programmed nothing at all, where the share is 0/0.  Such a row
    must be dropped from a share mean entirely rather than counted as a 0.0 --
    an unflown match is not evidence of a category being avoided.

    Contrast ``keep_rates``, which is deliberately left alone (OMN-15587 AC6):
    a keep-rate for a category that was never dealt IS 0/0-undefined, so
    excluding it from that mean is correct.
    """
    categories = sorted(set(dealt) | set(planned))
    total_planned = sum(planned.values())
    if not total_planned:
        return dict.fromkeys(categories, None)
    return {category: planned[category] / total_planned for category in categories}


def _measure_match(
    overlay: ModelSOApplicationOverlay,
    *,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    seed: int,
    phase: str,
    learning_player: str,
    learning_seat: str,
    learning_mech: str,
) -> dict[str, Any]:
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=None,
        secret_resolver=NoSecretResolver(),  # keyless provider; composition owns the transport
    )
    try:
        final = stack.runner.run()
        events: tuple[ModelSOEventEnvelope, ...] = tuple(
            stack.ledger.read_all(stack.identity.match_id)
        )
    finally:
        stack.close()

    snapshot = stack.card_runtime_snapshot
    assert snapshot is not None
    catalog = snapshot.card_catalog

    dealt: Counter[str] = Counter()
    planned: Counter[str] = Counter()
    started_provenance: dict[str, Any] | None = None
    scored: ModelSOMatchScoredPayload | None = None
    promoted: dict[str, Any] | None = None
    failed_completions = 0
    for event in events:
        if event.event_type is SOEventType.MATCH_STARTED:
            payload = ModelSOMatchStartedPayload.model_validate(event.payload)
            assert payload.policy_provenance is not None, "learning lane must record provenance"
            (seat_entry,) = payload.policy_provenance
            assert seat_entry.player_id == learning_player
            started_provenance = seat_entry.model_dump(mode="json")
        elif event.event_type is SOEventType.HAND_DEALT and event.subject.mech_id == learning_mech:
            raw_cards = event.payload["card_ids"]
            assert isinstance(raw_cards, (list, tuple))
            for card_id in raw_cards:
                dealt[_category(str(card_id), catalog)] += 1
        elif (
            event.event_type is SOEventType.PLAN_COMMITTED
            and event.subject.mech_id == learning_mech
        ):
            raw_registers = event.payload["registers"]
            assert isinstance(raw_registers, (list, tuple))
            for register in raw_registers:
                planned[_category(str(register["card_id"]), catalog)] += 1
        elif event.event_type is SOEventType.LLM_COMPLETION_FAILED:
            failed_completions += 1
        elif event.event_type is SOEventType.MATCH_SCORED:
            scored = ModelSOMatchScoredPayload.model_validate(event.payload)
        elif event.event_type is SOEventType.POLICY_PROMOTED:
            promoted = ModelSOPolicyPromotedPayload.model_validate(event.payload).model_dump(
                mode="json"
            )

    assert scored is not None, f"match {stack.identity.match_id} did not score"
    keep_rates = {
        category: (planned[category] / dealt[category]) if dealt[category] else None
        for category in sorted(dealt)
    }
    return {
        "phase": phase,
        "seed": seed,
        "match_id": stack.identity.match_id,
        "policy_provenance": started_provenance,
        "winner_player_id": scored.winner_player_id,
        "is_draw": scored.is_draw,
        "end_reason": final.end_reason.value if final.end_reason else None,
        "duration_ticks": scored.duration_ticks,
        "replay_validity": {
            player: score.replay_validity for player, score in scored.scores.items()
        },
        "learning_seat": {
            "seat": learning_seat,
            "dealt": dict(sorted(dealt.items())),
            "planned": dict(sorted(planned.items())),
            "keep_rates": keep_rates,
            "planned_share": _planned_share(planned=planned, dealt=dealt),
        },
        "failed_completions": failed_completions,
        "empty_content_completions": _empty_content_counts(events),
        "policy_promoted": promoted,
    }


def _record_casualty(
    *, phase: str, seed: int, exc: BaseException, skipped_path: Path
) -> dict[str, Any]:
    """Record one seed-level casualty durably and loudly (OMN-15566).

    Mirrors ``run_display_salience_battery.py``'s contamination-safety
    contract (2026-07-25 SO-COMP-CA/SO-COMP-R1): a dead seed is SKIPPED, not
    fatal to the whole battery -- but the FULL (never console-truncated)
    diagnostic is persisted verbatim. It is both appended to a durable
    ``skipped_seeds.jsonl`` sibling of the raw evidence file (so the record
    survives even if a LATER, unrelated failure ends the process before the
    final ``battery_summary.json`` write) and returned so the caller can
    fold it into the run's accumulated ``skipped`` list for the end-of-run
    summary and the force-fail exit code. Only the console preview is
    truncated to 240 chars -- the persisted record never is (same OMN-15240
    lesson: a benign preamble must never eat a downstream truncation budget
    and hide the real error).
    """
    full_detail = " ".join(f"{type(exc).__name__}: {exc}".split())
    skip_record: dict[str, Any] = {"phase": phase, "seed": seed, "error": full_detail}
    # Dedicated structured fields, present only when the raised exception
    # actually carries them (e.g. LlmSemanticExhaustedError/LlmTransportError
    # from the delegation client) -- absent for every other exception shape,
    # so this never invents data the failure didn't actually provide.
    argv = getattr(exc, "argv", None)
    exit_code = getattr(exc, "exit_code", None)
    stderr = getattr(exc, "stderr", None)
    stdout = getattr(exc, "stdout", None)
    if argv is not None:
        skip_record["argv"] = list(argv)
    if exit_code is not None:
        skip_record["exit_code"] = exit_code
    if stderr is not None:
        skip_record["stderr"] = stderr
    if stdout is not None:
        skip_record["stdout"] = stdout
    with skipped_path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(skip_record, sort_keys=True) + "\n")
    console_detail = full_detail[:240]
    print(f"[{phase}] seed={seed} SKIPPED — {console_detail}", file=sys.stderr, flush=True)
    return skip_record


def _summarize(
    rows: list[dict[str, Any]],
    *,
    learning_player: str,
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    empty_content: dict[str, dict[str, int]] = {}
    for row in rows:
        _merge_empty_content(empty_content, row.get("empty_content_completions", {}))

    categories = sorted(
        {category for row in rows for category in row["learning_seat"]["keep_rates"]}
        | {category for row in rows for category in row["learning_seat"]["planned_share"]}
    )
    # OMN-15587: the share denominator is every row that programmed ANYTHING --
    # not the rows that happen to carry a given category's key.  A row that
    # planned none of category `c` contributes an explicit 0.0 to `c`'s mean;
    # only a row that planned nothing at all (share undefined, every entry
    # None) drops out, and it drops out of EVERY category identically, which is
    # why one scalar denominator describes the whole map.
    share_rows = [
        row["learning_seat"]["planned_share"]
        for row in rows
        if any(value is not None for value in row["learning_seat"]["planned_share"].values())
    ]

    def _share(shares: dict[str, float | None], category: str) -> float:
        value = shares.get(category)
        return 0.0 if value is None else value

    return {
        "matches": len(rows),
        # OMN-15566: casualties must never count toward the requested n
        # silently -- this list, scoped to the phase this summary covers,
        # names exactly which seeds were skipped and why.
        "skipped_seeds": skipped or [],
        "policy_ids": sorted({row["policy_provenance"]["policy_id"] for row in rows}),
        "generations": sorted({row["policy_provenance"]["generation"] for row in rows}),
        "mean_keep_rate": {
            category: _mean(
                [
                    row["learning_seat"]["keep_rates"][category]
                    for row in rows
                    if row["learning_seat"]["keep_rates"].get(category) is not None
                ]
            )
            for category in categories
        },
        "mean_planned_share": {
            category: _mean([_share(shares, category) for shares in share_rows])
            for category in categories
        },
        # The denominator behind every `mean_planned_share` entry, published so
        # a reader can falsify this class of defect from the artifact alone
        # (OMN-15587 AC5) instead of recomputing from `battery_raw.jsonl`.
        "planned_share_matches": len(share_rows),
        "learner_wins": sum(
            1 for row in rows if row["winner_player_id"] == learning_player and not row["is_draw"]
        ),
        "failed_completions": sum(row["failed_completions"] for row in rows),
        "empty_content_completions": empty_content,
    }


def _phase_caps(args: argparse.Namespace) -> tuple[float, float, float]:
    """Baseline/promote/post evaluator ``max_value`` caps derived from
    ``--genesis``/``--step``.

    Baseline flies generation 0 capped at ``genesis`` (a candidate would have
    to exceed the cap to promote, so promotion is impossible); promote and
    post are BOTH capped at ``genesis + step`` -- promote so the exact
    candidate the evaluator proposes on a decisive win (``current + step``,
    where ``current == genesis`` during the promote phase) can actually
    clear the cap, post so the chain freezes at generation 1 once promoted
    (OMN-15488: the ``--genesis`` knob generalizes the prior hardcoded
    ``_GENESIS["aggression"] == 1.0`` / promote-phase ``max_value=3.0``
    constants so a decisive endpoint-regime contrast, e.g. 0.5 -> 2.5, can be
    run without touching the driver. Latent bug fixed here: an EARLIER
    version of this knob threaded ``--genesis``/``--step`` into baseline/post
    only and left the promote phase's cap hardcoded at ``3.0`` -- correct for
    every genesis/step pair whose target stays under 3.0 (this battery's own
    0.5/2.0 included, candidate 2.5), but silently unreachable for any pair
    where ``genesis + step > 3.0`` [e.g. ``--genesis 1.5 --step 2.0``,
    candidate 3.5], which would fire the pre-declared NO-PROMOTION escape
    for a reason unrelated to the hypothesis under test.  See
    ``tests/contracts/test_lgate2_delegation_overlay_omn15488.py::
    TestPromotePhaseCapTracksGenesisAndStep`` for the regression proof
    against the underlying ``WinDamageDifferentialEvaluator``.).
    """
    baseline_cap = args.genesis
    post_cap = args.genesis + args.step
    promote_cap = post_cap
    return baseline_cap, promote_cap, post_cap


def _run_battery(args: argparse.Namespace, state_root: Path, raw_path: Path) -> int:
    learning_player, learning_mech = _SEATS[args.seat]
    rows: list[dict[str, Any]] = []
    # OMN-15566: a seed-level exception (e.g. the delegation client's
    # LlmSemanticExhaustedError after a bounded reprompt exhausts, or any
    # other unclassified per-match failure) must never kill the whole
    # battery process -- it is recorded as a loud, durable casualty and the
    # run continues. `skipped_path` is a sibling of `raw_path`, matching
    # `run_display_salience_battery.py`'s contamination-safety contract.
    skipped: list[dict[str, Any]] = []
    skipped_path = state_root / "skipped_seeds.jsonl"
    baseline_cap, promote_cap, post_cap = _phase_caps(args)

    def _run_phase(
        phase: str, *, max_value: float, seeds: list[int], stop_on_promotion: bool
    ) -> list[dict[str, Any]]:
        overlay = _lane_overlay(
            state_root,
            overlay_path=args.overlay,
            max_value=max_value,
            learning_player=learning_player,
            step=args.step,
            genesis=args.genesis,
        )
        phase_rows: list[dict[str, Any]] = []
        for seed in seeds:
            try:
                row = _measure_match(
                    overlay,
                    red_loadout_path=args.red_loadout,
                    blue_loadout_path=args.blue_loadout,
                    seed=seed,
                    phase=phase,
                    learning_player=learning_player,
                    learning_seat=args.seat,
                    learning_mech=learning_mech,
                )
            except KeyboardInterrupt:
                raise
            except AssertionError:
                # OMN-15566 r5b (adversarial-verifier finding 3): the
                # in-match integrity asserts inside ``_measure_match``
                # ("learning lane must record provenance", "match did not
                # score") are invariant violations, not the recoverable
                # provider/quality-gate failures this containment exists
                # for -- swallowing them here would silently hide a broken
                # instrumentation/harness bug behind a routine "casualty"
                # entry. Excluded from containment BEFORE the generic
                # ``except Exception`` arm below so they abort the process
                # hard, exactly as they did before containment existed.
                raise
            except Exception as exc:  # one dead seed must not kill the whole battery (OMN-15566)
                skipped.append(
                    _record_casualty(phase=phase, seed=seed, exc=exc, skipped_path=skipped_path)
                )
                continue
            rows.append(row)
            phase_rows.append(row)
            with raw_path.open("a", encoding="utf-8") as sink:
                sink.write(json.dumps(row, sort_keys=True) + "\n")
            provenance = row["policy_provenance"]
            print(
                f"[{phase}] seed={seed} match={row['match_id']} "
                f"gen={provenance['generation']} winner={row['winner_player_id']} "
                f"ticks={row['duration_ticks']} keep={row['learning_seat']['keep_rates']} "
                f"promoted={'yes' if row['policy_promoted'] else 'no'}",
                flush=True,
            )
            if stop_on_promotion and row["policy_promoted"] is not None:
                break
        return phase_rows

    # Phase assertions below stay HARD failures -- they operate on the
    # returned, already-successful rows only (casualties never enter these
    # lists), so containment above does not weaken them.
    baseline = _run_phase(
        "baseline",
        max_value=baseline_cap,  # == genesis: candidate would exceed the cap, never promotes
        seeds=[4000 + index for index in range(1, args.n + 1)],
        stop_on_promotion=False,
    )
    assert all(row["policy_promoted"] is None for row in baseline), (
        "baseline cap must forbid promotion"
    )
    assert all(row["policy_provenance"]["generation"] == 0 for row in baseline)

    promote = _run_phase(
        "promote",
        max_value=promote_cap,  # == genesis + step: the exact candidate a decisive win proposes
        seeds=[4100 + index for index in range(1, args.promote_attempts + 1)],
        stop_on_promotion=True,
    )
    promotion = next((row["policy_promoted"] for row in promote if row["policy_promoted"]), None)
    if promotion is None:
        casualty_note = (
            f" ({len(skipped)} seed casualty(ies) recorded, see {skipped_path})" if skipped else ""
        )
        print(
            "FINDING: no promotion occurred within "
            f"{args.promote_attempts} promote-phase matches; L-GATE-2 not exercised"
            f"{casualty_note}",
            flush=True,
        )
        return 1

    post = _run_phase(
        "post",
        max_value=post_cap,  # == genesis + step: freeze the chain at generation 1
        seeds=[4200 + index for index in range(1, args.n + 1)],
        stop_on_promotion=False,
    )
    for row in post:
        provenance = row["policy_provenance"]
        assert provenance["generation"] == 1, "post-phase match did not fly the promoted policy"
        assert provenance["policy_id"] == promotion["policy_id"]
        assert provenance["spec_hash"] == promotion["spec_hash"]
        assert provenance["source_lineage_digest"] == promotion["source_lineage_digest"]

    lineage_path = (
        state_root
        / "lineage"
        / promotion["archetype"]
        / promotion["spec_hash"]
        / f"{promotion['source_lineage_digest']}.yaml"
    )
    baseline_skipped = [s for s in skipped if s["phase"] == "baseline"]
    promote_skipped = [s for s in skipped if s["phase"] == "promote"]
    post_skipped = [s for s in skipped if s["phase"] == "post"]
    summary = {
        "seat": args.seat,
        "genesis": args.genesis,
        "step": args.step,
        "baseline": _summarize(baseline, learning_player=learning_player, skipped=baseline_skipped),
        "promote": _summarize(promote, learning_player=learning_player, skipped=promote_skipped),
        "post": _summarize(post, learning_player=learning_player, skipped=post_skipped),
        "promotion": promotion,
        "chain": {
            "lineage_record_exists": lineage_path.is_file(),
            "all_replay_valid": all(
                validity == 1 for row in rows for validity in row["replay_validity"].values()
            ),
        },
        # OMN-15566: the full, run-wide casualty list -- never silently
        # folded into the n=30 row target above.
        "skipped_seeds": skipped,
    }
    summary_path = state_root / "battery_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw: {raw_path}\nsummary: {summary_path}")
    if skipped:
        print(
            f"BATTERY COMPLETED WITH CASUALTIES: {len(skipped)} seed(s) skipped, no row "
            f"written (see {skipped_path}) -- force-failing exit code per the "
            "contamination-safety contract (OMN-15566)",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


def _run_live_fire(args: argparse.Namespace, state_root: Path, raw_path: Path) -> int:
    """First live run of the selection_outcome_v1 lane: spine proof, small n."""
    learning_player, learning_mech = _SEATS[args.seat]
    overlay = _live_fire_overlay(state_root, learning_player=learning_player, args=args)
    rows: list[dict[str, Any]] = []
    # OMN-15566: same contamination-safety contract as the battery mode's
    # _run_phase -- one dead seed (or the one-off confirm match) must not
    # kill the process.
    skipped: list[dict[str, Any]] = []
    skipped_path = state_root / "skipped_seeds.jsonl"
    promotion: dict[str, Any] | None = None

    def _one(seed: int, phase: str) -> dict[str, Any] | None:
        try:
            row = _measure_match(
                overlay,
                red_loadout_path=args.red_loadout,
                blue_loadout_path=args.blue_loadout,
                seed=seed,
                phase=phase,
                learning_player=learning_player,
                learning_seat=args.seat,
                learning_mech=learning_mech,
            )
        except KeyboardInterrupt:
            raise
        except AssertionError:
            # OMN-15566 r5b: see the matching ``_run_phase`` exclusion above
            # -- an in-match integrity assert is a hard invariant violation,
            # never a contained casualty.
            raise
        except Exception as exc:  # one dead seed must not kill live-fire either (OMN-15566)
            skipped.append(
                _record_casualty(phase=phase, seed=seed, exc=exc, skipped_path=skipped_path)
            )
            return None
        rows.append(row)
        with raw_path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(row, sort_keys=True) + "\n")
        provenance = row["policy_provenance"]
        print(
            f"[{phase}] seed={seed} match={row['match_id']} "
            f"gen={provenance['generation']} winner={row['winner_player_id']} "
            f"ticks={row['duration_ticks']} "
            f"promoted={'yes' if row['policy_promoted'] else 'no'}",
            flush=True,
        )
        return row

    for index in range(1, args.lf_matches + 1):
        row = _one(4300 + index, "live_fire")
        if row is None:  # casualty -- recorded already, this attempt is spent, not retried
            continue
        if row["policy_promoted"] is not None:
            promotion = row["policy_promoted"]
            break

    confirm: dict[str, Any] | None = None
    confirm_casualty = False
    if promotion is not None:
        # The spine proof: the NEXT admission must fly the promoted policy.
        confirm = _one(4400, "live_fire_confirm")
        if confirm is None:
            confirm_casualty = True
        else:
            provenance = confirm["policy_provenance"]
            assert provenance["generation"] == promotion["generation"], (
                "confirm match did not fly the promoted policy"
            )
            assert provenance["policy_id"] == promotion["policy_id"]
            assert provenance["spec_hash"] == promotion["spec_hash"]
            assert provenance["source_lineage_digest"] == promotion["source_lineage_digest"]

    # Duel-gate evidence: every terminal evaluation leaves an evaluation
    # workspace (materialized specs/loadouts + per-duel sqlite ledgers) even
    # when the gate declines — cite them either way.
    evaluation_dirs = sorted(
        str(path.relative_to(state_root))
        for path in (state_root / "evaluations").glob("eval_*")
        if path.is_dir()
    )
    lineage_path: Path | None = None
    if promotion is not None:
        lineage_path = (
            state_root
            / "lineage"
            / promotion["archetype"]
            / promotion["spec_hash"]
            / f"{promotion['source_lineage_digest']}.yaml"
        )
    summary = {
        "mode": "live-fire",
        "seat": args.seat,
        "parameter": args.lf_parameter,
        "thresholds": {
            "p_value_max": args.lf_p_value_max,
            "min_decisive_n": args.lf_min_decisive_n,
            "max_draw_rate": args.lf_max_draw_rate,
        },
        "duel_battery": {
            "n_search_seeds": args.lf_search_seeds,
            "n_holdout_seeds": args.lf_holdout_seeds,
            "duel_max_ticks": args.lf_duel_max_ticks,
        },
        "matches": _summarize(rows, learning_player=learning_player, skipped=skipped),
        "promotion": promotion,
        "confirm_provenance": (confirm or {}).get("policy_provenance"),
        "confirm_casualty": confirm_casualty,
        "chain": {
            "evaluation_workspaces": evaluation_dirs,
            "lineage_record_exists": lineage_path.is_file() if lineage_path else False,
            "all_replay_valid": all(
                validity == 1 for row in rows for validity in row["replay_validity"].values()
            ),
        },
        # OMN-15566: never silently folded into the match budget above.
        "skipped_seeds": skipped,
    }
    summary_path = state_root / "live_fire_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw: {raw_path}\nsummary: {summary_path}")
    if skipped:
        print(
            f"LIVE-FIRE COMPLETED WITH CASUALTIES: {len(skipped)} seed(s) skipped, no row "
            f"written (see {skipped_path}) -- force-failing exit code per the "
            "contamination-safety contract (OMN-15566)",
            file=sys.stderr,
            flush=True,
        )
        return 1
    if promotion is None:
        print(
            f"FINDING: the duel gate declined promotion in all {len(rows)} matches; "
            "decline evidence retained in the evaluation workspaces above",
            flush=True,
        )
        return 0  # a legitimate decline is a reported finding, not a failure
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("battery", "live-fire"), default="battery")
    parser.add_argument(
        "--overlay",
        type=Path,
        default=_OVERLAY,
        help=(
            "application overlay for every phase — carries BOTH seats' provider "
            "bindings and the pilot registry, so this flag selects the model under test"
        ),
    )
    parser.add_argument(
        "--red-loadout",
        type=Path,
        default=_RED_LOADOUT,
        help="red-seat loadout (pilot_id must resolve in the overlay's pilot registry)",
    )
    parser.add_argument(
        "--blue-loadout",
        type=Path,
        default=_BLUE_LOADOUT,
        help="blue-seat loadout (pilot_id must resolve in the overlay's pilot registry)",
    )
    parser.add_argument("--seat", choices=tuple(_SEATS), default="blue", help="learning seat")
    parser.add_argument("--n", type=int, default=10, help="matches per before/after phase")
    parser.add_argument(
        "--step", type=float, default=0.25, help="aggression perturbation per promotion"
    )
    parser.add_argument(
        "--genesis",
        type=float,
        default=_GENESIS["aggression"],
        help=(
            "starting aggression value (OMN-15488): the baseline phase caps the "
            "evaluator at this value (promotion impossible) and the promote AND "
            "post phases cap it at genesis + step (chain frozen at generation 1 "
            "once promoted). Default 1.0 reproduces the #126/#128 baseline/post "
            "cap arithmetic on a FRESH (--fresh) state-root. It does NOT guarantee "
            "identical promote-phase behavior on a WARM re-run: remediation round "
            "1 replaced the pre-OMN-15488 hardcoded promote-phase max_value=3.0 "
            "with genesis + step, so a state-root already promoted past that new, "
            "lower cap by an earlier run can no longer promote further under the "
            "default step 0.25 (candidate current + step may exceed the new cap "
            "where the old fixed 3.0 admitted it) -- use --fresh for a clean "
            "before/after comparison. A decisive endpoint-regime contrast (e.g. "
            "--genesis 0.5 --step 2.0) spans both named regimes of the aggression "
            "semantics sentence without any other driver change."
        ),
    )
    parser.add_argument(
        "--promote-attempts",
        type=int,
        default=_MAX_PROMOTE_ATTEMPTS,
        help="promote-phase match budget (the evaluator needs a decisive learner win to fire)",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=_REPO_ROOT / ".onex_state/steel_onslaught/lgate2_adaptation_battery",
    )
    parser.add_argument("--fresh", action="store_true", help="wipe the battery lane first")
    # live-fire (selection_outcome_v1) knobs
    parser.add_argument("--lf-matches", type=int, default=8, help="live-fire match budget")
    parser.add_argument(
        "--lf-parameter",
        default="vent_at_heat_margin",
        help="perturbed aggressive-archetype spec parameter (numeric bound)",
    )
    parser.add_argument("--lf-search-seeds", type=int, default=2)
    parser.add_argument("--lf-holdout-seeds", type=int, default=2)
    parser.add_argument("--lf-duel-max-ticks", type=int, default=200)
    # Spine-proof thresholds: n_decisive from a 4-seed gate can never reach the
    # offline default min_decisive_n=10, so the lane would decline vacuously.
    # These overrides keep the gate real (parent can still win) while letting
    # promotion actually fire; the evidence doc must state them.
    parser.add_argument("--lf-min-decisive-n", type=int, default=1)
    parser.add_argument("--lf-p-value-max", type=float, default=1.0)
    parser.add_argument("--lf-max-draw-rate", type=float, default=1.0)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    args.overlay = args.overlay.resolve(strict=True)
    args.red_loadout = args.red_loadout.resolve(strict=True)
    args.blue_loadout = args.blue_loadout.resolve(strict=True)

    state_root = args.state_root.resolve()
    if args.fresh and state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    raw_path = state_root / (
        "battery_raw.jsonl" if args.mode == "battery" else "live_fire_raw.jsonl"
    )

    if args.mode == "battery":
        return _run_battery(args, state_root, raw_path)
    return _run_live_fire(args, state_root, raw_path)


if __name__ == "__main__":
    sys.exit(main())
