"""Display-salience arm #1 battery driver (OMN-15171): platform-path battery.

Covers, without live infra (no ``confluent_kafka`` extra, no delegation
subprocess, no network):

- ``--corner`` selection resolves the exact committed overlay + loadout pair
  (#223, OMN-15166) and rejects an unknown corner.
- ``_lane_overlay`` repoints every durable-state surface into the battery
  lane AND overrides the ``onex_delegation`` provider's
  ``omnibase_infra_path``/``state_root`` -- the worktree-vs-sibling-checkout
  footgun this driver exists to route around (module docstring).
- ``_run_seed`` end to end, hermetically: a real ``assemble_match_live``
  match (stub LLM provider, no network) forwards its terminal events onto a
  FAKE Kafka transport and the returned row carries a minted
  ``correlation_id`` plus the exact forwarded event-type set -- proving the
  row-building + forwarding logic this driver adds, not just a mock.
- ``main()``'s skip/exit-code contract (one dead seed must not kill the
  battery, but must force a non-zero exit and never write a synthetic row)
  -- the same contamination-safety bar
  ``run_ogate_objectives_battery.py``'s own tests hold it to
  (2026-07-25 SO-COMP-CA / SO-COMP-R1 fix).
- ``confluent_kafka`` absent -> ``KafkaLiveTransportUnavailableError``,
  never a bare ``ImportError`` traceback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.run_display_salience_battery import (
    _BLUE,
    _CORNER_LOADOUTS,
    _CORNER_OVERLAYS,
    _RED,
    KafkaLiveTransportUnavailableError,
    _build_kafka_transport,
    _build_parser,
    _lane_overlay,
    _preflight_delegation_cli,
    _run_seed,
    main,
)
from steel_onslaught.bus.kafka_forwarder import STEEL_MATCH_TERMINAL_TOPIC, TERMINAL_EVENT_TYPES
from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSODelegationProviderBinding,
)
from steel_onslaught.contracts.arena import arena_contract_hash
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.llm.schemas import LlmTransportError
from steel_onslaught.match.composition import load_match_contract_catalog
from tests.overlay import complete_test_overlay

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_DIR = _REPO_ROOT / "contracts_data"
_LOADOUTS = _CATALOG_DIR / "loadouts"
_DRAW_SEED = 99999  # tests/integration/test_proof_of_life.py's canonical draw seed
_OPEN_FIELD_ARENA_ID = "open_field"  # tests/overlay.py::complete_test_overlay's fixed arena


class _FakeKafkaTransport:
    """Records every published message; no real network involved."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, bytes]] = []
        self.delivery_errors: list[str] = []

    def publish(self, *, topic: str, key: str, value: bytes) -> None:
        self.published.append((topic, key, value))

    def flush(self, timeout_seconds: float) -> int:
        return 0


class _FakeProducer:
    def __init__(self, transport: _FakeKafkaTransport) -> None:
        self._transport = transport

    def flush(self, timeout_seconds: float) -> int:
        return self._transport.flush(timeout_seconds)


# ---------------------------------------------------------------------------
# --corner CLI selection
# ---------------------------------------------------------------------------


def test_default_corner_is_default() -> None:
    args = _build_parser().parse_args([])
    assert args.corner == "default"


def test_corner_selects_prominent() -> None:
    args = _build_parser().parse_args(["--corner", "prominent"])
    assert args.corner == "prominent"


def test_unknown_corner_rejected() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["--corner", "bogus"])


def test_both_corners_have_a_committed_overlay_and_loadout_pair() -> None:
    assert set(_CORNER_OVERLAYS) == {"default", "prominent"}
    assert set(_CORNER_LOADOUTS) == {"default", "prominent"}
    for corner, overlay_path in _CORNER_OVERLAYS.items():
        assert overlay_path.exists(), f"{corner} overlay missing: {overlay_path}"
        red, blue = _CORNER_LOADOUTS[corner]
        assert red.exists(), f"{corner} red loadout missing: {red}"
        assert blue.exists(), f"{corner} blue loadout missing: {blue}"


