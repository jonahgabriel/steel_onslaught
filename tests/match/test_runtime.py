"""Unit proof for the transport-free runtime lifecycle owner."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, Thread
from time import sleep
from uuid import UUID

import pytest

from steel_onslaught.contracts.runtime import ModelSORuntimeCommand
from steel_onslaught.match.runtime import (
    ConditionProgressGate,
    MatchRuntime,
    ProgressGateStoppedError,
    RuntimeCommandConflictError,
    RuntimeRevisionConflictError,
    RuntimeTransitionError,
)

_OWNER = "runtime_owner.test"
_MATCH = "match.runtime.test"
_START_ID = UUID("11111111-1111-4111-8111-111111111111")


def _command(
    action: str,
    *,
    revision: int,
    command_id: UUID,
    owner: str = _OWNER,
    mode: str | None = None,
) -> ModelSORuntimeCommand:
    raw: dict[str, object] = {
        "schema_version": "1",
        "kind": "steel_onslaught.runtime_command",
        "command_id": command_id,
        "expected_revision": revision,
        "owner_id": owner,
        "action": action,
    }
    if mode is not None:
        raw["mode"] = mode
    return ModelSORuntimeCommand.model_validate(raw)


@pytest.mark.unit
def test_condition_gate_pauses_at_the_next_tick_boundary() -> None:
    gate = ConditionProgressGate()
    gate.pause()
    admitted = Event()

    def wait_for_tick() -> None:
        gate.checkpoint(match_id=_MATCH, next_tick=2)
        admitted.set()

    worker = Thread(target=wait_for_tick)
    worker.start()
    sleep(0.02)
    assert not admitted.is_set()

    gate.resume()
    worker.join(timeout=1)
    assert admitted.is_set()

    gate.stop()
    with pytest.raises(ProgressGateStoppedError):
        gate.checkpoint(match_id=_MATCH, next_tick=3)


@pytest.mark.unit
def test_runtime_enforces_owner_revision_and_exact_command_idempotency() -> None:
    gate = ConditionProgressGate()
    runtime = MatchRuntime(
        match_id=_MATCH,
        owner_id=_OWNER,
        run_match=lambda: "done",
        progress_gate=gate,
        terminal_evidence=lambda _match_id: True,
    )
    start = _command("start", revision=0, command_id=_START_ID, mode="one_game")

    first = runtime.dispatch(start)
    assert first is runtime.dispatch(start)
    assert runtime.status.revision == 1
    assert runtime.status.status.value == "running"

    with pytest.raises(RuntimeCommandConflictError):
        runtime.dispatch(_command("start", revision=0, command_id=_START_ID, mode="continuous"))
    with pytest.raises(RuntimeRevisionConflictError):
        runtime.dispatch(
            _command(
                "pause",
                revision=0,
                command_id=UUID("22222222-2222-4222-8222-222222222222"),
            )
        )
    with pytest.raises(RuntimeCommandConflictError):
        runtime.dispatch(
            _command(
                "pause",
                revision=1,
                command_id=UUID("33333333-3333-4333-8333-333333333333"),
                owner="runtime_owner.other",
            )
        )


@pytest.mark.unit
def test_pause_resume_hold_progress_and_stop_waits_for_terminal_evidence() -> None:
    gate = ConditionProgressGate()
    calls: list[str] = []
    worker_started = Event()
    release_worker = Event()

    def run_match() -> str:
        worker_started.set()
        release_worker.wait(timeout=1)
        calls.append("run")
        return "result"

    runtime = MatchRuntime(
        match_id=_MATCH,
        owner_id=_OWNER,
        run_match=run_match,
        progress_gate=gate,
        terminal_evidence=lambda _match_id: True,
    )
    runtime.dispatch(_command("start", revision=0, command_id=_START_ID, mode="one_game"))

    runtime_worker = Thread(target=runtime.run)
    runtime_worker.start()
    assert worker_started.wait(timeout=1)

    pause_id = UUID("22222222-2222-4222-8222-222222222222")
    runtime.dispatch(_command("pause", revision=1, command_id=pause_id))
    assert runtime.status.status.value == "paused"
    blocked = Event()

    def wait_for_tick() -> None:
        gate.checkpoint(match_id=_MATCH, next_tick=1)
        blocked.set()

    checkpoint_worker = Thread(target=wait_for_tick)
    checkpoint_worker.start()
    sleep(0.02)
    assert not blocked.is_set()
    # The command-side waiter resolves only after the runner (or an injected
    # equivalent checkpoint) has actually reached the safe boundary.
    assert runtime.wait_for_pause_boundary(pause_id) == 0

    resume_id = UUID("33333333-3333-4333-8333-333333333333")
    runtime.dispatch(_command("resume", revision=2, command_id=resume_id))
    checkpoint_worker.join(timeout=1)
    assert blocked.is_set()
    assert runtime.status.status.value == "running"

    stop_id = UUID("44444444-4444-4444-8444-444444444444")
    stop_receipt = runtime.dispatch(_command("stop", revision=3, command_id=stop_id))
    # A stop request closes admission but is not terminal evidence itself.
    assert stop_receipt.status.status.value == "running"
    assert runtime.status.status.value == "running"
    release_worker.set()
    runtime_worker.join(timeout=1)
    assert calls == ["run"]

    ended = runtime.mark_match_ended()
    assert ended.status.value == "ended"
    assert ended.revision == 5
    assert runtime.mark_match_ended() == ended


@pytest.mark.unit
def test_continuous_successor_uses_an_injected_fresh_match_factory() -> None:
    gate = ConditionProgressGate()
    successors: list[int] = []

    def successor_factory(index: int) -> tuple[str, Callable[[], None]]:
        successors.append(index)
        return f"match.runtime.successor.{index}", lambda: None

    runtime = MatchRuntime(
        match_id=_MATCH,
        owner_id=_OWNER,
        run_match=lambda: None,
        progress_gate=gate,
        terminal_evidence=lambda _match_id: True,
        successor_factory=successor_factory,
    )
    runtime.dispatch(_command("start", revision=0, command_id=_START_ID, mode="continuous"))
    with pytest.raises(RuntimeTransitionError):
        runtime.dispatch(
            _command(
                "start",
                revision=1,
                command_id=UUID("22222222-2222-4222-8222-222222222222"),
                mode="continuous",
            )
        )
    # A terminal observation is the only path to a successor match.
    runtime.mark_match_ended()
    successor = runtime.dispatch(
        _command(
            "start",
            revision=2,
            command_id=UUID("33333333-3333-4333-8333-333333333333"),
            mode="continuous",
        )
    )
    assert successor.status.status.value == "running"
    assert successor.status.match_index == 1
    assert runtime.match_id == "match.runtime.successor.1"
    assert successors == [1]


@pytest.mark.unit
def test_continuous_successor_without_factory_fails_closed() -> None:
    gate = ConditionProgressGate()
    durable = False
    runtime = MatchRuntime(
        match_id=_MATCH,
        owner_id=_OWNER,
        run_match=lambda: None,
        progress_gate=gate,
        terminal_evidence=lambda _match_id: durable,
    )
    runtime.dispatch(_command("start", revision=0, command_id=_START_ID, mode="continuous"))
    with pytest.raises(RuntimeTransitionError, match="durable MATCH_ENDED"):
        runtime.mark_match_ended()
    durable = True
    runtime.mark_match_ended()
    with pytest.raises(RuntimeTransitionError, match="successor factory"):
        runtime.dispatch(
            _command(
                "start",
                revision=2,
                command_id=UUID("22222222-2222-4222-8222-222222222222"),
                mode="continuous",
            )
        )


@pytest.mark.unit
def test_worker_exception_commits_a_terminal_failed_status() -> None:
    """A crashed worker must leave a TERMINAL projection, never RUNNING.

    Regression for match-composition-02: ``run`` used to stop the gate, set
    ``_stop_requested`` and re-raise without touching ``_status``.  The runtime
    stayed ``RUNNING`` forever, because ``mark_match_ended`` correctly refuses
    to commit ``ENDED`` without durable ``MATCH_ENDED`` evidence — which a
    crashed worker never produced.
    """
    gate = ConditionProgressGate()

    def run_match() -> None:
        raise RuntimeError("worker exploded mid-tick")

    runtime = MatchRuntime(
        match_id=_MATCH,
        owner_id=_OWNER,
        run_match=run_match,
        progress_gate=gate,
        # No terminal evidence exists on this path; asserting it does would
        # weaken the proof, so the probe reports the truth.
        terminal_evidence=lambda _match_id: False,
    )
    runtime.dispatch(_command("start", revision=0, command_id=_START_ID, mode="one_game"))

    with pytest.raises(RuntimeError, match="worker exploded mid-tick"):
        runtime.run()

    status = runtime.status
    assert status.status.value == "failed"
    assert status.revision == 2
    # FAILED is terminal and is NOT ENDED: no further lifecycle command is legal
    # and the match can never be reported as completed.
    with pytest.raises(RuntimeTransitionError, match="only an active runtime can be ended"):
        runtime.mark_match_ended()
    with pytest.raises(RuntimeTransitionError):
        runtime.dispatch(
            _command(
                "stop",
                revision=2,
                command_id=UUID("55555555-5555-4555-8555-555555555555"),
            )
        )
    with pytest.raises(ProgressGateStoppedError):
        gate.checkpoint(match_id=_MATCH, next_tick=1)


@pytest.mark.unit
def test_worker_exception_does_not_overwrite_an_already_ended_status() -> None:
    """A raise AFTER terminal evidence keeps ENDED; FAILED never downgrades it."""
    gate = ConditionProgressGate()
    marked = Event()

    def run_match() -> None:
        marked.set()
        raise RuntimeError("late teardown failure")

    runtime = MatchRuntime(
        match_id=_MATCH,
        owner_id=_OWNER,
        run_match=run_match,
        progress_gate=gate,
        terminal_evidence=lambda _match_id: True,
    )
    runtime.dispatch(_command("start", revision=0, command_id=_START_ID, mode="one_game"))
    ended = runtime.mark_match_ended()
    assert ended.status.value == "ended"

    with pytest.raises(RuntimeTransitionError, match="must be running"):
        runtime.run()
    assert runtime.status.status.value == "ended"
    assert not marked.is_set()
