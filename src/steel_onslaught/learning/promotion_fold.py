"""Fold POLICY_PROMOTED events into replayable promotion-chain state.

The event stream is the source of truth for promotion: an in-memory policy or
a lineage YAML on disk is a *projection* of this chain, never the other way
around.  Folding the same events always reconstructs the same chain, and the
chain fails closed on any break — a missing generation, a broken parent link,
a payload that disagrees with its envelope — instead of guessing.

Cross-match ordering authority is ``generation`` + the ``parent_spec_hash``
chain (never wall clock): promotions from different match streams are merged
by chain position, exactly as the event payload documents.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from steel_onslaught.contracts.live_learning import ModelSOLiveLearningPolicy
from steel_onslaught.events.envelope import ModelSOEventEnvelope, SOEventType
from steel_onslaught.events.payloads import ModelSOPolicyPromotedPayload
from steel_onslaught.learning.lineage_store import (
    ModelSOPersistedLineageRecord,
    record_digest,
)
from steel_onslaught.learning.live import _policy_from_record
from steel_onslaught.ledger.protocol import ReplayEventCatalog


def fold_policy_promotions(
    events: Iterable[ModelSOEventEnvelope],
) -> tuple[ModelSOPolicyPromotedPayload, ...]:
    """Extract every validated promotion fact from a canonical event stream.

    Each payload is validated through the payload authority and cross-checked
    against its envelope; any disagreement raises rather than folding a lie.
    """

    payloads: list[ModelSOPolicyPromotedPayload] = []
    for event in events:
        if event.event_type is not SOEventType.POLICY_PROMOTED:
            continue
        payload = ModelSOPolicyPromotedPayload.model_validate(event.payload)
        if payload.match_id != event.match_id:
            raise ValueError(
                f"POLICY_PROMOTED payload match_id {payload.match_id!r} disagrees "
                f"with its envelope match_id {event.match_id!r}"
            )
        payloads.append(payload)
    return tuple(payloads)


def resolve_promotion_chain(
    payloads: Iterable[ModelSOPolicyPromotedPayload],
    *,
    archetype: str,
) -> tuple[ModelSOPolicyPromotedPayload, ...]:
    """Order one archetype's promotions into a verified genesis-rooted chain.

    Fails closed on duplicate generations, a chain that does not start at
    generation 1, a generation gap, or a broken ``parent_spec_hash`` link.
    """

    selected = sorted(
        (payload for payload in payloads if payload.archetype == archetype),
        key=lambda payload: payload.generation,
    )
    for index, payload in enumerate(selected):
        expected_generation = index + 1
        if payload.generation != expected_generation:
            raise ValueError(
                f"promotion chain for {archetype!r} is broken at generation "
                f"{payload.generation}: expected generation {expected_generation}"
            )
        if index > 0 and payload.parent_spec_hash != selected[index - 1].spec_hash:
            raise ValueError(
                f"promotion chain for {archetype!r} has a broken parent link at "
                f"generation {payload.generation}: parent_spec_hash "
                f"{payload.parent_spec_hash!r} != prior spec_hash "
                f"{selected[index - 1].spec_hash!r}"
            )
    return tuple(selected)


def _load_promoted_lineage_record(
    lineage_root: Path, tip: ModelSOPolicyPromotedPayload
) -> ModelSOPersistedLineageRecord:
    """Resolve the chain tip's digests to the durable lineage record."""

    path = lineage_root / tip.archetype / tip.spec_hash / f"{tip.source_lineage_digest}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"promotion chain tip cites lineage record {tip.source_lineage_digest!r} "
            f"but {path} does not exist — the event chain and the lineage store "
            "disagree; refusing to guess a policy"
        )
    persisted = ModelSOPersistedLineageRecord.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    actual_digest = record_digest(persisted.record)
    if actual_digest != tip.source_lineage_digest:
        raise ValueError(
            f"lineage record at {path} hashes to {actual_digest!r}, not the "
            f"event-cited {tip.source_lineage_digest!r}"
        )
    if persisted.record.spec_hash != tip.spec_hash:
        raise ValueError(
            f"lineage record spec_hash {persisted.record.spec_hash!r} disagrees "
            f"with the promotion event spec_hash {tip.spec_hash!r}"
        )
    if persisted.record.parent_hash != tip.parent_spec_hash:
        raise ValueError(
            f"lineage record parent_hash {persisted.record.parent_hash!r} disagrees "
            f"with the promotion event parent_spec_hash {tip.parent_spec_hash!r}"
        )
    return persisted


def rehydrate_current_policy(
    catalog: ReplayEventCatalog,
    *,
    archetype: str,
    genesis: ModelSOLiveLearningPolicy,
    lineage_root: Path,
) -> ModelSOLiveLearningPolicy:
    """Reconstruct the current policy from the durable promotion chain.

    Folds every recorded match stream, verifies the archetype's chain from
    genesis, and resolves the tip's digests to the persisted lineage record
    (parameter truth).  An empty chain yields the genesis policy; any break —
    including a chain whose root does not descend from *genesis* — raises.
    """

    if genesis.archetype != archetype:
        raise ValueError(
            f"genesis policy archetype {genesis.archetype!r} does not match "
            f"the learning archetype {archetype!r}"
        )
    if genesis.generation != 0:
        raise ValueError("genesis policy must be generation 0")

    promotions: list[ModelSOPolicyPromotedPayload] = []
    for match_id in catalog.read_match_ids():
        promotions.extend(fold_policy_promotions(catalog.read_all(match_id)))
    chain = resolve_promotion_chain(promotions, archetype=archetype)
    if not chain:
        return genesis
    if chain[0].parent_spec_hash != genesis.spec_hash:
        raise ValueError(
            f"promotion chain for {archetype!r} descends from parent "
            f"{chain[0].parent_spec_hash!r}, not the configured genesis "
            f"{genesis.spec_hash!r} — genesis parameters changed after "
            "promotions were recorded; refusing to graft the chain"
        )
    tip = chain[-1]
    persisted = _load_promoted_lineage_record(lineage_root, tip)
    policy = _policy_from_record(persisted.record, generation=tip.generation)
    if policy.policy_id != tip.policy_id:
        raise ValueError(
            f"rehydrated policy id {policy.policy_id!r} disagrees with the "
            f"event-recorded policy id {tip.policy_id!r}"
        )
    return policy


__all__ = [
    "fold_policy_promotions",
    "rehydrate_current_policy",
    "resolve_promotion_chain",
]
