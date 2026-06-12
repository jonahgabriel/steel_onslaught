"""`so` command line — Task 28.

Commands:
  - ``so run``         drive a live match through the minimal runner stack
  - ``so replay``      re-emit ledger events through a fresh bus + renderer
  - ``so leaderboard`` query the leaderboard projection (materialised by
    the Task 30 handler into the same SQLite file as the event ledger)

All match output is rendered by ``CliTextRenderer`` on stdout; bookkeeping
(`match_id`) goes to stderr so that same-seed runs stay byte-identical on
stdout.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import click
import ulid

from steel_onslaught.bus.in_process import InProcessEventBus
from steel_onslaught.cli.balance import balance_command
from steel_onslaught.cli.learn import learn_command
from steel_onslaught.cli.serve import serve_command
from steel_onslaught.ledger.sqlite_ledger import SQLiteLedger
from steel_onslaught.match.runner import MatchRunner, load_loadout
from steel_onslaught.projections.cli.renderer import CliTextRenderer

_LOADOUT_PATH = click.Path(exists=True, dir_okay=False, path_type=Path)
_LEDGER_PATH_EXISTING = click.Path(exists=True, dir_okay=False, path_type=Path)

_LEADERBOARD_TOP_SQL = """
SELECT match_id, winner_player_id, winner_loadout_id, winner_score, duration_ticks
  FROM leaderboard_entries
 WHERE is_draw = 0
 ORDER BY winner_score DESC, match_id ASC
 LIMIT ?
"""


@click.group()
def main() -> None:
    """Steel Onslaught — steampunk tactical mech duels."""


main.add_command(serve_command)
main.add_command(balance_command)
main.add_command(learn_command)


@main.command(name="run")
@click.option("--loadout-a", "loadout_a_path", type=_LOADOUT_PATH, required=True)
@click.option("--loadout-b", "loadout_b_path", type=_LOADOUT_PATH, required=True)
@click.option("--seed", type=click.IntRange(min=0), required=True)
@click.option(
    "--ledger-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Append every event to this SQLite ledger (created if missing).",
)
@click.option("--max-ticks", type=click.IntRange(min=1), default=200, show_default=True)
@click.option("--no-color", is_flag=True, default=False, help="Disable ANSI colors.")
def run_command(
    loadout_a_path: Path,
    loadout_b_path: Path,
    seed: int,
    ledger_path: Path | None,
    max_ticks: int,
    no_color: bool,
) -> None:
    """Run a live match between two loadouts."""
    bus = InProcessEventBus()
    renderer = CliTextRenderer(out=click.get_text_stream("stdout"), color=not no_color)
    renderer.attach(bus)
    if ledger_path is not None:
        ledger = SQLiteLedger(ledger_path)
        bus.subscribe(ledger.append)

    match_id = f"match.{ulid.new().str}"
    runner = MatchRunner(
        match_id=match_id,
        seed=seed,
        loadout_a=load_loadout(loadout_a_path),
        loadout_b=load_loadout(loadout_b_path),
        bus=bus,
        max_ticks=max_ticks,
    )
    runner.run()
    click.echo(f"match_id: {match_id}", err=True)


@main.command(name="replay")
@click.option("--ledger", "ledger_path", type=_LEDGER_PATH_EXISTING, required=True)
@click.option("--match", "match_id", required=True)
@click.option("--from", "from_tick", type=click.IntRange(min=0), default=None)
@click.option("--to", "to_tick", type=click.IntRange(min=0), default=None)
@click.option("--no-color", is_flag=True, default=False, help="Disable ANSI colors.")
def replay_command(
    ledger_path: Path,
    match_id: str,
    from_tick: int | None,
    to_tick: int | None,
    no_color: bool,
) -> None:
    """Re-emit a recorded match's events through a fresh bus + renderer."""
    ledger = SQLiteLedger(ledger_path)
    bus = InProcessEventBus()
    renderer = CliTextRenderer(out=click.get_text_stream("stdout"), color=not no_color)
    renderer.attach(bus)

    published = 0
    for event in ledger.read_all(match_id):
        if from_tick is not None and event.tick < from_tick:
            continue
        if to_tick is not None and event.tick > to_tick:
            continue
        bus.publish(event)
        published += 1

    if published == 0:
        raise click.ClickException(
            f"no events found for match {match_id!r} in {ledger_path}"
            + (
                f" within tick window [{from_tick}, {to_tick}]"
                if from_tick is not None or to_tick is not None
                else ""
            )
        )


@main.command(name="leaderboard")
@click.option("--ledger", "ledger_path", type=_LEDGER_PATH_EXISTING, required=True)
@click.option("--top", "top_n", type=click.IntRange(min=1), default=10, show_default=True)
def leaderboard_command(ledger_path: Path, top_n: int) -> None:
    """Show the top-N leaderboard entries (draws excluded)."""
    conn = sqlite3.connect(ledger_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='leaderboard_entries'"
        ).fetchone()
        if table is None:
            raise click.ClickException(
                "no leaderboard data: leaderboard_entries table not found "
                "(score a match first — Task 30 handler materialises it)"
            )
        rows = conn.execute(_LEADERBOARD_TOP_SQL, (top_n,)).fetchall()
    finally:
        conn.close()

    if not rows:
        click.echo("leaderboard is empty")
        return

    click.echo(f"{'#':>3}  {'player':<20} {'score':>8}  {'loadout':<36} {'ticks':>5}  match")
    for rank, (match_id, player, loadout, score, ticks) in enumerate(rows, start=1):
        click.echo(f"{rank:>3}  {player:<20} {score:>8}  {loadout:<36} {ticks:>5}  {match_id}")
