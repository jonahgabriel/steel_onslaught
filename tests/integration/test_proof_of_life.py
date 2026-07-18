"""Proof of Life — end-to-end duel (Task 34, the binding gate).

Two tests, two terminal states:

1. ``test_proof_of_life_decisive_victory`` — the canonical decisive-victory
   seed.  Five independent proofs: live terminal state, replay state equality
   (R9), leaderboard row contents, CLI byte-identity, and a Playwright DOM
   assertion against the Vite dev server (R10, projection proof).
2. ``test_proof_of_life_draw_max_ticks`` — two passive defensive loadouts
   (no weapons, no sensors) that never engage; the match terminates at the
   ``max_ticks`` bound with ``end_reason == draw_max_ticks``.

Seed note (plan Task 34): the plan designates seed ``12345`` as the canonical
decisive-victory seed, to be verified once Tasks 18-26 were wired.  With the
full reducer stack wired, seed ``12345`` produces a decisive victory, so the
canonical seed is kept.

Module-substitution note: the plan's red loadout names ``machine_gun`` and
``auxiliary_vent``.  ``weapon.light.machine_gun`` is not chassis-compatible
with ``chassis.heavy.ironclad_mk1`` per its contract, and no ``auxiliary_vent``
gizmo contract exists; the loadout substitutes ``weapon.heavy.harpoon_gun``
and ``gizmo.efficiency.efficient_regulator`` (see the loadout YAML comments).
"""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pytest
from click.testing import CliRunner

from scripts.export_frontend_bootstrap import export_frontend_bootstrap
from steel_onslaught.cli.main import main as cli_main
from steel_onslaught.contracts.application import ModelSOApplicationOverlay
from steel_onslaught.match.composition import assemble_match_live
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.replay.engine import ReplayEngine
from tests.overlay import complete_test_overlay
from tests.sqlite_ledger import open_sqlite_ledger

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts"

# Canonical decisive-victory seed (plan Task 34; verified post-wiring).
DECISIVE_SEED = 12345
# Draw seed — the passive loadouts draw structurally, independent of seed.
DRAW_SEED = 99999

_VITE_BOOTSTRAP = _REPO_ROOT / "frontend" / ".steel-onslaught-bootstrap.generated.json"