# ---------------------------------------------------------------------------
# _lane_overlay: state repointing + delegation provider path override
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("corner", ["default", "prominent"])
def test_lane_overlay_repoints_durable_state(tmp_path: Path, corner: str) -> None:
    fake_infra = tmp_path / "fake_omnibase_infra"
    overlay = _lane_overlay(tmp_path, corner, omnibase_infra_path=fake_infra)
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    assert overlay.evaluation_storage.root == tmp_path / "evaluation_storage"


@pytest.mark.parametrize("corner", ["default", "prominent"])
def test_lane_overlay_overrides_delegation_provider_paths(tmp_path: Path, corner: str) -> None:
    """The worktree-vs-sibling-checkout footgun this driver exists to avoid:
    the committed overlay's own ``omnibase_infra_path: ../omnibase_infra``
    is CWD-relative and must never be trusted verbatim."""
    fake_infra = tmp_path / "fake_omnibase_infra"
    overlay = _lane_overlay(tmp_path, corner, omnibase_infra_path=fake_infra)
    (provider,) = [
        p for p in overlay.llm.providers if isinstance(p, ModelSODelegationProviderBinding)
    ]
    assert provider.omnibase_infra_path == fake_infra
    assert provider.state_root == tmp_path / "delegation_state"
    # Nothing else about the committed provider binding is silently changed.
    assert provider.backend_id == "local-coder-mlx"
    assert provider.model == "mlx-community/Qwen3.6-35B-A3B-8bit"


def test_lane_overlay_default_and_prominent_share_the_arena() -> None:
    default_overlay = _lane_overlay(
        Path("/tmp/unused-default"), "default", omnibase_infra_path=Path("/tmp")
    )
    prominent_overlay = _lane_overlay(
        Path("/tmp/unused-prominent"), "prominent", omnibase_infra_path=Path("/tmp")
    )
    assert (
        default_overlay.contracts.arena_id
        == prominent_overlay.contracts.arena_id
        == "foundry_60_asym_v1"
    )


# ---------------------------------------------------------------------------
# _run_seed: hermetic real match + fake Kafka transport (no live infra)
# ---------------------------------------------------------------------------


