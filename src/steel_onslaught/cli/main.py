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

from pathlib import Path

import click

from steel_onslaught.cli.adaptation import adaptation_command
from steel_onslaught.cli.application import CliApplicationFactory
from steel_onslaught.cli.balance import balance_command
from steel_onslaught.cli.experiment import learn_experiment_command
from steel_onslaught.cli.learn import learn_command
from steel_onslaught.cli.play import play_command
from steel_onslaught.cli.serve import serve_command
from steel_onslaught.match.composition import load_application_overlay
from steel_onslaught.projections.cli.renderer import CliTextRenderer

_LOADOUT_PATH = click.Path(exists=True, dir_okay=False, path_type=Path)
_OVERLAY_PATH = click.Path(exists=True, dir_okay=False, path_type=Path)


@click.group()
def main() -> None:
    """Steel Onslaught — steampunk tactical mech duels."""


main.add_command(serve_command)
main.add_command(balance_command)
main.add_command(learn_command)
main.add_command(learn_experiment_command)
main.add_command(adaptation_command)
main.add_command(play_command)


@main.command(name="run")
@click.option("--overlay", "overlay_path", type=_OVERLAY_PATH, required=True)
@click.option("--loadout-a", "loadout_a_path", type=_LOADOUT_PATH, required=True)
@click.option("--loadout-b", "loadout_b_path", type=_LOADOUT_PATH, required=True)
@click.option("--seed", type=click.IntRange(min=0), required=True)
@click.option(
    "--max-ticks",
    type=click.IntRange(min=1),
    default=None,
    help="Optional debug/test cap. Omit for normal winner-only matches.",
)
@click.option("--no-color", is_flag=True, default=False, help="Disable ANSI colors.")
def run_command(
    overlay_path: Path,
    loadout_a_path: Path,
    loadout_b_path: Path,
    seed: int,
    max_ticks: int | None,
    no_color: bool,
) -> None:
    """Run a live match between two loadouts."""
    overlay = load_application_overlay(overlay_path)
    stack = CliApplicationFactory.packaged().match(
        overlay=overlay,
        red_loadout_path=loadout_a_path,
        blue_loadout_path=loadout_b_path,
        seed=seed,
        max_ticks=max_ticks,
    )
    renderer = CliTextRenderer(out=click.get_text_stream("stdout"), color=not no_color)
    try:
        stack.runner.run()
        # Render the durable canonical order. Re-entrant in-process dispatch can
        # deliver derived events to a live observer before the outer event whose
        # lower sequence number is already in the ledger.
        for event in stack.ledger.read_all(stack.match_id):
            renderer.handle(event)
        click.echo(f"match_id: {stack.match_id}", err=True)
    finally:
        stack.close()


@main.command(name="replay")
@click.option("--overlay", "overlay_path", type=_OVERLAY_PATH, required=True)
@click.option("--match", "match_id", required=True)
@click.option("--from", "from_tick", type=click.IntRange(min=0), default=None)
@click.option("--to", "to_tick", type=click.IntRange(min=0), default=None)
@click.option("--no-color", is_flag=True, default=False, help="Disable ANSI colors.")
def replay_command(
    overlay_path: Path,
    match_id: str,
    from_tick: int | None,
    to_tick: int | None,
    no_color: bool,
) -> None:
    """Re-emit a recorded match's events through a fresh bus + renderer."""
    overlay = load_application_overlay(overlay_path)
    dependencies = CliApplicationFactory.packaged().runtime(overlay)
    try:
        renderer = CliTextRenderer(out=click.get_text_stream("stdout"), color=not no_color)
        renderer.attach(dependencies.bus)

        published = 0
        for event in dependencies.ledger.read_all(match_id):
            if from_tick is not None and event.tick < from_tick:
                continue
            if to_tick is not None and event.tick > to_tick:
                continue
            dependencies.bus.publish(event)
            published += 1

        if published == 0:
            raise click.ClickException(
                f"no events found for match {match_id!r} in {overlay.event_ledger.path}"
                + (
                    f" within tick window [{from_tick}, {to_tick}]"
                    if from_tick is not None or to_tick is not None
                    else ""
                )
            )
    finally:
        dependencies.close()


@main.command(name="leaderboard")
@click.option("--overlay", "overlay_path", type=_OVERLAY_PATH, required=True)
@click.option("--top", "top_n", type=click.IntRange(min=1), default=10, show_default=True)
def leaderboard_command(overlay_path: Path, top_n: int) -> None:
    """Show the top-N leaderboard entries (draws excluded)."""
    overlay = load_application_overlay(overlay_path)
    dependencies = CliApplicationFactory.packaged().runtime(overlay)
    try:
        rows = dependencies.leaderboard.top_n(top_n)
    finally:
        dependencies.close()

    if not rows:
        click.echo("leaderboard is empty")
        return

    click.echo(f"{'#':>3}  {'player':<20} {'score':>8}  {'loadout':<36} {'ticks':>5}  match")
    for rank, entry in enumerate(rows, start=1):
        click.echo(
            f"{rank:>3}  {entry.winner_player_id:<20} {entry.winner_score:>8}  "
            f"{entry.winner_loadout_id:<36} {entry.duration_ticks:>5}  {entry.match_id}"
        )
