"""OMN-15170 live driver test -- the steel half of the hostile-#1 proof split.

Proves that STEEL'S OWN CODE -- ``assemble_match_live`` wired with the real
``LlmBusDelegationClient`` (#217, OMN-15157/OMN-15159) and the real
``KafkaTerminalEventForwarder`` (#218, OMN-15167) -- produced the terminal
event observed on ``onex.evt.steel-onslaught.match-terminal.v1``. An
omnibase_infra-resident test structurally cannot drive steel code (private-
repo boundary) -- this is why the proof is split across two repos, and why
this half must live here.

What is proven, end to end, by one real match:

1. **Delegation-pinned routing.** The red-side pilot is bound to the
   ``onex_delegation`` LLM provider (``backend_id=local-coder-mlx``), so
   every one of its decisions is routed through
   ``uv run --project <omnibase_infra> onex node
   node_delegate_skill_orchestrator`` (steel's actual subprocess boundary,
   :class:`~steel_onslaught.llm.client_delegation.SubprocessDelegationCliRunner`
   -- never faked, unlike the hermetic unit tests in
   ``tests/llm/test_client_delegation_omn15159.py``). The delegation node
   resolves ``backend_id`` to the pinned MLX endpoint
   (OMN-15180 + this ticket's client-side fix -- see
   ``steel_onslaught.llm.client_delegation`` module docstring) and the
   served ``model`` is asserted against the pin.
2. **Real Kafka forwarding.** ``kafka_transport`` is a real
   ``confluent_kafka.Producer`` (not the fake every other test in this repo
   uses), wrapped to satisfy
   :class:`~steel_onslaught.bus.kafka_forwarder.ProtocolTerminalEventTransport`.
   The forwarder subscribes it onto the in-process match bus exactly as
   production composition wires it (``assemble_match_live(kafka_transport=
   ...)``) -- no test-only bypass of the forwarder itself.
3. **Consumer-side proof.** A real ``confluent_kafka.Consumer`` (a fresh
   consumer group, ``auto.offset.reset=earliest``) reads the topic back and
   asserts the terminal event's ONEX envelope ``correlation_id`` matches this
   match's uniquely-minted identity -- the one piece of evidence an
   omnibase_infra-resident test could never produce, because it never drove
   the steel code that minted it.

Explicit, deliberate non-goals:

* Multi-match / multi-seed statistics. One seed, one match, per the ticket.
* Exercising the escalation ladder (``routing_tiers.yaml`` cheap_cloud/claude
  tiers) -- ``backend_id`` is pinned, bypassing tier selection for the
  initial attempt (OMN-15156/OMN-15180); this test proves the pin, not the
  escalation path.

Gating (three independent layers, so this can never run by accident):

1. ``pytest.mark.live`` -- the one category CI excludes, via its
   ``-m "not live"`` selection (``.github/workflows/ci.yml``).
2. ``confluent_kafka`` is an opt-in extra (``uv sync --extra live``), never
   installed by CI's ``uv sync --extra dev``. A missing import skips at
   collection time via ``pytest.importorskip`` -- CI never even attempts to
   import a package it never installed.
3. An explicit ``STEEL_LIVE_DRIVER=1`` environment opt-in is required even
   when the extra IS installed locally, so a stray full-suite ``pytest``
   invocation on a workstation with ``--extra live`` synced still will not
   dial real infra unless a human explicitly asks for it.

Known live blocker as of 2026-07-26 (see
``docs/evidence/2026-07-26-omn15170-live-driver.md``): the stability-test
Kafka lane is OVER its configured partition-allocation cap (7046/7000,
OMN-13855-class regression, tracked reopened as OMN-14013) --
``rpk topic create onex.evt.steel-onslaught.match-terminal.v1`` fails
``INVALID_PARTITIONS`` even for a single partition. This test is written and
ready to run the moment that clears; it has NOT been executed live by this
ticket (blocked-honest, not faked).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

confluent_kafka = pytest.importorskip(
    "confluent_kafka", reason="OMN-15170 live driver test requires `uv sync --extra live`"
)

from steel_onslaught.bus.kafka_forwarder import (  # noqa: E402
    STEEL_MATCH_TERMINAL_TOPIC,
    TERMINAL_EVENT_TYPES,
)
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType  # noqa: E402
from steel_onslaught.match.composition import assemble_match_live  # noqa: E402
from tests.overlay import complete_test_overlay  # noqa: E402

pytestmark = pytest.mark.live

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_DIR = _REPO_ROOT / "contracts_data"
_LOADOUTS = _CATALOG_DIR / "loadouts"
_DRAW_SEED = 99999  # tests/integration/test_proof_of_life.py's canonical draw seed

# Stability-test lane's redpanda ADVERTISED Kafka listener (verified live,
# 2026-07-26: `docker exec omnibase-infra-stability-test-redpanda cat
# /etc/redpanda/redpanda.yaml` -> advertised_kafka_api address). This is the
# literal address the broker hands back in metadata responses to every
# client after the initial bootstrap connection, so -- unlike ssh/rpk access,
# which goes through the Tailscale MagicDNS hostname `omninode-pc` -- a real
# Kafka client MUST dial this exact address; a hostname substitute here
# would break on the post-bootstrap metadata-driven reconnect. Overridable
# via STEEL_LIVE_KAFKA_BOOTSTRAP for any other lane.
_DEFAULT_BOOTSTRAP = "100.109.203.94:39092"  # sanitize-ok
_PINNED_MODEL = "mlx-community/Qwen3.6-35B-A3B-8bit"
_ENV_OPT_IN = "STEEL_LIVE_DRIVER"
_ENV_BOOTSTRAP = "STEEL_LIVE_KAFKA_BOOTSTRAP"

# Small enough that a 2-3 tick draw against a passive opponent (no engagement
# possible -- see proof_blue_defensive_passive.yaml) bounds this to a handful
# of real LLM calls, not dozens.
_MAX_TICKS = 3
_DELEGATION_MAX_TOKENS = 96
_DELEGATION_TIMEOUT_SECONDS = 180.0
_PRODUCER_FLUSH_TIMEOUT_SECONDS = 30.0
_CONSUMER_TIMEOUT_SECONDS = 180.0


def _require_live_opt_in() -> None:
    if os.environ.get(_ENV_OPT_IN) != "1":
        pytest.skip(
            f"set {_ENV_OPT_IN}=1 to run the OMN-15170 live driver test against real "
            "infra (stability-test Kafka + the .200 MLX server)"
        )


class _KafkaProducerTransport:
    """Satisfies ``ProtocolTerminalEventTransport`` with a real producer.

    ``produce()`` only enqueues; delivery is not guaranteed until
    ``flush()`` is called (done explicitly by the test after the match
    completes, before the consumer reads the topic back). Every delivery
    report is recorded on ``self.delivery_errors`` -- ``flush()`` returning
    the queue to 0 only proves librdkafka stopped retrying, NOT that every
    message was delivered successfully (a topic-missing / partition-cap
    failure surfaces here, as a per-message error, not as a raised
    exception) -- so the test asserts this list is empty rather than
    trusting a bare flush() return value.
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