def _hermetic_overlay(tmp_path: Path) -> ModelSOApplicationOverlay:
    raw: dict[str, Any] = {
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
    return ModelSOApplicationOverlay.model_validate(complete_test_overlay(raw, tmp_path))


def test_run_seed_forwards_terminal_events_and_returns_a_contamination_safe_row(
    tmp_path: Path,
) -> None:
    overlay = _hermetic_overlay(tmp_path)
    catalog = load_match_contract_catalog(_CATALOG_DIR)
    expected_hash = arena_contract_hash(catalog.arenas[_OPEN_FIELD_ARENA_ID].to_snapshot())
    transport = _FakeKafkaTransport()
    producer = _FakeProducer(transport)

    row = _run_seed(
        overlay,
        seed=_DRAW_SEED,
        max_ticks=50,
        expected_arena_hash=expected_hash,
        expected_arena_id=_OPEN_FIELD_ARENA_ID,
        red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
        blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
        kafka_transport=transport,  # type: ignore[arg-type]
        producer=producer,
    )

    # check_contamination_gate.py's exact minimum row shape (seed, match_id).
    assert row["seed"] == _DRAW_SEED
    assert isinstance(row["match_id"], str) and row["match_id"]
    # The minted proof this ticket adds: a real correlation_id per row.
    assert isinstance(row["correlation_id"], str) and row["correlation_id"]

    assert transport.published, "the forwarder must have forwarded at least one terminal event"
    forwarded = [
        ModelSOEventEnvelope.model_validate_json(value)
        for _topic, _key, value in transport.published
    ]
    forwarded_types = {event.event_type for event in forwarded}
    assert forwarded_types <= set(TERMINAL_EVENT_TYPES)
    assert SOEventType.VICTORY_DECLARED not in forwarded_types  # a draw declares no victor
    assert SOEventType.MATCH_STARTED in forwarded_types
    assert SOEventType.MATCH_ENDED in forwarded_types
    assert SOEventType.MATCH_SCORED in forwarded_types
    assert set(row["kafka_forwarded_event_types"]) == {t.value for t in forwarded_types}
    assert row["kafka_topic"] == STEEL_MATCH_TERMINAL_TOPIC

    for topic, key, _value in transport.published:
        assert topic == STEEL_MATCH_TERMINAL_TOPIC
        assert key == row["match_id"]


def test_run_seed_raises_on_arena_id_mismatch(tmp_path: Path) -> None:
    overlay = _hermetic_overlay(tmp_path)
    transport = _FakeKafkaTransport()
    producer = _FakeProducer(transport)

    with pytest.raises(ValueError, match="arena_id"):
        _run_seed(
            overlay,
            seed=_DRAW_SEED,
            max_ticks=50,
            expected_arena_hash="deadbeef",
            expected_arena_id="foundry_60_asym_v1",  # overlay is actually open_field
            red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
            blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
            kafka_transport=transport,  # type: ignore[arg-type]
            producer=producer,
        )


def test_run_seed_raises_on_undelivered_kafka_messages(tmp_path: Path) -> None:
    overlay = _hermetic_overlay(tmp_path)
    catalog = load_match_contract_catalog(_CATALOG_DIR)
    expected_hash = arena_contract_hash(catalog.arenas[_OPEN_FIELD_ARENA_ID].to_snapshot())
    transport = _FakeKafkaTransport()

    class _StuckProducer:
        def flush(self, timeout_seconds: float) -> int:
            return 3  # 3 messages still stuck in the queue

    with pytest.raises(RuntimeError, match="undelivered"):
        _run_seed(
            overlay,
            seed=_DRAW_SEED,
            max_ticks=50,
            expected_arena_hash=expected_hash,
            expected_arena_id=_OPEN_FIELD_ARENA_ID,
            red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
            blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
            kafka_transport=transport,  # type: ignore[arg-type]
            producer=_StuckProducer(),
        )


def test_run_seed_raises_on_kafka_delivery_errors(tmp_path: Path) -> None:
    overlay = _hermetic_overlay(tmp_path)
    catalog = load_match_contract_catalog(_CATALOG_DIR)
    expected_hash = arena_contract_hash(catalog.arenas[_OPEN_FIELD_ARENA_ID].to_snapshot())
    transport = _FakeKafkaTransport()
    transport.delivery_errors.append("simulated: topic missing")
    producer = _FakeProducer(transport)

    with pytest.raises(RuntimeError, match="delivery failures"):
        _run_seed(
            overlay,
            seed=_DRAW_SEED,
            max_ticks=50,
            expected_arena_hash=expected_hash,
            expected_arena_id=_OPEN_FIELD_ARENA_ID,
            red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
            blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
            kafka_transport=transport,  # type: ignore[arg-type]
            producer=producer,
        )


# ---------------------------------------------------------------------------
# confluent_kafka unavailable
# ---------------------------------------------------------------------------


def test_build_kafka_transport_raises_typed_error_when_confluent_kafka_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "confluent_kafka", None)
    with pytest.raises(KafkaLiveTransportUnavailableError, match="uv sync --extra live"):
        _build_kafka_transport("127.0.0.1:9092")


# ---------------------------------------------------------------------------
# main(): skip/exit-code contract (monkeypatched _run_seed, no live infra)
# ---------------------------------------------------------------------------


