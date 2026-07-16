"""Closed-schema tests for the sole Slice-1 application overlay."""

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.match.composition import load_application_overlay


def _overlay_data(tmp_path: Path) -> dict[str, object]:
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
        },
        "contracts": {
            "catalog_dir": tmp_path / "catalog",
            "pilot_registry_dir": tmp_path / "pilots",
        },
        "clock": {"kind": "system_utc"},
        "identity": {"kind": "system"},
    }


@pytest.mark.unit
def test_overlay_is_complete_and_frozen(tmp_path: Path) -> None:
    overlay = ModelSOApplicationOverlay.model_validate(_overlay_data(tmp_path))

    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    with pytest.raises(ValueError, match="frozen"):
        overlay.event_ledger.path = tmp_path / "other.sqlite3"


@pytest.mark.unit
def test_overlay_rejects_unknown_nested_policy(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    assert isinstance(raw["event_ledger"], dict)
    ledger = dict(raw["event_ledger"])
    ledger["implicit_fallback"] = True
    raw["event_ledger"] = ledger

    with pytest.raises(ValueError, match="implicit_fallback"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_overlay_rejects_unsupported_adapter_kind(tmp_path: Path) -> None:
    raw = _overlay_data(tmp_path)
    raw["bus"] = {"kind": "redis"}

    with pytest.raises(ValueError, match="in_process"):
        ModelSOApplicationOverlay.model_validate(raw)


@pytest.mark.unit
def test_overlay_relative_paths_resolve_from_overlay_directory(tmp_path: Path) -> None:
    raw = _overlay_data(Path("."))
    overlay_path = tmp_path / "application.yaml"
    serialized = ModelSOApplicationOverlay.model_validate(raw).model_dump(mode="json")
    overlay_path.write_text(yaml.safe_dump(serialized), encoding="utf-8")

    overlay = load_application_overlay(overlay_path)

    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.contracts.catalog_dir == tmp_path / "catalog"
