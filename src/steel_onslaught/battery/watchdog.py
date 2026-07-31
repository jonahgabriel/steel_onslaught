"""Active terminal signalling for long-running batteries — OMN-15588.

Batteries used to report their state exclusively through disk sentinels
(``BATTERY_DONE`` / ``NEEDS_ATTENTION``) written by an unversioned shell
wrapper. A file on disk cannot wake anyone: on the OMN-15488 run an attempt-1
crash sat undetected for roughly five hours until an operator happened to ask.
The versioned half of that apparatus was a bash snippet inside a runbook which
polled for process *absence*, so a driver that hung while still alive was
invisible to it indefinitely, and a driver that died was noticed only by
whoever next listed the directory.

This module replaces both. :class:`BatteryWatchdog` supervises a battery driver
process and PUSHES exactly one terminal notification — completed, incomplete,
crashed, or stalled — through an active channel. Two properties make that
signalling non-optional rather than merely available:

* :func:`resolve_notifiers` raises when no channel is configured, and the CLI
  resolves notifiers *before* it launches the battery, so a disk-only run
  cannot be started through the sanctioned path at all.
* A notification that fails to deliver is carried on the result and mapped to
  a distinct nonzero exit code, so a dead channel can never present itself as
  a clean run.
* The chain-forward hook is gated on that same delivery fact (OMN-15595), so a
  battery chain cannot advance run after run with nobody told. Chaining anyway
  is reachable only through the explicit ``chain_on_delivery_failure`` opt-in,
  which is recorded on the result the watchdog prints.

Everything that observes the outside world — the clock, the supervised
process, the row counter, the log tail, the follow-on launcher — is injected,
so the stall deadline and the crash path are tested against a fake clock with
no wall-clock sleeps in CI.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

ENV_NOTIFY_COMMAND = "STEEL_BATTERY_NOTIFY_COMMAND"
ENV_NOTIFY_WEBHOOK = "STEEL_BATTERY_NOTIFY_WEBHOOK"

_DEFAULT_LOG_TAIL_BYTES = 4000
_DEFAULT_NOTIFY_TIMEOUT_SECONDS = 30.0
_DEFAULT_TERMINATE_GRACE_SECONDS = 30.0


class BatteryTerminalState(StrEnum):
    """How a supervised battery ended. Only ``COMPLETED`` is a clean run."""

    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    CRASHED = "crashed"
    STALLED = "stalled"


class NotificationError(RuntimeError):
    """One notification channel failed to deliver."""


class NoActiveNotifierError(RuntimeError):
    """No active notification channel is configured, so a run must not start."""


def expected_rows_label(minimum: int | None, maximum: int | None) -> str:
    """How a row contract renders in a human-facing summary line."""
    if minimum is None:
        return "?"
    if maximum is None or maximum == minimum:
        return str(minimum)
    return f"{minimum}-{maximum}"


def rows_satisfy_contract(rows: int, minimum: int | None, maximum: int | None) -> bool:
    """Whether an observed row count honours the declared row contract.

    ``minimum is None`` — no contract, any clean exit is COMPLETED (unchanged).
    ``maximum is None`` — exact equality, the pre-OMN-15488-leg-(a) behaviour.
    both set       — inclusive range ``minimum <= rows <= maximum``.

    The range form exists because a battery's clean row count is not always a
    constant. ``scripts/run_lgate2_adaptation_battery.py``'s promote phase
    stops at the FIRST promotion, so a clean run writes ``n + k + n`` rows for
    an unknown ``k`` in ``1..promote_attempts`` — 61 through 75 at the
    OMN-15488 leg (a) configuration. Under the previous strict ``!=`` the only
    expressible contract was a single literal, and the literal to hand was 61
    (the red battery promoted on its first attempt), which would have declared
    every ``k > 1`` run INCOMPLETE and withheld its ``--on-complete-exec``
    chain despite the battery being perfectly clean.

    Dropping ``--expected-rows`` entirely was the other available answer and is
    strictly worse: it also disarms the short-clean-exit check this watchdog
    was built for (OMN-15588 — "a short clean exit is INCOMPLETE, not
    COMPLETED"), so a battery that quietly wrote 27 rows and exited 0 would
    read as COMPLETED. A bounded range keeps the floor.
    """
    if minimum is None:
        return True
    if maximum is None:
        return rows == minimum
    return minimum <= rows <= maximum


class ModelBatteryOutcome(BaseModel):
    """The single terminal fact about a supervised battery run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    state: BatteryTerminalState
    rows_observed: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0.0)
    stall_deadline_seconds: float = Field(gt=0.0)
    detail: str
    exit_code: int | None = None
    expected_rows: int | None = Field(default=None, ge=0)
    expected_rows_max: int | None = Field(default=None, ge=0)
    log_tail: str = ""

    @property
    def is_clean(self) -> bool:
        return self.state is BatteryTerminalState.COMPLETED

    def summary_line(self) -> str:
        """One-line human summary — the subject line of any notification."""
        expected = expected_rows_label(self.expected_rows, self.expected_rows_max)
        return (
            f"[steel battery {self.run_id}] {self.state.value.upper()} "
            f"rows={self.rows_observed}/{expected} "
            f"exit={self.exit_code} elapsed={self.elapsed_seconds:.0f}s — {self.detail}"
        )

    def payload(self) -> dict[str, Any]:
        """JSON body handed to every channel (Slack renders ``text``)."""
        body = self.model_dump(mode="json")
        body["text"] = self.summary_line()
        return body


