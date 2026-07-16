"""Tests for learning/lineage_store.py — YAML persistence for lineage records.

Step 1: failing tests. Expected failure: ModuleNotFoundError on
steel_onslaught.learning.lineage_store.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from pathlib import Path

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
from steel_onslaught.learning.lineage_store import (
    ModelSOPersistedLineageRecord,
    load_lineage_records,
    record_digest,
    write_lineage_record,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    *,
    archetype: str = "aggressive",
    parameters: dict[str, int | float | str] | None = None,
    status: SOPromotionStatus = SOPromotionStatus.PROMOTED,
    rejection_reasons: tuple[SOPromotionRejection, ...] = (),
) -> ModelSOLineageRecord:
    if parameters is None:
        parameters = {"attack": 5, "defense": 3}
    sh = spec_hash(archetype, parameters)
    parent_params: dict[str, int | float | str] = {"attack": 4, "defense": 3}
    ph = spec_hash(archetype, parent_params)
    mh = meta_hash(["opp_hash_a"])
    if status == SOPromotionStatus.PROMOTED and rejection_reasons:
        raise ValueError("promoted cannot have rejection reasons")
    if status == SOPromotionStatus.REJECTED and not rejection_reasons:
        rejection_reasons = (SOPromotionRejection.NOT_SIGNIFICANT,)
    return ModelSOLineageRecord(
        archetype=archetype,
        parameters=parameters,
        spec_hash=sh,
        parent_hash=ph,
        meta_hash=mh,
        evidence=ModelSOLineageEvidence(
            search_seeds=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
            holdout_seeds=(101, 102, 103, 104, 105),
        ),
        performance=ModelSOLineagePerformance(
            candidate_win_rate=0.75,
            win_rate_delta=0.25,
            overload_rate_delta=0.0,
            draw_rate=0.2,
            p_value=0.03,
            decisive_n=12,
        ),
        generator=ModelSOLineageGenerator(
            generator_id="search.hill_climb",
            selection_reason="best neighbor",
        ),
        promotion=ModelSOLineagePromotion(
            status=status,
            rejection_reasons=rejection_reasons,
        ),
    )


def _aware_now() -> datetime:
    return datetime(2026, 6, 12, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ModelSOPersistedLineageRecord
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelSOPersistedLineageRecord:
    def test_valid_construction(self) -> None:
        rec = _make_record()
        ts = _aware_now()
        envelope = ModelSOPersistedLineageRecord(record=rec, recorded_at=ts)
        assert envelope.record == rec
        assert envelope.recorded_at == ts

    def test_frozen(self) -> None:
        """Frozen model: direct attribute assignment must be blocked."""
        rec = _make_record()
        envelope = ModelSOPersistedLineageRecord(record=rec, recorded_at=_aware_now())
        with pytest.raises((ValidationError, TypeError)):
            envelope.recorded_at = datetime(2026, 1, 1, tzinfo=UTC)

    def test_extra_fields_forbidden(self) -> None:
        rec = _make_record()
        with pytest.raises(ValidationError):
            ModelSOPersistedLineageRecord(  # type: ignore[call-arg]
                record=rec, recorded_at=_aware_now(), extra_field="oops"
            )

    def test_naive_recorded_at_raises(self) -> None:
        """A timezone-unaware datetime must be rejected."""
        rec = _make_record()
        naive_dt = datetime(2026, 6, 12, 10, 0, 0)  # no tzinfo
        with pytest.raises(ValidationError):
            ModelSOPersistedLineageRecord(record=rec, recorded_at=naive_dt)

    def test_recorded_at_has_no_default(self) -> None:
        """recorded_at must be a required field — no default of any kind."""

        from pydantic.fields import FieldInfo

        field_info: FieldInfo = ModelSOPersistedLineageRecord.model_fields["recorded_at"]
        # PydanticUndefined means no default was set
        from pydantic_core import PydanticUndefinedType

        assert isinstance(field_info.default, PydanticUndefinedType), (
            "recorded_at must have no default; wall-clock must be injected by the caller"
        )

    def test_record_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ModelSOPersistedLineageRecord(recorded_at=_aware_now())  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# record_digest
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordDigest:
    def test_returns_64_char_hex(self) -> None:
        rec = _make_record()
        digest = record_digest(rec)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_invariant_under_different_recorded_at(self) -> None:
        """Digest must not change when recorded_at changes — it covers inner record only."""
        rec = _make_record()
        d1 = record_digest(rec)
        # digest is pure function of the record, no recorded_at involvement
        d2 = record_digest(rec)
        assert d1 == d2

    def test_changes_when_performance_field_changes(self) -> None:
        """Flipping one performance field must produce a new digest."""
        params: dict[str, int | float | str] = {"attack": 5, "defense": 3}
        archetype = "aggressive"
        sh = spec_hash(archetype, params)
        parent_params: dict[str, int | float | str] = {"attack": 4, "defense": 3}
        ph = spec_hash(archetype, parent_params)
        mh = meta_hash(["opp_hash_a"])

        def _make(p_value: float) -> ModelSOLineageRecord:
            return ModelSOLineageRecord(
                archetype=archetype,
                parameters=params,
                spec_hash=sh,
                parent_hash=ph,
                meta_hash=mh,
                evidence=ModelSOLineageEvidence(
                    search_seeds=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
                    holdout_seeds=(101, 102, 103, 104, 105),
                ),
                performance=ModelSOLineagePerformance(
                    candidate_win_rate=0.75,
                    win_rate_delta=0.25,
                    overload_rate_delta=0.0,
                    draw_rate=0.2,
                    p_value=p_value,
                    decisive_n=12,
                ),
                generator=ModelSOLineageGenerator(
                    generator_id="search.hill_climb",
                    selection_reason="best neighbor",
                ),
                promotion=ModelSOLineagePromotion(status=SOPromotionStatus.PROMOTED),
            )

        rec_a = _make(0.03)
        rec_b = _make(0.04)
        assert record_digest(rec_a) != record_digest(rec_b)

    def test_stable_across_two_calls(self) -> None:
        rec = _make_record()
        assert record_digest(rec) == record_digest(rec)

    def test_digest_uses_inner_record_only(self) -> None:
        """Two envelopes with the same inner record but different recorded_at
        must produce the same digest (verified via record_digest taking only a record)."""
        rec = _make_record()
        digest = record_digest(rec)
        # The digest function takes ModelSOLineageRecord — no recorded_at involved
        assert isinstance(digest, str)
        assert len(digest) == 64


# ---------------------------------------------------------------------------
# write_lineage_record
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWriteLineageRecord:
    def test_creates_yaml_file(self, tmp_path: Path) -> None:
        rec = _make_record()
        path = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        assert path.exists()
        assert path.suffix == ".yaml"

    def test_path_scheme(self, tmp_path: Path) -> None:
        """Path must be root/<archetype>/<spec_hash>/<record_digest>.yaml."""
        rec = _make_record()
        ts = _aware_now()
        path = write_lineage_record(rec, root=tmp_path, recorded_at=ts)
        expected_dir = tmp_path / rec.archetype / rec.spec_hash
        expected_name = record_digest(rec) + ".yaml"
        assert path == expected_dir / expected_name

    def test_spec_hash_in_path_matches_record(self, tmp_path: Path) -> None:
        rec = _make_record()
        path = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        # path.parent.name is the spec_hash segment
        assert path.parent.name == rec.spec_hash

    def test_round_trip_promoted(self, tmp_path: Path) -> None:
        rec = _make_record(status=SOPromotionStatus.PROMOTED)
        ts = _aware_now()
        write_lineage_record(rec, root=tmp_path, recorded_at=ts)
        records = load_lineage_records(tmp_path)
        assert len(records) == 1
        assert records[0].record == rec
        assert records[0].recorded_at == ts

    def test_round_trip_rejected(self, tmp_path: Path) -> None:
        rec = _make_record(
            status=SOPromotionStatus.REJECTED,
            rejection_reasons=(SOPromotionRejection.NOT_SIGNIFICANT,),
        )
        ts = _aware_now()
        write_lineage_record(rec, root=tmp_path, recorded_at=ts)
        records = load_lineage_records(tmp_path)
        assert len(records) == 1
        assert records[0].record.promotion.status == SOPromotionStatus.REJECTED

    def test_first_write_wins_same_path(self, tmp_path: Path) -> None:
        """Writing the same inner record twice returns the same path; the
        first file's bytes are not overwritten."""
        rec = _make_record()
        ts1 = _aware_now()
        ts2 = datetime(2026, 6, 13, 10, 0, 0, tzinfo=UTC)

        path1 = write_lineage_record(rec, root=tmp_path, recorded_at=ts1)
        first_bytes = path1.read_bytes()

        path2 = write_lineage_record(rec, root=tmp_path, recorded_at=ts2)

        assert path1 == path2
        assert path1.read_bytes() == first_bytes  # unchanged

    def test_first_write_wins_different_recorded_at_same_inner(self, tmp_path: Path) -> None:
        """Same inner record but different clock: path is the same (digest is
        the same), original content survives."""
        rec = _make_record()
        ts1 = _aware_now()
        ts2 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)

        write_lineage_record(rec, root=tmp_path, recorded_at=ts1)
        write_lineage_record(rec, root=tmp_path, recorded_at=ts2)

        records = load_lineage_records(tmp_path)
        assert len(records) == 1
        assert records[0].recorded_at == ts1  # first wins

    def test_existing_target_with_tampered_record_fails_closed(self, tmp_path: Path) -> None:
        """First-write-wins must validate existing bytes before returning."""
        import yaml  # type: ignore[import-untyped]

        rec = _make_record()
        path = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw["record"]["performance"]["p_value"] = 0.04
        path.write_text(yaml.safe_dump(raw, sort_keys=True), encoding="utf-8")

        with pytest.raises(ValueError, match="record digest filename mismatch"):
            write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())

    def test_different_inner_records_produce_different_paths(self, tmp_path: Path) -> None:
        rec_a = _make_record(parameters={"attack": 5, "defense": 3})
        rec_b = _make_record(parameters={"attack": 6, "defense": 3})
        ts = _aware_now()
        path_a = write_lineage_record(rec_a, root=tmp_path, recorded_at=ts)
        path_b = write_lineage_record(rec_b, root=tmp_path, recorded_at=ts)
        assert path_a != path_b

    def test_yaml_loads_via_safe_load(self, tmp_path: Path) -> None:
        """Written file must be parseable by yaml.safe_load — no custom tags."""
        import yaml

        rec = _make_record()
        path = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        content = path.read_text()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_returns_path_object(self, tmp_path: Path) -> None:
        rec = _make_record()
        result = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# load_lineage_records
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadLineageRecords:
    def test_empty_root_returns_empty_list(self, tmp_path: Path) -> None:
        results = load_lineage_records(tmp_path)
        assert results == []

    def test_loads_multiple_records(self, tmp_path: Path) -> None:
        ts = _aware_now()
        rec_a = _make_record(parameters={"attack": 5, "defense": 3})
        rec_b = _make_record(parameters={"attack": 6, "defense": 3})
        rec_c = _make_record(
            archetype="defensive",
            parameters={"armor": 10, "speed": 2},
        )
        for r in (rec_a, rec_b, rec_c):
            write_lineage_record(r, root=tmp_path, recorded_at=ts)
        records = load_lineage_records(tmp_path)
        assert len(records) == 3

    def test_ordering_deterministic(self, tmp_path: Path) -> None:
        """Two calls to load_lineage_records return records in the same order."""
        ts = _aware_now()
        recs = [_make_record(parameters={"attack": i, "defense": 3}) for i in range(5, 10)]
        # Write in reverse order to ensure ordering is not write-order-dependent
        for r in reversed(recs):
            write_lineage_record(r, root=tmp_path, recorded_at=ts)

        load1 = load_lineage_records(tmp_path)
        load2 = load_lineage_records(tmp_path)
        assert [e.record for e in load1] == [e.record for e in load2]

    def test_ordering_independent_of_write_order(self, tmp_path: Path) -> None:
        """Order of writes must not affect the load order (sorted by archetype/spec_hash/digest)."""
        ts = _aware_now()
        recs = [_make_record(parameters={"attack": i, "defense": 3}) for i in (7, 5, 9, 6, 8)]
        tmp_a = tmp_path / "a"
        tmp_b = tmp_path / "b"
        tmp_a.mkdir()
        tmp_b.mkdir()

        for r in recs:
            write_lineage_record(r, root=tmp_a, recorded_at=ts)
        for r in reversed(recs):
            write_lineage_record(r, root=tmp_b, recorded_at=ts)

        order_a = [e.record for e in load_lineage_records(tmp_a)]
        order_b = [e.record for e in load_lineage_records(tmp_b)]
        assert order_a == order_b

    def test_sort_key_is_archetype_spec_hash_digest(self, tmp_path: Path) -> None:
        """Verify sort key: sort by (archetype, spec_hash, digest)."""
        ts = _aware_now()
        recs = [
            _make_record(archetype="aggressive", parameters={"attack": 5, "defense": 3}),
            _make_record(archetype="aggressive", parameters={"attack": 6, "defense": 3}),
            _make_record(archetype="defensive", parameters={"armor": 10, "speed": 2}),
        ]
        for r in reversed(recs):
            write_lineage_record(r, root=tmp_path, recorded_at=ts)

        loaded = load_lineage_records(tmp_path)
        keys = [(e.record.archetype, e.record.spec_hash, record_digest(e.record)) for e in loaded]
        assert keys == sorted(keys)

    def test_unparseable_file_raises(self, tmp_path: Path) -> None:
        """A file that cannot be parsed must raise (no silent skip)."""
        bad_dir = tmp_path / "aggressive" / ("a" * 64)
        bad_dir.mkdir(parents=True)
        bad_file = bad_dir / ("b" * 64 + ".yaml")
        # Valid YAML structure but fails model validation
        bad_file.write_text("not_a_record_key: some_garbage_value\n")
        with pytest.raises((ValueError, ValidationError)):
            load_lineage_records(tmp_path)

    def test_tampered_record_digest_filename_raises(self, tmp_path: Path) -> None:
        rec = _make_record()
        original = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        tampered = original.with_name(f"{'0' * 64}.yaml")
        original.rename(tampered)

        with pytest.raises(ValueError, match="record digest filename mismatch"):
            load_lineage_records(tmp_path)

    def test_archetype_directory_mismatch_raises(self, tmp_path: Path) -> None:
        rec = _make_record()
        original = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        tampered = tmp_path / "defensive" / rec.spec_hash / original.name
        tampered.parent.mkdir(parents=True)
        original.rename(tampered)

        with pytest.raises(ValueError, match="archetype directory mismatch"):
            load_lineage_records(tmp_path)

    def test_spec_hash_directory_mismatch_raises(self, tmp_path: Path) -> None:
        rec = _make_record()
        original = write_lineage_record(rec, root=tmp_path, recorded_at=_aware_now())
        tampered = tmp_path / rec.archetype / ("0" * 64) / original.name
        tampered.parent.mkdir(parents=True)
        original.rename(tampered)

        with pytest.raises(ValueError, match="spec_hash directory mismatch"):
            load_lineage_records(tmp_path)

    def test_frozen_model_equality(self, tmp_path: Path) -> None:
        """Frozen-model equality: loaded record equals the original envelope."""
        rec = _make_record()
        ts = _aware_now()
        write_lineage_record(rec, root=tmp_path, recorded_at=ts)
        loaded = load_lineage_records(tmp_path)
        assert len(loaded) == 1
        expected = ModelSOPersistedLineageRecord(record=rec, recorded_at=ts)
        assert loaded[0] == expected


# ---------------------------------------------------------------------------
# Source-scan: no datetime.now / datetime.utcnow / default for recorded_at
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSourceScan:
    def test_no_datetime_now_in_module(self) -> None:
        """lineage_store.py must not contain datetime.now or datetime.utcnow.
        Wall-clock is injected by the caller (Architectural Decision #4)."""
        import steel_onslaught.learning.lineage_store as mod

        source = inspect.getsource(mod)
        assert "datetime.now" not in source, (
            "lineage_store.py must not call datetime.now — clock is injected by caller"
        )
        assert "datetime.utcnow" not in source, (
            "lineage_store.py must not call datetime.utcnow — clock is injected by caller"
        )

    def test_no_default_for_recorded_at_in_source(self) -> None:
        """No default= for recorded_at field. Confirmed via model_fields too."""
        import steel_onslaught.learning.lineage_store as mod

        source = inspect.getsource(mod)
        # Should not see a default assignment for recorded_at in the source
        # (this is belt-and-suspenders alongside the model_fields check above)
        assert re.search(r"recorded_at\s*=\s*Field\(.*default\s*=", source) is None, (
            "recorded_at must not have a default in Field()"
        )
