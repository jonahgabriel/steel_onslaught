"""Shared complete test overlay additions for the Slice-2 dependency graph."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def complete_test_overlay(raw: dict[str, object], root: Path) -> dict[str, object]:
    learning = raw.get("learning_artifacts")
    if not isinstance(learning, dict):
        raise TypeError("test overlay must declare learning_artifacts")
    return {
        **raw,
        "learning_artifacts": {
            **learning,
            "experiment_root": str(root / "experiments"),
        },
        "llm": {
            "providers": [
                {
                    "kind": "stub",
                    "provider_id": "stub",
                    "model": "stub",
                },
                {"kind": "stub", "provider_id": "qwen35", "model": "qwen35-test"},
                {"kind": "stub", "provider_id": "qwen27", "model": "qwen27-test"},
                {"kind": "stub", "provider_id": "deepseek", "model": "deepseek-test"},
            ],
            "personas_dir": str(_REPO_ROOT / "contracts_data/pilots/personas"),
            "secret_resolver": {"kind": "none"},
        },
        "frontend_transport": {
            "kind": "websocket",
            "contract": "steel_onslaught.frontend_transport.v1",
            "websocket_url": "ws://127.0.0.1:8765/events",
            "event_schema": "canonical_event_v1",
            "milliseconds_per_tick": 500,
        },
    }


__all__ = ["complete_test_overlay"]
