"""`so balance` — deterministic round-robin win matrix (tunable-pilots Task 6).

Enumerates every shipped non-proof loadout under ``contracts_data/loadouts/``
(or ``--loadouts-dir``), re-pilots each with each of the 3 canonical template
pilot specs (``pilot.template.{aggressive,defensive,predictive}``), runs every
unordered pairing round-robin over seeds ``1..N``, and emits a win-matrix
table plus the overall draw rate.

Determinism: each match outcome is a pure function of
``(seed, loadouts, max_ticks, geometry)`` (MatchRunner contract), the config
ordering is a lexicographic sort, and the CSV carries no ULIDs or timestamps —
so two runs with the same arguments produce byte-identical CSV output.

The command never writes to any match ledger directory implicitly: matches
run against a ledger inside a ``TemporaryDirectory`` that is deleted when the
sweep finishes. The only persistent artifact is the explicitly requested
``--csv`` file.
"""

from __future__ import annotations

import itertools
import tempfile
from pathlib import Path

import click

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot_registry import PilotSpecRegistry
from steel_onslaught.match.duel import run_duel
from steel_onslaught.match.fold import MatchContractCatalog
from steel_onslaught.match.runner import load_loadout
from steel_onslaught.projections.balance.matrix import (
    ModelSOBalanceMatrix,
    ModelSOBalancePairing,
)

DEFAULT_LOADOUTS_DIR = Path(__file__).parent.parent.parent.parent / "contracts_data" / "loadouts"

# The three canonical template pilot specs every loadout is re-piloted with.
_TEMPLATE_PILOT_IDS: tuple[str, ...] = (
    "pilot.template.aggressive",
    "pilot.template.defensive",
    "pilot.template.predictive",
)

_SIDE_A = "a"
_SIDE_B = "b"


def _enumerate_configs(loadouts_dir: Path) -> list[tuple[str, ModelSOLoadout]]:
    """Every (config_id, re-piloted loadout): non-proof loadouts x template pilots.

    Proof-of-Life fixtures (``proof_*.yaml``) are pinned to specific duels and
    excluded from the balance sweep. Re-piloting re-validates through the full
    loadout model and clears any player-supplied ``pilot_spec_path`` so the
    template spec resolves via the registry (resolution step 2).
    """
    configs: list[tuple[str, ModelSOLoadout]] = []
    for path in sorted(loadouts_dir.glob("*.yaml")):
        if path.name.startswith("proof_"):
            continue
        base = load_loadout(path)
        for pilot_id in _TEMPLATE_PILOT_IDS:
            repiloted = ModelSOLoadout.model_validate(
                {**base.model_dump(), "pilot_id": pilot_id, "pilot_spec_path": None}
            )
            configs.append((f"{base.id}+{pilot_id}", repiloted))
    configs.sort(key=lambda item: item[0])
    return configs


@click.command(name="balance")
@click.option(
    "--seeds",
    "seed_count",
    type=click.IntRange(min=1),
    required=True,
    help="Sweep seeds 1..N for every pairing (deterministic).",
)
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Also write the matrix as CSV to this path.",
)
@click.option(
    "--loadouts-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Loadout contract directory (default: shipped contracts_data/loadouts/).",
)
@click.option("--max-ticks", type=click.IntRange(min=1), default=200, show_default=True)
def balance_command(
    seed_count: int,
    csv_path: Path | None,
    loadouts_dir: Path | None,
    max_ticks: int,
) -> None:
    """Round-robin win matrix over template loadout x template pilot pairings."""
    data_dir = loadouts_dir if loadouts_dir is not None else DEFAULT_LOADOUTS_DIR
    configs = _enumerate_configs(data_dir)
    if len(configs) < 2:
        raise click.ClickException(
            f"no non-proof loadouts (need at least one, found {len(configs) // 3}) under {data_dir}"
        )

    catalog = MatchContractCatalog.load()
    registry = PilotSpecRegistry.load()

    pairings: list[ModelSOBalancePairing] = []
    with tempfile.TemporaryDirectory(prefix="so-balance-") as tmp_dir:
        ledger_path = Path(tmp_dir) / "balance_ledger.sqlite3"
        for (config_a, loadout_a), (config_b, loadout_b) in itertools.combinations(configs, 2):
            wins_a = wins_b = draws = 0
            for seed in range(1, seed_count + 1):
                final = run_duel(
                    loadout_a=loadout_a,
                    loadout_b=loadout_b,
                    seed=seed,
                    max_ticks=max_ticks,
                    catalog=catalog,
                    registry=registry,
                    ledger_path=ledger_path,
                    side_a=_SIDE_A,
                    side_b=_SIDE_B,
                )
                winner_id = final.winner_id
                if winner_id is None:
                    draws += 1
                elif winner_id == f"player.{_SIDE_A}":
                    wins_a += 1
                elif winner_id == f"player.{_SIDE_B}":
                    wins_b += 1
                else:  # pragma: no cover - lifecycle invariant violation
                    raise click.ClickException(
                        f"unrecognized winner_id {winner_id!r} for {config_a} vs {config_b}"
                    )
            pairings.append(
                ModelSOBalancePairing(
                    config_a=config_a,
                    config_b=config_b,
                    wins_a=wins_a,
                    wins_b=wins_b,
                    draws=draws,
                )
            )

    matrix = ModelSOBalanceMatrix(seeds=seed_count, pairings=tuple(pairings))

    width = max(len(config_id) for config_id, _ in configs)
    click.echo(f"{'config_a':<{width}}  {'config_b':<{width}}  {'a':>3} {'b':>3} {'draw':>4}")
    for pairing in matrix.pairings:
        click.echo(
            f"{pairing.config_a:<{width}}  {pairing.config_b:<{width}}  "
            f"{pairing.wins_a:>3} {pairing.wins_b:>3} {pairing.draws:>4}"
        )
    click.echo(
        f"overall draw rate: {matrix.draw_rate:.4f} "
        f"({matrix.total_draws}/{matrix.total_matches} matches)"
    )

    if csv_path is not None:
        csv_path.write_text(matrix.to_csv(), encoding="utf-8")
        click.echo(f"csv: {csv_path}", err=True)
