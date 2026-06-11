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
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from steel_onslaught.cli.main import main as cli_main
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.runner import run_match
from steel_onslaught.match.state import SOMatchEndReason, SOMatchStatus
from steel_onslaught.projections.leaderboard.handler import LeaderboardProjection
from steel_onslaught.replay.engine import ReplayEngine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOADOUTS = _REPO_ROOT / "contracts_data" / "loadouts"

# Canonical decisive-victory seed (plan Task 34; verified post-wiring).
DECISIVE_SEED = 12345
# Draw seed — the passive loadouts draw structurally, independent of seed.
DRAW_SEED = 99999

_WS_PORT = 8765
_VITE_PORT = 5173


def capture_cli_replay(ledger_path: Path, match_id: str) -> str:
    """Run ``so replay`` against *ledger_path* and return its stdout."""
    result = CliRunner().invoke(
        cli_main,
        ["replay", "--ledger", str(ledger_path), "--match", match_id, "--no-color"],
    )
    assert result.exit_code == 0, f"so replay failed: {result.output}"
    return result.output


def _wait_for_port(port: int, *, timeout: float = 60.0) -> None:
    # "localhost" so both IPv4 (websockets, 127.0.0.1) and IPv6 (Vite, ::1)
    # listeners are detected — create_connection walks every addrinfo entry.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError):
            with socket.create_connection(("localhost", port), timeout=1.0):
                return
        time.sleep(0.2)
    raise TimeoutError(f"port {port} did not start listening within {timeout}s")


@contextlib.contextmanager
def _subprocess_server(args: list[str], *, cwd: Path, port: int) -> Iterator[None]:
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        yield
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


@pytest.mark.integration
@pytest.mark.slow
def test_proof_of_life_decisive_victory(tmp_path: Path) -> None:
    # 1) Run match live with the canonical decisive-victory seed.
    ledger_path = tmp_path / "match.sqlite"
    leaderboard_path = tmp_path / "leaderboard.sqlite"
    live_state = run_match(
        red_loadout=_LOADOUTS / "proof_red_predictive_ironclad.yaml",
        blue_loadout=_LOADOUTS / "proof_blue_aggressive_hunter.yaml",
        seed=DECISIVE_SEED,
        max_ticks=200,
        ledger_path=ledger_path,
        leaderboard_path=leaderboard_path,
    )
    assert live_state.status is SOMatchStatus.ENDED
    assert live_state.tick <= 200
    assert live_state.end_reason is SOMatchEndReason.LAST_MECH_STANDING
    assert live_state.winner_id in {"player.red", "player.blue"}

    # 2) Replay reconstructs canonical state exactly (R9 data flow proof).
    replay = ReplayEngine(SQLiteLedger(ledger_path), match_id=live_state.match_id)
    reconstructed = replay.reconstruct_at_tick(live_state.tick)
    assert reconstructed == live_state, "replay must reproduce canonical state exactly"

    # 3) Leaderboard updated correctly (winning entry, not a draw).
    lb = LeaderboardProjection(leaderboard_path)
    top = lb.top_n(1)
    assert len(top) == 1
    assert top[0].match_id == live_state.match_id
    assert top[0].winner_player_id == live_state.winner_id
    assert top[0].winner_score > top[0].loser_score
    assert top[0].is_draw is False

    # 4) CLI projection produces byte-identical output across runs.
    cli_out_1 = capture_cli_replay(ledger_path, live_state.match_id)
    cli_out_2 = capture_cli_replay(ledger_path, live_state.match_id)
    assert cli_out_1 == cli_out_2, "CLI replay must be byte-identical across runs"
    assert f"VICTORY: {live_state.winner_id}" in cli_out_1

    # 5) Web UI rendered output (Playwright — projection proof, NOT byte-identity).
    from playwright.sync_api import sync_playwright

    serve_cmd = [
        sys.executable,
        "-c",
        "from steel_onslaught.cli import main; main()",
        "serve",
        "--ledger",
        str(ledger_path),
        "--match",
        live_state.match_id,
        "--port",
        str(_WS_PORT),
    ]
    vite_cmd = ["npm", "run", "dev"]
    with (
        _subprocess_server(serve_cmd, cwd=_REPO_ROOT, port=_WS_PORT),
        _subprocess_server(vite_cmd, cwd=_REPO_ROOT / "frontend", port=_VITE_PORT),
    ):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://localhost:{_VITE_PORT}/")  # dev server, started above
            page.wait_for_selector(
                f'[data-testid="victory-banner"][data-winner="{live_state.winner_id}"]',
                timeout=10_000,
            )
            # R10: assert the rendered banner names the correct winner.
            banner_text = page.locator("[data-testid=victory-banner]").inner_text()
            assert live_state.winner_id in banner_text
            browser.close()


@pytest.mark.integration
@pytest.mark.slow
def test_proof_of_life_draw_max_ticks(tmp_path: Path) -> None:
    """Two defensive pilots that never engage → match terminates at max_ticks."""
    ledger_path = tmp_path / "draw.sqlite"
    leaderboard_path = tmp_path / "draw_leaderboard.sqlite"
    live_state = run_match(
        red_loadout=_LOADOUTS / "proof_red_defensive_passive.yaml",
        blue_loadout=_LOADOUTS / "proof_blue_defensive_passive.yaml",
        seed=DRAW_SEED,
        max_ticks=50,  # short cap to keep the test fast
        ledger_path=ledger_path,
        leaderboard_path=leaderboard_path,
    )
    assert live_state.status is SOMatchStatus.ENDED
    assert live_state.tick == 50  # match runs the full cap
    assert live_state.end_reason is SOMatchEndReason.DRAW_MAX_TICKS
    assert live_state.winner_id is None

    # The leaderboard records the draw with is_draw=True; top_n(N) excludes it.
    lb = LeaderboardProjection(leaderboard_path)
    assert lb.top_n(10) == []  # no decisive entries
    assert lb.draw_count() == 1

    # The draw replays exactly, too (same fold, same ledger discipline).
    replay = ReplayEngine(SQLiteLedger(ledger_path), match_id=live_state.match_id)
    assert replay.reconstruct_at_tick(live_state.tick) == live_state