# OMN-15170's own pilot + loadout are deliberately NOT committed to
# contracts_data/{pilots,loadouts}/ -- two golden catalog-completeness tests
# enumerate those directories and assert an EXACT registered set
# (tests/contracts/test_application_overlay.py::
# test_full_named_provider_graph_resolves_every_shipped_llm_spec and
# tests/contracts/test_pilot_registry.py::
# test_all_shipped_loadouts_have_exact_registered_provenance) -- a real
# regression this test's own first draft caused and reverted. Mirroring the
# ``local_200`` precedent (a DEDICATED ``pilot_registry_dir`` swap, never the
# flat top-level ``pilots/`` catalog), this test builds its own isolated
# pilot registry directory under ``tmp_path`` instead: a verbatim copy of
# the real, committed ``template_defensive.yaml`` (so the existing committed
# ``proof_blue_defensive_passive.yaml`` loadout's pilot_id still resolves)
# plus this ticket's new delegation-bound pilot, written directly. The
# red loadout referencing that new pilot is likewise written to ``tmp_path``,
# never committed. ``contracts.catalog_dir`` stays the real, shared
# ``contracts_data`` root -- chassis/boiler/weapon/sensor specs are read-only
# reuse, not new catalog members, so they carry no completeness-test risk.
_RED_PILOT_YAML = """\
schema_version: "0.1.0"
kind: steel_onslaught.pilot
id: pilot.llm.onex_delegation_mlx
display_name: "Qwen3.6-35B-A3B-8bit (ONEX delegation chain, local-coder-mlx)"
archetype: llm
lineage:
  parent: pilot.template.llm
parameters:
  persona: berserker
  provider: onex-local-coder-mlx
"""

