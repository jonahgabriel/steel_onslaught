"""Battery execution supervision — active failure signalling for long runs."""

from steel_onslaught.battery.watchdog import (
    BatteryTerminalState,
    BatteryWatchdog,
    CommandNotifier,
    ModelBatteryOutcome,
    ModelWatchdogResult,
    NoActiveNotifierError,
    NotificationError,
    ProtocolBatteryNotifier,
    ProtocolClock,
    ProtocolSupervisedProcess,
    WebhookNotifier,
    count_jsonl_rows,
    exit_code_for,
    read_log_tail,
    resolve_notifiers,
)

__all__ = [
    "BatteryTerminalState",
    "BatteryWatchdog",
    "CommandNotifier",
    "ModelBatteryOutcome",
    "ModelWatchdogResult",
    "NoActiveNotifierError",
    "NotificationError",
    "ProtocolBatteryNotifier",
    "ProtocolClock",
    "ProtocolSupervisedProcess",
    "WebhookNotifier",
    "count_jsonl_rows",
    "exit_code_for",
    "read_log_tail",
    "resolve_notifiers",
]
