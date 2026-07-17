"""Durability tests for the explicit filesystem learning artifact adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.llm.experiment import (
    ModelSOArmMetrics,
    ModelSOExperimentRow,
    ModelSOExperimentSummary,
    ModelSOTunerUsage,
)
from tests.fixtures.event_samples import build_sample_envelopes

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _store(tmp_path: Path) -> YamlFilesystemLearningArtifactStore:
    return YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=tmp_path / "evaluations",
            lineage_root=tmp_path / "lineage",
            experiment_root=tmp_path / "experiments",
        )
    )


def _contracts() -> tuple[ModelSOLoadout, ModelSOPilotSpec]:
    loadout = ModelSOLoadout.model_validate(
        yaml.safe_load(
            (_REPO_ROOT / "contracts_data/loadouts/example_aggressive_light.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    spec = ModelSOPilotSpec.model_validate(
        yaml.safe_load(
            (_REPO_ROOT / "contracts_data/pilots/template_aggressive.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    return loadout, spec


def _summary(*, master_seed: int = 11) -> ModelSOExperimentSummary:
    return ModelSOExperimentSummary(
        experiment_seed=7,
        archetype="aggressive",
        provider="stub",
        k_trials=1,
        master_seeds=(master_seed,),
        arms=("baseline",),
        arm_metrics=(
            ModelSOArmMetrics(
                arm="baseline",
                k_trials=1,
                n_promoted=1,
                attempts_to_promotion=(1,),
                mean_attempts_to_promotion=1.0,
                total_cost_usd=0.0,
                cost_per_promotion=0.0,
                first_batch_promotion_rate=1.0,
            ),
        ),
    )


def _row(*, run_id: str = "exp7.baseline.trial0", model_id: str = "stub") -> ModelSOExperimentRow:
    return ModelSOExperimentRow(
        run_id=run_id,
        correlation_id=f"correlation.{run_id}",
        attempt_count=1,
        first_pass_success=True,
        final_success=True,
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        model_id=model_id,
        provider="stub",
        context_factor_subset="baseline",
        context_manifest_hash="a" * 64,
        failure_stage=None,
        endpoint_ref="stub",
        factor_subset_hash="b" * 64,
        prompt_template_version="v1",
        routing_overlay_hash="c" * 64,
        temperature=0.0,
        run_order=0,
    )


def _usage(*, run_id: str = "run.1", correlation_id: str = "correlation.1") -> ModelSOTunerUsage:
    return ModelSOTunerUsage(
        run_id=run_id,
        correlation_id=correlation_id,
        arm="llm_off",
        provider="stub",
        model_id="stub",
        prompt_tokens=2,
        completion_tokens=1,
        cost_usd=0.0,
        recorded_at=datetime(2026, 7, 16, tzinfo=UTC),
    )


@pytest.mark.unit
def test_prepare_evaluation_never_reuses_or_overwrites_existing_workspace(
    tmp_path: Path,
) -> None:
    evaluation_root = tmp_path / "evaluations"
    occupied = evaluation_root / "eval_0001"
    occupied.mkdir(parents=True)
    sentinel = occupied / "seed_7_cand_red.sqlite3"
    sentinel_bytes = b"pre-existing-duel-evidence"
    sentinel.write_bytes(sentinel_bytes)

    workspace = _store(tmp_path).prepare_evaluation(1)

    assert workspace.key == "eval_0001_0002"
    assert (evaluation_root / workspace.key).is_dir()
    assert sentinel.read_bytes() == sentinel_bytes


@pytest.mark.unit
def test_repeated_workspace_reservations_use_deterministic_suffixes_and_preserve_bytes(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    evaluation_root = tmp_path / "evaluations"
    keys: list[str] = []
    sentinels: dict[Path, bytes] = {}

    for marker in range(1, 4):
        workspace = store.prepare_evaluation(8)
        keys.append(workspace.key)
        sentinel = evaluation_root / workspace.key / "sentinel.bin"
        content = f"reservation-{marker}".encode()
        sentinel.write_bytes(content)
        sentinels[sentinel] = content

    assert keys == ["eval_0008", "eval_0008_0002", "eval_0008_0003"]
    assert {path: path.read_bytes() for path in sentinels} == sentinels


@pytest.mark.unit
def test_materialization_accepts_only_byte_identical_existing_artifacts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    loadout, spec = _contracts()
    workspace = store.prepare_evaluation(1)

    first = store.materialize_loadout(workspace, base=loadout, spec=spec, role="cand")
    first_spec_bytes = first.path.with_name(f"{spec.id}.yaml").read_bytes()
    first_loadout_bytes = first.path.read_bytes()

    repeated = store.materialize_loadout(workspace, base=loadout, spec=spec, role="cand")

    assert repeated == first
    assert first.path.with_name(f"{spec.id}.yaml").read_bytes() == first_spec_bytes
    assert first.path.read_bytes() == first_loadout_bytes


@pytest.mark.unit
@pytest.mark.parametrize("conflict", ["spec", "loadout"])
def test_materialization_never_replaces_non_identical_existing_artifact(
    tmp_path: Path,
    conflict: str,
) -> None:
    store = _store(tmp_path)
    loadout, spec = _contracts()
    workspace = store.prepare_evaluation(1)
    workspace_path = tmp_path / "evaluations" / workspace.key
    target = (
        workspace_path / f"{spec.id}.yaml"
        if conflict == "spec"
        else workspace_path / f"loadout.learn.cand_{spec.id.rsplit('_', 1)[-1]}.yaml"
    )
    sentinel_bytes = f"pre-existing-{conflict}".encode()
    target.write_bytes(sentinel_bytes)

    with pytest.raises(FileExistsError, match="refusing to replace non-identical"):
        store.materialize_loadout(workspace, base=loadout, spec=spec, role="cand")

    assert target.read_bytes() == sentinel_bytes


@pytest.mark.unit
def test_content_addressed_artifacts_repeat_identically_and_read_back_deterministically(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    summary = _summary()
    rows = (_row(),)
    usage = _usage()
    event = build_sample_envelopes()[SOEventType.LLM_COMPLETION_REQUESTED]

    written = (
        (store.write_experiment_summary(summary), summary.model_dump(mode="json")),
        (store.write_experiment_rows(rows), [row.model_dump(mode="json") for row in rows]),
        (store.write_tuner_usage(usage, lineage_record=None), usage.model_dump(mode="json")),
        (store.write_llm_event(event), event.model_dump(mode="json")),
    )
    repeated = (
        store.write_experiment_summary(summary),
        store.write_experiment_rows(rows),
        store.write_tuner_usage(usage, lineage_record=None),
        store.write_llm_event(event),
    )

    assert repeated == tuple(path for path, _ in written)
    for path, expected in written:
        assert yaml.safe_load(path.read_text(encoding="utf-8")) == expected


@pytest.mark.unit
def test_distinct_run_and_event_identities_preserve_both_artifacts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    usage_a = store.write_tuner_usage(_usage(run_id="run.a"), lineage_record=None)
    usage_b = store.write_tuner_usage(
        _usage(run_id="run.b", correlation_id="correlation.b"),
        lineage_record=None,
    )
    events = build_sample_envelopes()
    event_a = store.write_llm_event(events[SOEventType.LLM_COMPLETION_REQUESTED])
    event_b = store.write_llm_event(events[SOEventType.LLM_COMPLETION_RESOLVED])

    assert usage_a != usage_b
    assert event_a != event_b
    assert all(path.is_file() for path in (usage_a, usage_b, event_a, event_b))


@pytest.mark.unit
def test_resolved_llm_cost_survives_artifact_materialization_exactly(tmp_path: Path) -> None:
    event = build_sample_envelopes()[SOEventType.LLM_COMPLETION_RESOLVED]
    assert event.payload["cost_usd"] == 0.0

    path = _store(tmp_path).write_llm_event(event)
    persisted = ModelSOEventEnvelope.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )

    assert persisted == event
    assert persisted.payload["cost_usd"] == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["summary", "rows", "usage", "llm_event"])
def test_conflicting_logical_identity_refuses_fork_and_preserves_first_claim(
    tmp_path: Path,
    kind: str,
) -> None:
    store = _store(tmp_path)
    if kind == "summary":
        original = store.write_experiment_summary(_summary(master_seed=11))
        conflicting_write = partial(store.write_experiment_summary, _summary(master_seed=12))
        claim_kind = "summaries"
    elif kind == "rows":
        original = store.write_experiment_rows((_row(model_id="first"),))
        conflicting_write = partial(store.write_experiment_rows, (_row(model_id="second"),))
        claim_kind = "rows"
    elif kind == "usage":
        original = store.write_tuner_usage(_usage(correlation_id="first"), lineage_record=None)
        conflicting_write = partial(
            store.write_tuner_usage,
            _usage(correlation_id="second"),
            lineage_record=None,
        )
        claim_kind = "usage"
    else:
        event = build_sample_envelopes()[SOEventType.LLM_COMPLETION_FAILED]
        original = store.write_llm_event(event)
        conflicting = ModelSOEventEnvelope.model_validate(
            {
                **event.model_dump(mode="json"),
                "payload": {**event.payload, "reason_code": "consumer_error"},
            }
        )
        conflicting_write = partial(store.write_llm_event, conflicting)
        claim_kind = "llm_events"

    original_bytes = original.read_bytes()
    claims = tuple((tmp_path / "experiments" / "claims" / claim_kind).glob("*.sha256"))
    assert len(claims) == 1
    claim_bytes = claims[0].read_bytes()

    with pytest.raises(FileExistsError, match="refusing to replace non-identical"):
        conflicting_write()

    assert original.read_bytes() == original_bytes
    assert claims[0].read_bytes() == claim_bytes
