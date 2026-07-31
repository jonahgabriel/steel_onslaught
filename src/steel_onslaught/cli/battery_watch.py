"""``so battery-watch`` — the sanctioned way to launch a long battery (OMN-15588).

This is the single supervised entrypoint that replaces the hand-typed
``nohup`` launch plus the runbook's bash chain-watcher and its
``NEEDS_ATTENTION`` sentinel. It launches the driver, watches its progress
heartbeat, and pushes one terminal notification on crash, stall, incomplete
exit, or clean completion.

Notification channels are resolved BEFORE the battery is launched, so a run
with no way to report its own failure never starts.
"""

from __future__ import annotations

import functools
import json
import shlex
import subprocess
import sys
from pathlib import Path

import click

from steel_onslaught.battery.watchdog import (
    ENV_NOTIFY_COMMAND,
    ENV_NOTIFY_WEBHOOK,
    BatteryTerminalState,
    BatteryWatchdog,
    ModelWatchdogResult,
    NoActiveNotifierError,
    count_jsonl_rows,
    exit_code_for,
    read_log_tail,
    resolve_notifiers,
)

_CONFIG_ERROR_EXIT = 4


def _launch(argv: tuple[str, ...], log_path: Path) -> subprocess.Popen[bytes]:
    """Start the driver detached from stdin, with all output tee'd to one log.

    ``stdin=DEVNULL`` is load-bearing, not tidiness: an inherited terminal
    stdin has repeatedly woken a backgrounded battery driver on an unrelated
    keystroke and produced a double-launch race on the same state root.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab")
    return subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


@click.command(
    name="battery-watch",
    context_settings={"ignore_unknown_options": True},
)
@click.option("--run-id", required=True, help="Identifier carried on every notification.")
@click.option(
    "--raw-path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="The driver's battery_raw.jsonl — its per-seed progress heartbeat.",
)
@click.option(
    "--log-path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Driver stdout+stderr sink; its tail rides along on failure notifications.",
)
@click.option(
    "--expected-rows",
    type=click.IntRange(min=1),
    default=None,
    help="Row count of a fully clean run. A short clean exit is INCOMPLETE, not COMPLETED.",
)
@click.option(
    "--stall-deadline-seconds",
    type=click.FloatRange(min=1.0),
    default=3600.0,
    show_default=True,
    help="Terminate and alert when no new row appears within this window.",
)
@click.option(
    "--poll-seconds",
    type=click.FloatRange(min=1.0),
    default=60.0,
    show_default=True,
)
@click.option(
    "--settle-seconds",
    type=click.FloatRange(min=0.0),
    default=15.0,
    show_default=True,
    help="Pause after the driver exits so its final summary/raw writes land.",
)
@click.option(
    "--on-complete-exec",
    default=None,
    help="Command launched ONLY on a clean COMPLETED run (the chain-forward gate).",
)
@click.option(
    "--notify-command",
    default=None,
    envvar=ENV_NOTIFY_COMMAND,
    help=(
        "argv run with the outcome JSON on stdin. Populated from "
        f"${ENV_NOTIFY_COMMAND} when not passed explicitly."
    ),
)
@click.option(
    "--notify-webhook",
    default=None,
    envvar=ENV_NOTIFY_WEBHOOK,
    help=(
        "Chat-compatible webhook URL. Populated from "
        f"${ENV_NOTIFY_WEBHOOK} when not passed explicitly."
    ),
)
@click.argument("battery_command", nargs=-1, type=click.UNPROCESSED, required=True)
def battery_watch_command(
    run_id: str,
    raw_path: Path,
    log_path: Path,
    expected_rows: int | None,
    stall_deadline_seconds: float,
    poll_seconds: float,
    settle_seconds: float,
    on_complete_exec: str | None,
    notify_command: str | None,
    notify_webhook: str | None,
    battery_command: tuple[str, ...],
) -> None:
    """Supervise BATTERY_COMMAND and actively report how it ended.

    Click reads the two channel settings from their documented environment
    variables; nothing below this edge touches the environment, which is the
    composition boundary ``tests/test_di_enforcement.py`` enforces.
    """
    try:
        notifiers = resolve_notifiers(
            {
                ENV_NOTIFY_COMMAND: notify_command or "",
                ENV_NOTIFY_WEBHOOK: notify_webhook or "",
            }
        )
    except NoActiveNotifierError as exc:
        click.echo(f"battery-watch refused to launch: {exc}", err=True)
        raise SystemExit(_CONFIG_ERROR_EXIT) from exc

    chain_argv = tuple(shlex.split(on_complete_exec)) if on_complete_exec else ()
    chain_log = log_path.with_suffix(".chain.log")

    def _launch_chain() -> None:
        _launch(chain_argv, chain_log)

    process = _launch(battery_command, log_path)
    watchdog = BatteryWatchdog(
        run_id=run_id,
        process=process,
        read_rows=functools.partial(count_jsonl_rows, raw_path),
        notifiers=notifiers,
        stall_deadline_seconds=stall_deadline_seconds,
        poll_seconds=poll_seconds,
        expected_rows=expected_rows,
        read_tail=functools.partial(read_log_tail, log_path),
        settle_seconds=settle_seconds,
        on_complete=_launch_chain if chain_argv else None,
    )
    result = watchdog.run()
    _report(result)
    raise SystemExit(exit_code_for(result))


def _report(result: ModelWatchdogResult) -> None:
    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    click.echo(result.outcome.summary_line(), err=True)
    for failure in result.notification_failures:
        click.echo(f"NOTIFICATION FAILED — {failure}", err=True)
    if not result.delivered:
        click.echo(
            "no channel accepted this outcome — nobody has been told; treat as unreported",
            err=True,
        )
    if result.outcome.state is not BatteryTerminalState.COMPLETED:
        print(result.outcome.log_tail, file=sys.stderr)
