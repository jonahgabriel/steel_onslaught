"""Transport-free lifecycle ownership for a composed match.

The browser transport is deliberately not involved here.  ``MatchRuntime``
owns the small mutable lifecycle projection (status, revision, owner and
command receipts), while ``ProgressGate`` is the injected boundary at which a
runner may begin its next *complete* tick transaction.  This keeps pause and
resume semantics testable without giving a client authority over match state.

The runtime does not infer terminal state from a worker returning.  A caller
must first observe durable ``MATCH_ENDED`` evidence and then call
``mark_match_ended``.  That ordering is intentional: a worker completion (or
transport frame) is not proof that the terminal event made it to the ledger.

A worker that RAISES is the other half of that rule: there is no terminal
evidence to observe, so ``run`` commits the distinct terminal
``SORuntimeStatus.FAILED`` rather than leaving the projection on ``RUNNING``
forever.  ``FAILED`` is never ``ENDED`` — it is the un-fakeable record that
this match produced no canonical terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, RLock
from typing import Protocol
from uuid import UUID

from steel_onslaught.contracts.runtime import (
    ModelSORuntimeCommand,
    ModelSORuntimeStatusPayload,
    SORuntimeAction,
    SORuntimeMode,
    SORuntimeStatus,
)


class RuntimeCommandError(ValueError):
    """Base class for fail-closed lifecycle command admission."""


class RuntimeCommandConflictError(RuntimeCommandError):
    """A command id was reused by a different owner or request body."""


class RuntimeRevisionConflictError(RuntimeCommandError):
    """The command's optimistic-concurrency revision is stale."""


class RuntimeTransitionError(RuntimeCommandError):
    """The command is not legal in the current lifecycle state."""


class ProgressGateStoppedError(RuntimeError):
    """A stopped runtime cannot begin another tick transaction."""


class ProgressGate(Protocol):
    """Injected checkpoint called immediately before each next match tick."""

    def checkpoint(self, *, match_id: str, next_tick: int) -> None:
        """Block until this complete tick transaction is admitted."""
        ...


class RuntimeProgressGate(ProgressGate, Protocol):
    """Lifecycle controls consumed by ``MatchRuntime``."""

    def pause(self) -> int: ...

    def resume(self) -> None: ...

    def stop(self) -> None: ...

    def start(self) -> None: ...

    def wait_for_pause_boundary(self, epoch: int) -> int: ...


class OpenProgressGate:
    """Default no-op gate used by legacy/non-lifecycle runner callers."""

    def checkpoint(self, *, match_id: str, next_tick: int) -> None:
        del match_id, next_tick

    def pause(self) -> int:
        return 0

    def resume(self) -> None:
        return

    def stop(self) -> None:
        return

    def start(self) -> None:
        return

    def wait_for_pause_boundary(self, epoch: int) -> int:
        del epoch
        return 0


class ConditionProgressGate:
    """Thread-safe pause/resume gate with safe tick-boundary semantics.

    ``pause`` only closes the gate.  A tick already admitted by
    ``checkpoint`` completes; the following checkpoint blocks.  ``stop``
    releases blocked workers with a typed exception, and ``start`` resets a
    stopped gate for a successor match after terminal evidence is observed.
    """

    def __init__(self) -> None:
        self._condition = Condition()
        self._open = True
        self._stopped = False
        self._pause_epoch = 0
        self._last_blocked_epoch = 0
        self._last_blocked_next_tick: int | None = None

    def checkpoint(self, *, match_id: str, next_tick: int) -> None:
        if not match_id:
            raise ValueError("match_id must be non-empty")
        if next_tick < 1:
            raise ValueError("next_tick must be positive")
        with self._condition:
            while not self._open and not self._stopped:
                self._last_blocked_epoch = self._pause_epoch
                self._last_blocked_next_tick = next_tick
                self._condition.notify_all()
                self._condition.wait()
            if self._stopped:
                raise ProgressGateStoppedError("progress gate is stopped")

    def pause(self) -> int:
        with self._condition:
            if not self._stopped:
                self._open = False
            self._pause_epoch += 1
            self._condition.notify_all()
            return self._pause_epoch

    def resume(self) -> None:
        with self._condition:
            if self._stopped:
                raise ProgressGateStoppedError("cannot resume a stopped progress gate")
            self._open = True
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._open = False
            self._condition.notify_all()

    def start(self) -> None:
        with self._condition:
            self._stopped = False
            self._open = True
            self._condition.notify_all()

    def wait_for_pause_boundary(self, epoch: int) -> int:
        if epoch < 1:
            return 0
        with self._condition:
            while self._last_blocked_epoch < epoch and not self._stopped:
                self._condition.wait()
            if self._stopped and self._last_blocked_epoch < epoch:
                raise ProgressGateStoppedError("progress gate is stopped")
            if self._last_blocked_next_tick is None:
                raise RuntimeError("pause boundary did not record a next tick")
            return self._last_blocked_next_tick - 1


