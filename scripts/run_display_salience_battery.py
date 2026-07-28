"""Display-salience arm #1 battery via the platform path (OMN-15171).

Retires the nohup/sequential-in-process battery lifecycle
(``run_ogate_objectives_battery.py``-style + the uncommitted per-seed shell
wrapper named in ``docs/evidence/2026-07-24-vl_vertex_rerun-battery.md:37``)
for display-salience arm #1 ONLY (OMN-15166, the "default"/"prominent"
corners committed in #223). All other arms' drivers are untouched --
``OpenAICompatibleClient`` stays fully supported for them indefinitely
(OMN-15154 hostile-#9 disposition; migrating the rest is a separate,
explicitly out-of-scope Backlog candidate, plan §5 item 20).

Battery execution for this arm now goes through the same platform path
OMN-15170's live driver test (``tests/live/test_omn15170_live_driver.py``)
already proved live, generalized from one match to n seeds:

- :func:`~steel_onslaught.match.composition.assemble_match_live` wired with
  the arm's real, committed delegation-bound overlay (``kind:
  onex_delegation``, backend_id ``local-coder-mlx`` -- #223, OMN-15166) --
  every pilot decision routes through the real
  ``node_delegate_skill_orchestrator`` platform path
  (:class:`~steel_onslaught.llm.client_delegation.LlmBusDelegationClient`),
  never a raw HTTP call.
- The real :class:`~steel_onslaught.bus.kafka_forwarder
  .KafkaTerminalEventForwarder` (#218, OMN-15167) -- every seed's 4 terminal
  lifecycle events (``MATCH_STARTED``/``MATCH_ENDED``/``MATCH_SCORED``/
  ``VICTORY_DECLARED``) are forwarded onto
  ``onex.evt.steel-onslaught.match-terminal.v1``, keyed by ``match_id``,
  through a real ``confluent_kafka.Producer`` -- never a local-only,
  nohup-invisible run.
- One typed, in-process Python entrypoint (this script) drives the seeds --
  a fresh :class:`~steel_onslaught.match.composition.LiveMatchStack` per
  seed (own bus, own ledger connection, own minted ``match_id``/
  ``correlation_id``), closed before the next seed starts, so per-seed
  isolation is preserved exactly as every other battery driver in this
  program already provides -- generalizing the live driver test's
  single-match pattern to n seeds, instead of
  ``nohup uv run python scripts/run_X_battery.py & disown``. One dead seed
  is skipped, loudly (never silently), and force-fails the process exit
  code -- the same contamination-safety contract
  ``run_ogate_objectives_battery.py`` already carries (2026-07-25
  SO-COMP-CA / SO-COMP-R1 fix).

Evidence artifacts are unchanged from every other battery in this program:
``battery_raw.jsonl`` (one JSON row per completed seed) and
``events.sqlite3`` (the lane's canonical event ledger) under
``--state-root``, read verbatim by ``scripts/check_contamination_gate.py``
and ``scripts/check_preregistration_timing.py`` (#207) and every
``docs/evidence/*.md`` analysis script in this repo. Each row additionally
carries ``correlation_id`` and ``kafka_forwarded_event_types`` -- the
minted, machine-checkable proof that THIS seed's terminal events crossed
the platform-bus boundary, not just that a match ran locally.

Scope: display-salience arm #1 ONLY. Running the full ``n=30`` acceptance
battery is OMN-15172's scope (the plan's vertical-slice acceptance run),
not this ticket's -- this script is the retired-nohup DRIVER, proven here
only by a 2-seed smoke run (quarantined, non-battery evidence; the arm's
own pre-registration discipline for its real battery is unaffected -- it
was already committed in #223, and this smoke run makes no hypothesis or
statistical claim).

Before the seed loop starts, :func:`_preflight_delegation_cli` issues one
real completion through the exact delegation-CLI path every seed uses and
fails the whole run (exit 2, no seeds attempted) on any transport error --
OMN-15240, added after a 2026-07-27 acceptance run burned 58 dead seeds
across both corners on one environmental failure (the omnibase_infra
venv's co-installed ``omnimarket`` drifting from the canonical
``$OMNI_HOME/omnimarket`` clone mid-run) that this probe would have caught
in seconds. Every per-seed skip record (``battery_summary.json``'s
``skipped_seeds``) also now carries the FULL, untruncated error text plus
``argv``/``exit_code``/``stderr`` when the failure is a CLI subprocess
exit -- only the console print stays truncated -- so a masked tail (the
same OMN-15240 root cause: a ~190-char benign uv ``VIRTUAL_ENV`` warning
ate a downstream 240-char truncation budget and hid the real error) can
never recur undiagnosed.

OMN-15265 belt: the launch-time preflight above is structurally blind to
drift that lands HOURS into a run -- exactly what killed the 2026-07-27
evening re-run (5h22m of healthy execution, then a concurrent session's
merge advanced the canonical ``$OMNI_HOME/omnimarket`` clone mid-battery).
:func:`_drift_recheck` re-runs the SAME in-process, no-network guard
(``omnibase_infra.cli.omnimarket_drift_guard.check_omnimarket_drift``,
loaded directly by file path -- never
``scripts/check-omnimarket-venv-drift.sh``, which does a live ``git
fetch`` and false-positives against a pinned hermetic snapshot clone that
is intentionally behind the remote by design) every
``_DRIFT_RECHECK_INTERVAL_SEEDS`` completed seeds, turning a
multi-hour/20-dead-seed burn into a seconds-fast abort. This only ever
touches the RUNNING process's own ``$OMNI_HOME`` -- it cannot affect, and
is not affected by, any other lane's environment.

Requires the ``live`` extra (a real Kafka client -- see
``pyproject.toml``'s own ``live`` extra docstring for why this is opt-in
and never installed by CI) and ``$OMNI_HOME`` set (resolves the local
``omnibase_infra`` clone whose ``onex`` CLI the delegation client shells
out to; never hardcode this path -- the overlay's own committed
``omnibase_infra_path: ../omnibase_infra`` is CWD-relative and only
resolves when run from a sibling-of-``omnibase_infra`` checkout, which a
worktree is not -- see :func:`_lane_overlay`).

Run (defaults: corner=default, n=30 seeds 5001..5030 -- the real-battery
shape; pass ``--n 2`` for a smoke run):

    uv sync --extra live
    uv run python scripts/run_display_salience_battery.py --n 2 --seed-base 90000 --fresh
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from steel_onslaught.bus.kafka_forwarder import STEEL_MATCH_TERMINAL_TOPIC, TERMINAL_EVENT_TYPES
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSODelegationProviderBinding,
)
from steel_onslaught.contracts.arena import arena_contract_hash
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import (
    ModelSOMatchScoredPayload,
    ModelSOMatchStartedPayload,
    ModelSOObjectiveScoredPayload,
    ModelSOVictoryDeclaredPayload,
)
from steel_onslaught.llm.client_delegation import LlmBusDelegationClient
from steel_onslaught.llm.schemas import LlmTransportError, ModelSOLlmCompletionRequest
from steel_onslaught.match.composition import (
    SystemIdentityProvider,
    assemble_match_live,
    load_application_overlay,
    load_match_contract_catalog,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OVERLAYS_DIR = _REPO_ROOT / "contracts_data" / "overlays"
_LOADOUTS_DIR = _REPO_ROOT / "contracts_data" / "loadouts" / "delegation_salience"

# The arm's two committed corners (#223, OMN-15166) -- the ONLY two overlays
# this driver knows how to launch. Deliberately not a free-form --overlay
# flag (unlike run_ogate_objectives_battery.py, which spans many lanes):
# this driver is scoped to exactly one arm, and pairing the wrong loadouts
# with a corner's overlay is an invalid launch (the committed overlay's own
# header states the pilot registry is SHARED between corners -- only the
# loadout pair disambiguates which pilots are actually seated).
_CORNER_OVERLAYS: dict[str, Path] = {
    "default": _OVERLAYS_DIR / "foundry_60_asym_v1_salience_default_delegation.yaml",
    "prominent": _OVERLAYS_DIR / "foundry_60_asym_v1_salience_prominent_delegation.yaml",
}
_CORNER_LOADOUTS: dict[str, tuple[Path, Path]] = {
    "default": (_LOADOUTS_DIR / "red_default.yaml", _LOADOUTS_DIR / "blue_default.yaml"),
    "prominent": (_LOADOUTS_DIR / "red_prominent.yaml", _LOADOUTS_DIR / "blue_prominent.yaml"),
}
_ARENA_ID = "foundry_60_asym_v1"
_RED = "player.red"
_BLUE = "player.blue"

_ELIMINATION_REASONS = frozenset({"last_mech_standing", "pilot_killed", "draw_mutual_destruction"})
_TERMINAL_EVENT_TYPE_VALUES = frozenset(member.value for member in TERMINAL_EVENT_TYPES)

# Same stability-test redpanda advertised listener OMN-15170's live driver
# test dials (tests/live/test_omn15170_live_driver.py -- see that module's
# docstring for how this was verified live: `docker exec
# omnibase-infra-stability-test-redpanda cat /etc/redpanda/redpanda.yaml` ->
# advertised_kafka_api). Overridable via STEEL_LIVE_KAFKA_BOOTSTRAP (env,
# matching that test's own override name) for any other lane.
_DEFAULT_KAFKA_BOOTSTRAP = "100.109.203.94:39092"  # sanitize-ok
_ENV_BOOTSTRAP = "STEEL_LIVE_KAFKA_BOOTSTRAP"
_KAFKA_FLUSH_TIMEOUT_SECONDS = 30.0

# OMN-15265: how often (in COMPLETED seeds, never attempted/skipped ones)
# the mid-run drift belt re-checks. 5 trades a small, cheap (local
# `git rev-parse HEAD`, no network, ~2s timeout) recheck cost against how
# long a drifted run can burn before being caught.
_DRIFT_RECHECK_INTERVAL_SEEDS = 5
_OMNI_HOME_ENV = "OMNI_HOME"


class KafkaLiveTransportUnavailableError(RuntimeError):
    """``confluent_kafka`` is not installed -- run ``uv sync --extra live``."""


class _KafkaProducerTransport:
    """Satisfies ``ProtocolTerminalEventTransport`` with a real producer.

    Byte-for-byte the same adapter shape as
    ``tests/live/test_omn15170_live_driver.py``'s ``_KafkaProducerTransport``
    (not imported from there -- a test module is not a production
    dependency of a script). ``publish()`` only enqueues; delivery is not
    guaranteed until ``flush()`` is called (done explicitly, per seed, by
    :func:`_run_seed`). Every delivery report is recorded on
    ``self.delivery_errors`` -- a topic-missing / partition-cap failure
    surfaces here as a per-message error, not a raised exception.
    """

    def __init__(self, producer: Any) -> None:
        self._producer = producer
        self.delivery_errors: list[str] = []

    def _on_delivery(self, err: Any, message: Any) -> None:
        if err is not None:
            self.delivery_errors.append(f"{err} (topic={message.topic()!r} key={message.key()!r})")

    def publish(self, *, topic: str, key: str, value: bytes) -> None:
        self._producer.produce(
            topic=topic, key=key.encode("utf-8"), value=value, callback=self._on_delivery
        )
        self._producer.poll(0)  # serve delivery-report callbacks, non-blocking

    def flush(self, timeout_seconds: float) -> int:
        return int(self._producer.flush(timeout_seconds))


def _build_kafka_transport(bootstrap: str) -> tuple[Any, _KafkaProducerTransport]:
    """Lazily import ``confluent_kafka`` -- never at module import time.

    ``confluent_kafka`` is the ``live`` extra (never installed by CI's
    ``uv sync --extra dev`` -- see ``pyproject.toml``), so importing it at
    module scope would break every test that merely imports this module
    (``tests/cli/test_display_salience_battery_driver.py`` monkeypatches
    this function itself so it never needs the extra installed either).
    """
    try:
        import confluent_kafka
    except ImportError as exc:
        raise KafkaLiveTransportUnavailableError(
            "confluent_kafka is not installed -- run `uv sync --extra live` first. "
            "OMN-15171 retires the nohup lifecycle onto the platform path, which "
            "requires real Kafka forwarding for display-salience arm #1; there is "
            "no --no-kafka escape hatch (that would reintroduce exactly the "
            "local-only, unproven-on-the-bus lifecycle this ticket retires)."
        ) from exc

    producer = confluent_kafka.Producer({"bootstrap.servers": bootstrap})
    return producer, _KafkaProducerTransport(producer)


def _lane_overlay(
    state_root: Path, corner: str, *, omnibase_infra_path: Path
) -> ModelSOApplicationOverlay:
    """Load the selected corner's committed overlay and repoint it into the lane.

    Two kinds of repointing happen here:

    1. Every durable state surface (event ledger, leaderboard, learning
       artifacts, evaluation storage) is repointed into ``state_root``,
       exactly like ``run_ogate_objectives_battery.py``'s own
       ``_lane_overlay``.
    2. The ``onex_delegation`` provider's ``omnibase_infra_path`` is
       overridden to the caller-resolved absolute path (never the committed
       overlay's own ``../omnibase_infra``, which is CWD-relative and only
       resolves when launched from a checkout that sits next to
       ``omnibase_infra`` on disk -- true for ``omni_home/steel_onslaught``
       directly, false for this ticket's own worktree at
       ``omni_worktrees/OMN-15171/steel_onslaught``). Its ``state_root``
       (the delegation client's own per-call scratch directory) is likewise
       repointed under the battery lane's ``state_root``, not the overlay's
       relative default, so concurrent lanes never share scratch files.
    """
    overlay_path = _CORNER_OVERLAYS[corner]
    base = load_application_overlay(overlay_path)

    delegation_state_root = state_root / "delegation_state"
    providers: list[Any] = []
    found_delegation = False
    for provider in base.llm.providers:
        if isinstance(provider, ModelSODelegationProviderBinding):
            provider = provider.model_copy(
                update={
                    "omnibase_infra_path": omnibase_infra_path,
                    "state_root": delegation_state_root,
                }
            )
            found_delegation = True
        providers.append(provider)
    if not found_delegation:
        raise RuntimeError(
            f"corner {corner!r} overlay {overlay_path} has no onex_delegation provider "
            "binding -- this driver only launches delegation-bound arm-1 overlays"
        )
    llm = base.llm.model_copy(update={"providers": tuple(providers)})

    return base.model_copy(
        update={
            "llm": llm,
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


_PREFLIGHT_PROMPT = (
    "Respond with exactly this JSON object and nothing else: "
    '{"action": "remain", "action_params": {}, "confidence": 1.0, '
    '"rationale": "preflight"}'
)


def _preflight_delegation_cli(overlay: ModelSOApplicationOverlay) -> None:
    """OMN-15240: prove the delegation-CLI transport this arm depends on is
    healthy BEFORE burning any seeds on it.

    Root cause this closes: the 2026-07-27 acceptance run burned all 28-30
    remaining seeds of BOTH the default and prominent corners (58 dead seeds
    total) on an entirely environmental failure -- the omnibase_infra venv's
    co-installed ``omnimarket`` package drifted from the canonical
    ``$OMNI_HOME/omnimarket`` clone mid-run (a `git pull --ff-only` fast-
    forwarded the local clone 5 commits ahead without the venv being
    reinstalled), tripping OMN-14060's own ``OmnimarketDriftError``
    fail-closed pre-flight guard inside the ``onex`` CLI itself. Every
    subsequent seed's delegation call exited 1 near-instantly (~3.5s, per
    live reproduction) instead of ever reaching the LLM -- a single up-front
    probe here would have caught it before burning ~2h40m of wall-clock
    across both corners.

    One real, minimal-cost completion call through the exact same
    ``LlmBusDelegationClient`` -> ``onex node node_delegate_skill_orchestrator``
    path every seed's pilot decision uses (never a separate/parallel
    mechanism) -- so this probe fails on ANY transport-boundary problem
    (drift guard, missing venv, CLI crash, unreachable MLX endpoint), not
    just the one root cause observed here. Raises ``LlmTransportError``
    (uncaught here -- the caller decides how to report/exit) on failure; a
    no-op for overlays with no ``onex_delegation`` provider bound (this
    driver's own committed overlays always have one -- see
    :func:`_lane_overlay` -- but this stays defensive rather than assuming).
    """
    provider = next(
        (p for p in overlay.llm.providers if isinstance(p, ModelSODelegationProviderBinding)),
        None,
    )
    if provider is None:
        return
    identity = SystemIdentityProvider()
    client = LlmBusDelegationClient(config=provider, new_correlation_id=identity.new_correlation_id)
    client.complete(
        ModelSOLlmCompletionRequest(
            system_prompt="Preflight health check for the delegation CLI transport.",
            user_prompt=_PREFLIGHT_PROMPT,
            persona="preflight",
            temperature=0.0,
            json_mode=True,
            evidence_context=None,
        )
    )


def _load_omnimarket_drift_checker(omnibase_infra_path: Path) -> Any:
    """Load ``omnibase_infra.cli.omnimarket_drift_guard.check_omnimarket_drift``
    directly by file path, bypassing ``import omnibase_infra`` entirely
    (OMN-15265).

    ``import omnibase_infra...`` would first execute
    ``omnibase_infra/__init__.py``, which eagerly imports the rest of that
    package (including ``asyncpg`` and other runtime dependencies this repo
    deliberately never installs -- pyproject.toml's own dependency list:
    "Infra is intentionally excluded from this engine"). The guard module
    itself has zero such dependencies (stdlib-only: json / logging /
    subprocess / importlib.metadata / pathlib), so loading it as a
    standalone file sidesteps that whole chain and keeps this driver's own
    venv untouched.
    """
    module_path = (
        omnibase_infra_path / "src" / "omnibase_infra" / "cli" / "omnimarket_drift_guard.py"
    )
    spec = importlib.util.spec_from_file_location("_steel_omnimarket_drift_guard", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"cannot load the omnimarket drift guard module from {module_path} -- "
            "is --omnibase-infra-path/$OMNI_HOME/omnibase_infra a real checkout?"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_omnimarket_drift


def _drift_recheck(*, omnibase_infra_path: Path, omni_home: str | None) -> None:
    """OMN-15265 belt: re-run the IN-PROCESS, no-network drift gate mid-run.

    Deliberately the SAME check ``_preflight_delegation_cli`` never touches
    -- ``omnibase_infra.cli.omnimarket_drift_guard.check_omnimarket_drift``,
    never ``scripts/check-omnimarket-venv-drift.sh``. That shell script does
    a live ``git fetch`` against the remote and compares against the
    fetched ref -- it FALSE-POSITIVES on a pinned hermetic snapshot clone
    (this ticket's own frozen-execution-environment battery) that is
    intentionally behind the remote by design. This function only compares
    the current interpreter's installed omnimarket commit against the run's
    own ``$OMNI_HOME/omnimarket`` checkout -- never the network -- so a
    pinned snapshot with a stable local HEAD reads as clean, exactly as it
    should.

    Raises whatever ``check_omnimarket_drift`` raises (an
    ``OmnimarketDriftError`` naming both the installed and canonical SHAs)
    on a real trip; the caller decides how to abort. Fails open only when
    ``check_omnimarket_drift`` itself would (no ``$OMNI_HOME`` / no
    canonical clone present) -- this function adds no additional fallback
    of its own.
    """
    checker = _load_omnimarket_drift_checker(omnibase_infra_path)
    checker(omni_home=omni_home)


def _terminal_class(end_reason: str | None, victory_kind: str | None) -> str:
    """Same terminal-class taxonomy every battery in this program reports.

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
    return "abort"


def _row_winner_player_id(scored: ModelSOMatchScoredPayload) -> str | None:
    """Re-derive the decisive winner rather than forwarding the reducer's
    draw-convention placeholder -- see ``run_ogate_objectives_battery.py``'s
    ``_row_winner_player_id`` for the full root-cause (seed 5028,
    composition_ca_only_dmg16); the same convention applies here."""
    return None if scored.is_draw else scored.winner_player_id


def _run_seed(
    overlay: ModelSOApplicationOverlay,
    *,
    seed: int,
    max_ticks: int,
    expected_arena_hash: str,
    red_loadout_path: Path,
    blue_loadout_path: Path,
    kafka_transport: _KafkaProducerTransport,
    producer: Any,
    flush_timeout_seconds: float = _KAFKA_FLUSH_TIMEOUT_SECONDS,
    expected_arena_id: str = _ARENA_ID,
) -> dict[str, Any]:
    """Run one seed's match through the platform path and forward its
    terminal events onto the real Kafka topic before returning its row.

    A fresh ``LiveMatchStack`` is built and closed for exactly this one
    seed (per-seed isolation); the Kafka producer/transport is the only
    thing shared across seeds (a live connection, safe to reuse and cheaper
    than reconnecting per seed -- each seed's own fresh in-process bus is
    what the forwarder actually subscribes onto, so message routing stays
    per-seed isolated regardless).
    """
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=red_loadout_path,
        blue_loadout_path=blue_loadout_path,
        seed=seed,
        max_ticks=max_ticks,
        kafka_transport=kafka_transport,
    )
    correlation_id = stack.identity.correlation_id
    try:
        final = stack.runner.run()
        events: tuple[ModelSOEventEnvelope, ...] = tuple(
            stack.ledger.read_all(stack.identity.match_id)
        )
    finally:
        stack.close()

    # Force delivery of every message this seed's forwarder enqueued before
    # trusting the row -- a topic-missing / partition-cap failure surfaces
    # as a per-message delivery_errors entry, not a raised exception, so
    # both must be checked explicitly (see _KafkaProducerTransport).
    pending = producer.flush(flush_timeout_seconds)
    if pending != 0:
        raise RuntimeError(
            f"seed {seed}: {pending} Kafka message(s) still undelivered after "
            f"{flush_timeout_seconds}s flush timeout"
        )
    if kafka_transport.delivery_errors:
        errors = list(kafka_transport.delivery_errors)
        kafka_transport.delivery_errors.clear()
        raise RuntimeError(f"seed {seed}: Kafka producer reported delivery failures: {errors}")

    scored: ModelSOMatchScoredPayload | None = None
    victory_kind: str | None = None
    awards: list[ModelSOObjectiveScoredPayload] = []
    failed_completions = 0
    forwarded_event_types: set[str] = set()
    for event in events:
        if event.event_type is SOEventType.MATCH_STARTED:
            started = ModelSOMatchStartedPayload.model_validate(event.payload)
            if started.arena.arena_id != expected_arena_id:
                raise ValueError(
                    f"seed {seed}: arena_id {started.arena.arena_id!r} != expected "
                    f"{expected_arena_id!r}"
                )
            if started.arena_contract_hash != expected_arena_hash:
                raise ValueError(f"seed {seed}: arena_contract_hash provenance seam broken")
        elif event.event_type is SOEventType.OBJECTIVE_SCORED:
            awards.append(ModelSOObjectiveScoredPayload.model_validate(event.payload))
        elif event.event_type is SOEventType.VICTORY_DECLARED:
            victory_kind = ModelSOVictoryDeclaredPayload.model_validate(event.payload).victory_kind
        elif event.event_type is SOEventType.LLM_COMPLETION_FAILED:
            failed_completions += 1
        elif event.event_type is SOEventType.MATCH_SCORED:
            scored = ModelSOMatchScoredPayload.model_validate(event.payload)
        if event.event_type.value in _TERMINAL_EVENT_TYPE_VALUES:
            forwarded_event_types.add(event.event_type.value)

    assert scored is not None, f"seed {seed}: match {stack.identity.match_id} did not score"
    end_reason = final.end_reason.value if final.end_reason else None
    vp_totals = {player: int(vp) for player, vp in sorted(final.vp_totals.items())}
    return {
        "seed": seed,
        "match_id": stack.identity.match_id,
        "correlation_id": str(correlation_id),
        "end_reason": end_reason,
        "victory_kind": victory_kind,
        "terminal_class": _terminal_class(end_reason, victory_kind),
        "winner_player_id": _row_winner_player_id(scored),
        "is_draw": scored.is_draw,
        "duration_ticks": scored.duration_ticks,
        "vp_totals": vp_totals,
        "vp_margin": abs(vp_totals.get(_RED, 0) - vp_totals.get(_BLUE, 0)),
        "total_awards": len(awards),
        "failed_completions": failed_completions,
        "replay_validity": {
            player: score.replay_validity for player, score in scored.scores.items()
        },
        "kafka_topic": STEEL_MATCH_TERMINAL_TOPIC,
        "kafka_forwarded_event_types": sorted(forwarded_event_types),
    }


