"""Durability tests for the explicit filesystem learning artifact adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOPilotSpec
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _store(tmp_path: Path) -> YamlFilesystemLearningArtifactStore:
    return YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=tmp_path / "evaluations",
            lineage_root=tmp_path / "lineage",
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
