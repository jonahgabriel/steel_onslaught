"""Real deterministic duel evaluator over an injected duel capability."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.lineage import ParamDict, spec_hash
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.learning.protocols import ModelSOSeedOutcome, SOSeedWinner
from steel_onslaught.learning.spec_adapter import spec_from_params
from steel_onslaught.match.duel import DuelExecutor

_SIDE_RED = "red"
_SIDE_BLUE = "blue"

_TEMPLATE_ID_FORMAT = "pilot.template.{archetype}"


def aggregate_pair(first: SOSeedWinner, second: SOSeedWinner) -> SOSeedWinner:
    """Pure pair aggregation per Architectural Decision #2: CANDIDATE+CANDIDATE
    -> CANDIDATE, PARENT+PARENT -> PARENT, all 7 other combinations -> DRAW.
    Inputs are already side-normalized (each duel's winner mapped to
    candidate/parent/draw by the caller)."""
    if first is SOSeedWinner.CANDIDATE and second is SOSeedWinner.CANDIDATE:
        return SOSeedWinner.CANDIDATE
    if first is SOSeedWinner.PARENT and second is SOSeedWinner.PARENT:
        return SOSeedWinner.PARENT
    return SOSeedWinner.DRAW


class DuelEvaluator:
    """EvaluatorProtocol implementation that runs real deterministic duels.

    Per seed: two duels with sides swapped, candidate and parent fielding the
    SAME base loadout (chassis, boiler, modules — only pilot parameters differ).
    candidate_overloads / parent_overloads = count of BOILER_OVERLOADED ledger
    events for that side's mech, summed over the seed's two duels.
    """

    def __init__(
        self,
        *,
        archetype: str,
        base_loadout: ModelSOLoadout,
        workdir: Path,  # ALL ledgers/specs/loadouts materialize under here
        max_ticks: int,
        duel_executor: DuelExecutor,
    ) -> None:
        self._archetype = archetype
        self._workdir = workdir
        self._max_ticks = max_ticks
        self._base = base_loadout
        self._duel_executor = duel_executor
        # Per-instance evaluate counter: each call gets its own subdirectory so
        # ledgers from distinct calls never collide and the gate evaluation's
        # ledgers can be retained as replay evidence.
        self._eval_count = 0

    def evaluate(
        self,
        candidate_params: ParamDict,
        parent_params: ParamDict,
        seeds: Sequence[int],
    ) -> list[ModelSOSeedOutcome]:
        """One outcome per seed, in the given seed order (EvaluatorProtocol)."""
        seed_list = list(seeds)
        if len(set(seed_list)) != len(seed_list):
            duplicates = sorted({s for s in seed_list if seed_list.count(s) > 1})
            raise ValueError(f"duplicate seeds in evaluation battery: {duplicates}")

        self._eval_count += 1
        eval_dir = self._workdir / f"eval_{self._eval_count:04d}"
        eval_dir.mkdir(parents=True, exist_ok=True)
        candidate_loadout, parent_loadout = self._materialize(
            eval_dir, candidate_params, parent_params
        )

        outcomes: list[ModelSOSeedOutcome] = []
        for seed in seed_list:
            # Side-swapped pair (Decision #2): candidate fields red, then blue.
            first, cand_first, par_first = self._duel(
                eval_dir,
                seed=seed,
                loadout_red=candidate_loadout,
                loadout_blue=parent_loadout,
                candidate_side=_SIDE_RED,
            )
            second, cand_second, par_second = self._duel(
                eval_dir,
                seed=seed,
                loadout_red=parent_loadout,
                loadout_blue=candidate_loadout,
                candidate_side=_SIDE_BLUE,
            )
            outcomes.append(
                ModelSOSeedOutcome(
                    seed=seed,
                    winner=aggregate_pair(first, second),
                    candidate_overloads=cand_first + cand_second,
                    parent_overloads=par_first + par_second,
                )
            )
        return outcomes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _materialize(
        self, eval_dir: Path, candidate_params: ParamDict, parent_params: ParamDict
    ) -> tuple[ModelSOLoadout, ModelSOLoadout]:
        """Write the two pilot spec YAMLs + two derived loadout YAMLs (pinned).

        The parent spec's ``lineage.parent`` is the archetype's template id
        (path-resolved specs must have a non-null parent — characterization
        (c)); the candidate spec's ``lineage.parent`` is the parent spec's id.
        """
        parent_hash = spec_hash(self._archetype, parent_params)
        candidate_hash = spec_hash(self._archetype, candidate_params)
        parent_spec = spec_from_params(
            archetype=self._archetype,
            params=parent_params,
            spec_id=f"pilot.learn.par_{parent_hash[:12]}",
            parent_id=_TEMPLATE_ID_FORMAT.format(archetype=self._archetype),
            display_name=f"Learn parent {parent_hash[:12]}",
        )
        candidate_spec = spec_from_params(
            archetype=self._archetype,
            params=candidate_params,
            spec_id=f"pilot.learn.cand_{candidate_hash[:12]}",
            parent_id=parent_spec.id,
            display_name=f"Learn candidate {candidate_hash[:12]}",
        )
        candidate_loadout = self._write_pair(eval_dir, candidate_spec, role="cand")
        parent_loadout = self._write_pair(eval_dir, parent_spec, role="par")
        return candidate_loadout, parent_loadout

    def _write_pair(self, eval_dir: Path, spec: ModelSOPilotSpec, *, role: str) -> ModelSOLoadout:
        """Write one spec YAML + its derived loadout YAML; return the loadout."""
        spec_path = eval_dir / f"{spec.id}.yaml"
        spec_path.write_text(
            yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
        hash_fragment = spec.id.rsplit("_", 1)[-1]
        loadout = ModelSOLoadout.model_validate(
            {
                **self._base.model_dump(),
                "id": f"loadout.learn.{role}_{hash_fragment}",
                "pilot_id": spec.id,
                "pilot_spec_path": spec_path.name,  # relative; resolved via eval_dir
            }
        )
        loadout_path = eval_dir / f"{loadout.id}.yaml"
        loadout_path.write_text(
            yaml.safe_dump(loadout.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
        return loadout

    def _duel(
        self,
        eval_dir: Path,
        *,
        seed: int,
        loadout_red: ModelSOLoadout,
        loadout_blue: ModelSOLoadout,
        candidate_side: str,
    ) -> tuple[SOSeedWinner, int, int]:
        """Run one duel; return (side-normalized winner, candidate_overloads,
        parent_overloads) for this duel alone."""
        parent_side = _SIDE_BLUE if candidate_side == _SIDE_RED else _SIDE_RED
        match_id = f"match.learn.seed_{seed}.cand_{candidate_side}"
        ledger_path = eval_dir / f"seed_{seed}_cand_{candidate_side}.sqlite3"
        result = self._duel_executor(
            loadout_a=loadout_red,
            loadout_b=loadout_blue,
            seed=seed,
            max_ticks=self._max_ticks,
            ledger_path=ledger_path,
            match_id=match_id,
            loadout_path_a=eval_dir / f"{loadout_red.id}.yaml",
            loadout_path_b=eval_dir / f"{loadout_blue.id}.yaml",
            side_a=_SIDE_RED,
            side_b=_SIDE_BLUE,
        )
        final = result.final_state
        if final.winner_id is None:
            winner = SOSeedWinner.DRAW
        elif final.winner_id == f"player.{candidate_side}":
            winner = SOSeedWinner.CANDIDATE
        elif final.winner_id == f"player.{parent_side}":
            winner = SOSeedWinner.PARENT
        else:  # pragma: no cover - lifecycle invariant violation
            raise ValueError(f"unrecognized winner_id {final.winner_id!r} in {match_id}")
        candidate_overloads = self._count_overloads(
            result.events, mech_id=f"mech.{candidate_side}.01"
        )
        parent_overloads = self._count_overloads(result.events, mech_id=f"mech.{parent_side}.01")
        return winner, candidate_overloads, parent_overloads

    @staticmethod
    def _count_overloads(events: tuple[ModelSOEventEnvelope, ...], *, mech_id: str) -> int:
        """Count BOILER_OVERLOADED ledger events for one mech in one duel."""
        return sum(
            1
            for envelope in events
            if envelope.event_type is SOEventType.BOILER_OVERLOADED
            and envelope.subject.mech_id == mech_id
        )
