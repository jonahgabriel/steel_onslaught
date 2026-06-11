"""Tests for contracts/lineage.py — canonical spec hashing, lineage models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.contracts.lineage import (
    ModelSOLineageEvidence,
    ModelSOLineageGenerator,
    ModelSOLineagePerformance,
    ModelSOLineagePromotion,
    ModelSOLineageRecord,
    SOPromotionRejection,
    SOPromotionStatus,
    meta_hash,
    spec_hash,
)


@pytest.mark.unit
class TestSpecHash:
    def test_deterministic(self) -> None:
        h1 = spec_hash("aggressive", {"a": 1, "b": 2})
        h2 = spec_hash("aggressive", {"a": 1, "b": 2})
        assert h1 == h2

    def test_key_order_independent(self) -> None:
        h1 = spec_hash("aggressive", {"a": 1, "b": 2})
        h2 = spec_hash("aggressive", {"b": 2, "a": 1})
        assert h1 == h2

    def test_64_char_hex(self) -> None:
        h = spec_hash("aggressive", {"x": 1})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_archetype_changes_hash(self) -> None:
        h1 = spec_hash("aggressive", {"a": 1})
        h2 = spec_hash("defensive", {"a": 1})
        assert h1 != h2

    def test_different_param_value_changes_hash(self) -> None:
        h1 = spec_hash("aggressive", {"a": 1})
        h2 = spec_hash("aggressive", {"a": 2})
        assert h1 != h2

    def test_different_param_key_changes_hash(self) -> None:
        h1 = spec_hash("aggressive", {"a": 1})
        h2 = spec_hash("aggressive", {"b": 1})
        assert h1 != h2

    def test_int_float_distinction(self) -> None:
        """JSON serializes 1 and 1.0 differently; hashes must differ."""
        h_int = spec_hash("aggressive", {"x": 1})
        h_float = spec_hash("aggressive", {"x": 1.0})
        assert h_int != h_float, (
            "int 1 and float 1.0 must hash differently — adapter must emit exact types"
        )


@pytest.mark.unit
class TestMetaHash:
    def test_order_insensitive(self) -> None:
        h1 = meta_hash(["hash_a", "hash_b"])
        h2 = meta_hash(["hash_b", "hash_a"])
        assert h1 == h2

    def test_duplicate_insensitive(self) -> None:
        h1 = meta_hash(["hash_a", "hash_b"])
        h2 = meta_hash(["hash_a", "hash_b", "hash_a"])
        assert h1 == h2

    def test_different_opponent_changes_hash(self) -> None:
        h1 = meta_hash(["hash_a", "hash_b"])
        h2 = meta_hash(["hash_a", "hash_c"])
        assert h1 != h2

    def test_added_opponent_changes_hash(self) -> None:
        h1 = meta_hash(["hash_a"])
        h2 = meta_hash(["hash_a", "hash_b"])
        assert h1 != h2

    def test_returns_64_char_hex(self) -> None:
        h = meta_hash(["h1"])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.unit
class TestModelSOLineageEvidence:
    def test_valid(self) -> None:
        ev = ModelSOLineageEvidence(search_seeds=(1, 2, 3), holdout_seeds=(4, 5))
        assert ev.search_seeds == (1, 2, 3)
        assert ev.holdout_seeds == (4, 5)

    def test_rejects_overlapping_seeds(self) -> None:
        with pytest.raises(ValueError, match="holdout seeds overlap"):
            ModelSOLineageEvidence(search_seeds=(1, 2, 3), holdout_seeds=(3, 4))

    def test_rejects_empty_search_seeds(self) -> None:
        with pytest.raises(ValidationError):
            ModelSOLineageEvidence(search_seeds=(), holdout_seeds=(1,))

    def test_rejects_empty_holdout_seeds(self) -> None:
        with pytest.raises(ValidationError):
            ModelSOLineageEvidence(search_seeds=(1,), holdout_seeds=())


@pytest.mark.unit
class TestModelSOLineagePromotion:
    def test_promoted_no_reasons(self) -> None:
        p = ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED)
        assert p.rejection_reasons == ()

    def test_rejected_with_reasons(self) -> None:
        p = ModelSOLineagePromotion(
            status=SOPromotionStatus.REJECTED,
            rejection_reasons=(SOPromotionRejection.NOT_SIGNIFICANT,),
        )
        assert len(p.rejection_reasons) == 1

    def test_rejects_promoted_with_reasons(self) -> None:
        with pytest.raises(ValueError, match="promoted record cannot carry rejection reasons"):
            ModelSOLineagePromotion(
                status=SOPromotionStatus.PROMOTED,
                rejection_reasons=(SOPromotionRejection.NOT_SIGNIFICANT,),
            )

    def test_rejects_rejected_without_reasons(self) -> None:
        with pytest.raises(ValueError, match="rejected record must carry at least one reason"):
            ModelSOLineagePromotion(
                status=SOPromotionStatus.REJECTED,
                rejection_reasons=(),
            )


def _make_valid_record() -> ModelSOLineageRecord:
    archetype = "aggressive"
    parameters: dict[str, int | float | str] = {"attack": 5, "defense": 3}
    sh = spec_hash(archetype, parameters)
    parent_params: dict[str, int | float | str] = {"attack": 4, "defense": 3}
    ph = spec_hash(archetype, parent_params)
    mh = meta_hash(["opp_hash_a", "opp_hash_b"])
    return ModelSOLineageRecord(
        archetype=archetype,
        parameters=parameters,
        spec_hash=sh,
        parent_hash=ph,
        meta_hash=mh,
        evidence=ModelSOLineageEvidence(
            search_seeds=(1, 2, 3, 4, 5),
            holdout_seeds=(101, 102, 103),
        ),
        performance=ModelSOLineagePerformance(
            candidate_win_rate=0.75,
            win_rate_delta=0.25,
            overload_rate_delta=0.0,
            draw_rate=0.2,
            p_value=0.03,
            decisive_n=10,
        ),
        generator=ModelSOLineageGenerator(
            generator_id="search.hill_climb",
            selection_reason="best neighbor",
        ),
        promotion=ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED),
    )


@pytest.mark.unit
class TestModelSOLineageRecord:
    def test_valid_record_constructs(self) -> None:
        rec = _make_valid_record()
        assert rec.schema_version == "0.1.0"
        assert rec.kind == "steel_onslaught.lineage_record"

    def test_rejects_wrong_spec_hash(self) -> None:
        archetype = "aggressive"
        parameters: dict[str, int | float | str] = {"attack": 5, "defense": 3}
        wrong_hash = "a" * 64
        parent_params: dict[str, int | float | str] = {"attack": 4, "defense": 3}
        ph = spec_hash(archetype, parent_params)
        mh = meta_hash(["opp"])
        with pytest.raises(ValueError, match="spec_hash does not match"):
            ModelSOLineageRecord(
                archetype=archetype,
                parameters=parameters,
                spec_hash=wrong_hash,
                parent_hash=ph,
                meta_hash=mh,
                evidence=ModelSOLineageEvidence(
                    search_seeds=(1,),
                    holdout_seeds=(2,),
                ),
                performance=ModelSOLineagePerformance(
                    candidate_win_rate=0.5,
                    win_rate_delta=0.0,
                    overload_rate_delta=0.0,
                    draw_rate=0.0,
                    p_value=1.0,
                    decisive_n=0,
                ),
                generator=ModelSOLineageGenerator(
                    generator_id="search.grid",
                    selection_reason="first",
                ),
                promotion=ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED),
            )

    def test_round_trip(self) -> None:
        rec = _make_valid_record()
        dumped = rec.model_dump()
        restored = ModelSOLineageRecord.model_validate(dumped)
        assert restored == rec