def _free_port() -> int:
    """Return an available localhost port for one hermetic child server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_overlay(
    tmp_path: Path,
    *,
    ledger_path: Path,
    leaderboard_path: Path,
    websocket_port: int = 8765,
    milliseconds_per_tick: int = 500,
) -> tuple[ModelSOApplicationOverlay, Path]:
    raw_overlay = complete_test_overlay(
        {
            "schema_version": "1",
            "bus": {"kind": "in_process"},
            "event_ledger": {
                "kind": "sqlite",
                "path": ledger_path,
                "journal_mode": "WAL",
                "check_same_thread": True,
                "transaction_mode": "autocommit",
                "event_schema": "canonical_event_v1",
            },
            "leaderboard": {
                "kind": "sqlite",
                "path": leaderboard_path,
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
                "catalog_dir": _REPO_ROOT / "contracts_data",
                "pilot_registry_dir": _REPO_ROOT / "contracts_data" / "pilots",
            },
            "clock": {"kind": "system_utc"},
            "identity": {"kind": "system"},
        },
        tmp_path,
    )
    # complete_test_overlay supplies the canonical default; this proof lane
    # overrides only its injected loopback endpoint and pacing.
    raw_overlay["frontend_transport"] = {
        "kind": "websocket",
        "contract": "steel_onslaught.frontend_transport.v1",
        "websocket_url": f"ws://127.0.0.1:{websocket_port}/events",
        "event_schema": "canonical_event_v1",
        "milliseconds_per_tick": milliseconds_per_tick,
    }
    overlay = ModelSOApplicationOverlay.model_validate(raw_overlay)
    overlay_path = tmp_path / "application.json"
    overlay_path.write_text(json.dumps(overlay.model_dump(mode="json")), encoding="utf-8")
    return overlay, overlay_path


def capture_cli_replay(overlay_path: Path, match_id: str) -> str:
    """Run ``so replay`` against *ledger_path* and return its stdout."""
    result = CliRunner().invoke(
        cli_main,
        ["replay", "--overlay", str(overlay_path), "--match", match_id, "--no-color"],
    )
    assert result.exit_code == 0, f"so replay failed: {result.output}"
    return result.output


def _wait_for_port(
    port: int,
    *,
    timeout: float = 60.0,
    proc: subprocess.Popen[bytes] | None = None,
    stderr_file: IO[bytes] | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            detail = ""
            if stderr_file is not None:
                stderr_file.seek(0)
                detail = stderr_file.read().decode("utf-8", "replace").strip()
            raise RuntimeError(
                f"server exited early (rc={proc.returncode}) before port {port} opened:\n{detail}"
            )
        with contextlib.suppress(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        time.sleep(0.2)
    raise TimeoutError(f"port {port} did not start listening within {timeout}s")


@contextlib.contextmanager
def _subprocess_server(args: list[str], *, cwd: Path, port: int) -> Iterator[None]:
    stderr_file = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
    )
    try:
        _wait_for_port(port, proc=proc, stderr_file=stderr_file)
        yield
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        stderr_file.close()


@contextlib.contextmanager
def _generated_vite_bootstrap(overlay_path: Path) -> Iterator[None]:
    """Generate the ignored Vite authority and restore any prior local copy."""
    previous = _VITE_BOOTSTRAP.read_bytes() if _VITE_BOOTSTRAP.exists() else None
    export_frontend_bootstrap(overlay_path, _VITE_BOOTSTRAP)
    try:
        yield
    finally:
        if previous is None:
            _VITE_BOOTSTRAP.unlink(missing_ok=True)
        else:
            _VITE_BOOTSTRAP.write_bytes(previous)


@pytest.mark.integration
@pytest.mark.slow
def test_proof_of_life_decisive_victory(tmp_path: Path) -> None:
    # 1) Run match live with the canonical decisive-victory seed.
    ledger_path = tmp_path / "match.sqlite"
    leaderboard_path = tmp_path / "leaderboard.sqlite"
    ws_port = _free_port()
    overlay, overlay_path = _write_overlay(
        tmp_path,
        ledger_path=ledger_path,
        leaderboard_path=leaderboard_path,
        websocket_port=ws_port,
        # The browser proof is a terminal-state projection assertion.  Pace its
        # dedicated overlay at 1 ms/tick so match length never races a fixed
        # browser wait; production overlays retain the 500 ms operator pace.
        milliseconds_per_tick=1,
    )
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=_LOADOUTS / "proof_red_predictive_ironclad.yaml",
        blue_loadout_path=_LOADOUTS / "proof_blue_aggressive_hunter.yaml",
        seed=DECISIVE_SEED,
        max_ticks=200,
    )
    live_state = stack.runner.run()
    assert live_state.status is SOMatchStatus.ENDED
    assert live_state.tick <= 200
    assert live_state.end_reason is SOMatchEndReason.LAST_MECH_STANDING
    assert live_state.winner_id in {"player.red", "player.blue"}

    # 2) Replay reconstructs canonical state exactly (R9 data flow proof).
    replay = ReplayEngine(
        open_sqlite_ledger(ledger_path),
        match_id=live_state.match_id,
        catalog=stack.catalog,
        event_factory=stack.event_factory,
    )
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state, "replay must reproduce canonical state exactly"

    # 3) Leaderboard updated correctly (winning entry, not a draw).
    top = stack.leaderboard.top_n(1)
    assert len(top) == 1
    assert top[0].match_id == live_state.match_id
    assert top[0].winner_player_id == live_state.winner_id
    assert top[0].winner_score > top[0].loser_score
    assert top[0].is_draw is False

    # 4) CLI projection produces byte-identical output across runs.
    cli_out_1 = capture_cli_replay(overlay_path, live_state.match_id)
    cli_out_2 = capture_cli_replay(overlay_path, live_state.match_id)
    assert cli_out_1 == cli_out_2, "CLI replay must be byte-identical across runs"
    assert f"VICTORY: {live_state.winner_id}" in cli_out_1

    # 5) Web UI rendered output (Playwright — projection proof, NOT byte-identity).
    from playwright.sync_api import sync_playwright

    vite_port = _free_port()
    serve_cmd = [
        sys.executable,
        "-c",
        "from steel_onslaught.cli import main; main()",
        "serve",
        "--overlay",
        str(overlay_path),
        "--match",
        live_state.match_id,
    ]
    vite_cmd = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(vite_port),
        "--strictPort",
    ]
    with (
        _generated_vite_bootstrap(overlay_path),
        _subprocess_server(serve_cmd, cwd=_REPO_ROOT, port=ws_port),
        _subprocess_server(vite_cmd, cwd=_REPO_ROOT / "frontend", port=vite_port),
    ):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{vite_port}/")
            victory_selector = (
                f'[data-testid="arena-victory"][data-winner="{live_state.winner_id}"]'
            )
            page.wait_for_selector(victory_selector, timeout=30_000)
            # R10: assert the rendered arena victory state names the exact winner.
            victory = page.locator(victory_selector)
            assert victory.get_attribute("data-winner") == live_state.winner_id
            assert live_state.winner_id in victory.inner_text()
            browser.close()


@pytest.mark.integration
@pytest.mark.slow
def test_proof_of_life_draw_max_ticks(tmp_path: Path) -> None:
    """Two defensive pilots that never engage → match terminates at max_ticks."""
    ledger_path = tmp_path / "draw.sqlite"
    leaderboard_path = tmp_path / "draw_leaderboard.sqlite"
    overlay, _ = _write_overlay(
        tmp_path, ledger_path=ledger_path, leaderboard_path=leaderboard_path
    )
    stack = assemble_match_live(
        overlay=overlay,
        red_loadout_path=_LOADOUTS / "proof_red_defensive_passive.yaml",
        blue_loadout_path=_LOADOUTS / "proof_blue_defensive_passive.yaml",
        seed=DRAW_SEED,
        max_ticks=50,  # short cap to keep the test fast
    )
    live_state = stack.runner.run()
    assert live_state.status is SOMatchStatus.ENDED
    assert live_state.tick == 50  # match runs the full cap
    assert live_state.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert live_state.winner_id is None

    # The leaderboard records the draw with is_draw=True; top_n(N) excludes it.
    assert stack.leaderboard.top_n(10) == []  # no decisive entries
    assert stack.leaderboard.draw_count() == 1

    # The draw replays exactly, too (same fold, same ledger discipline).
    replay = ReplayEngine(
        open_sqlite_ledger(ledger_path),
        match_id=live_state.match_id,
        catalog=stack.catalog,
        event_factory=stack.event_factory,
    )
    assert replay.reconstruct_at_tick(live_state.tick) == live_state
