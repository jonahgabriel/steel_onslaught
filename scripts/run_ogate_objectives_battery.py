"""O-GATE objectives battery on live keyless Qwen (design 2026-07-22 §5).

Answers the gate's empirical question: **do matches end on play, not clock?**
Runs N live matches on the Phase-4 objective arena ``foundry_60_asym_v1``
(overlay ``tactical_split_overdeal_asym_v1_qwen.yaml``), red berserker
(the brawler) vs blue sniper — the same seat/loadout pairing as every
prior battery — and produces the terminal-class scorecard the O-GATE row
requires:

- terminal-class distribution (``vp_threshold`` / ``elimination`` /
  ``tick_cap`` / ``abort``) — the gate passes iff >= 95% of matches end on
  VP threshold or elimination;
- winner-side distribution and the brawler win-rate (a REPORTED observable,
  never a tuning target — design §2);
- match-length distribution (``duration_ticks``);
- objective-contest metrics read from ``OBJECTIVE_SCORED`` events: per-
  objective award counts by side, control changes (consecutive awards of the
  same objective by different players), and final VP margins;
- abort classes (expected 0 per the #124 post-fix battery).

``max_ticks`` is passed explicitly (default 1000) so the design's clock
failsafe is the reachable anomaly class (``victory_kind=tick_cap_failsafe``
or ``draw_max_ticks``) rather than the engine's ``aborted_runaway`` guard.

Every match also verifies the Phase-4 provenance seam inline: MATCH_STARTED
must carry ``arena_contract_hash`` equal to the recomputed digest of the
shipped ``--expected-arena`` contract (default ``foundry_60_asym_v1``). Pass a
symmetric, objective-less arena (``--expected-arena foundry_60`` with a utility
overlay that references it) to run the same battery on a non-asym scenario: the
objective/VP scorecard then aggregates zero objectives without error, and the
keep/terminal-class/winner statistics still compute.

Run (defaults: n=30, seeds 5001..5030):

    uv run python scripts/run_ogate_objectives_battery.py --n 30
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOOpenAICompatibleProviderBinding,
    ModelSOSecretRef,
)
from steel_onslaught.contracts.arena import arena_contract_hash
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOObjectiveScoredPayload,
    ModelSOVictoryDeclaredPayload,
)
from steel_onslaught.llm.client_http import NoSecretResolver
from steel_onslaught.llm.schemas import ProtocolSecretResolver, SecretResolutionError
from steel_onslaught.match.composition import (
    assemble_match_live,
    load_application_overlay,
    load_match_contract_catalog,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OVERLAY = _REPO_ROOT / "contracts_data/overlays/tactical_split_overdeal_asym_v1_qwen.yaml"
_RED_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/llm_qwen35_berserker.yaml"
_BLUE_LOADOUT = _REPO_ROOT / "contracts_data/loadouts/qwen35/sniper_ironclad.yaml"
_ARENA_ID = "foundry_60_asym_v1"

_RED = "player.red"  # brawler (berserker) — the reported observable's seat
_BLUE = "player.blue"  # sniper

_ELIMINATION_REASONS = frozenset({"last_mech_standing", "pilot_killed", "draw_mutual_destruction"})

# Opaque overlay secret refs -> the env var names that carry their value. The
# battery driver only ever resolves keys for cross-provider ARMS whose overlay
# declares a secret-bearing provider (the OpenRouter free arm). No key is
# inferred from provider or model naming; the mapping is explicit and narrow.
_SECRET_REF_ENV_NAMES: dict[str, tuple[str, ...]] = {
    # OpenRouter Bearer key. Canonical name in ~/.omnibase/.env is
    # OPEN_ROUTER_API_KEY; OPENROUTER_API_KEY is accepted as the documented
    # ``so play-live`` alias so one exported key serves both paths.
    "secret://llm/openrouter": ("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY"),
    # Zhipu/GLM (z.ai) Bearer key for the cross-architecture arm. Canonical name
    # in ~/.omnibase/.env is LLM_GLM_API_KEY; resolved at the battery edge exactly
    # like the OpenRouter key so the real key never touches the overlay or argv.
    "secret://llm/glm": ("LLM_GLM_API_KEY",),
    # Direct (non-OpenRouter) Google Gemini API key, own-billed -- used by the
    # 2026-07-24 vision-representation experiment (V-TEXT/V-IMG arms). Canonical
    # name in ~/.omnibase/.env is GEMINI_API_KEY.
    "secret://llm/gemini": ("GEMINI_API_KEY",),
    # Google Cloud Vertex AI, OpenAI-compatible endpoint -- the 2026-07-24
    # vision-representation experiment's OpenRouter/Gemini-direct rerun
    # (both free-tier-blocked). Unlike the other refs above, this is NOT a
    # static API key: it is a short-lived (~1hr) OAuth2 access token minted
    # per invocation via ``gcloud auth application-default print-access-token``
    # and exported as VERTEX_ACCESS_TOKEN immediately before each battery
    # process launches. Because this driver runs one process per seed
    # (per-seed isolated invocation), re-minting before every seed removes
    # all token-expiry risk across a multi-hour battery -- no caching, no
    # refresh-mid-process logic needed here.
    "secret://llm/vertex": ("VERTEX_ACCESS_TOKEN",),
}


def _load_omnibase_dotenv() -> dict[str, str]:
    """Parse ``~/.omnibase/.env`` into a name->value map (portable, no deps).

    Read-only and best-effort: a missing file yields an empty map. Values are
    never logged; only names are ever surfaced in error text.
    """

    path = Path.home() / ".omnibase" / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _first_env_value(names: Sequence[str], dotenv: Mapping[str, str]) -> str | None:
    """First non-empty value for ``names`` from the process env, then the dotenv."""

    for name in names:
        value = os.environ.get(name) or dotenv.get(name)
        if value:
            return value
    return None


class _EnvBackedSecretResolver:
    """Resolve overlay ``secret://`` refs from the environment / ~/.omnibase/.env.

    Composition never reads the environment; this tiny edge adapter is the only
    place the real key is loaded, and it is handed only to the OpenAI-compatible
    client's Authorization header at request time. The key is never written to a
    file, printed, or placed on argv. Selected per-reference so an overlay with
    no secret-bearing provider never triggers a key lookup.
    """

    def __init__(self, secrets: Mapping[str, str]) -> None:
        self._secrets = MappingProxyType(dict(secrets))

    @classmethod
    def for_references(cls, references: Sequence[str]) -> _EnvBackedSecretResolver:
        """Build a resolver that has already loaded every required secret ref.

        Fails closed (``SecretResolutionError``) if a ref has no known env
        mapping or the mapped env var is absent/empty, so a missing key is a
        loud edge failure, never a silently unauthenticated request.
        """

        dotenv = _load_omnibase_dotenv()
        resolved: dict[str, str] = {}
        for reference in references:
            env_names = _SECRET_REF_ENV_NAMES.get(reference)
            if env_names is None:
                raise SecretResolutionError(f"no env mapping for secret ref {reference!r}")
            value = _first_env_value(env_names, dotenv)
            if not value:
                raise SecretResolutionError(
                    f"secret ref {reference!r} requires one of {env_names} in the "
                    "environment or ~/.omnibase/.env"
                )
            resolved[reference] = value
        return cls(resolved)

    def resolve(self, reference: ModelSOSecretRef) -> str:
        try:
            return self._secrets[str(reference.ref)]
        except KeyError:
            raise SecretResolutionError(f"unmapped secret ref {reference.ref!r}") from None


def _select_secret_resolver(
    overlay: ModelSOApplicationOverlay,
) -> ProtocolSecretResolver | None:
    """Pick the resolver capability the overlay's declared binding requires.

    - ``none``  -> ``None``: composition rejects an injected resolver and builds
      its own fail-closed ``NoSecretResolver`` (keyless local arms, e.g. deepseek).
    - ``injected`` with no secret-bearing provider -> ``NoSecretResolver``: the
      keyless-but-injected local arms (e.g. qwen, ``secret_ref: null``) whose
      resolver is never consulted. Byte-identical to the prior behavior.
    - ``injected`` with a secret-bearing provider -> an env-backed resolver that
      loads the real key at the edge (the OpenRouter free arm). This is the only
      path that touches OPEN_ROUTER_API_KEY.
    """

    if overlay.llm.secret_resolver.kind == "none":
        return None
    secret_bearing = tuple(
        provider
        for provider in overlay.llm.providers
        if isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
        and provider.secret_ref is not None
    )
    if not secret_bearing:
        return NoSecretResolver()
    references = tuple(
        str(provider.secret_ref.ref)
        for provider in secret_bearing
        if provider.secret_ref is not None
    )
    return _EnvBackedSecretResolver.for_references(references)


def _lane_overlay(state_root: Path, overlay_path: Path = _OVERLAY) -> ModelSOApplicationOverlay:
    """Repoint every durable surface of the overlay into the battery lane."""
    base = load_application_overlay(overlay_path)
    return base.model_copy(
        update={
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
    )


def _terminal_class(end_reason: str | None, victory_kind: str | None) -> str:
    """The O-GATE scorecard class for one terminal.

    Order matters: an explicit-cap victory keeps its historical
    ``last_mech_standing`` reason but is classified by its
    ``tick_cap_failsafe`` victory_kind, so the clock check precedes the
    elimination check.
    """
    if end_reason == "vp_threshold":
        return "vp_threshold"
    if victory_kind == "tick_cap_failsafe" or end_reason == "draw_max_ticks":
        return "tick_cap"
    if end_reason in _ELIMINATION_REASONS:
        return "elimination"
    return "abort"  # aborted / aborted_runaway / provider_semantic_failure / unknown


def _objective_metrics(
    awards: list[ModelSOObjectiveScoredPayload],
) -> dict[str, Any]:
    per_objective: dict[str, dict[str, Any]] = {}
    for payload in awards:
        entry = per_objective.setdefault(
            payload.objective_id,
            {"awards": 0, "by_player": Counter(), "control_changes": 0, "last_controller": None},
        )
        entry["awards"] += 1
        entry["by_player"][payload.controlling_player_id] += 1
        if (
            entry["last_controller"] is not None
            and entry["last_controller"] != payload.controlling_player_id
        ):
            entry["control_changes"] += 1
        entry["last_controller"] = payload.controlling_player_id
    return {
        objective_id: {
            "awards": entry["awards"],
            "by_player": dict(sorted(entry["by_player"].items())),
            "control_changes": entry["control_changes"],
        }
        for objective_id, entry in sorted(per_objective.items())
    }


def _row_winner_player_id(scored: ModelSOMatchScoredPayload) -> str | None:
    """The battery row's decisive-winner answer, self-consistent with ``is_draw``.

    ``ModelSOMatchScoredPayload.winner_player_id`` is a required ``str`` field
    that is NOT usable verbatim as "who won this match": the scoring
    reducer's documented Task 30 draw convention
    (``reducers/scoring.py::_score``) stamps the alphabetically-first player
    into that flattened field even on a draw, because the leaderboard's SQL
    schema declares the column ``NOT NULL`` for its own bucketing purposes --
    ``is_draw`` (and the nested ``winner`` block, which the payload's own
    validator requires to be ``None`` exactly when ``is_draw``) is the
    required disambiguator. A battery evidence row must never carry both a
    winner and a draw flag, so this re-derives the field rather than
    forwarding the reducer's placeholder.

    Root-caused against a real aborted match (seed 5028,
    match.01KYAT1XPK61H653M0YBKR2B88, pair_p4_dmg8 ledger): the terminal
    MATCH_ENDED event correctly carried ``winner_id=null``, but the
    downstream MATCH_SCORED event's flattened ``winner_player_id`` was still
    ``"player.blue"`` despite ``is_draw=true`` -- exactly the leaderboard
    convention above, forwarded uncritically into the evidence row.
    """
    return None if scored.is_draw else scored.winner_player_id


def _run_match(
    overlay: ModelSOApplicationOverlay,
    *,
    seed: int,
    max_ticks: int,
    expected_arena_hash: str,
    expected_arena_id: str = _ARENA_ID,
    red_loadout_path: Path = _RED_LOADOUT,
    blue_loadout_path: Path = _BLUE_LOADOUT,
) -> dict[str, Any]:
    # A ``none`` overlay rejects an injected resolver and lets composition build
    # its own ``NoSecretResolver``; a keyless ``injected`` overlay wants a
    # never-consulted ``NoSecretResolver``; a secret-bearing ``injected`` overlay
    # (the OpenRouter free arm) wants a real env-backed resolver. Selecting by
    # the declared binding + provider secret_ref keeps every arm launchable from
    # one driver without leaking a key into argv or logs.
    secret_resolver = _select_secret_resolver(overlay)
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
        secret_resolver=secret_resolver,
    )
    try:
        final = stack.runner.run()
        events: tuple[ModelSOEventEnvelope, ...] = tuple(
            stack.ledger.read_all(stack.identity.match_id)
        )
    finally:
        stack.close()

    scored: ModelSOMatchScoredPayload | None = None
    victory_kind: str | None = None
    awards: list[ModelSOObjectiveScoredPayload] = []
    failed_completions = 0
    for event in events:
        if event.event_type is SOEventType.MATCH_STARTED:
            started = ModelSOMatchStartedPayload.model_validate(event.payload)
            assert started.arena.arena_id == expected_arena_id, started.arena.arena_id
            assert started.arena_contract_hash == expected_arena_hash, (
                "arena_contract_hash provenance seam broken"
            )
        elif event.event_type is SOEventType.OBJECTIVE_SCORED:
            awards.append(ModelSOObjectiveScoredPayload.model_validate(event.payload))
        elif event.event_type is SOEventType.VICTORY_DECLARED:
            victory_kind = ModelSOVictoryDeclaredPayload.model_validate(event.payload).victory_kind
        elif event.event_type is SOEventType.LLM_COMPLETION_FAILED:
            failed_completions += 1
        elif event.event_type is SOEventType.MATCH_SCORED:
            scored = ModelSOMatchScoredPayload.model_validate(event.payload)

    assert scored is not None, f"match {stack.identity.match_id} did not score"
    end_reason = final.end_reason.value if final.end_reason else None
    vp_totals = {player: int(vp) for player, vp in sorted(final.vp_totals.items())}
    return {
        "seed": seed,
        "match_id": stack.identity.match_id,
        "end_reason": end_reason,
        "victory_kind": victory_kind,
        "terminal_class": _terminal_class(end_reason, victory_kind),
        "winner_player_id": _row_winner_player_id(scored),
        "is_draw": scored.is_draw,
        "duration_ticks": scored.duration_ticks,
        "vp_totals": vp_totals,
        "vp_margin": abs(vp_totals.get(_RED, 0) - vp_totals.get(_BLUE, 0)),
        "first_award_tick": min((a.round_index for a in awards), default=None),
        "objectives": _objective_metrics(awards),
        "total_awards": len(awards),
        "total_control_changes": sum(
            entry["control_changes"] for entry in _objective_metrics(awards).values()
        ),
        "failed_completions": failed_completions,
        "replay_validity": {
            player: score.replay_validity for player, score in scored.scores.items()
        },
    }


def _summarize(rows: list[dict[str, Any]], *, gate_threshold: float) -> dict[str, Any]:
    n = len(rows)
    classes = Counter(row["terminal_class"] for row in rows)
    reason_kind = Counter(f"{row['end_reason']}/{row['victory_kind'] or '-'}" for row in rows)
    winners = Counter("draw" if row["is_draw"] else str(row["winner_player_id"]) for row in rows)
    decided = [row for row in rows if not row["is_draw"]]
    brawler_wins = sum(1 for row in decided if row["winner_player_id"] == _RED)
    ticks = sorted(row["duration_ticks"] for row in rows)
    play_terminals = classes["vp_threshold"] + classes["elimination"]

    objective_totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        for objective_id, entry in row["objectives"].items():
            total = objective_totals.setdefault(
                objective_id,
                {"awards": 0, "by_player": Counter(), "control_changes": 0, "matches_scored": 0},
            )
            total["awards"] += entry["awards"]
            total["by_player"].update(entry["by_player"])
            total["control_changes"] += entry["control_changes"]
            total["matches_scored"] += 1

    vp_matches = [row for row in rows if row["terminal_class"] == "vp_threshold"]
    return {
        "n": n,
        "terminal_classes": dict(sorted(classes.items())),
        "end_reason_x_victory_kind": dict(sorted(reason_kind.items())),
        "play_terminal_fraction": round(play_terminals / n, 4) if n else None,
        "o_gate_pass": bool(n and play_terminals / n >= gate_threshold),
        "winners": dict(sorted(winners.items())),
        "brawler": {
            "player_id": _RED,
            "wins": brawler_wins,
            "win_rate_all": round(brawler_wins / n, 4) if n else None,
            "win_rate_decided": round(brawler_wins / len(decided), 4) if decided else None,
        },
        "duration_ticks": {
            "min": ticks[0] if ticks else None,
            "median": statistics.median(ticks) if ticks else None,
            "mean": round(statistics.fmean(ticks), 1) if ticks else None,
            "max": ticks[-1] if ticks else None,
        },
        "objectives": {
            objective_id: {
                "awards": total["awards"],
                "by_player": dict(sorted(total["by_player"].items())),
                "control_changes": total["control_changes"],
                "matches_scored": total["matches_scored"],
            }
            for objective_id, total in sorted(objective_totals.items())
        },
        "matches_with_control_change": sum(1 for row in rows if row["total_control_changes"] > 0),
        "vp_threshold_margins": sorted(row["vp_margin"] for row in vp_matches),
        "failed_completions": sum(row["failed_completions"] for row in rows),
        "all_replay_valid": all(
            validity == 1 for row in rows for validity in row["replay_validity"].values()
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overlay",
        type=Path,
        default=_OVERLAY,
        help=(
            "application overlay for the battery (default: the asym objective "
            "overlay). Pass the combined asym+utility overlay "
            "(tactical_split_overdeal_utility_asym_v1_qwen.yaml) to measure "
            "whether utility counterplay lets the brawler contest VP. The "
            "overlay's arena must match --expected-arena (default "
            "foundry_60_asym_v1); pass a symmetric utility overlay together with "
            "--expected-arena foundry_60 to run the utility battery on the "
            "objective-less arena."
        ),
    )
    parser.add_argument(
        "--red-loadout",
        type=Path,
        default=_RED_LOADOUT,
        help=(
            "red-seat loadout (pilot_id must resolve in the overlay's pilot "
            "registry); default preserves the qwen35 berserker byte-for-byte. "
            "Pass the qwen27 loadout (contracts_data/loadouts/qwen27/"
            "berserker_scout.yaml) alongside the qwen27 overlay for cross-model B."
        ),
    )
    parser.add_argument(
        "--blue-loadout",
        type=Path,
        default=_BLUE_LOADOUT,
        help=(
            "blue-seat loadout (pilot_id must resolve in the overlay's pilot "
            "registry); default preserves the qwen35 sniper byte-for-byte. "
            "Pass the qwen27 loadout (contracts_data/loadouts/qwen27/"
            "sniper_ironclad.yaml) alongside the qwen27 overlay for cross-model B."
        ),
    )
    parser.add_argument(
        "--expected-arena",
        default=_ARENA_ID,
        help=(
            "arena_id the selected overlay must resolve to; asserted on every "
            "MATCH_STARTED and used to compute the expected arena_contract_hash "
            "provenance seam (default: the asym objective arena). Pass "
            "'foundry_60' to run the symmetric, objective-less arena — the "
            "objective/VP scorecard then aggregates zero objectives without "
            "error while keep/terminal/winner stats still compute."
        ),
    )
    parser.add_argument("--n", type=int, default=30, help="battery size")
    parser.add_argument("--seed-base", type=int, default=5000, help="seeds are base+1..base+n")
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=1000,
        help="explicit clock failsafe (design: tick cap is failsafe-only)",
    )
    parser.add_argument(
        "--gate-threshold", type=float, default=0.95, help="O-GATE play-terminal fraction"
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=_REPO_ROOT / ".onex_state/steel_onslaught/ogate_objectives_battery",
    )
    parser.add_argument("--fresh", action="store_true", help="wipe the battery lane first")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    state_root = args.state_root.resolve()
    if args.fresh and state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    raw_path = state_root / "battery_raw.jsonl"

    expected_arena_id = args.expected_arena
    expected_arena_hash = arena_contract_hash(
        load_match_contract_catalog(_REPO_ROOT / "contracts_data")
        .arenas[expected_arena_id]
        .to_snapshot()
    )
    overlay = _lane_overlay(state_root, args.overlay.resolve(strict=True))
    red_loadout_path = args.red_loadout.resolve(strict=True)
    blue_loadout_path = args.blue_loadout.resolve(strict=True)

    rows: list[dict[str, Any]] = []
    # Seeds whose match died on an unhandled error (provider 429/5xx, transport
    # drop, etc.).  Before 2026-07-24 a single such error propagated out of the
    # loop and killed the whole battery process: the V-IMG vision arm lost 29 of
    # 30 seeds to one 429 on the first call.  A dead seed is now skipped so the
    # remaining seeds still run — but it is recorded and reported LOUDLY, never
    # silently dropped, because a shrunken denominator that looks like a
    # completed battery is worse than a crash.  Skipped seeds are deliberately
    # NOT written to battery_raw.jsonl: that file is the evidence ledger of
    # matches that actually ran, and a synthetic row would corrupt it.
    skipped: list[dict[str, str]] = []
    for index in range(1, args.n + 1):
        seed = args.seed_base + index
        try:
            row = _run_match(
                overlay,
                seed=seed,
                max_ticks=args.max_ticks,
                expected_arena_hash=expected_arena_hash,
                expected_arena_id=expected_arena_id,
                red_loadout_path=red_loadout_path,
                blue_loadout_path=blue_loadout_path,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # broad on purpose: one dead seed must not kill the battery
            detail = " ".join(f"{type(exc).__name__}: {exc}".split())[:240]
            skipped.append({"seed": str(seed), "error": detail})
            print(f"[{index}/{args.n}] seed={seed} SKIPPED — {detail}", flush=True)
            continue
        rows.append(row)
        with raw_path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(row, sort_keys=True) + "\n")
        print(
            f"[{index}/{args.n}] seed={seed} match={row['match_id']} "
            f"class={row['terminal_class']} reason={row['end_reason']} "
            f"kind={row['victory_kind']} winner={row['winner_player_id']} "
            f"ticks={row['duration_ticks']} vp={row['vp_totals']} "
            f"awards={row['total_awards']} changes={row['total_control_changes']}",
            flush=True,
        )

    summary = _summarize(rows, gate_threshold=args.gate_threshold)
    # Surface the shortfall in the summary itself so no downstream reader can
    # mistake a partially-completed battery for a clean n-of-n run.  ``n`` in
    # the summary counts matches that RAN; ``requested_n`` is what was asked
    # for.  o_gate_pass is force-failed on any skip: a trust gate computed over
    # a silently-shrunk denominator is not a trust gate.
    summary["requested_n"] = args.n
    summary["skipped_seeds"] = skipped
    if skipped:
        summary["o_gate_pass"] = False
        print(
            f"\n!! BATTERY INCOMPLETE: {len(skipped)}/{args.n} seeds skipped on error "
            f"({', '.join(s['seed'] for s in skipped)}). "
            f"o_gate_pass force-failed; rerun the skipped seeds before citing this battery.",
            flush=True,
        )
    summary_path = state_root / "battery_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw: {raw_path}\nsummary: {summary_path}")
    if skipped:
        # 2026-07-25 (SO-COMP-CA / SO-COMP-R1): a caller that retries on exit
        # code alone must be able to see a skipped seed. Before this, `main`
        # unconditionally returned 0 even when seeds landed no row -- the
        # summary force-failed `o_gate_pass`, but nothing on `$?` reflected
        # the shortfall, so an exit-code-keyed retry loop silently accepted a
        # shrunken battery (the SO-COMP-CA discarded run: 4 of 30 rows lost
        # with zero error signal). This does not change the exit code or any
        # stdout for a battery with no skips.
        skipped_seed_list = ", ".join(s["seed"] for s in skipped)
        print(
            f"BATTERY FAILED: {len(skipped)} seed(s) skipped, no row written "
            f"(seeds: {skipped_seed_list})",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