_RED_LOADOUT_YAML = """\
schema_version: "0.1.0"
kind: steel_onslaught.loadout
id: loadout.proof.red_onex_delegation_mlx

chassis_id: chassis.light.scout_mk1
boiler_id: boiler.compact.v1
pilot_id: pilot.llm.onex_delegation_mlx

modules:
  weapons:
    - weapon.light.machine_gun
    - weapon.light.shrapnel_thrower
  sensors:
    - sensor.short_range_scanner
  cooling: []
  armor: []
  gizmos: []

budgets:
  points_used: 40
  points_max: 100
  mass_used: 30
  mass_max: 60
  slots_used: 3
  slots_max: 4
  expected_heat_peak: 30
  expected_signature: 35
"""


def _write_local_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Write this test's own pilot registry + red loadout under ``tmp_path``.

    Returns ``(pilot_registry_dir, red_loadout_path)``.
    """
    pilots_dir = tmp_path / "pilots"
    pilots_dir.mkdir()
    real_defensive_pilot = _CATALOG_DIR / "pilots" / "template_defensive.yaml"
    (pilots_dir / "template_defensive.yaml").write_text(
        real_defensive_pilot.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (pilots_dir / "llm_onex_delegation_mlx.yaml").write_text(_RED_PILOT_YAML, encoding="utf-8")

    loadouts_dir = tmp_path / "loadouts"
    loadouts_dir.mkdir()
    red_loadout_path = loadouts_dir / "proof_red_onex_delegation_mlx.yaml"
    red_loadout_path.write_text(_RED_LOADOUT_YAML, encoding="utf-8")

    return pilots_dir, red_loadout_path


def _overlay_raw(tmp_path: Path, *, pilot_registry_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "bus": {"kind": "in_process"},
        "event_ledger": {
            "kind": "sqlite",
            "path": tmp_path / "events.sqlite3",
            "journal_mode": "WAL",
            "check_same_thread": True,
            "transaction_mode": "autocommit",
            "event_schema": "canonical_event_v1",
        },
        "leaderboard": {
            "kind": "sqlite",
            "path": tmp_path / "leaderboard.sqlite3",
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
            "catalog_dir": _CATALOG_DIR,
            "pilot_registry_dir": pilot_registry_dir,
        },
        "clock": {"kind": "system_utc"},
        "identity": {"kind": "system"},
    }


def _require_object_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _overlay(tmp_path: Path, *, omnibase_infra_path: Path, pilot_registry_dir: Path) -> Any:
    from steel_onslaught.contracts.application import ModelSOApplicationOverlay

    raw = complete_test_overlay(
        _overlay_raw(tmp_path, pilot_registry_dir=pilot_registry_dir), tmp_path
    )
    llm = _require_object_dict(raw["llm"])
    llm_providers = llm["providers"]
    assert isinstance(llm_providers, list)
    providers: list[object] = list(llm_providers)
    providers.append(
        {
            "kind": "onex_delegation",
            "provider_id": "onex-local-coder-mlx",
            "backend_id": "local-coder-mlx",
            "task_type": "agent_delegation",
            "source": "external-client",
            "model": _PINNED_MODEL,
            "max_tokens": _DELEGATION_MAX_TOKENS,
            "timeout_seconds": _DELEGATION_TIMEOUT_SECONDS,
            "omnibase_infra_path": omnibase_infra_path,
            "state_root": tmp_path / "delegation_state",
        }
    )
    llm["providers"] = providers
    raw["llm"] = llm
    return ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.live
def test_live_match_produces_real_kafka_terminal_event_via_delegation_pin(
    tmp_path: Path,
) -> None:
    _require_live_opt_in()

    omnibase_infra_path = Path(os.environ["OMNI_HOME"]) / "omnibase_infra"
    bootstrap = os.environ.get(_ENV_BOOTSTRAP, _DEFAULT_BOOTSTRAP)
    pilot_registry_dir, red_loadout_path = _write_local_fixtures(tmp_path)

    producer = confluent_kafka.Producer({"bootstrap.servers": bootstrap})
    transport = _KafkaProducerTransport(producer)

    # Create and subscribe consumer BEFORE the match runs to ensure no events are missed
    consumer = confluent_kafka.Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": f"omn15170-live-driver-{uuid4().hex}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([STEEL_MATCH_TERMINAL_TOPIC])

    served_models: list[str] = []

    def _capture_served_model(event: ModelSOEventEnvelope) -> None:
        model = event.payload.get("model")
        if isinstance(model, str):
            served_models.append(model)

    stack = assemble_match_live(
        overlay=_overlay(
            tmp_path,
            omnibase_infra_path=omnibase_infra_path,
            pilot_registry_dir=pilot_registry_dir,
        ),
        red_loadout_path=red_loadout_path,
        blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
        seed=_DRAW_SEED,
        max_ticks=_MAX_TICKS,
        kafka_transport=transport,
    )
    stack.bus.subscribe(_capture_served_model, event_types=[SOEventType.LLM_COMPLETION_RESOLVED])

    correlation_id: UUID = stack.identity.correlation_id
    match_id: str = stack.identity.match_id

    started = time.monotonic()
    try:
        final = stack.runner.run()
    finally:
        stack.close()
    wall_clock_seconds = time.monotonic() - started

    assert final.match_id == match_id

    # Force delivery of every message the forwarder enqueued during the
    # match before the consumer reads the topic back.
    pending = producer.flush(_PRODUCER_FLUSH_TIMEOUT_SECONDS)
    assert pending == 0, f"{pending} message(s) still undelivered after flush timeout"
    assert not transport.delivery_errors, (
        "Kafka producer reported delivery failures (topic missing / partition-cap "
        f"class): {transport.delivery_errors}"
    )

    assert served_models, (
        "no LLM_COMPLETION_RESOLVED event observed -- the delegation-bound pilot "
        "never completed a real LLM call during the match"
    )
    assert served_models[0] == _PINNED_MODEL, (
        f"delegation served model {served_models[0]!r} does not match the pinned "
        f"backend's model {_PINNED_MODEL!r} -- the backend_id pin did not reach "
        "the actual served backend"
    )

    try:
        deadline = time.monotonic() + _CONSUMER_TIMEOUT_SECONDS
        matched_message = None
        matched_envelope = None
        while time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                continue
            envelope = ModelSOEventEnvelope.model_validate_json(message.value())
            if envelope.envelope.correlation_id == correlation_id and envelope.match_id == match_id:
                matched_message = message
                matched_envelope = envelope
                break
    finally:
        consumer.close()

    assert matched_message is not None and matched_envelope is not None, (
        f"no terminal event with correlation_id={correlation_id} match_id={match_id!r} "
        f"observed on {STEEL_MATCH_TERMINAL_TOPIC} within {_CONSUMER_TIMEOUT_SECONDS}s"
    )
    assert matched_envelope.event_type in TERMINAL_EVENT_TYPES
    assert matched_message.key().decode("utf-8") == match_id

    print(
        "\nOMN-15170 live driver proof:\n"
        f"  correlation_id={correlation_id}\n"
        f"  match_id={match_id}\n"
        f"  served_model={served_models[0]}\n"
        f"  wall_clock_seconds={wall_clock_seconds:.2f}\n"
        f"  consumed_topic={STEEL_MATCH_TERMINAL_TOPIC}\n"
        f"  consumed_partition={matched_message.partition()}\n"
        f"  consumed_offset={matched_message.offset()}\n"
        f"  consumed_event_type={matched_envelope.event_type.value}\n"
    )
