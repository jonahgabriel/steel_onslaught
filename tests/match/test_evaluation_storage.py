"""Atomic ownership proofs for injected evaluation evidence storage."""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

from steel_onslaught.contracts.application import (
    ModelSOApplicationOverlay,
    ModelSOSQLiteEvaluationStorageBinding,
)
from steel_onslaught.ledger.sqlite_ledger import ModelSOSQLiteLedgerConfig, SQLiteLedger
from steel_onslaught.match import composition
from steel_onslaught.match.composition import (
    build_duel_executor,
    build_duel_executor_with_dependencies,
    build_llm_dependencies,
    load_loadout,
)
from steel_onslaught.match.duel import DuelResult, ModelSOEvaluationStorageKey
from steel_onslaught.match.evaluation_storage import SQLiteEvaluationStorageAllocator
from steel_onslaught.replay.engine import ReplayEngine
from tests.overlay import complete_test_overlay
from tests.runtime import runtime_dependencies

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "contracts_data"
_LOADOUT_A = _CONTRACTS / "loadouts/example_aggressive_light.yaml"
_LOADOUT_B = _CONTRACTS / "loadouts/example_predictive_heavy.yaml"


def _binding(root: Path) -> ModelSOSQLiteEvaluationStorageBinding:
    return ModelSOSQLiteEvaluationStorageBinding(
        kind="sqlite",
        root=root,
        journal_mode="WAL",
        check_same_thread=True,
        transaction_mode="autocommit",
        event_schema="canonical_event_v1",
        leaderboard_schema="leaderboard_v1",
    )


def _overlay(root: Path) -> ModelSOApplicationOverlay:
    return ModelSOApplicationOverlay.model_validate(
        complete_test_overlay(
            {
                "schema_version": "1",
                "bus": {"kind": "in_process"},
                "event_ledger": {
                    "kind": "sqlite",
                    "path": root / "global-events.sqlite3",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "event_schema": "canonical_event_v1",
                },
                "leaderboard": {
                    "kind": "sqlite",
                    "path": root / "global-leaderboard.sqlite3",
                    "journal_mode": "WAL",
                    "check_same_thread": True,
                    "transaction_mode": "autocommit",
                    "storage_schema": "leaderboard_v1",
                },
                "learning_artifacts": {
                    "kind": "filesystem_yaml",
                    "evaluation_root": root / "learning",
                    "lineage_root": root / "lineage",
                },
                "evaluation_storage": _binding(root / "evaluation").model_dump(),
                "contracts": {
                    "catalog_dir": _CONTRACTS,
                    "pilot_registry_dir": _CONTRACTS / "pilots",
                },
                "clock": {"kind": "system_utc"},
                "identity": {"kind": "system"},
            },
            root,
        )
    )


def _claim_in_process(root: str, barrier: Any, output: Any) -> None:
    allocator = SQLiteEvaluationStorageAllocator(_binding(Path(root)))
    barrier.wait()
    claim = allocator.claim(ModelSOEvaluationStorageKey(namespace="parallel", duel="same"))
    output.put(str(claim.path))


@pytest.mark.unit
def test_claim_is_frozen_and_selected_policies_are_preserved(tmp_path: Path) -> None:
    claim = SQLiteEvaluationStorageAllocator(_binding(tmp_path)).claim(
        ModelSOEvaluationStorageKey(namespace="frozen", duel="duel")
    )

    assert claim.path == tmp_path / "frozen/duel.sqlite3"
    assert claim.path.read_bytes() == b""
    assert claim.journal_mode == "WAL"
    assert claim.event_schema == "canonical_event_v1"
    assert claim.leaderboard_schema == "leaderboard_v1"
    with pytest.raises(FrozenInstanceError):
        claim.path = tmp_path / "forged.sqlite3"  # type: ignore[misc]


@pytest.mark.unit
def test_sequential_independent_allocators_use_deterministic_suffix(tmp_path: Path) -> None:
    key = ModelSOEvaluationStorageKey(namespace="balance", duel="same")

    first = SQLiteEvaluationStorageAllocator(_binding(tmp_path)).claim(key)
    second = SQLiteEvaluationStorageAllocator(_binding(tmp_path)).claim(key)

    assert first.path == tmp_path / "balance/same.sqlite3"
    assert second.path == tmp_path / "balance_0002/same.sqlite3"
    assert first.path.read_bytes() == b""
    assert second.path.read_bytes() == b""


@pytest.mark.unit
def test_n_processes_claim_distinct_suffixes_and_preserve_sentinel(tmp_path: Path) -> None:
    sentinel = tmp_path / "parallel/same.sqlite3"
    sentinel.parent.mkdir(parents=True)
    sentinel_bytes = b"prior-evaluation-evidence"
    sentinel.write_bytes(sentinel_bytes)
    process_count = 5
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(process_count)
    output = context.Queue()
    processes = [
        context.Process(target=_claim_in_process, args=(str(tmp_path), barrier, output))
        for _ in range(process_count)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)

    assert [process.exitcode for process in processes] == [0] * process_count
    paths = {Path(output.get(timeout=2)) for _ in processes}
    assert paths == {tmp_path / f"parallel_{suffix:04d}/same.sqlite3" for suffix in range(2, 7)}
    assert all(path.read_bytes() == b"" for path in paths)
    assert sentinel.read_bytes() == sentinel_bytes