def _summarize(
    rows: list[dict[str, Any]],
    *,
    corner: str,
    requested_n: int,
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    n = len(rows)
    classes = Counter(row["terminal_class"] for row in rows)
    winners = Counter("draw" if row["is_draw"] else str(row["winner_player_id"]) for row in rows)
    ticks = sorted(row["duration_ticks"] for row in rows)
    every_row_forwarded_all_observed_terminals = all(
        set(row["kafka_forwarded_event_types"]) <= _TERMINAL_EVENT_TYPE_VALUES for row in rows
    )
    return {
        "corner": corner,
        "n": n,
        "requested_n": requested_n,
        "skipped_seeds": skipped,
        "terminal_classes": dict(sorted(classes.items())),
        "winners": dict(sorted(winners.items())),
        "duration_ticks": {
            "min": ticks[0] if ticks else None,
            "median": statistics.median(ticks) if ticks else None,
            "mean": round(statistics.fmean(ticks), 1) if ticks else None,
            "max": ticks[-1] if ticks else None,
        },
        "failed_completions": sum(row["failed_completions"] for row in rows),
        "all_replay_valid": all(
            validity == 1 for row in rows for validity in row["replay_validity"].values()
        ),
        "kafka_topic": STEEL_MATCH_TERMINAL_TOPIC,
        "every_row_forwarded_valid_terminal_types": every_row_forwarded_all_observed_terminals,
        "all_seeds_forwarded_terminal_events": bool(n)
        and all(row["kafka_forwarded_event_types"] for row in rows),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corner",
        choices=sorted(_CORNER_OVERLAYS),
        default="default",
        help="display-salience arm #1 corner to launch (default: 'default')",
    )
    parser.add_argument("--n", type=int, default=30, help="battery size (default: 30)")
    parser.add_argument(
        "--seed-base", type=int, default=5000, help="seeds are base+1..base+n (default: 5000)"
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=1000,
        help="explicit clock failsafe (matches every other battery driver's default)",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=_REPO_ROOT / ".onex_state/steel_onslaught/omn15171_display_salience_battery",
    )
    parser.add_argument("--fresh", action="store_true", help="wipe the battery lane first")
    parser.add_argument(
        "--kafka-bootstrap",
        default=None,
        help=f"Kafka bootstrap servers (default: ${_ENV_BOOTSTRAP} env if set, else "
        f"{_DEFAULT_KAFKA_BOOTSTRAP})",
    )
    parser.add_argument(
        "--omnibase-infra-path",
        type=Path,
        default=None,
        help="local omnibase_infra clone for the delegation subprocess "
        "(default: $OMNI_HOME/omnibase_infra)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    state_root = args.state_root.resolve()
    if args.fresh and state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    raw_path = state_root / "battery_raw.jsonl"

    omnibase_infra_path = (
        args.omnibase_infra_path
        if args.omnibase_infra_path is not None
        else Path(os.environ["OMNI_HOME"]) / "omnibase_infra"
    ).resolve(strict=True)
    # OMN-15265 belt: the RUN's own $OMNI_HOME, read directly (not derived
    # from omnibase_infra_path above, which may be independently overridden
    # via --omnibase-infra-path) -- `.get()`, not `[...]`, because
    # `check_omnimarket_drift` itself documents unset $OMNI_HOME as "cannot
    # determine" and fails open; this is that guard's own contract, not a
    # silent fallback introduced here.
    omni_home_env = os.environ.get(_OMNI_HOME_ENV)

    catalog = load_match_contract_catalog(_REPO_ROOT / "contracts_data")
    expected_arena_hash = arena_contract_hash(catalog.arenas[_ARENA_ID].to_snapshot())

    overlay = _lane_overlay(state_root, args.corner, omnibase_infra_path=omnibase_infra_path)
    red_loadout_path, blue_loadout_path = _CORNER_LOADOUTS[args.corner]

    bootstrap = args.kafka_bootstrap or os.environ.get(_ENV_BOOTSTRAP, _DEFAULT_KAFKA_BOOTSTRAP)
    try:
        producer, transport = _build_kafka_transport(bootstrap)
    except KafkaLiveTransportUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        _preflight_delegation_cli(overlay)
    except LlmTransportError as exc:
        print(
            "delegation CLI preflight FAILED (OMN-15240 guard) -- aborting "
            f"before any seed runs: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        if exc.stderr is not None:
            print(f"full subprocess stderr:\n{exc.stderr}", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    # A dead seed (provider error, transport drop, Kafka delivery failure)
    # is skipped, never fatal to the whole battery -- but always recorded
    # loudly and never written a synthetic row. Same contract as every
    # other battery driver in this program (2026-07-25 SO-COMP-CA fix).
    skipped: list[dict[str, Any]] = []
    for index in range(1, args.n + 1):
        seed = args.seed_base + index
        try:
            row = _run_seed(
                overlay,
                seed=seed,
                max_ticks=args.max_ticks,
                expected_arena_hash=expected_arena_hash,
                red_loadout_path=red_loadout_path,
                blue_loadout_path=blue_loadout_path,
                kafka_transport=transport,
                producer=producer,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # broad on purpose: one dead seed must not kill the battery
            # OMN-15240: the PERSISTED record (this dict, written verbatim
            # into battery_summary.json) must never be truncated -- only the
            # console preview below is. A prior version truncated this same
            # "error" text to 240 chars, which is what let a ~190-char benign
            # uv VIRTUAL_ENV warning at the front of a CLI subprocess's
            # stderr eat the entire budget and hide the real error that
            # followed it (root cause of the 38/60 acceptance-seed skips).
            full_detail = " ".join(f"{type(exc).__name__}: {exc}".split())
            skip_record: dict[str, Any] = {"seed": str(seed), "error": full_detail}
            # Dedicated structured fields, present only when the raised
            # exception actually carries them (e.g. LlmTransportError from
            # SubprocessDelegationCliRunner on a non-zero onex CLI exit) --
            # absent for every other exception shape, so this never invents
            # data the failure didn't actually provide.
            argv = getattr(exc, "argv", None)
            exit_code = getattr(exc, "exit_code", None)
            stderr = getattr(exc, "stderr", None)
            if argv is not None:
                skip_record["argv"] = list(argv)
            if exit_code is not None:
                skip_record["exit_code"] = exit_code
            if stderr is not None:
                skip_record["stderr"] = stderr
            skipped.append(skip_record)
            console_detail = full_detail[:240]
            print(f"[{index}/{args.n}] seed={seed} SKIPPED — {console_detail}", flush=True)
            continue
        rows.append(row)
        with raw_path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(row, sort_keys=True) + "\n")
        print(
            f"[{index}/{args.n}] seed={seed} match={row['match_id']} "
            f"correlation_id={row['correlation_id']} class={row['terminal_class']} "
            f"kafka_topic={row['kafka_topic']} "
            f"kafka_forwarded={row['kafka_forwarded_event_types']}",
            flush=True,
        )

        # OMN-15265 belt: re-check every N completed seeds, not just once at
        # launch -- catches drift a concurrent session introduces hours into
        # a run (both real OMN-15172 acceptance kills: 13:04:22Z and
        # 19:23:26Z, neither present at this run's own launch-time
        # preflight). FAIL FAST -- abort the whole battery immediately, do
        # not keep burning seeds against a now-unverifiable environment.
        if len(rows) % _DRIFT_RECHECK_INTERVAL_SEEDS == 0:
            try:
                _drift_recheck(omnibase_infra_path=omnibase_infra_path, omni_home=omni_home_env)
            except Exception as exc:  # OmnimarketDriftError from the loaded guard module
                print(
                    f"BATTERY ABORTED (OMN-15265 mid-run drift belt): {len(rows)} seed(s) "
                    f"completed cleanly, then a mid-run omnimarket drift was detected -- "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                abort_summary = _summarize(
                    rows, corner=args.corner, requested_n=args.n, skipped=skipped
                )
                abort_summary["aborted"] = True
                abort_summary["abort_reason"] = f"{type(exc).__name__}: {exc}"
                (state_root / "battery_summary.json").write_text(
                    json.dumps(abort_summary, indent=2, sort_keys=True), encoding="utf-8"
                )
                return 3

    summary = _summarize(rows, corner=args.corner, requested_n=args.n, skipped=skipped)
    summary_path = state_root / "battery_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"raw: {raw_path}\nsummary: {summary_path}")

    if skipped:
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