@dataclass(frozen=True)
class RuntimeCommandReceipt:
    """Stable response retained for process-lifetime command idempotency."""

    command: ModelSORuntimeCommand
    status: ModelSORuntimeStatusPayload


class MatchRuntime:
    """Own the lifecycle FSM and execute an injected match worker.

    Commands use owner + expected revision as a compare-and-swap admission
    check.  Exact duplicate command deliveries return the original receipt;
    reuse with different content fails closed.  ``run`` is intentionally
    separate from ``dispatch(start)`` so an adapter can schedule the injected
    worker on its own executor without coupling this owner to a transport.
    """

    def __init__(
        self,
        *,
        match_id: str,
        owner_id: str,
        run_match: Callable[[], object],
        progress_gate: RuntimeProgressGate,
        terminal_evidence: Callable[[str], bool],
        successor_factory: Callable[[int], tuple[str, Callable[[], object]]] | None = None,
    ) -> None:
        if not match_id:
            raise ValueError("match_id must be non-empty")
        if not owner_id:
            raise ValueError("owner_id must be non-empty")
        self._match_id = match_id
        self._owner_id = owner_id
        self._run_match = run_match
        self._successor_factory = successor_factory
        self._gate = progress_gate
        self._terminal_evidence = terminal_evidence
        self._lock = RLock()
        self._status = ModelSORuntimeStatusPayload(
            status=SORuntimeStatus.READY,
            mode=None,
            revision=0,
            owner_id=owner_id,
            match_index=0,
            last_command_id=None,
        )
        self._receipts: dict[UUID, RuntimeCommandReceipt] = {}
        self._active_mode: SORuntimeMode | None = None
        self._stop_requested = False
        self._worker_started = False
        self._pause_epochs: dict[UUID, int] = {}

    @property
    def match_id(self) -> str:
        return self._match_id

    @property
    def status(self) -> ModelSORuntimeStatusPayload:
        with self._lock:
            return self._status

    @property
    def progress_gate(self) -> RuntimeProgressGate:
        return self._gate

    def dispatch(self, command: ModelSORuntimeCommand) -> RuntimeCommandReceipt:
        """CAS-admit one command and return its stable receipt."""
        with self._lock:
            if command.owner_id != self._owner_id:
                raise RuntimeCommandConflictError("command owner does not own this runtime")

            previous = self._receipts.get(command.command_id)
            if previous is not None:
                if previous.command != command:
                    raise RuntimeCommandConflictError(
                        f"command id {command.command_id} was reused with different content"
                    )
                return previous

            if command.expected_revision != self._status.revision:
                raise RuntimeRevisionConflictError(
                    f"expected revision {command.expected_revision} does not match "
                    f"current revision {self._status.revision}"
                )

            self._admit_transition(command)
            receipt = RuntimeCommandReceipt(command=command, status=self._status)
            self._receipts[command.command_id] = receipt
            return receipt

    def run(self) -> object:
        """Run the injected worker after a successful start admission."""
        with self._lock:
            if self._status.status is not SORuntimeStatus.RUNNING:
                raise RuntimeTransitionError("runtime must be running before its worker is run")
            if self._stop_requested:
                raise RuntimeTransitionError("runtime stop has already been requested")
            if self._worker_started:
                raise RuntimeTransitionError("runtime worker has already been started")
            self._worker_started = True
        try:
            return self._run_match()
        except BaseException:
            # A failed worker must not leave a future worker able to advance,
            # and must not leave the projection stuck on RUNNING.  There is no
            # canonical terminal evidence on this path (that is exactly what
            # went wrong), so the runtime commits its own FAILED terminal
            # instead of ENDED.  The whole transition is taken under the lock:
            # `_stop_requested` was previously mutated outside it, racing every
            # concurrent `dispatch`.
            self._gate.stop()
            with self._lock:
                self._stop_requested = True
                if self._status.status not in {
                    SORuntimeStatus.ENDED,
                    SORuntimeStatus.FAILED,
                }:
                    self._status = self._next_status(
                        status=SORuntimeStatus.FAILED,
                        mode=self._status.mode,
                        command_id=self._status.last_command_id,
                        match_index=self._status.match_index,
                    )
            raise

    def wait_for_pause_boundary(self, command_id: UUID) -> int:
        """Wait until a pause command has blocked the runner before its next tick."""
        with self._lock:
            try:
                epoch = self._pause_epochs[command_id]
            except KeyError as exc:
                raise RuntimeTransitionError(
                    f"pause command {command_id} has no recorded boundary"
                ) from exc
        return self._gate.wait_for_pause_boundary(epoch)

    def mark_match_ended(self) -> ModelSORuntimeStatusPayload:
        """Commit terminal status only after durable ``MATCH_ENDED`` evidence."""
        with self._lock:
            if self._status.status is SORuntimeStatus.ENDED:
                return self._status
            if self._status.status not in {
                SORuntimeStatus.RUNNING,
                SORuntimeStatus.PAUSED,
            }:
                raise RuntimeTransitionError("only an active runtime can be ended")
            if not self._terminal_evidence(self._match_id):
                raise RuntimeTransitionError(
                    "durable MATCH_ENDED evidence is required before runtime ENDED"
                )
            self._status = self._next_status(
                status=SORuntimeStatus.ENDED,
                mode=self._status.mode,
                command_id=self._status.last_command_id,
                match_index=self._status.match_index,
            )
            self._gate.stop()
            return self._status

    def _admit_transition(self, command: ModelSORuntimeCommand) -> None:
        status = self._status.status
        if command.action is SORuntimeAction.START:
            if status is SORuntimeStatus.READY:
                assert command.mode is not None
                self._gate.start()
                self._active_mode = command.mode
                self._stop_requested = False
                self._worker_started = False
                self._status = self._next_status(
                    status=SORuntimeStatus.RUNNING,
                    mode=command.mode,
                    command_id=command.command_id,
                    match_index=0,
                )
                return
            if status is SORuntimeStatus.ENDED and self._active_mode is SORuntimeMode.CONTINUOUS:
                if command.mode is not SORuntimeMode.CONTINUOUS:
                    raise RuntimeTransitionError(
                        "continuous runtime successors must remain continuous"
                    )
                if self._successor_factory is None:
                    raise RuntimeTransitionError(
                        "continuous successor requires an injected successor factory"
                    )
                next_index = self._status.match_index + 1
                next_match_id, next_worker = self._successor_factory(next_index)
                if not next_match_id:
                    raise RuntimeCommandError("successor factory returned an empty match id")
                self._match_id = next_match_id
                self._run_match = next_worker
                self._gate.start()
                self._stop_requested = False
                self._worker_started = False
                self._status = self._next_status(
                    status=SORuntimeStatus.RUNNING,
                    mode=command.mode,
                    command_id=command.command_id,
                    match_index=self._status.match_index + 1,
                )
                return
            raise RuntimeTransitionError(f"start is not legal from {status.value}")

        if command.action is SORuntimeAction.PAUSE:
            if status is not SORuntimeStatus.RUNNING:
                raise RuntimeTransitionError(f"pause is not legal from {status.value}")
            pause_epoch = self._gate.pause()
            self._pause_epochs[command.command_id] = pause_epoch
            self._status = self._next_status(
                status=SORuntimeStatus.PAUSED,
                mode=self._status.mode,
                command_id=command.command_id,
                match_index=self._status.match_index,
            )
            return

        if command.action is SORuntimeAction.RESUME:
            if status is not SORuntimeStatus.PAUSED:
                raise RuntimeTransitionError(f"resume is not legal from {status.value}")
            self._gate.resume()
            self._status = self._next_status(
                status=SORuntimeStatus.RUNNING,
                mode=self._status.mode,
                command_id=command.command_id,
                match_index=self._status.match_index,
            )
            return

        if command.action is SORuntimeAction.STOP:
            if status not in {SORuntimeStatus.RUNNING, SORuntimeStatus.PAUSED}:
                raise RuntimeTransitionError(f"stop is not legal from {status.value}")
            # STOP is a request.  The worker must emit MATCH_ENDED and the
            # ledger must durably append it before mark_match_ended changes
            # the runtime projection to ENDED.
            if not self._worker_started:
                raise RuntimeTransitionError("stop requires a started runtime worker")
            self._gate.stop()
            self._stop_requested = True
            self._status = self._next_status(
                status=status,
                mode=self._status.mode,
                command_id=command.command_id,
                match_index=self._status.match_index,
            )
            return

        raise RuntimeCommandError(f"unsupported runtime action {command.action!r}")

    def _next_status(
        self,
        *,
        status: SORuntimeStatus,
        mode: SORuntimeMode | None,
        command_id: UUID | None,
        match_index: int,
    ) -> ModelSORuntimeStatusPayload:
        # UUID is deliberately typed by the command/status models; callers
        # only pass a command UUID or the existing status UUID.
        return ModelSORuntimeStatusPayload(
            status=status,
            mode=mode,
            revision=self._status.revision + 1,
            owner_id=self._owner_id,
            match_index=match_index,
            last_command_id=command_id,
        )


__all__ = [
    "ConditionProgressGate",
    "MatchRuntime",
    "OpenProgressGate",
    "ProgressGate",
    "ProgressGateStoppedError",
    "RuntimeCommandConflictError",
    "RuntimeCommandError",
    "RuntimeCommandReceipt",
    "RuntimeProgressGate",
    "RuntimeRevisionConflictError",
    "RuntimeTransitionError",
]