@pytest.mark.unit
def test_failed_post_claim_runtime_construction_retains_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = _overlay(tmp_path)
    allocator = SQLiteEvaluationStorageAllocator(overlay.evaluation_storage)
    executor = build_duel_executor_with_dependencies(
        overlay,
        evaluation_storage=allocator,
        llm_dependencies=build_llm_dependencies(overlay),
    )
    attempted_overlays: list[ModelSOApplicationOverlay] = []

    def fail_after_claim(attempted: ModelSOApplicationOverlay, *, llm_dependencies: object) -> None:
        del llm_dependencies
        attempted_overlays.append(attempted)
        raise RuntimeError("injected construction failure")

    monkeypatch.setattr(composition, "build_runtime_dependencies", fail_after_claim)
    with pytest.raises(RuntimeError, match="injected construction failure"):
        executor(
            loadout_a=load_loadout(_LOADOUT_A),
            loadout_b=load_loadout(_LOADOUT_B),
            seed=1,
            max_ticks=1,
            storage=ModelSOEvaluationStorageKey(namespace="failed", duel="same"),
            match_id="match.failed.claim",
            loadout_path_a=_LOADOUT_A,
            loadout_path_b=_LOADOUT_B,
            side_a="a",
            side_b="b",
        )

    retained = tmp_path / "evaluation/failed/same.sqlite3"
    assert retained.exists()
    assert retained.read_bytes() == b""
    assert len(attempted_overlays) == 1
    assert attempted_overlays[0].event_ledger.path == retained
    assert attempted_overlays[0].leaderboard.path == retained
    next_claim = SQLiteEvaluationStorageAllocator(overlay.evaluation_storage).claim(
        ModelSOEvaluationStorageKey(namespace="failed", duel="same")
    )
    assert next_claim.path == tmp_path / "evaluation/failed_0002/same.sqlite3"


@pytest.mark.integration
def test_barrier_synchronized_executors_produce_replayable_isolated_databases(
    tmp_path: Path,
) -> None:
    overlay = _overlay(tmp_path)
    loadout_a = load_loadout(_LOADOUT_A)
    loadout_b = load_loadout(_LOADOUT_B)
    executor_count = 4
    executors = [build_duel_executor(overlay) for _ in range(executor_count)]
    barrier = Barrier(executor_count)
    storage = ModelSOEvaluationStorageKey(namespace="live", duel="same")

    def run(index: int) -> tuple[str, DuelResult]:
        match_id = f"match.parallel.{index}"
        barrier.wait()
        result = executors[index](
            loadout_a=loadout_a,
            loadout_b=loadout_b,
            seed=index + 1,
            max_ticks=1,
            storage=storage,
            match_id=match_id,
            loadout_path_a=_LOADOUT_A,
            loadout_path_b=_LOADOUT_B,
            side_a="a",
            side_b="b",
        )
        return match_id, result

    with ThreadPoolExecutor(max_workers=executor_count) as pool:
        completed = dict(pool.map(run, range(executor_count)))

    evaluation_root = overlay.evaluation_storage.root
    databases = sorted(evaluation_root.glob("live*/same.sqlite3"))
    assert len(databases) == executor_count
    assert {path.parent.name for path in databases} == {
        "live",
        "live_0002",
        "live_0003",
        "live_0004",
    }
    assert not overlay.event_ledger.path.exists()
    assert not overlay.leaderboard.path.exists()

    runtime = runtime_dependencies()
    replayed_matches: set[str] = set()
    for database in databases:
        ledger = SQLiteLedger(
            ModelSOSQLiteLedgerConfig(
                path=database,
                journal_mode="WAL",
                check_same_thread=True,
                transaction_mode="autocommit",
                event_schema="canonical_event_v1",
            )
        )
        matching = [match_id for match_id in completed if ledger.contains_match(match_id)]
        assert len(matching) == 1
        match_id = matching[0]
        replayed_matches.add(match_id)
        replayed = ReplayEngine(
            ledger,
            match_id,
            catalog=runtime.catalog,
            event_factory=runtime.event_factory,
        ).reconstruct_at_tick(1)
        assert replayed == completed[match_id].final_state

    assert replayed_matches == set(completed)


@pytest.mark.unit
def test_root_rejects_corrupted_unsupported_evaluation_binding(tmp_path: Path) -> None:
    overlay = _overlay(tmp_path)
    corrupted_binding = overlay.evaluation_storage.model_copy(update={"kind": "unsupported"})
    corrupted_overlay = overlay.model_copy(update={"evaluation_storage": corrupted_binding})

    with pytest.raises(ValueError, match="unsupported evaluation storage adapter kind"):
        composition.build_evaluation_storage_allocator(corrupted_overlay)