def _fake_row(seed: int) -> dict[str, Any]:
    return {
        "seed": seed,
        "match_id": f"match.fixture.{seed}",
        "correlation_id": f"corr-{seed}",
        "end_reason": "last_mech_standing",
        "victory_kind": "last_mech_standing",
        "terminal_class": "elimination",
        "winner_player_id": _RED,
        "is_draw": False,
        "duration_ticks": 10,
        "vp_totals": {},
        "vp_margin": 0,
        "total_awards": 0,
        "failed_completions": 0,
        "replay_validity": {_RED: 1, _BLUE: 1},
        "kafka_topic": STEEL_MATCH_TERMINAL_TOPIC,
        "kafka_forwarded_event_types": ["match_started", "match_ended", "match_scored"],
    }


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dead_seed: int | None = None,
    dead_seed_exc: Exception | None = None,
) -> None:
    def _fake_run_seed(
        overlay: object,
        *,
        seed: int,
        max_ticks: int,
        expected_arena_hash: str,
        red_loadout_path: Path,
        blue_loadout_path: Path,
        kafka_transport: object,
        producer: object,
        **_kwargs: object,
    ) -> dict[str, Any]:
        if seed == dead_seed:
            raise dead_seed_exc or RuntimeError("simulated LlmTransportError: connection reset")
        return _fake_row(seed)

    monkeypatch.setattr("scripts.run_display_salience_battery._run_seed", _fake_run_seed)
    monkeypatch.setattr(
        "scripts.run_display_salience_battery._build_kafka_transport",
        lambda bootstrap: (_FakeProducer(_FakeKafkaTransport()), _FakeKafkaTransport()),
    )
    monkeypatch.setattr(
        "scripts.run_display_salience_battery._lane_overlay",
        lambda state_root, corner, *, omnibase_infra_path: object(),
    )
    monkeypatch.setattr(
        "scripts.run_display_salience_battery.load_match_contract_catalog",
        lambda root: load_match_contract_catalog(root),
    )
    # OMN-15240: the delegation-CLI preflight probe issues a REAL LLM call
    # against a real overlay -- every test here uses a fake, provider-less
    # overlay object (see _lane_overlay's fake above), so the preflight is a
    # no-op by default. Tests that specifically cover the preflight contract
    # override this back to the real function or a failing fake.
    monkeypatch.setattr(
        "scripts.run_display_salience_battery._preflight_delegation_cli",
        lambda overlay: None,
    )


def _argv(*, n: int, seed_base: int, state_root: Path) -> list[str]:
    return [
        "run_display_salience_battery.py",
        "--n",
        str(n),
        "--seed-base",
        str(seed_base),
        "--state-root",
        str(state_root),
        "--fresh",
        # Explicit, existing path -- these tests must never depend on
        # $OMNI_HOME being set or a real omnibase_infra checkout existing
        # (CI has neither); _lane_overlay is monkeypatched in every test
        # that reaches it, so this value is never actually dereferenced.
        "--omnibase-infra-path",
        str(state_root),
    ]