class ModelWatchdogResult(BaseModel):
    """Terminal outcome plus what actually happened to the notifications."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ModelBatteryOutcome
    delivered_channels: tuple[str, ...] = ()
    notification_failures: tuple[str, ...] = ()
    chained: bool = False
    chain_withheld_reason: str | None = None
    chain_forced_on_undelivered: bool = False

    @property
    def delivered(self) -> bool:
        return bool(self.delivered_channels)


@runtime_checkable
class ProtocolBatteryNotifier(Protocol):
    """An active channel that can reach a human or a session."""

    @property
    def channel(self) -> str: ...

    def notify(self, outcome: ModelBatteryOutcome) -> None: ...


@runtime_checkable
class ProtocolSupervisedProcess(Protocol):
    """The subset of ``subprocess.Popen`` the watchdog depends on."""

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


@runtime_checkable
class ProtocolClock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class MonotonicClock:
    """The production clock. Tests inject a fake instead of sleeping."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def count_jsonl_rows(path: Path) -> int:
    """Count non-blank lines, treating a not-yet-created file as zero rows.

    This is the battery's progress heartbeat: the driver appends one row per
    completed seed, so a growing count is the only liveness signal that
    distinguishes real work from a process that is merely still resident.
    """
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except FileNotFoundError:
        return 0


