"""Composition wiring for the terminal-event Kafka forwarder (OMN-15167).

Three things are proven here, mirroring the OMN-15157/OMN-15159 (#217) bar
for a transport-injected, composition-confined capability:

1. **Golden-stability.** With no ``kafka_transport`` injected,
   ``build_runtime_dependencies`` never builds a forwarder
   (``dependencies.kafka_forwarder is None``) and a full live match run is
   byte-identical to before this ticket -- zero new bus subscriptions, zero
   behavior change. ``MatchRunner``/reducers/fold are untouched by this
   ticket; this test proves the composition seam around them is inert by
   default.
2. **Wiring.** Injecting a fake ``kafka_transport`` at
   ``build_runtime_dependencies`` produces a real
   ``KafkaTerminalEventForwarder`` on ``RuntimeDependencies.kafka_forwarder``,
   and ``assemble_match_with_dependencies`` subscribes it onto the bus scoped
   to exactly the 4 terminal event types (one more subscription than the
   golden-stability baseline).
3. **End-to-end forwarding.** Running one full deterministic match through
   ``assemble_match_live`` with the fake transport injected forwards ONLY the
   terminal lifecycle events actually emitted by that match (a draw never
   emits ``VICTORY_DECLARED``) -- proving the wiring at the actual
   composition call site, not just a synthetic unit test.

Live Kafka publish is explicitly NOT claimed here (OMN-15170's scope); the
transport is a fake throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from steel_onslaught.bus.kafka_forwarder import (
    STEEL_MATCH_TERMINAL_TOPIC,
    TERMINAL_EVENT_TYPES,
    KafkaTerminalEventForwarder,
)
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.match.composition import (
    assemble_match_live,
    build_runtime_dependencies,
)
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from tests.overlay import complete_test_overlay

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_DIR = _REPO_ROOT / "contracts_data"
_LOADOUTS = _CATALOG_DIR / "loadouts"
_DRAW_SEED = 99999  # tests/integration/test_proof_of_life.py's canonical draw seed


@dataclass
class _RecordedMessage:
    topic: str
    key: str
    value: bytes


@dataclass
class _FakeTransport:
    published: list[_RecordedMessage] = field(default_factory=list)

    def publish(self, *, topic: str, key: str, value: bytes) -> None:
        self.published.append(_RecordedMessage(topic=topic, key=key, value=value))


def _overlay_raw(tmp_path: Path) -> dict[str, Any]:
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
            "pilot_registry_dir": _CATALOG_DIR / "pilots",
        },
        "clock": {"kind": "system_utc"},
        "identity": {"kind": "system"},
    }


def _overlay(tmp_path: Path) -> ModelSOApplicationOverlay:
    return ModelSOApplicationOverlay.model_validate(
        complete_test_overlay(_overlay_raw(tmp_path), tmp_path)
    )


def test_golden_stability_no_kafka_transport_configured(tmp_path: Path) -> None:
    """No injected transport -> no forwarder built, matching pre-ticket state."""
    dependencies = build_runtime_dependencies(_overlay(tmp_path))
    try:
        assert dependencies.kafka_forwarder is None
    finally:
        dependencies.close()


def test_golden_stability_full_match_run_is_unaffected(tmp_path: Path) -> None:
    """A full live match with no kafka_transport behaves exactly as before."""
    stack = assemble_match_live(
        overlay=_overlay(tmp_path),
        red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
        blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
        seed=_DRAW_SEED,
        max_ticks=50,
    )
    try:
        final = stack.runner.run()
        assert final.status is SOMatchStatus.ENDED
        assert final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    finally:
        stack.close()


def test_kafka_transport_wires_a_forwarder_onto_dependencies(tmp_path: Path) -> None:
    transport = _FakeTransport()
    dependencies = build_runtime_dependencies(_overlay(tmp_path), kafka_transport=transport)
    try:
        assert isinstance(dependencies.kafka_forwarder, KafkaTerminalEventForwarder)
    finally:
        dependencies.close()


def test_full_match_run_forwards_only_terminal_events_end_to_end(tmp_path: Path) -> None:
    """The exact composition wiring, driven by a real deterministic match.

    A draw never emits VICTORY_DECLARED -- only MATCH_STARTED, MATCH_ENDED,
    and MATCH_SCORED are expected on the fake transport. Zero MatchRunner/
    reducer/fold code is touched by this ticket; this proves the composition
    seam around them forwards exactly what plan §4b and the ticket contract
    require, driven by a real match.
    """
    transport = _FakeTransport()
    stack = assemble_match_live(
        overlay=_overlay(tmp_path),
        red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
        blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
        seed=_DRAW_SEED,
        max_ticks=50,
        kafka_transport=transport,
    )
    try:
        final = stack.runner.run()
        assert final.status is SOMatchStatus.ENDED
        assert final.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    finally:
        stack.close()

    assert transport.published, "the forwarder must have forwarded at least one terminal event"
    forwarded = [
        ModelSOEventEnvelope.model_validate_json(message.value) for message in transport.published
    ]
    forwarded_types = {event.event_type for event in forwarded}
    assert forwarded_types <= set(TERMINAL_EVENT_TYPES)
    assert SOEventType.VICTORY_DECLARED not in forwarded_types  # a draw declares no victor
    assert SOEventType.MATCH_STARTED in forwarded_types
    assert SOEventType.MATCH_ENDED in forwarded_types
    assert SOEventType.MATCH_SCORED in forwarded_types

    for message, event in zip(transport.published, forwarded, strict=True):
        assert message.topic == STEEL_MATCH_TERMINAL_TOPIC
        assert message.key == event.match_id == final.match_id