def test_clean_battery_exits_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fakes(monkeypatch)
    monkeypatch.setattr(sys, "argv", _argv(n=2, seed_base=90000, state_root=tmp_path))

    exit_code = main()

    assert exit_code == 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    assert summary["n"] == 2
    assert summary["requested_n"] == 2
    assert summary["skipped_seeds"] == []
    assert summary["all_seeds_forwarded_terminal_events"] is True
    raw_lines = (tmp_path / "battery_raw.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2
    for line in raw_lines:
        row = json.loads(line)
        assert row.get("correlation_id")


def test_dead_seed_is_skipped_and_forces_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dead_seed = 90000 + 2
    _install_fakes(monkeypatch, dead_seed=dead_seed)
    monkeypatch.setattr(sys, "argv", _argv(n=3, seed_base=90000, state_root=tmp_path))

    exit_code = main()

    assert exit_code != 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    assert summary["n"] == 2
    assert summary["requested_n"] == 3
    assert summary["skipped_seeds"] == [
        {
            "seed": str(dead_seed),
            "error": "RuntimeError: simulated LlmTransportError: connection reset",
        }
    ]
    raw_lines = (tmp_path / "battery_raw.jsonl").read_text(encoding="utf-8").splitlines()
    recorded_seeds = {json.loads(line)["seed"] for line in raw_lines}
    assert dead_seed not in recorded_seeds


def test_dead_seed_with_long_stderr_surfaces_full_tail_in_persisted_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OMN-15240: a subprocess failing with a long stderr whose tail matters
    must surface the tail in the persisted record.

    Reproduces the exact acceptance-battery failure mode: the CLI subprocess
    stderr begins with a long, benign preamble (the real uv VIRTUAL_ENV
    warning was ~190 chars) and the actual, actionable error sits at the
    tail. The console print may stay short, but ``battery_summary.json`` --
    the durable, persisted record -- must never lose the tail to truncation.
    """
    dead_seed = 90000 + 2
    tail_marker = "REAL_ERROR_TAIL_MARKER_qqzz9182"
    long_stderr = (
        "warning: `VIRTUAL_ENV=.venv` does not match the project environment "
        "path and will be ignored; use `--active` to target the active "
        "environment instead " + ("filler " * 40) + f"Error: {tail_marker}"
    )
    argv = ("uv", "run", "--project", "/fake/omnibase_infra", "onex", "node", "fake")
    dead_seed_exc = LlmTransportError(
        f"onex delegation CLI exited 1: {long_stderr[-2000:]}",
        retryable=False,
        argv=argv,
        exit_code=1,
        stderr=long_stderr,
    )
    _install_fakes(monkeypatch, dead_seed=dead_seed, dead_seed_exc=dead_seed_exc)
    monkeypatch.setattr(sys, "argv", _argv(n=3, seed_base=90000, state_root=tmp_path))

    exit_code = main()

    assert exit_code != 0
    summary = json.loads((tmp_path / "battery_summary.json").read_text(encoding="utf-8"))
    skipped = summary["skipped_seeds"]
    assert len(skipped) == 1
    record = skipped[0]
    assert record["seed"] == str(dead_seed)
    # The persisted "error" text itself must never be truncated to a short
    # console-style preview -- the tail marker must survive.
    assert tail_marker in record["error"]
    # Dedicated structured fields (OMN-15240) let a caller act on the exact
    # failure without re-parsing a flattened message string.
    assert record["exit_code"] == 1
    assert record["argv"] == list(argv)
    assert tail_marker in record["stderr"]


def test_kafka_unavailable_exits_2_before_any_seed_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise(bootstrap: str) -> tuple[object, object]:
        raise KafkaLiveTransportUnavailableError("confluent_kafka is not installed")

    monkeypatch.setattr("scripts.run_display_salience_battery._build_kafka_transport", _raise)
    monkeypatch.setattr(
        "scripts.run_display_salience_battery._lane_overlay",
        lambda state_root, corner, *, omnibase_infra_path: object(),
    )
    monkeypatch.setattr(sys, "argv", _argv(n=2, seed_base=90000, state_root=tmp_path))

    exit_code = main()

    assert exit_code == 2
    assert not (tmp_path / "battery_raw.jsonl").exists()


def test_delegation_cli_preflight_failure_exits_2_before_any_seed_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OMN-15240: a broken delegation-CLI transport must fail the WHOLE
    battery before any seed runs -- never burn N seeds one at a time to
    discover it (the exact waste the 2026-07-27 acceptance run incurred:
    58 dead seeds across both corners on one environmental failure).
    """

    def _raise_preflight(overlay: object) -> None:
        raise LlmTransportError(
            "onex delegation CLI exited 1: Error: omnimarket venv is STALE",
            retryable=False,
            argv=("uv", "run", "onex", "node", "fake"),
            exit_code=1,
            stderr="Error: omnimarket venv is STALE: installed commit abc != canonical def",
        )

    def _unreachable_run_seed(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("_run_seed must never be called when the preflight fails")

    monkeypatch.setattr(
        "scripts.run_display_salience_battery._build_kafka_transport",
        lambda bootstrap: (_FakeProducer(_FakeKafkaTransport()), _FakeKafkaTransport()),
    )
    monkeypatch.setattr(
        "scripts.run_display_salience_battery._lane_overlay",
        lambda state_root, corner, *, omnibase_infra_path: object(),
    )
    monkeypatch.setattr(
        "scripts.run_display_salience_battery._preflight_delegation_cli", _raise_preflight
    )
    monkeypatch.setattr("scripts.run_display_salience_battery._run_seed", _unreachable_run_seed)
    monkeypatch.setattr(sys, "argv", _argv(n=2, seed_base=90000, state_root=tmp_path))

    exit_code = main()

    assert exit_code == 2
    assert not (tmp_path / "battery_raw.jsonl").exists()
    assert not (tmp_path / "battery_summary.json").exists()


def test_preflight_is_a_noop_for_a_delegation_less_overlay(tmp_path: Path) -> None:
    """A non-delegation-bound overlay (no ``onex_delegation`` provider) must
    never be probed -- this driver's own overlays always have one, but the
    function stays defensive rather than assuming."""
    overlay = _hermetic_overlay(tmp_path)
    assert not any(isinstance(p, ModelSODelegationProviderBinding) for p in overlay.llm.providers)

    _preflight_delegation_cli(overlay)  # must not raise
