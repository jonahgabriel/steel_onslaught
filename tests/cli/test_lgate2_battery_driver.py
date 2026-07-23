"""Model-selection + empty-content-counter surface of the L-GATE-2 battery driver.

Cross-model design prerequisites B1 (parameterized model selection: overlay +
both seat loadouts CLI-selectable, defaults preserving the #126/#128 qwen35
configuration) and B4 (per-provider empty-content counter — the tripwire for
reasoning-channel providers that return empty ``content`` on an otherwise
"successful" completion).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml  # type: ignore[import-untyped]
from omnibase_core.models.common.model_envelope import ModelEnvelope

from scripts.run_lgate2_adaptation_battery import (
    _BLUE_LOADOUT,
    _OVERLAY,
    _RED_LOADOUT,
    _build_parser,
    _empty_content_counts,
    _lane_overlay,
    _merge_empty_content,
)
from steel_onslaught.contracts.application import ModelSOOpenAICompatibleProviderBinding
from steel_onslaught.contracts.loadout import ModelSOLoadout
from steel_onslaught.contracts.pilot import ModelSOLlmPilotParams
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
)
from steel_onslaught.match.composition import load_pilot_registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_QWEN27_OVERLAY = _REPO_ROOT / "contracts_data/overlays/tactical_split_overdeal_v1_qwen27.yaml"
_QWEN27_RED = _REPO_ROOT / "contracts_data/loadouts/qwen27/berserker_scout.yaml"
_QWEN27_BLUE = _REPO_ROOT / "contracts_data/loadouts/qwen27/sniper_ironclad.yaml"


# ---------------------------------------------------------------------------
# B1 — CLI model selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_args_preserve_the_128_configuration() -> None:
    args = _build_parser().parse_args([])
    assert args.overlay == _OVERLAY
    assert args.red_loadout == _RED_LOADOUT
    assert args.blue_loadout == _BLUE_LOADOUT
    assert _OVERLAY.name == "tactical_split_overdeal_v1_qwen.yaml"


@pytest.mark.unit
def test_cli_selects_overlay_and_loadouts_per_run() -> None:
    args = _build_parser().parse_args(
        [
            "--overlay",
            str(_QWEN27_OVERLAY),
            "--red-loadout",
            str(_QWEN27_RED),
            "--blue-loadout",
            str(_QWEN27_BLUE),
        ]
    )
    assert args.overlay == _QWEN27_OVERLAY
    assert args.red_loadout == _QWEN27_RED
    assert args.blue_loadout == _QWEN27_BLUE


@pytest.mark.unit
def test_lane_overlay_binds_selected_provider_and_repoints_durable_surfaces(
    tmp_path: Path,
) -> None:
    overlay = _lane_overlay(
        tmp_path,
        overlay_path=_QWEN27_OVERLAY,
        max_value=1.0,
        learning_player="player.blue",
        step=0.5,
    )
    # Provider binding is the qwen27 llama.cpp endpoint with the declared
    # reasoning-budget deltas (max_tokens/timeout raised vs the qwen35 overlay).
    (provider,) = overlay.llm.providers
    assert isinstance(provider, ModelSOOpenAICompatibleProviderBinding)
    assert provider.provider_id == "qwen27"
    assert provider.endpoint_url.endswith(":8001/v1/chat/completions")
    assert provider.model == "Qwen3.6-27B-MTP-IQ4_XS.gguf"
    assert provider.max_tokens == 4096
    assert provider.timeout_seconds == 120.0
    # Both seats program via the qwen27 pilot specs.
    assert overlay.contracts.card_catalog is not None
    programmers = overlay.contracts.card_catalog.programmers
    assert {p.pilot_spec_id for p in programmers} == {
        "pilot.llm.qwen27_berserker",
        "pilot.llm.qwen27_sniper",
    }
    # Durable surfaces are repointed into the battery lane.
    assert overlay.event_ledger.path == tmp_path / "events.sqlite3"
    assert overlay.leaderboard.path == tmp_path / "leaderboard.sqlite3"
    assert overlay.learning_artifacts.lineage_root == tmp_path / "lineage"
    # The live-learning binding is the #128 battery configuration.
    assert overlay.live_learning is not None
    assert overlay.live_learning.kind == "win_damage_differential_v1"
    assert overlay.live_learning.parameter == "aggression"
    assert overlay.live_learning.step == 0.5


@pytest.mark.unit
def test_qwen27_registry_resolves_both_battery_loadouts() -> None:
    registry = load_pilot_registry(_REPO_ROOT / "contracts_data/pilots/fire_dense_qwen27")
    for loadout_path, pilot_id, persona in (
        (_QWEN27_RED, "pilot.llm.qwen27_berserker", "berserker"),
        (_QWEN27_BLUE, "pilot.llm.qwen27_sniper", "sniper"),
    ):
        loadout = ModelSOLoadout.model_validate(
            yaml.safe_load(loadout_path.read_text(encoding="utf-8"))
        )
        assert loadout.pilot_id == pilot_id
        spec = registry.resolve(loadout)
        assert spec.id == pilot_id
        params = spec.parameters
        assert isinstance(params, ModelSOLlmPilotParams)
        assert params.persona == persona
        assert params.provider == "qwen27"


@pytest.mark.unit
def test_qwen27_overlay_differs_from_qwen35_only_in_declared_surfaces() -> None:
    """B2 comparability: same arena/deck policy/personas; only the provider
    binding, pilot registry/specs, lane paths, and the declared
    max_tokens/timeout deltas may differ."""
    qwen35 = yaml.safe_load(_OVERLAY.read_text(encoding="utf-8"))
    qwen27 = yaml.safe_load(_QWEN27_OVERLAY.read_text(encoding="utf-8"))
    c35, c27 = qwen35["contracts"], qwen27["contracts"]
    assert c27["arena_id"] == c35["arena_id"] == "foundry_60"
    assert (
        c27["card_catalog"]["deck_policy"] == c35["card_catalog"]["deck_policy"]
    )  # identical over-deal shape
    assert c27["card_catalog"]["card_cadence"] == c35["card_catalog"]["card_cadence"]
    assert qwen27["llm"]["personas_dir"] == qwen35["llm"]["personas_dir"]
    p35, p27 = qwen35["llm"]["providers"][0], qwen27["llm"]["providers"][0]
    assert p27["retry"] == p35["retry"]
    assert p27["secret_ref"] is None and p35["secret_ref"] is None


# ---------------------------------------------------------------------------
# B4 — empty-content counter
# ---------------------------------------------------------------------------


def _resolved_event(
    *, response_length: int, provider_id: str = "qwen27", finish_reason: str = "stop"
) -> ModelSOEventEnvelope:
    match_id = "match.2026-07-23.001"
    return ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEFGX",
        match_id=match_id,
        tick=1,
        sequence_in_tick=0,
        event_type=SOEventType.LLM_COMPLETION_RESOLVED,
        producer_node="node.llm.effect",
        subject=ModelSOEventSubject(mech_id="mech.blue.01", player_id="player.blue"),
        payload={
            "provider_id": provider_id,
            "model": "Qwen3.6-27B-MTP-IQ4_XS.gguf",
            "finish_reason": finish_reason,
            "prompt_tokens": 4000,
            "completion_tokens": 0 if response_length == 0 else 128,
            "response_length": response_length,
            "cost_usd": None,
        },
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=None,
            entity_id=match_id,
            emitted_at=datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC),
        ),
    )


def _non_resolved_event() -> ModelSOEventEnvelope:
    match_id = "match.2026-07-23.001"
    return ModelSOEventEnvelope(
        event_id="01JABCDE0123456789ABCDEFGX",
        match_id=match_id,
        tick=1,
        sequence_in_tick=1,
        event_type=SOEventType.PILOT_DECISION_MADE,
        producer_node="node.pilot.blue.01",
        subject=ModelSOEventSubject(mech_id="mech.blue.01", player_id="player.blue"),
        payload={"action": "vent"},
        envelope=ModelEnvelope(
            message_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=None,
            entity_id=match_id,
            emitted_at=datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC),
        ),
    )


@pytest.mark.unit
def test_empty_content_counts_flags_only_zero_length_resolved_completions() -> None:
    events = (
        _resolved_event(response_length=0, finish_reason="stop"),
        _resolved_event(response_length=0, finish_reason="length"),
        _resolved_event(response_length=0, finish_reason="stop"),
        _resolved_event(response_length=512),
        _resolved_event(response_length=0, provider_id="qwen35"),
        _non_resolved_event(),
    )
    assert _empty_content_counts(events) == {
        "qwen27": {"stop": 2, "length": 1},
        "qwen35": {"stop": 1},
    }


@pytest.mark.unit
def test_empty_content_counts_empty_when_all_completions_have_content() -> None:
    events = (_resolved_event(response_length=64), _non_resolved_event())
    assert _empty_content_counts(events) == {}


@pytest.mark.unit
def test_merge_empty_content_accumulates_across_rows() -> None:
    total: dict[str, dict[str, int]] = {}
    _merge_empty_content(total, {"qwen27": {"stop": 1}})
    _merge_empty_content(total, {"qwen27": {"stop": 2, "length": 1}, "qwen35": {"stop": 1}})
    _merge_empty_content(total, {})
    assert total == {"qwen27": {"stop": 3, "length": 1}, "qwen35": {"stop": 1}}


# ---------------------------------------------------------------------------
# Row/summary shape (guards the raw-JSONL contract the evidence docs read)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_summary_aggregates_empty_content_counter() -> None:
    from scripts.run_lgate2_adaptation_battery import _summarize

    def _row(empty: dict[str, dict[str, int]], **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "policy_provenance": {"policy_id": "policy.x", "generation": 0},
            "winner_player_id": "player.blue",
            "is_draw": False,
            "failed_completions": 0,
            "empty_content_completions": empty,
            "learning_seat": {"keep_rates": {}, "planned_share": {}},
        }
        base.update(overrides)
        return base

    summary = _summarize(
        [
            _row({"qwen27": {"stop": 1}}),
            _row({"qwen27": {"length": 2}}),
            _row({}),
        ],
        learning_player="player.blue",
    )
    assert summary["empty_content_completions"] == {"qwen27": {"stop": 1, "length": 2}}
    assert summary["matches"] == 3
