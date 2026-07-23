"""Unit tests for the POLICY_PROMOTED fold, chain resolution, and rehydration."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid5

import pytest

from steel_onslaught.contracts.lineage import (
    ModelSOLineageEvidence,
    ModelSOLineageGenerator,
    ModelSOLineagePerformance,
    ModelSOLineagePromotion,
    ModelSOLineageRecord,
    ParamDict,
    SOPromotionStatus,
    meta_hash,
    spec_hash,
)
from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.envelope import (
    ModelSOEventEnvelope,
    ModelSOEventSubject,
    SOEventType,
    make_event,
)
from steel_onslaught.events.payloads import ModelSOPolicyPromotedPayload
from steel_onslaught.learning.filesystem_artifacts import (
    ModelSOFilesystemLearningArtifactsConfig,
    YamlFilesystemLearningArtifactStore,
)
from steel_onslaught.learning.lineage_store import record_digest
from steel_onslaught.learning.promotion_fold import (
    fold_policy_promotions,
    rehydrate_current_policy,
    resolve_promotion_chain,
)
from steel_onslaught.ledger.protocol import ReplayEventCatalog

_NS = UUID("00000000-0000-0000-0000-00000000abcd")
_SUBJECT = ModelSOEventSubject(mech_id="*", player_id="*")
_ARCHETYPE = "aggressive"


def _hex(seed: str) -> str:
    return (seed * 64)[:64]


def _payload(
    *,
    generation: int,
    spec: str,
    parent: str,
    match_id: str = "match.a",
    digest: str | None = None,
) -> ModelSOPolicyPromotedPayload:
    return ModelSOPolicyPromotedPayload(
        match_id=match_id,
        policy_id=f"policy.{_ARCHETYPE}.{spec[:16]}",
        archetype=_ARCHETYPE,
        generation=generation,
        spec_hash=spec,
        parent_spec_hash=parent,
        source_lineage_digest=digest if digest is not None else _hex("d"),
        evidence_scored_event_id="01HZY3E9ZTAV5J6BQF8KM2WXSC",
    )


def _envelope(
    payload: ModelSOPolicyPromotedPayload, *, match_id: str | None = None
) -> ModelSOEventEnvelope:
    stream_match = match_id if match_id is not None else payload.match_id
    return make_event(
        match_id=stream_match,
        tick=10,
        sequence_in_tick=3,
        event_type=SOEventType.POLICY_PROMOTED,
        producer_node="node.learning.after_match",
        subject=_SUBJECT,
        payload=payload.model_dump(mode="json"),
        correlation_id=uuid5(_NS, f"corr.{stream_match}"),
        event_id="01HZY3E9ZTAV5J6BQF8KM2WXAA",
        message_id=uuid5(_NS, f"msg.{payload.spec_hash}.{stream_match}"),
        emitted_at=datetime(2026, 7, 22, tzinfo=UTC),
    )


@pytest.mark.unit
def test_fold_extracts_validated_promotions_and_ignores_other_events() -> None:
    payload = _payload(generation=1, spec=_hex("a"), parent=_hex("b"))
    tick = make_event(
        match_id="match.a",
        tick=1,
        sequence_in_tick=0,
        event_type=SOEventType.MATCH_TICK,
        producer_node="node.test",
        subject=_SUBJECT,
        payload={},
        correlation_id=uuid5(_NS, "corr.match.a"),
        event_id="01HZY3E9ZTAV5J6BQF8KM2WXAB",
        message_id=uuid5(_NS, "msg.tick"),
        emitted_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    folded = fold_policy_promotions([tick, _envelope(payload)])
    assert folded == (payload,)


@pytest.mark.unit
def test_fold_rejects_payload_that_disagrees_with_its_envelope() -> None:
    payload = _payload(generation=1, spec=_hex("a"), parent=_hex("b"), match_id="match.a")
    with pytest.raises(ValueError, match="disagrees"):
        fold_policy_promotions([_envelope(payload, match_id="match.b")])


@pytest.mark.unit
def test_chain_resolves_in_generation_order_with_verified_links() -> None:
    one = _payload(generation=1, spec=_hex("a"), parent=_hex("0"))
    two = _payload(generation=2, spec=_hex("b"), parent=_hex("a"), match_id="match.b")
    chain = resolve_promotion_chain([two, one], archetype=_ARCHETYPE)
    assert chain == (one, two)


@pytest.mark.unit
def test_chain_fails_closed_on_gap_broken_link_and_wrong_start() -> None:
    one = _payload(generation=1, spec=_hex("a"), parent=_hex("0"))
    with pytest.raises(ValueError, match="expected generation 1"):
        resolve_promotion_chain(
            [_payload(generation=2, spec=_hex("b"), parent=_hex("a"))], archetype=_ARCHETYPE
        )
    with pytest.raises(ValueError, match="expected generation 2"):
        resolve_promotion_chain(
            [one, _payload(generation=3, spec=_hex("c"), parent=_hex("b"))],
            archetype=_ARCHETYPE,
        )
    with pytest.raises(ValueError, match="broken parent link"):
        resolve_promotion_chain(
            [one, _payload(generation=2, spec=_hex("c"), parent=_hex("f"))],
            archetype=_ARCHETYPE,
        )


class _Catalog:
    def __init__(self, streams: dict[str, list[ModelSOEventEnvelope]]) -> None:
        self._streams = streams

    def read_all(self, match_id: str) -> Iterator[ModelSOEventEnvelope]:
        return iter(self._streams[match_id])

    def read_match_ids(self) -> Iterator[str]:
        return iter(sorted(self._streams))


def _promoted_record(parameters: ParamDict, *, parent: ParamDict) -> ModelSOLineageRecord:
    return ModelSOLineageRecord(
        archetype=_ARCHETYPE,
        parameters=parameters,
        spec_hash=spec_hash(_ARCHETYPE, parameters),
        parent_hash=spec_hash(_ARCHETYPE, parent),
        meta_hash=meta_hash(("live:player.blue",)),
        evidence=ModelSOLineageEvidence(search_seeds=(1,), holdout_seeds=(2,)),
        performance=ModelSOLineagePerformance(
            candidate_win_rate=1.0,
            win_rate_delta=0.5,
            overload_rate_delta=0.0,
            draw_rate=0.0,
            p_value=1.0,
            decisive_n=1,
        ),
        generator=ModelSOLineageGenerator(
            generator_id="live.win_damage_differential.v1",
            selection_reason="unit fixture",
        ),
        promotion=ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED),
    )


def _genesis(parameters: ParamDict) -> ModelSOLiveLearningPolicy:
    return ModelSOLiveLearningPolicy(
        policy_id=f"policy.{_ARCHETYPE}.genesis",
        archetype=_ARCHETYPE,
        parameters=parameters,
        spec_hash=spec_hash(_ARCHETYPE, parameters),
        generation=0,
    )


@pytest.mark.unit
def test_rehydrate_returns_genesis_when_no_promotions_exist(tmp_path: Path) -> None:
    genesis = _genesis({"aggression": 1.0})
    policy = rehydrate_current_policy(
        cast(ReplayEventCatalog, _Catalog({})),
        archetype=_ARCHETYPE,
        genesis=genesis,
        lineage_root=tmp_path / "lineage",
    )
    assert policy == genesis


@pytest.mark.unit
def test_rehydrate_reconstructs_the_promoted_policy_from_chain_and_lineage(
    tmp_path: Path,
) -> None:
    genesis = _genesis({"aggression": 1.0})
    record = _promoted_record({"aggression": 1.25}, parent={"aggression": 1.0})
    store = YamlFilesystemLearningArtifactStore(
        ModelSOFilesystemLearningArtifactsConfig(
            evaluation_root=tmp_path / "evaluations",
            lineage_root=tmp_path / "lineage",
            experiment_root=tmp_path / "experiments",
        )
    )
    store.write_lineage(record, recorded_at=datetime(2026, 7, 22, tzinfo=UTC))
    tip = _payload(
        generation=1,
        spec=record.spec_hash,
        parent=genesis.spec_hash,
        digest=record_digest(record),
    )
    policy = rehydrate_current_policy(
        cast(ReplayEventCatalog, _Catalog({"match.a": [_envelope(tip)]})),
        archetype=_ARCHETYPE,
        genesis=genesis,
        lineage_root=tmp_path / "lineage",
    )
    assert policy.generation == 1
    assert policy.spec_hash == record.spec_hash
    assert policy.parameters["aggression"] == 1.25
    assert policy.source_lineage_digest == record_digest(record)
    assert policy.policy_id == tip.policy_id


@pytest.mark.unit
def test_rehydrate_fails_closed_when_chain_root_is_not_the_genesis(tmp_path: Path) -> None:
    tip = _payload(generation=1, spec=_hex("a"), parent=_hex("e"))
    with pytest.raises(ValueError, match="refusing to graft"):
        rehydrate_current_policy(
            cast(ReplayEventCatalog, _Catalog({"match.a": [_envelope(tip)]})),
            archetype=_ARCHETYPE,
            genesis=_genesis({"aggression": 1.0}),
            lineage_root=tmp_path / "lineage",
        )


@pytest.mark.unit
def test_rehydrate_fails_closed_when_lineage_record_is_missing(tmp_path: Path) -> None:
    genesis = _genesis({"aggression": 1.0})
    record = _promoted_record({"aggression": 1.25}, parent={"aggression": 1.0})
    tip = _payload(
        generation=1,
        spec=record.spec_hash,
        parent=genesis.spec_hash,
        digest=record_digest(record),
    )
    with pytest.raises(FileNotFoundError, match="refusing to guess"):
        rehydrate_current_policy(
            cast(ReplayEventCatalog, _Catalog({"match.a": [_envelope(tip)]})),
            archetype=_ARCHETYPE,
            genesis=genesis,
            lineage_root=tmp_path / "lineage",
        )
