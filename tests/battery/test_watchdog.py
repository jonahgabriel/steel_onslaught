"""OMN-15588 — a crashed or stalled battery must surface actively, not on disk.

Each test names the failure it forbids. The two that matter most are the ones
the previous arrangement could not do at all: a driver that dies is reported
(``test_crash_path_emits_terminal_notification``) and a driver that hangs while
still resident is reported (``test_stall_deadline_fires_and_terminates_driver``).
The old runbook watcher polled for process *absence*, so the second case was
invisible to it for as long as the process stayed alive.

All timing is driven by an injected clock. Nothing here sleeps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from steel_onslaught.battery.watchdog import (
    ENV_NOTIFY_COMMAND,
    ENV_NOTIFY_WEBHOOK,
    BatteryTerminalState,
    BatteryWatchdog,
    CommandNotifier,
    ModelBatteryOutcome,
    NoActiveNotifierError,
    NotificationError,
    WebhookNotifier,
    count_jsonl_rows,
    exit_code_for,
    read_log_tail,
    resolve_notifiers,
)
from steel_onslaught.cli import battery_watch as battery_watch_module
from steel_onslaught.cli.battery_watch import battery_watch_command

_RUNBOOK = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "runbooks"
    / "2026-07-28-hermetic-battery-snapshot-recipe.md"
)


class FakeClock:
    """Advances only when the code under test sleeps."""

    def __init__(self) -> None:
        self.time = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.time

    def sleep(self, seconds: float) -> None:
        self.time += seconds
        self.slept.append(seconds)


class FakeProcess:
    """A driver that stays alive for ``exit_after_polls`` polls, then exits."""

    def __init__(self, *, exit_code: int | None = None, exit_after_polls: int = 0) -> None:
        self._exit_code = exit_code
        self._exit_after_polls = exit_after_polls
        self.polls = 0
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        self.polls += 1
        if self._exit_code is None:
            return None
        return self._exit_code if self.polls > self._exit_after_polls else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return self._exit_code if self._exit_code is not None else 0


class RecordingNotifier:
    def __init__(self, name: str = "recording") -> None:
        self._name = name
        self.received: list[ModelBatteryOutcome] = []

    @property
    def channel(self) -> str:
        return self._name

    def notify(self, outcome: ModelBatteryOutcome) -> None:
        self.received.append(outcome)


class DeadNotifier:
    @property
    def channel(self) -> str:
        return "dead"

    def notify(self, outcome: ModelBatteryOutcome) -> None:
        raise NotificationError("channel unreachable")


def _rows(*values: int) -> Callable[[], int]:
    """Return a reader that walks ``values`` then repeats the last one."""
    state: dict[str, int] = {"index": 0}

    def read() -> int:
        index = min(state["index"], len(values) - 1)
        state["index"] += 1
        return values[index]

    return read


@pytest.mark.unit
def test_crash_path_emits_terminal_notification() -> None:
    notifier = RecordingNotifier()
    watchdog = BatteryWatchdog(
        run_id="omn15588_crash",
        process=FakeProcess(exit_code=1, exit_after_polls=2),
        read_rows=_rows(0, 7, 7),
        notifiers=[notifier],
        stall_deadline_seconds=600.0,
        poll_seconds=60.0,
        clock=FakeClock(),
        expected_rows=61,
        read_tail=lambda: "Traceback (most recent call last): boom",
    )

    result = watchdog.run()

    assert result.outcome.state is BatteryTerminalState.CRASHED
    assert result.outcome.exit_code == 1
    assert result.outcome.rows_observed == 7
    assert "Traceback" in result.outcome.log_tail
    assert [outcome.state for outcome in notifier.received] == [BatteryTerminalState.CRASHED]
    assert notifier.received[0].run_id == "omn15588_crash"
    assert exit_code_for(result) == 1


@pytest.mark.unit
def test_stall_deadline_fires_and_terminates_driver() -> None:
    """A driver alive but making no progress is the case disk sentinels miss."""
    notifier = RecordingNotifier()
    process = FakeProcess()  # never exits
    clock = FakeClock()
    watchdog = BatteryWatchdog(
        run_id="omn15588_stall",
        process=process,
        read_rows=_rows(4),  # frozen at 4 rows forever
        notifiers=[notifier],
        stall_deadline_seconds=300.0,
        poll_seconds=60.0,
        clock=clock,
        expected_rows=61,
    )

    result = watchdog.run()

    assert result.outcome.state is BatteryTerminalState.STALLED
    assert result.outcome.exit_code is None
    assert result.outcome.rows_observed == 4
    assert process.terminated is True
    assert clock.time == pytest.approx(300.0)  # fired at the deadline, not before
    assert [outcome.state for outcome in notifier.received] == [BatteryTerminalState.STALLED]
    assert exit_code_for(result) == 1


@pytest.mark.unit
def test_progress_resets_the_stall_deadline() -> None:
    """A slow-but-advancing battery must never be killed as stalled."""
    notifier = RecordingNotifier()
    process = FakeProcess(exit_code=0, exit_after_polls=6)
    watchdog = BatteryWatchdog(
        run_id="omn15588_slow",
        process=process,
        read_rows=_rows(0, 1, 2, 3, 4, 5, 6, 6),
        notifiers=[notifier],
        stall_deadline_seconds=90.0,
        poll_seconds=60.0,  # one poll short of the deadline, so only progress saves it
        clock=FakeClock(),
        expected_rows=6,
    )

    result = watchdog.run()

    assert result.outcome.state is BatteryTerminalState.COMPLETED
    assert process.terminated is False
    assert result.outcome.rows_observed == 6
    assert exit_code_for(result) == 0


@pytest.mark.unit
def test_clean_exit_with_short_row_count_is_incomplete_and_withholds_chain() -> None:
    """The fail-closed branch that `touch NEEDS_ATTENTION` used to implement."""
    notifier = RecordingNotifier()
    chained: list[str] = []
    watchdog = BatteryWatchdog(
        run_id="omn15588_short",
        process=FakeProcess(exit_code=0, exit_after_polls=1),
        read_rows=_rows(0, 27),
        notifiers=[notifier],
        stall_deadline_seconds=600.0,
        poll_seconds=60.0,
        clock=FakeClock(),
        expected_rows=61,
        on_complete=lambda: chained.append("launched"),
    )

    result = watchdog.run()

    assert result.outcome.state is BatteryTerminalState.INCOMPLETE
    assert result.outcome.exit_code == 0
    assert result.chained is False
    assert chained == []
    assert notifier.received[0].state is BatteryTerminalState.INCOMPLETE
    assert exit_code_for(result) == 2


@pytest.mark.unit
def test_completed_run_chains_forward() -> None:
    chained: list[str] = []
    watchdog = BatteryWatchdog(
        run_id="omn15588_clean",
        process=FakeProcess(exit_code=0, exit_after_polls=1),
        read_rows=_rows(0, 61),
        notifiers=[RecordingNotifier()],
        stall_deadline_seconds=600.0,
        poll_seconds=60.0,
        clock=FakeClock(),
        expected_rows=61,
        on_complete=lambda: chained.append("launched"),
    )

    result = watchdog.run()

    assert result.outcome.state is BatteryTerminalState.COMPLETED
    assert result.chained is True
    assert chained == ["launched"]


@pytest.mark.unit
def test_one_dead_channel_does_not_mute_the_others() -> None:
    live = RecordingNotifier("live")
    watchdog = BatteryWatchdog(
        run_id="omn15588_partial",
        process=FakeProcess(exit_code=2, exit_after_polls=1),
        read_rows=_rows(0, 3),
        notifiers=[DeadNotifier(), live],
        stall_deadline_seconds=600.0,
        poll_seconds=60.0,
        clock=FakeClock(),
    )

    result = watchdog.run()

    assert len(live.received) == 1
    assert result.delivered_channels == ("live",)
    assert result.notification_failures == ("dead: channel unreachable",)
    assert exit_code_for(result) == 1  # crash, not a delivery failure


@pytest.mark.unit
def test_total_delivery_failure_is_never_reported_as_a_clean_run() -> None:
    watchdog = BatteryWatchdog(
        run_id="omn15588_unreported",
        process=FakeProcess(exit_code=0, exit_after_polls=1),
        read_rows=_rows(0, 61),
        notifiers=[DeadNotifier()],
        stall_deadline_seconds=600.0,
        poll_seconds=60.0,
        clock=FakeClock(),
        expected_rows=61,
    )

    result = watchdog.run()

    assert result.outcome.state is BatteryTerminalState.COMPLETED
    assert result.delivered is False
    assert exit_code_for(result) == 3


@pytest.mark.unit
def test_watchdog_refuses_to_construct_without_a_notifier() -> None:
    with pytest.raises(NoActiveNotifierError):
        BatteryWatchdog(
            run_id="omn15588_nochannel",
            process=FakeProcess(exit_code=0),
            read_rows=_rows(0),
            notifiers=[],
            stall_deadline_seconds=600.0,
            poll_seconds=60.0,
            clock=FakeClock(),
        )


@pytest.mark.unit
def test_resolve_notifiers_requires_a_configured_channel() -> None:
    with pytest.raises(NoActiveNotifierError) as excinfo:
        resolve_notifiers({})
    assert ENV_NOTIFY_COMMAND in str(excinfo.value)
    assert ENV_NOTIFY_WEBHOOK in str(excinfo.value)

    with pytest.raises(NoActiveNotifierError):
        resolve_notifiers({ENV_NOTIFY_COMMAND: "   ", ENV_NOTIFY_WEBHOOK: ""})

    resolved = resolve_notifiers(
        {
            ENV_NOTIFY_COMMAND: "notify-send steel",
            ENV_NOTIFY_WEBHOOK: "https://example.invalid/hook",
        }
    )
    assert [notifier.channel for notifier in resolved] == ["command:notify-send", "webhook"]


@pytest.mark.unit
def test_command_notifier_hands_the_outcome_json_to_the_command(tmp_path: Path) -> None:
    sink = tmp_path / "delivered.json"
    notifier = CommandNotifier(
        argv=(
            sys.executable,
            "-c",
            f"import sys, pathlib; pathlib.Path({str(sink)!r}).write_text(sys.stdin.read())",
        )
    )
    outcome = ModelBatteryOutcome(
        run_id="omn15588_cmd",
        state=BatteryTerminalState.CRASHED,
        rows_observed=7,
        elapsed_seconds=12.0,
        stall_deadline_seconds=300.0,
        detail="driver exited 1",
        exit_code=1,
        expected_rows=61,
    )

    notifier.notify(outcome)

    payload = json.loads(sink.read_text())
    assert payload["state"] == "crashed"
    assert payload["run_id"] == "omn15588_cmd"
    assert payload["exit_code"] == 1
    assert "CRASHED" in payload["text"]


@pytest.mark.unit
def test_command_notifier_reports_a_nonzero_exit_as_a_delivery_failure() -> None:
    notifier = CommandNotifier(argv=(sys.executable, "-c", "raise SystemExit(9)"))
    outcome = ModelBatteryOutcome(
        run_id="omn15588_cmdfail",
        state=BatteryTerminalState.STALLED,
        rows_observed=0,
        elapsed_seconds=1.0,
        stall_deadline_seconds=300.0,
        detail="stalled",
    )

    with pytest.raises(NotificationError) as excinfo:
        notifier.notify(outcome)
    assert "exited 9" in str(excinfo.value)


@pytest.mark.unit
def test_webhook_notifier_posts_payload_and_fails_on_http_error() -> None:
    posted: list[tuple[str, dict[str, Any]]] = []

    def ok(url: str, payload: dict[str, Any], timeout: float) -> int:
        posted.append((url, payload))
        return 200

    def rejected(url: str, payload: dict[str, Any], timeout: float) -> int:
        return 503

    outcome = ModelBatteryOutcome(
        run_id="omn15588_hook",
        state=BatteryTerminalState.CRASHED,
        rows_observed=2,
        elapsed_seconds=5.0,
        stall_deadline_seconds=300.0,
        detail="driver exited 1",
        exit_code=1,
    )

    WebhookNotifier(url="https://example.invalid/hook", post_json=ok).notify(outcome)
    assert posted[0][0] == "https://example.invalid/hook"
    assert posted[0][1]["state"] == "crashed"

    with pytest.raises(NotificationError):
        WebhookNotifier(url="https://example.invalid/hook", post_json=rejected).notify(outcome)


@pytest.mark.unit
def test_row_counter_and_log_tail_tolerate_a_not_yet_created_run(tmp_path: Path) -> None:
    missing = tmp_path / "battery_raw.jsonl"
    assert count_jsonl_rows(missing) == 0
    assert read_log_tail(tmp_path / "absent.log") == ""

    missing.write_text('{"seed": 1}\n\n{"seed": 2}\n')
    assert count_jsonl_rows(missing) == 2

    log = tmp_path / "driver.log"
    log.write_text("x" * 9000 + "TAIL-MARKER")
    tail = read_log_tail(log, max_bytes=64)
    assert tail.endswith("TAIL-MARKER")
    assert len(tail) <= 64


@pytest.mark.unit
def test_cli_refuses_to_launch_a_battery_with_no_active_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A disk-only battery cannot be started through the sanctioned path.

    The property under test is an *ordering*: channel resolution must happen
    strictly before the driver is spawned, so a run with no way to report its
    own failure never starts. The assertion is therefore on the launch seam
    itself -- ``battery_watch._launch``, the module's only ``Popen`` site --
    and not on a filesystem side effect of the spawned child.

    That distinction is load-bearing, not stylistic. The first version of this
    test asserted ``not marker.exists()`` after ``CliRunner`` returned, and it
    stayed green when the launch was moved *above* the channel resolution:
    the child had been spawned, it simply had not written its marker yet
    (verified directly -- exit 4, marker absent immediately, present 2s
    later). It proved the exit code and nothing else. A spy on the seam has no
    such race, so a refactor that reintroduces the "battery started with no
    way to report its own failure" ordering now lands RED.

    The complementary positive control -- that a properly configured run does
    spawn and supervise a real driver -- is
    ``test_cli_supervises_a_real_driver_and_delivers_a_crash_notification``
    below, which drives real processes end to end.
    """
    launched: list[tuple[str, ...]] = []

    def _spy_launch(argv: tuple[str, ...], log_path: Path) -> Any:
        launched.append(tuple(argv))
        return None

    monkeypatch.setattr(battery_watch_module, "_launch", _spy_launch)

    result = CliRunner().invoke(
        battery_watch_command,
        [
            "--run-id",
            "omn15588_cli_nochannel",
            "--raw-path",
            str(tmp_path / "battery_raw.jsonl"),
            "--log-path",
            str(tmp_path / "driver.log"),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        env={ENV_NOTIFY_COMMAND: "", ENV_NOTIFY_WEBHOOK: ""},
    )

    assert result.exit_code == 4
    assert "refused to launch" in result.output
    assert launched == []  # the refusal preceded every launch attempt


@pytest.mark.integration
def test_cli_supervises_a_real_driver_and_delivers_a_crash_notification(tmp_path: Path) -> None:
    """End-to-end over real processes: the artifact that runs, not a surrogate."""
    raw_path = tmp_path / "battery_raw.jsonl"
    log_path = tmp_path / "driver.log"
    delivered = tmp_path / "delivered.json"

    driver = tmp_path / "driver.py"
    driver.write_text(
        "import pathlib, sys\n"
        f"raw = pathlib.Path({str(raw_path)!r})\n"
        'raw.write_text(\'{"seed": 1}\\n{"seed": 2}\\n\')\n'
        "print('driver about to fail', file=sys.stderr)\n"
        "raise SystemExit(3)\n"
    )
    notify = tmp_path / "notify.py"
    notify.write_text(
        f"import pathlib, sys\npathlib.Path({str(delivered)!r}).write_text(sys.stdin.read())\n"
    )

    env = dict(os.environ)
    env[ENV_NOTIFY_COMMAND] = f"{sys.executable} {notify}"
    env.pop(ENV_NOTIFY_WEBHOOK, None)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from steel_onslaught.cli import main; main()",
            "battery-watch",
            "--run-id",
            "omn15588_cli_e2e",
            "--raw-path",
            str(raw_path),
            "--log-path",
            str(log_path),
            "--expected-rows",
            "61",
            "--poll-seconds",
            "1",
            "--settle-seconds",
            "0",
            "--stall-deadline-seconds",
            "120",
            "--",
            sys.executable,
            str(driver),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(delivered.read_text())
    assert payload["state"] == "crashed"
    assert payload["exit_code"] == 3
    assert payload["rows_observed"] == 2
    assert "driver about to fail" in payload["log_tail"]


@pytest.mark.unit
def test_runbook_no_longer_documents_the_disk_sentinel_bash_watcher() -> None:
    """Net-negative surface: the replaced recipe must not quietly come back."""
    text = _RUNBOOK.read_text()
    assert "so battery-watch" in text, "the runbook must launch batteries through the watchdog"
    assert 'touch "$ROOT/NEEDS_ATTENTION"' not in text
    assert "while pgrep -f" not in text
    assert "chain watcher started" not in text


# ---------------------------------------------------------------------------
# OMN-15488 leg (a): a data-dependent clean row count
# ---------------------------------------------------------------------------


class TestRangeRowContract:
    """A battery's clean row count is not always a constant.

    ``scripts/run_lgate2_adaptation_battery.py``'s promote phase stops at the
    FIRST promotion, so a clean run writes ``n + k + n`` rows for an unknown
    ``k`` in ``1..promote_attempts`` -- 61 through 75 at leg (a)'s n=30/15
    configuration. Under the exact-match contract the only expressible value
    was a single literal, and the literal to hand was 61 (the red battery
    promoted on its first attempt), so 14 of the 15 clean outcomes would have
    been declared INCOMPLETE and had their chain withheld.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("rows", [61, 62, 68, 75])
    def test_every_clean_outcome_in_range_completes_and_chains(self, rows: int) -> None:
        chained: list[str] = []
        watchdog = BatteryWatchdog(
            run_id="omn15488_legA_range",
            process=FakeProcess(exit_code=0, exit_after_polls=1),
            read_rows=_rows(0, rows),
            notifiers=[RecordingNotifier()],
            stall_deadline_seconds=600.0,
            poll_seconds=60.0,
            clock=FakeClock(),
            expected_rows=61,
            expected_rows_max=75,
            on_complete=lambda: chained.append("launched"),
        )

        result = watchdog.run()

        assert result.outcome.state is BatteryTerminalState.COMPLETED
        assert result.chained is True
        assert chained == ["launched"]

    @pytest.mark.unit
    def test_the_old_exact_contract_would_have_misreported_a_clean_run(self) -> None:
        """RED-before proof: the same 62-row run, under the literal 61."""
        chained: list[str] = []
        watchdog = BatteryWatchdog(
            run_id="omn15488_legA_exact",
            process=FakeProcess(exit_code=0, exit_after_polls=1),
            read_rows=_rows(0, 62),
            notifiers=[RecordingNotifier()],
            stall_deadline_seconds=600.0,
            poll_seconds=60.0,
            clock=FakeClock(),
            expected_rows=61,  # no upper bound -> equality, the prior behaviour
            on_complete=lambda: chained.append("launched"),
        )

        result = watchdog.run()

        assert result.outcome.state is BatteryTerminalState.INCOMPLETE
        assert result.chained is False
        assert chained == []

    @pytest.mark.unit
    @pytest.mark.parametrize("rows", [0, 27, 60, 76])
    def test_the_range_still_fails_closed_outside_its_bounds(self, rows: int) -> None:
        """The floor is the whole point of --expected-rows; a range keeps it.

        Dropping the flag entirely was the other way to accept 61-75, and it
        would have let a 27-row clean exit -- the exact shape of the abandoned
        OMN-15488 attempt -- read as COMPLETED.
        """
        watchdog = BatteryWatchdog(
            run_id="omn15488_legA_outside",
            process=FakeProcess(exit_code=0, exit_after_polls=1),
            read_rows=_rows(0, rows),
            notifiers=[RecordingNotifier()],
            stall_deadline_seconds=600.0,
            poll_seconds=60.0,
            clock=FakeClock(),
            expected_rows=61,
            expected_rows_max=75,
        )

        result = watchdog.run()

        assert result.outcome.state is BatteryTerminalState.INCOMPLETE
        assert "expected 61-75" in result.outcome.detail
        assert exit_code_for(result) == 2

    @pytest.mark.unit
    def test_summary_line_renders_the_range(self) -> None:
        outcome = ModelBatteryOutcome(
            run_id="omn15488_legA_blue",
            state=BatteryTerminalState.COMPLETED,
            rows_observed=68,
            elapsed_seconds=1.0,
            stall_deadline_seconds=3600.0,
            detail="ok",
            exit_code=0,
            expected_rows=61,
            expected_rows_max=75,
        )
        assert "rows=68/61-75" in outcome.summary_line()

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("minimum", "maximum"),
        [(None, 75), (75, 61)],
    )
    def test_an_incoherent_contract_is_rejected(self, minimum: int | None, maximum: int) -> None:
        """An upper bound with no lower bound is not a range, and an inverted
        range accepts nothing. Fail closed rather than ignoring half of it."""
        with pytest.raises(ValueError):
            BatteryWatchdog(
                run_id="omn15488_legA_bad",
                process=FakeProcess(),
                read_rows=_rows(0),
                notifiers=[RecordingNotifier()],
                stall_deadline_seconds=600.0,
                poll_seconds=60.0,
                clock=FakeClock(),
                expected_rows=minimum,
                expected_rows_max=maximum,
            )

    @pytest.mark.unit
    def test_cli_refuses_an_incoherent_contract_without_launching_the_driver(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal must happen BEFORE _launch.

        BatteryWatchdog's own guard fires too late in the CLI's order of
        operations: by then a multi-hour battery is already running and would
        be left with no supervisor -- the precise unsupervised-run failure
        mode this module exists to remove.
        """
        launched: list[tuple[str, ...]] = []

        def _never(argv: tuple[str, ...], log: Path) -> Any:
            launched.append(argv)
            raise AssertionError("the driver must not be launched on a bad row contract")

        monkeypatch.setattr(battery_watch_module, "_launch", _never)
        result = CliRunner().invoke(
            battery_watch_command,
            [
                "--run-id",
                "omn15488_legA_cli",
                "--raw-path",
                str(tmp_path / "battery_raw.jsonl"),
                "--log-path",
                str(tmp_path / "driver.log"),
                "--expected-rows-max",
                "75",
                "--notify-command",
                "true",
                "--",
                "true",
            ],
        )

        assert result.exit_code == 4
        assert "refused to launch" in result.output
        assert launched == []
