"""Tests for the REST replay endpoint — Task 33 invariants.

Endpoint contract:
  GET /api/replay/{match_id}/tick/{tick}

  200  match exists + tick requested
       - body: JSON array of PILOT_DECISION_MADE envelopes for that tick
       - empty list [] when the tick has no pilot decisions
  400  tick < 0            → {"error": "invalid_tick"}
  404  unknown match_id    → {"error": "match_not_found"}
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

import pytest
from omnibase_core.models.common.model_envelope import ModelEnvelope

from steel_onslaught.cli.serve import create_replay_http_handler
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from tests.sqlite_ledger import open_cross_thread_sqlite_ledger

_MATCH_ID = "match.test.replay.endpoint"
_EMITTED_AT = datetime(2026, 4, 30, 16, 0, 0, tzinfo=UTC)

_ENVELOPE_COUNTER: list[int] = [0]


def _uid() -> str:
    _ENVELOPE_COUNTER[0] += 1
    n = _ENVELOPE_COUNTER[0]
    # 26-char ULID-shaped ID (deterministic for tests, unique enough per session)
    return f"01TEST{str(n).zfill(20)}"


def _onex_envelope(entity_id: str, emitted_at: datetime = _EMITTED_AT) -> ModelEnvelope:
    """Composed ONEX ModelEnvelope."""
    return ModelEnvelope(
        message_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        entity_id=entity_id,
        emitted_at=emitted_at,
    )


def _make_decision_event(
    match_id: str,
    tick: int,
    seq: int,
    mech_id: str = "mech.red.01",
    player_id: str = "player.red",
) -> ModelSOEventEnvelope:
    return ModelSOEventEnvelope(
        event_id=_uid(),
        match_id=match_id,
        tick=tick,
        sequence_in_tick=seq,
        event_type=SOEventType.PILOT_DECISION_MADE,
        producer_node="node.pilot.red.01",
        subject=ModelSOEventSubject(mech_id=mech_id, player_id=player_id),
        payload={
            "action": "FIRE_WEAPON",
            "action_params": {"weapon_id": "module.weapon.machine_gun"},
            "reason_code": "enemy_in_range",
            "confidence": 0.85,
            "considered_actions": [{"action": "FIRE_WEAPON", "score": 0.85}],
        },
        envelope=_onex_envelope(match_id),
    )


def _make_other_event(match_id: str, tick: int, seq: int) -> ModelSOEventEnvelope:
    """Non-PILOT_DECISION_MADE event — should NOT appear in endpoint response."""
    return ModelSOEventEnvelope(
        event_id=_uid(),
        match_id=match_id,
        tick=tick,
        sequence_in_tick=seq,
        event_type=SOEventType.BOILER_UPDATED,
        producer_node="node.boiler",
        subject=ModelSOEventSubject(mech_id="mech.red.01", player_id="player.red"),
        payload={
            "pressure_before": 60,
            "pressure_after": 58,
            "heat_before": 30,
            "heat_after": 32,
        },
        envelope=_onex_envelope(match_id),
    )


def _start_test_server(handler_class: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{port}"


def _get(url: str) -> tuple[int, Any]:
    try:
        with urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        return e.code, json.loads(e.read().decode())


# ---------------------------------------------------------------------------
# Fixture: a ledger with known events
# ---------------------------------------------------------------------------


@pytest.fixture()
def ledger_with_events(tmp_path: Path) -> SQLiteLedger:
    ledger = open_cross_thread_sqlite_ledger(tmp_path / "test_endpoint.sqlite")
    # tick 5: two pilot decisions + one boiler event
    ledger.append(_make_decision_event(_MATCH_ID, tick=5, seq=0))
    ledger.append(_make_other_event(_MATCH_ID, tick=5, seq=1))
    ledger.append(
        _make_decision_event(
            _MATCH_ID, tick=5, seq=2, mech_id="mech.blue.01", player_id="player.blue"
        )
    )
    # tick 6: only a boiler event (no pilot decisions)
    ledger.append(_make_other_event(_MATCH_ID, tick=6, seq=0))
    return ledger


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_replay_http_handler_is_callable() -> None:
    """``create_replay_http_handler`` must accept ledger ports and return
    a BaseHTTPRequestHandler subclass."""
    handler_class = create_replay_http_handler([])
    assert issubclass(handler_class, BaseHTTPRequestHandler)


@pytest.mark.integration
def test_endpoint_returns_pilot_decisions_for_tick(
    ledger_with_events: SQLiteLedger,
) -> None:
    """200 + list of PILOT_DECISION_MADE envelopes for a tick that has them."""
    handler_class = create_replay_http_handler([ledger_with_events])
    server, base_url = _start_test_server(handler_class)
    try:
        status, body = _get(f"{base_url}/api/replay/{_MATCH_ID}/tick/5")
        assert status == 200, f"expected 200, got {status}: {body}"
        assert isinstance(body, list), f"expected list, got {type(body).__name__}"
        assert len(body) == 2, f"expected 2 pilot decisions, got {len(body)}"
        for item in body:
            assert item["event_type"] == "pilot_decision_made"
    finally:
        server.shutdown()


@pytest.mark.integration
def test_endpoint_returns_empty_list_when_no_decisions(
    ledger_with_events: SQLiteLedger,
) -> None:
    """200 + [] for a tick that exists but has no PILOT_DECISION_MADE events."""
    handler_class = create_replay_http_handler([ledger_with_events])
    server, base_url = _start_test_server(handler_class)
    try:
        status, body = _get(f"{base_url}/api/replay/{_MATCH_ID}/tick/6")
        assert status == 200, f"expected 200, got {status}: {body}"
        assert body == [], f"expected [], got {body}"
    finally:
        server.shutdown()


@pytest.mark.integration
def test_endpoint_returns_404_for_unknown_match(
    ledger_with_events: SQLiteLedger,
) -> None:
    """404 + {"error": "match_not_found"} for an unknown match_id."""
    handler_class = create_replay_http_handler([ledger_with_events])
    server, base_url = _start_test_server(handler_class)
    try:
        status, body = _get(f"{base_url}/api/replay/UNKNOWN_MATCH_XYZ/tick/0")
        assert status == 404, f"expected 404, got {status}: {body}"
        assert body == {"error": "match_not_found"}, f"unexpected body: {body}"
    finally:
        server.shutdown()


@pytest.mark.integration
def test_endpoint_returns_400_for_negative_tick(
    ledger_with_events: SQLiteLedger,
) -> None:
    """400 + {"error": "invalid_tick"} for tick < 0 (negative in the path)."""
    handler_class = create_replay_http_handler([ledger_with_events])
    server, base_url = _start_test_server(handler_class)
    try:
        # Negative ticks cannot appear in a URL path segment without encoding.
        # The endpoint must parse the path and validate tick >= 0.
        status, body = _get(f"{base_url}/api/replay/{_MATCH_ID}/tick/-1")
        assert status == 400, f"expected 400, got {status}: {body}"
        assert body == {"error": "invalid_tick"}, f"unexpected body: {body}"
    finally:
        server.shutdown()


@pytest.mark.integration
def test_endpoint_envelopes_are_valid_json_and_parseable(
    ledger_with_events: SQLiteLedger,
) -> None:
    """Each item in the 200 response parses into a ModelSOEventEnvelope."""
    handler_class = create_replay_http_handler([ledger_with_events])
    server, base_url = _start_test_server(handler_class)
    try:
        status, body = _get(f"{base_url}/api/replay/{_MATCH_ID}/tick/5")
        assert status == 200
        for item in body:
            env = ModelSOEventEnvelope.model_validate(item)
            assert env.event_type == SOEventType.PILOT_DECISION_MADE
            assert env.tick == 5
    finally:
        server.shutdown()