def read_log_tail(path: Path, *, max_bytes: int = _DEFAULT_LOG_TAIL_BYTES) -> str:
    """Return the tail of a driver log, or an empty string if unreadable.

    A crash notification without the traceback that caused it just moves the
    latency from "notice it" to "diagnose it", so the tail rides along.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return ""


@dataclass(frozen=True)
class CommandNotifier:
    """Deliver by running an operator-configured command with JSON on stdin.

    This is the general escape hatch: any channel the operator can reach from
    a shell (a chat webhook helper, an ssh ping, a bus publish CLI) becomes an
    active battery channel without this repo taking a dependency on it.
    """

    argv: tuple[str, ...]
    timeout_seconds: float = _DEFAULT_NOTIFY_TIMEOUT_SECONDS

    @property
    def channel(self) -> str:
        return f"command:{self.argv[0]}"

    def notify(self, outcome: ModelBatteryOutcome) -> None:
        payload = json.dumps(outcome.payload(), sort_keys=True)
        try:
            completed = subprocess.run(  # operator-configured argv, never a shell
                list(self.argv),
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise NotificationError(f"{self.channel} failed to run: {exc}") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-400:]
            raise NotificationError(f"{self.channel} exited {completed.returncode}: {tail}")


@dataclass(frozen=True)
class WebhookNotifier:
    """Deliver by POSTing the outcome JSON to a chat-compatible webhook."""

    url: str
    timeout_seconds: float = _DEFAULT_NOTIFY_TIMEOUT_SECONDS
    post_json: Callable[[str, dict[str, Any], float], int] | None = None

    @property
    def channel(self) -> str:
        return "webhook"

    def notify(self, outcome: ModelBatteryOutcome) -> None:
        post = self.post_json if self.post_json is not None else _httpx_post_json
        try:
            status = post(self.url, outcome.payload(), self.timeout_seconds)
        except Exception as exc:  # transport errors are channel failures
            raise NotificationError(f"{self.channel} failed to post: {exc}") from exc
        if status >= 400:
            raise NotificationError(f"{self.channel} returned HTTP {status}")


def _httpx_post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> int:
    import httpx

    response = httpx.post(url, json=payload, timeout=timeout_seconds)
    return int(response.status_code)


def resolve_notifiers(env: Mapping[str, str]) -> tuple[ProtocolBatteryNotifier, ...]:
    """Build the configured channels, refusing to return an empty set.

    Fail-fast rather than silent fallback: a watchdog with no channel is
    exactly the disk-only arrangement this module exists to remove, so the
    caller resolves channels before launching anything.
    """
    notifiers: list[ProtocolBatteryNotifier] = []
    raw_command = env.get(ENV_NOTIFY_COMMAND, "").strip()
    if raw_command:
        argv = tuple(shlex.split(raw_command))
        if not argv:
            raise NoActiveNotifierError(f"{ENV_NOTIFY_COMMAND} is set but parses to no command")
        notifiers.append(CommandNotifier(argv=argv))
    webhook = env.get(ENV_NOTIFY_WEBHOOK, "").strip()
    if webhook:
        notifiers.append(WebhookNotifier(url=webhook))
    if not notifiers:
        raise NoActiveNotifierError(
            "no active battery notification channel configured — set "
            f"{ENV_NOTIFY_COMMAND} (argv run with the outcome JSON on stdin) and/or "
            f"{ENV_NOTIFY_WEBHOOK} (chat-compatible webhook URL). A battery whose only "
            "failure signal is a file on disk cannot surface a crash or a stall."
        )
    return tuple(notifiers)


def exit_code_for(result: ModelWatchdogResult) -> int:
    """Map a terminal result onto a process exit code.

    An undelivered notification outranks a clean battery: the run may have been
    fine, but the mechanism that was supposed to tell someone was not. The
    chain-forward gate in :meth:`BatteryWatchdog._chain_decision` keys on the
    same predicate, so exit 3 and ``chained=True`` cannot co-occur unless the
    operator explicitly opted in (OMN-15595).
    """
    if result.notification_failures and not result.delivered:
        return 3
    if result.outcome.state is BatteryTerminalState.COMPLETED:
        return 0
    if result.outcome.state is BatteryTerminalState.INCOMPLETE:
        return 2
    return 1


@dataclass(frozen=True)
class BatteryWatchdog:
    """Supervise one battery driver and emit exactly one terminal notification."""

    run_id: str
    process: ProtocolSupervisedProcess
    read_rows: Callable[[], int]
    notifiers: Sequence[ProtocolBatteryNotifier]
    stall_deadline_seconds: float
    poll_seconds: float
    clock: ProtocolClock = field(default_factory=MonotonicClock)
    expected_rows: int | None = None
    expected_rows_max: int | None = None
    read_tail: Callable[[], str] = str
    settle_seconds: float = 0.0
    terminate_grace_seconds: float = _DEFAULT_TERMINATE_GRACE_SECONDS
    on_complete: Callable[[], None] | None = None
    chain_on_delivery_failure: bool = False

    def __post_init__(self) -> None:
        if self.stall_deadline_seconds <= 0:
            raise ValueError("stall_deadline_seconds must be positive")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if not self.notifiers:
            raise NoActiveNotifierError("BatteryWatchdog requires at least one notifier")
        # Fail closed on an incoherent row contract rather than silently
        # ignoring half of it: an upper bound with no lower bound is not a
        # range, and an inverted range accepts nothing.
        if self.expected_rows_max is not None:
            if self.expected_rows is None:
                raise ValueError("expected_rows_max requires expected_rows (the lower bound)")
            if self.expected_rows_max < self.expected_rows:
                raise ValueError(
                    "expected_rows_max must be >= expected_rows "
                    f"(got {self.expected_rows_max} < {self.expected_rows})"
                )

    def run(self) -> ModelWatchdogResult:
        outcome = self._supervise()
        delivered, failures = self._notify(outcome)
        should_chain, withheld_reason, forced = self._chain_decision(outcome, delivered, failures)
        if should_chain and self.on_complete is not None:
            self.on_complete()
        return ModelWatchdogResult(
            outcome=outcome,
            delivered_channels=delivered,
            notification_failures=failures,
            chained=should_chain,
            chain_withheld_reason=withheld_reason,
            chain_forced_on_undelivered=forced,
        )

    def _chain_decision(
        self,
        outcome: ModelBatteryOutcome,
        delivered: tuple[str, ...],
        failures: tuple[str, ...],
    ) -> tuple[bool, str | None, bool]:
        """Decide whether the follow-on battery may start — OMN-15595.

        A clean terminal state is necessary but NOT sufficient. Delivery is the
        second condition: a chain that advances while every channel was dead
        reproduces one layer up the exact failure OMN-15588 removed, because
        the next battery starts and the operator still learns nothing until
        they inspect disk. :func:`exit_code_for` already ranks an undelivered
        notification above a clean run (exit 3); before this the side effect
        and the exit code disagreed — the process reported "nobody was told"
        having already launched the successor.

        Partial delivery (at least one channel accepted, others failed) chains.
        That is a decision, not a fallthrough: the gate is "did anyone hear
        this", and it is deliberately the same predicate ``exit_code_for``
        uses for exit 3, so the two can never disagree.

        ``chain_on_delivery_failure`` is the only way past a total delivery
        failure, and it is opt-in precisely so it appears verbatim in the
        launch command and in this result — the default withholds.
        """
        if self.on_complete is None:
            return False, None, False
        if outcome.state is not BatteryTerminalState.COMPLETED:
            return False, f"terminal state is {outcome.state.value}, not completed", False
        if delivered:
            return True, None, False
        reason = (
            f"battery completed cleanly but no channel accepted the notification "
            f"({len(failures)} channel(s) failed) — nobody was told, so the chain "
            "is withheld; override with chain_on_delivery_failure"
        )
        if not self.chain_on_delivery_failure:
            return False, reason, False
        return True, None, True

    def _supervise(self) -> ModelBatteryOutcome:
        started = self.clock.now()
        rows = self.read_rows()
        last_progress_at = started
        while True:
            exit_code = self.process.poll()
            if exit_code is not None:
                if self.settle_seconds > 0:
                    self.clock.sleep(self.settle_seconds)
                return self._exited_outcome(
                    exit_code=exit_code,
                    rows=self.read_rows(),
                    elapsed=self.clock.now() - started,
                )
            self.clock.sleep(self.poll_seconds)
            observed = self.read_rows()
            now = self.clock.now()
            if observed > rows:
                rows = observed
                last_progress_at = now
                continue
            if now - last_progress_at >= self.stall_deadline_seconds:
                self._terminate()
                stalled_for = now - last_progress_at
                return self._outcome(
                    state=BatteryTerminalState.STALLED,
                    rows=observed,
                    elapsed=now - started,
                    exit_code=None,
                    detail=(
                        f"no new rows for {stalled_for:.0f}s "
                        f"(deadline {self.stall_deadline_seconds:.0f}s); driver terminated"
                    ),
                )

    def _exited_outcome(self, *, exit_code: int, rows: int, elapsed: float) -> ModelBatteryOutcome:
        if exit_code != 0:
            return self._outcome(
                state=BatteryTerminalState.CRASHED,
                rows=rows,
                elapsed=elapsed,
                exit_code=exit_code,
                detail=f"driver exited {exit_code}",
            )
        if not rows_satisfy_contract(rows, self.expected_rows, self.expected_rows_max):
            expected = expected_rows_label(self.expected_rows, self.expected_rows_max)
            return self._outcome(
                state=BatteryTerminalState.INCOMPLETE,
                rows=rows,
                elapsed=elapsed,
                exit_code=exit_code,
                detail=(
                    f"driver exited 0 with {rows} rows, expected {expected} — "
                    "follow-on work withheld"
                ),
            )
        return self._outcome(
            state=BatteryTerminalState.COMPLETED,
            rows=rows,
            elapsed=elapsed,
            exit_code=exit_code,
            detail="driver exited 0 with the expected row count",
        )

    def _outcome(
        self,
        *,
        state: BatteryTerminalState,
        rows: int,
        elapsed: float,
        exit_code: int | None,
        detail: str,
    ) -> ModelBatteryOutcome:
        tail = "" if state is BatteryTerminalState.COMPLETED else self.read_tail()
        return ModelBatteryOutcome(
            run_id=self.run_id,
            state=state,
            rows_observed=rows,
            elapsed_seconds=max(0.0, elapsed),
            stall_deadline_seconds=self.stall_deadline_seconds,
            detail=detail,
            exit_code=exit_code,
            expected_rows=self.expected_rows,
            expected_rows_max=self.expected_rows_max,
            log_tail=tail,
        )

    def _terminate(self) -> None:
        try:
            self.process.terminate()
            self.process.wait(timeout=self.terminate_grace_seconds)
        except Exception:  # a wedged driver must not block the alert
            try:
                self.process.kill()
            except Exception:  # best effort; the notification still goes out
                pass

    def _notify(self, outcome: ModelBatteryOutcome) -> tuple[tuple[str, ...], tuple[str, ...]]:
        delivered: list[str] = []
        failures: list[str] = []
        for notifier in self.notifiers:
            try:
                notifier.notify(outcome)
            except Exception as exc:  # one dead channel must not mute the rest
                failures.append(f"{notifier.channel}: {exc}")
            else:
                delivered.append(notifier.channel)
        return tuple(delivered), tuple(failures)
