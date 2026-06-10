"""Tests for learning/protocols.py and learning/fake_evaluator.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from steel_onslaught.learning.fake_evaluator import FakeEvaluator
from steel_onslaught.learning.protocols import (
    EvaluatorProtocol,
    ModelSOCategoricalBound,
    ModelSONumericBound,
    ModelSOPairedComparison,
    ModelSOSeedOutcome,
    SOSeedWinner,
)


@pytest.mark.unit
class TestModelSONumericBound:
    def test_valid(self) -> None:
        b = ModelSONumericBound(minimum=0.0, maximum=1.0, step=0.1)
        assert b.minimum == 0.0

    def test_rejects_minimum_gt_maximum(self) -> None:
        with pytest.raises(ValueError, match="minimum must be <= maximum"):
            ModelSONumericBound(minimum=2.0, maximum=1.0, step=0.1)

    def test_rejects_zero_step(self) -> None:
        with pytest.raises(ValidationError):
            ModelSONumericBound(minimum=0.0, maximum=1.0, step=0.0)

    def test_rejects_negative_step(self) -> None:
        with pytest.raises(ValidationError):
            ModelSONumericBound(minimum=0.0, maximum=1.0, step=-0.1)

    def test_equal_min_max_valid(self) -> None:
        b = ModelSONumericBound(minimum=1.0, maximum=1.0, step=0.5)
        assert b.minimum == b.maximum


@pytest.mark.unit
class TestModelSOCategoricalBound:
    def test_valid(self) -> None:
        b = ModelSOCategoricalBound(choices=("a", "b", "c"))
        assert len(b.choices) == 3

    def test_rejects_duplicates(self) -> None:
        with pytest.raises(ValueError, match="choices must be unique"):
            ModelSOCategoricalBound(choices=("a", "b", "a"))

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValidationError):
            ModelSOCategoricalBound(choices=())


@pytest.mark.unit
class TestModelSOPairedComparison:
    def test_valid(self) -> None:
        cmp = ModelSOPairedComparison(
            n_seeds=10,
            candidate_wins=6,
            parent_wins=2,
            draws=2,
            p_value=0.1,
            candidate_win_rate=0.75,
            ci_low=0.4,
            ci_high=0.9,
            effect_size=0.25,
        )
        assert cmp.n_seeds == 10

    def test_rejects_inconsistent_counts(self) -> None:
        with pytest.raises(ValueError, match=r"wins.*draws must equal n_seeds"):
            ModelSOPairedComparison(
                n_seeds=10,
                candidate_wins=6,
                parent_wins=2,
                draws=3,  # 6+2+3 = 11 != 10
                p_value=0.1,
                candidate_win_rate=0.75,
                ci_low=0.4,
                ci_high=0.9,
                effect_size=0.25,
            )

    def test_rejects_ci_low_gt_ci_high(self) -> None:
        with pytest.raises(ValueError, match="ci_low must be <= ci_high"):
            ModelSOPairedComparison(
                n_seeds=10,
                candidate_wins=6,
                parent_wins=2,
                draws=2,
                p_value=0.1,
                candidate_win_rate=0.75,
                ci_low=0.9,
                ci_high=0.4,
                effect_size=0.25,
            )


@pytest.mark.unit
class TestFakeEvaluator:
    def _make_outcome(self, seed: int, winner: SOSeedWinner) -> ModelSOSeedOutcome:
        return ModelSOSeedOutcome(
            seed=seed,
            winner=winner,
            candidate_overloads=0,
            parent_overloads=0,
        )

    def _make_script(self) -> dict[int, ModelSOSeedOutcome]:
        return {
            1: self._make_outcome(1, SOSeedWinner.CANDIDATE),
            2: self._make_outcome(2, SOSeedWinner.PARENT),
            3: self._make_outcome(3, SOSeedWinner.DRAW),
        }

    def test_returns_outcomes_in_seed_order(self) -> None:
        ev = FakeEvaluator(self._make_script())
        results = ev.evaluate({}, {}, [3, 1, 2])
        assert [r.seed for r in results] == [3, 1, 2]

    def test_returns_correct_winners(self) -> None:
        ev = FakeEvaluator(self._make_script())
        results = ev.evaluate({}, {}, [1, 2, 3])
        assert results[0].winner == SOSeedWinner.CANDIDATE
        assert results[1].winner == SOSeedWinner.PARENT
        assert results[2].winner == SOSeedWinner.DRAW

    def test_raises_on_unscripted_seed(self) -> None:
        ev = FakeEvaluator(self._make_script())
        with pytest.raises(KeyError, match="unscripted seeds"):
            ev.evaluate({}, {}, [99])

    def test_raises_on_construction_key_mismatch(self) -> None:
        outcome = self._make_outcome(2, SOSeedWinner.CANDIDATE)
        with pytest.raises(ValueError, match=r"script key 1 != outcome\.seed 2"):
            FakeEvaluator({1: outcome})

    def test_structurally_satisfies_evaluator_protocol(self) -> None:
        """Assign FakeEvaluator to EvaluatorProtocol-annotated variable.

        mypy --strict enforces structural compatibility at type-check time.
        At runtime we verify the method exists with correct signature.
        """
        ev: EvaluatorProtocol = FakeEvaluator(self._make_script())
        results = ev.evaluate({}, {}, [1])
        assert len(results) == 1

    def test_empty_seed_list(self) -> None:
        ev = FakeEvaluator(self._make_script())
        results = ev.evaluate({}, {}, [])
        assert results == []

    def test_params_are_ignored(self) -> None:
        """FakeEvaluator ignores parameter values — outcomes are fully scripted."""
        ev = FakeEvaluator(self._make_script())
        r1 = ev.evaluate({"x": 1}, {"x": 2}, [1])
        r2 = ev.evaluate({"x": 99}, {"x": 0}, [1])
        assert r1 == r2
